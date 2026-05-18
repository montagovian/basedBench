"""Multi-judge pipeline: each prediction is scored by every configured judge.

Running multiple judges per prediction lets us measure (and defend against)
judge-family bias. Concurrency is capped by a single semaphore across all
judge×prediction tasks; DB writes happen sequentially on the main coroutine.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, field

from rich.console import Console

from basedbench.config import Config
from basedbench.db import queries
from basedbench.db.connection import Database
from basedbench.errors import LlmJsonParseError, OpenAIError, is_fatal_llm_error
from basedbench.llm.judge import Judge, JudgeResult, make_judge
from basedbench.llm.prompts import JUDGE_SYSTEM_PROMPT, JUDGE_USER_TEMPLATE
from basedbench.llm.record import LlmCallRecord
from basedbench.pipeline._progress import make_progress
from basedbench.schemas import JudgeVerdict

log = logging.getLogger(__name__)

MAX_INFLIGHT = 10


@dataclass
class PerJudgeStats:
    correct: int = 0
    incorrect: int = 0
    errors: int = 0

    @property
    def total(self) -> int:
        return self.correct + self.incorrect

    @property
    def accuracy(self) -> float:
        return 100.0 * self.correct / self.total if self.total else 0.0


@dataclass
class JudgeStats:
    """Aggregate stats. `per_judge` keyed by judge model_id."""

    per_judge: dict[str, PerJudgeStats] = field(default_factory=dict)

    def add(self, judge_model: str) -> PerJudgeStats:
        return self.per_judge.setdefault(judge_model, PerJudgeStats())

    @property
    def correct(self) -> int:
        return sum(s.correct for s in self.per_judge.values())

    @property
    def incorrect(self) -> int:
        return sum(s.incorrect for s in self.per_judge.values())

    @property
    def errors(self) -> int:
        return sum(s.errors for s in self.per_judge.values())


@dataclass
class _Task:
    prediction_id: int
    target_model: str
    judge: Judge
    prediction: str
    ground_truth: str
    post_id: str


def _resolve_judge_models(config: Config, judge_models: list[str] | None) -> list[str]:
    models = judge_models if judge_models else config.judge_models
    if not models:
        raise ValueError("No judge models configured.")
    return models


async def run(
    db: Database,
    config: Config,
    model: str | None = None,
    judge_models: list[str] | None = None,
    rejudge_prompt: str | None = None,
    console: Console | None = None,
) -> JudgeStats:
    console = console or Console()
    judge_model_ids = _resolve_judge_models(config, judge_models)
    judges: dict[str, Judge] = {m: make_judge(m, config) for m in judge_model_ids}

    for j in judges.values():
        queries.register_prompt(
            db, j.prompt_id, "judge", JUDGE_SYSTEM_PROMPT, JUDGE_USER_TEMPLATE, "1.0"
        )

    # Build the work list: cartesian product of (predictions-needing-this-judge × judge).
    tasks: list[_Task] = []
    if rejudge_prompt:
        console.print(f"Re-judging predictions that used prompt {rejudge_prompt}...")
        preds = queries.predictions_needing_rejudgment(db, rejudge_prompt)
        for p in preds:
            for jm, judge in judges.items():
                tasks.append(
                    _Task(
                        prediction_id=p.prediction_id,
                        target_model=p.model_id,
                        judge=judge,
                        prediction=p.prediction,
                        ground_truth=p.ground_truth,
                        post_id=p.post_id,
                    )
                )
    else:
        for jm, judge in judges.items():
            preds = queries.predictions_needing_judgment(
                db, model_id=model, judge_model=jm
            )
            for p in preds:
                tasks.append(
                    _Task(
                        prediction_id=p.prediction_id,
                        target_model=p.model_id,
                        judge=judge,
                        prediction=p.prediction,
                        ground_truth=p.ground_truth,
                        post_id=p.post_id,
                    )
                )

    console.print(
        f"{len(tasks)} judging tasks across {len(judges)} judges: "
        f"{', '.join(judges)}"
    )
    if not tasks:
        console.print("Nothing to do.")
        return JudgeStats()

    sem = asyncio.Semaphore(MAX_INFLIGHT)
    queue: asyncio.Queue[
        tuple[_Task, JudgeResult | Exception, LlmCallRecord | None]
    ] = asyncio.Queue()

    async def worker(t: _Task) -> None:
        async with sem:
            try:
                result, record = await t.judge.judge(
                    t.prediction, t.ground_truth, t.post_id
                )
                await queue.put((t, result, record))
            except (OpenAIError, LlmJsonParseError) as e:
                await queue.put((t, e, None))
            except Exception as e:  # noqa: BLE001
                # Anthropic errors get wrapped as AnthropicError (raised as fatal)
                # or pass through as transient; treat anything we didn't expect
                # as an error so one bad call doesn't kill the whole run.
                await queue.put((t, e, None))

    bg_tasks = [asyncio.create_task(worker(t)) for t in tasks]
    stats = JudgeStats()
    fatal_judges: set[str] = set()

    with make_progress() as prog:
        prog_task = prog.add_task(
            f"judging ({len(judges)} judges × {len(tasks) // len(judges)} preds)",
            total=len(tasks),
        )
        for _ in range(len(tasks)):
            t, outcome, record = await queue.get()
            per = stats.add(t.judge.model_id)
            if record is not None:
                queries.insert_llm_call(db, record)

            if isinstance(outcome, Exception):
                if isinstance(outcome, OpenAIError) and is_fatal_llm_error(outcome):
                    if t.judge.model_id not in fatal_judges:
                        console.print(
                            f"\n[bold red]Fatal error from judge "
                            f"{t.judge.model_id}:[/bold red] {outcome}"
                        )
                        fatal_judges.add(t.judge.model_id)
                    per.errors += 1
                    prog.update(prog_task, advance=1)
                    continue
                log.warning(
                    "Judge %s failed on prediction %s: %s",
                    t.judge.model_id,
                    t.prediction_id,
                    outcome,
                )
                per.errors += 1
            else:
                if outcome.verdict == JudgeVerdict.CORRECT:
                    per.correct += 1
                else:
                    per.incorrect += 1
                queries.insert_judgment(
                    db,
                    t.prediction_id,
                    outcome.verdict.value,
                    outcome.reasoning,
                    t.judge.model_id,
                    t.judge.prompt_id,
                )
            prog.update(prog_task, advance=1)

    await asyncio.gather(*bg_tasks, return_exceptions=True)

    # ─── Summary + per-target agreement (uses freshly-written rows) ───
    console.print("\n[bold green]Judge complete[/bold green]")
    for jm, per in stats.per_judge.items():
        console.print(
            f"  {jm:<30} {per.total} judged "
            f"({per.correct} correct, {per.incorrect} incorrect, "
            f"{per.errors} errors, {per.accuracy:.1f}%)"
        )

    agreement_by_target = _compute_run_agreement(tasks, stats, db)
    if agreement_by_target:
        console.print("\n[bold]Judge agreement (this run's predictions):[/bold]")
        for target, (agree, total) in sorted(agreement_by_target.items()):
            if total:
                console.print(
                    f"  {target:<30} {agree}/{total} ({100 * agree / total:.1f}%)"
                )

    return stats


def _compute_run_agreement(
    tasks: list[_Task], stats: JudgeStats, db: Database
) -> dict[str, tuple[int, int]]:
    """For each target model, count predictions where all judges agreed in this run.

    Looks up the freshly-inserted verdicts via `get_judge_agreement` filtered to
    the prediction IDs we touched.
    """
    touched_preds: set[int] = {t.prediction_id for t in tasks}
    target_by_pred: dict[int, str] = {t.prediction_id: t.target_model for t in tasks}
    if not touched_preds:
        return {}
    placeholders = ",".join("?" * len(touched_preds))
    rows = db.conn.execute(
        f"""WITH latest AS (
                SELECT j.prediction_id, j.judge_model, j.verdict
                FROM judgments j
                WHERE j.prediction_id IN ({placeholders})
                  AND j.id = (
                    SELECT MAX(j2.id) FROM judgments j2
                    WHERE j2.prediction_id = j.prediction_id
                      AND j2.judge_model = j.judge_model
                  )
            )
            SELECT prediction_id,
                   COUNT(DISTINCT judge_model) as n_judges,
                   COUNT(DISTINCT verdict) as n_verdicts
            FROM latest
            GROUP BY prediction_id""",
        tuple(touched_preds),
    ).fetchall()

    out: dict[str, tuple[int, int]] = defaultdict(lambda: (0, 0))
    for prediction_id, n_judges, n_verdicts in rows:
        if n_judges < 2:
            continue
        target = target_by_pred.get(prediction_id, "(unknown)")
        agree, total = out[target]
        out[target] = (
            agree + (1 if n_verdicts == 1 else 0),
            total + 1,
        )
    return dict(out)
