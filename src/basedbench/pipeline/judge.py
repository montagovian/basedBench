"""Judge pipeline: concurrent LLM judging (semaphore=10), sequential DB inserts."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from rich.console import Console

from basedbench.config import Config
from basedbench.db import queries
from basedbench.db.connection import Database
from basedbench.errors import LlmJsonParseError, OpenAIError, is_fatal_llm_error
from basedbench.llm.judge import JudgeResult, LlmJudge
from basedbench.llm.prompts import JUDGE_SYSTEM_PROMPT, JUDGE_USER_TEMPLATE
from basedbench.llm.record import LlmCallRecord
from basedbench.pipeline._progress import make_progress
from basedbench.schemas import JudgeVerdict

log = logging.getLogger(__name__)

MAX_INFLIGHT = 10


@dataclass
class JudgeStats:
    correct: int = 0
    incorrect: int = 0
    errors: int = 0

    @property
    def accuracy(self) -> float:
        total = self.correct + self.incorrect
        return 100.0 * self.correct / total if total else 0.0


async def run(
    db: Database,
    config: Config,
    model: str | None = None,
    rejudge_prompt: str | None = None,
    console: Console | None = None,
) -> JudgeStats:
    console = console or Console()
    judge = LlmJudge(config.openai_api_key, config.judge_model)
    queries.register_prompt(
        db, judge.prompt_id, "judge", JUDGE_SYSTEM_PROMPT, JUDGE_USER_TEMPLATE, "1.0"
    )

    if rejudge_prompt:
        console.print(f"Re-judging predictions that used prompt {rejudge_prompt}...")
        preds = queries.predictions_needing_rejudgment(db, rejudge_prompt)
    else:
        preds = queries.predictions_needing_judgment(db, model)

    console.print(f"{len(preds)} predictions need judging")
    if not preds:
        console.print("Nothing to do.")
        return JudgeStats()

    sem = asyncio.Semaphore(MAX_INFLIGHT)
    queue: asyncio.Queue[
        tuple[int, JudgeResult | Exception, LlmCallRecord | None]
    ] = asyncio.Queue()

    async def worker(p: queries.PredictionForJudging) -> None:
        async with sem:
            try:
                result, record = await judge.judge(p.prediction, p.ground_truth, p.post_id)
                await queue.put((p.prediction_id, result, record))
            except (OpenAIError, LlmJsonParseError) as e:
                await queue.put((p.prediction_id, e, None))

    tasks = [asyncio.create_task(worker(p)) for p in preds]
    stats = JudgeStats()

    fatal_seen = False
    with make_progress() as prog:
        task = prog.add_task(f"judging ({config.judge_model})", total=len(preds))
        for _ in range(len(preds)):
            pid, outcome, record = await queue.get()
            if record is not None:
                queries.insert_llm_call(db, record)
            if isinstance(outcome, Exception):
                if isinstance(outcome, OpenAIError) and is_fatal_llm_error(outcome):
                    if not fatal_seen:
                        console.print(
                            f"\n[bold red]Fatal OpenAI error during judging:[/bold red] {outcome}"
                        )
                        console.print(
                            "[red]Remaining judgments aborted. Fix the API key / billing and rerun.[/red]"
                        )
                        fatal_seen = True
                    stats.errors += 1
                    prog.update(task, advance=1)
                    continue
                log.warning("Judge error for prediction %s: %s", pid, outcome)
                stats.errors += 1
            else:
                if outcome.verdict == JudgeVerdict.CORRECT:
                    stats.correct += 1
                else:
                    stats.incorrect += 1
                queries.insert_judgment(
                    db,
                    pid,
                    outcome.verdict.value,
                    outcome.reasoning,
                    config.judge_model,
                    judge.prompt_id,
                )
            prog.update(task, advance=1)

    await asyncio.gather(*tasks, return_exceptions=True)

    console.print(
        f"\n[bold green]Judge complete[/bold green]\n"
        f"  Judged: {stats.correct + stats.incorrect} "
        f"({stats.correct} correct, {stats.incorrect} incorrect, "
        f"{stats.errors} errors)\n"
        f"  Accuracy: {stats.accuracy:.1f}%"
    )
    return stats
