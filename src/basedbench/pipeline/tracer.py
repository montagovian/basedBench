"""Bounded end-to-end tracer bullet pipeline.

This command intentionally scopes every downstream phase to the batch it just
created. It is for smoke-testing the full shape of the system, not for adding
leaderboard-eligible evaluated rows.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from rich.console import Console

from basedbench.config import Config
from basedbench.db import queries
from basedbench.db.connection import Database
from basedbench.errors import (
    AnthropicError,
    ImageDownloadError,
    ImageNotFoundError,
    ImageValidationError,
    LlmJsonParseError,
    OpenAIError,
    is_fatal_llm_error,
)
from basedbench.llm.consensus import ConsensusDetector
from basedbench.llm.judge import Judge, make_judge
from basedbench.llm.prompts import (
    CONSENSUS_SYSTEM_PROMPT,
    CONSENSUS_USER_TEMPLATE,
    EXPLAIN_MEME_PROMPT,
    JUDGE_SYSTEM_PROMPT,
    JUDGE_USER_TEMPLATE,
    SAFETY_GATE_SYSTEM_PROMPT,
    SAFETY_GATE_USER_TEMPLATE,
)
from basedbench.llm.record import LlmCallRecord
from basedbench.llm.safety_gate import SafetyGate
from basedbench.pipeline._progress import make_progress
from basedbench.pipeline import ingest as ingest_pipe
from basedbench.pipeline.predict import USER_PROMPT, _build_predictor, _to_curated
from basedbench.reddit.client import RedditClient
from basedbench.reddit.images import ImageDownloader
from basedbench.schemas import ModelPrediction, RawPost, dataset_version

log = logging.getLogger(__name__)

DEFAULT_TIME_FILTERS = ("day", "week", "month")
MAX_INFLIGHT = 10


@dataclass
class TracerItem:
    post_id: str
    title: str
    status: str = "inserted"
    predicted: bool = False
    judged: int = 0


@dataclass
class TracerStats:
    batch_id: str
    inserted: int = 0
    comments: int = 0
    images_downloaded: int = 0
    safety_excluded: int = 0
    missing_images_excluded: int = 0
    no_consensus: int = 0
    consensus_found: int = 0
    predictions: int = 0
    prediction_errors: int = 0
    judgments: int = 0
    judgment_errors: int = 0
    items: list[TracerItem] = field(default_factory=list)


@dataclass
class _Outcome:
    item: Any
    result: Any = None
    record: LlmCallRecord | None = None
    error: Exception | None = None


@dataclass
class _JudgeTask:
    post_id: str
    prediction_id: int
    prediction: str
    ground_truth: str
    judge: Judge


def _new_batch_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"tracer-{stamp}"


async def _fan_out(
    items: list[Any],
    worker_fn: Callable[[Any], Awaitable[tuple[Any, LlmCallRecord | None]]],
    catchable: tuple[type[Exception], ...],
    max_inflight: int = MAX_INFLIGHT,
) -> tuple[list[asyncio.Task[None]], asyncio.Queue[_Outcome]]:
    """Run network-bound calls concurrently while returning writes to caller."""
    sem = asyncio.Semaphore(max_inflight)
    queue: asyncio.Queue[_Outcome] = asyncio.Queue()

    async def worker(item: Any) -> None:
        async with sem:
            try:
                result, record = await worker_fn(item)
                await queue.put(_Outcome(item=item, result=result, record=record))
            except catchable as e:
                await queue.put(_Outcome(item=item, error=e))

    tasks = [asyncio.create_task(worker(item)) for item in items]
    return tasks, queue


def _set_status(
    db: Database,
    batch_id: str,
    item: TracerItem,
    status: str,
) -> None:
    item.status = status
    queries.update_batch_meme_status(db, batch_id, item.post_id, status)


async def _fetch_new_posts(
    db: Database,
    config: Config,
    batch_id: str,
    fetch: int,
    subreddits: list[str],
    time_filters: list[str],
    stats: TracerStats,
    console: Console,
) -> list[RawPost]:
    """Fetch and persist up to `fetch` new posts into the tracer batch."""
    selected: list[RawPost] = []
    seen: set[str] = set()
    position = 0

    console.print(
        f"[bold]Tracer fetch:[/bold] collecting up to {fetch} new posts "
        f"from {', '.join('r/' + s for s in subreddits)}"
    )
    async with (
        RedditClient(config) as reddit,
        ImageDownloader(config.images_dir) as imgs,
    ):
        await reddit.authenticate()
        for time_filter in time_filters:
            for sub in subreddits:
                if len(selected) >= fetch:
                    return selected
                posts = await reddit.fetch_posts(sub, fetch, time_filter=time_filter)
                console.print(f"  r/{sub} ({time_filter}): fetched {len(posts)} posts")
                for post in posts:
                    if len(selected) >= fetch:
                        return selected
                    if post.post_id in seen:
                        continue
                    seen.add(post.post_id)
                    if not queries.insert_meme(db, post):
                        continue
                    stats.inserted += 1
                    for comment in post.comments:
                        if queries.insert_comment(db, post.post_id, comment):
                            stats.comments += 1
                    if post.image_url:
                        try:
                            path = await imgs.download(post.image_url, post.post_id)
                            queries.update_meme_image_path(db, post.post_id, path)
                            stats.images_downloaded += 1
                        except (ImageDownloadError, ImageValidationError) as e:
                            log.warning(
                                "Image download failed for %s: %s", post.post_id, e
                            )
                    position += 1
                    queries.add_batch_meme(db, batch_id, post.post_id, position)
                    stats.items.append(
                        TracerItem(post_id=post.post_id, title=post.title)
                    )
                    selected.append(post)
    return selected


async def _run_gates_and_consensus(
    db: Database,
    config: Config,
    batch_id: str,
    posts: list[RawPost],
    target_consensus: int,
    stats: TracerStats,
    console: Console,
) -> list[str]:
    safety = SafetyGate(config)
    detector = ConsensusDetector(config)
    queries.register_prompt(
        db,
        safety.prompt_id,
        "safety_gate",
        SAFETY_GATE_SYSTEM_PROMPT,
        SAFETY_GATE_USER_TEMPLATE,
        "1.0",
    )
    queries.register_prompt(
        db,
        detector.prompt_id,
        "consensus",
        CONSENSUS_SYSTEM_PROMPT,
        CONSENSUS_USER_TEMPLATE,
        "1.0",
    )

    item_by_id = {item.post_id: item for item in stats.items}
    console.print(
        f"\n[bold]Tracer curation:[/bold] stopping after {target_consensus} consensus rows"
    )

    safety_kept: list[RawPost] = []
    tasks, queue = await _fan_out(
        posts,
        safety.check,
        catchable=(OpenAIError, LlmJsonParseError),
    )
    aborted = False
    with make_progress() as prog:
        task = prog.add_task("tracer safety", total=len(posts))
        for _ in range(len(posts)):
            outcome = await queue.get()
            post = outcome.item
            item = item_by_id[post.post_id]
            if outcome.error is not None:
                e = outcome.error
                _set_status(db, batch_id, item, "safety_error")
                if isinstance(e, OpenAIError) and is_fatal_llm_error(e):
                    console.print(f"\n[bold red]Fatal safety gate error:[/bold red] {e}")
                    aborted = True
                else:
                    log.warning("Safety gate failed for %s: %s", post.post_id, e)
                prog.update(task, advance=1)
                continue
            if outcome.record is not None:
                call_id = queries.insert_llm_call(db, outcome.record)
            else:
                call_id = None
            if outcome.result.keep:
                queries.record_meme_processing_state(
                    db,
                    post.post_id,
                    "safety",
                    config.consensus_model,
                    safety.prompt_id,
                    "passed",
                    outcome.result.category,
                    call_id,
                )
                safety_kept.append(post)
            else:
                stats.safety_excluded += 1
                queries.insert_auto_review(
                    db, post.post_id, f"safety: {outcome.result.category}"
                )
                queries.record_meme_processing_state(
                    db,
                    post.post_id,
                    "safety",
                    config.consensus_model,
                    safety.prompt_id,
                    "excluded",
                    outcome.result.category,
                    call_id,
                )
                _set_status(db, batch_id, item, "safety_excluded")
            prog.update(task, advance=1)
    await asyncio.gather(*tasks, return_exceptions=True)
    if aborted:
        return []

    console.print(f"  Safety kept {len(safety_kept)}/{len(posts)}")
    consensus_ids = await _run_consensus_phase(
        db,
        config,
        batch_id,
        safety_kept,
        target_consensus,
        detector,
        item_by_id,
        stats,
        console,
    )

    return consensus_ids


async def _run_consensus_phase(
    db: Database,
    config: Config,
    batch_id: str,
    posts: list[RawPost],
    target_consensus: int,
    detector: ConsensusDetector,
    item_by_id: dict[str, TracerItem],
    stats: TracerStats,
    console: Console,
) -> list[str]:
    """Run consensus concurrently, starting only enough calls to find the target."""
    if target_consensus <= 0 or not posts:
        for post in posts:
            _set_status(
                db,
                batch_id,
                item_by_id[post.post_id],
                "not_processed_target_met",
            )
        return []

    consensus_ids: list[str] = []
    next_idx = 0
    pending: dict[asyncio.Task[_Outcome], RawPost] = {}
    max_inflight = max(1, min(MAX_INFLIGHT, target_consensus))

    async def call(post: RawPost) -> _Outcome:
        try:
            result, record = await detector.detect_consensus(post)
            return _Outcome(item=post, result=result, record=record)
        except OpenAIError as e:
            return _Outcome(item=post, error=e)

    def schedule() -> None:
        nonlocal next_idx
        while (
            len(pending) < max_inflight
            and next_idx < len(posts)
            and len(consensus_ids) < target_consensus
        ):
            post = posts[next_idx]
            next_idx += 1
            pending[asyncio.create_task(call(post))] = post

    console.print(f"  Consensus candidates: {len(posts)}")
    schedule()
    with make_progress() as prog:
        task = prog.add_task("tracer consensus", total=len(posts))
        while pending:
            done, _ = await asyncio.wait(
                pending.keys(), return_when=asyncio.FIRST_COMPLETED
            )
            for finished in done:
                pending.pop(finished)
                outcome = await finished
                post = outcome.item
                item = item_by_id[post.post_id]
                if outcome.error is not None:
                    e = outcome.error
                    if isinstance(e, OpenAIError) and is_fatal_llm_error(e):
                        console.print(f"\n[bold red]Fatal consensus error:[/bold red] {e}")
                        for task_to_cancel in pending:
                            task_to_cancel.cancel()
                        await asyncio.gather(*pending.keys(), return_exceptions=True)
                        return consensus_ids
                    _set_status(db, batch_id, item, "consensus_error")
                    stats.no_consensus += 1
                    log.warning("Consensus failed for %s: %s", post.post_id, e)
                    prog.update(task, advance=1)
                    continue
                if outcome.record is not None:
                    call_id = queries.insert_llm_call(db, outcome.record)
                else:
                    call_id = None
                if outcome.result is None or not outcome.result.has_consensus:
                    if outcome.record is None or (
                        outcome.record.error is None
                        and outcome.record.verdict == "no_consensus"
                    ):
                        queries.record_meme_processing_state(
                            db,
                            post.post_id,
                            "consensus",
                            config.consensus_model,
                            detector.prompt_id,
                            "no_consensus",
                            outcome.result.reasoning if outcome.result else None,
                            call_id,
                        )
                    _set_status(db, batch_id, item, "no_consensus")
                    stats.no_consensus += 1
                elif len(consensus_ids) < target_consensus:
                    queries.upsert_ground_truth(
                        db,
                        post.post_id,
                        outcome.result.selected_explanation or "",
                        outcome.result.confidence,
                        outcome.result.agreeing_comment_ids,
                        outcome.result.num_agreeing_comments,
                        outcome.result.avg_comment_score,
                        config.consensus_model,
                        detector.prompt_id,
                    )
                    queries.record_meme_processing_state(
                        db,
                        post.post_id,
                        "consensus",
                        config.consensus_model,
                        detector.prompt_id,
                        "consensus",
                        outcome.result.reasoning,
                        call_id,
                    )
                    _set_status(db, batch_id, item, "consensus")
                    stats.consensus_found += 1
                    consensus_ids.append(post.post_id)
                else:
                    _set_status(db, batch_id, item, "not_processed_target_met")
                prog.update(task, advance=1)
            if len(consensus_ids) >= target_consensus:
                for task_to_cancel in pending:
                    task_to_cancel.cancel()
                await asyncio.gather(*pending.keys(), return_exceptions=True)
                break
            schedule()

        for post in posts[next_idx:]:
            _set_status(
                db,
                batch_id,
                item_by_id[post.post_id],
                "not_processed_target_met",
            )
            prog.update(task, advance=1)
        for post in pending.values():
            _set_status(
                db,
                batch_id,
                item_by_id[post.post_id],
                "not_processed_target_met",
            )
            prog.update(task, advance=1)

    return consensus_ids


async def _predict_batch(
    db: Database,
    config: Config,
    batch_id: str,
    post_ids: list[str],
    model: str,
    stats: TracerStats,
    console: Console,
) -> list[str]:
    if not post_ids:
        return []

    predictor = _build_predictor(model, config)
    queries.register_prompt(
        db,
        predictor.prompt_id,
        "prediction",
        EXPLAIN_MEME_PROMPT,
        USER_PROMPT,
        "1.0",
    )
    ds_version = dataset_version(queries.get_all_ground_truths(db))
    rows = queries.memes_for_prediction_by_ids(db, model, post_ids, validated_only=False)
    item_by_id = {item.post_id: item for item in stats.items}
    predicted_ids: list[str] = []

    console.print(f"\n[bold]Tracer predict:[/bold] {len(rows)} rows for {model}")

    async def predict_one(payload: tuple[int, queries.MemeForPrediction]):
        idx, row = payload
        curated = _to_curated(row, idx)
        return await predictor.predict(curated, ds_version)

    tasks, queue = await _fan_out(
        list(enumerate(rows, start=1)),
        predict_one,
        catchable=(ImageNotFoundError, OpenAIError, AnthropicError),
    )
    aborted = False
    with make_progress() as prog:
        task = prog.add_task(f"tracer predict {model}", total=len(rows))
        for _ in range(len(rows)):
            outcome = await queue.get()
            _, row = outcome.item
            item = item_by_id[row.post_id]
            if outcome.error is not None:
                stats.prediction_errors += 1
                _set_status(db, batch_id, item, "prediction_error")
                if is_fatal_llm_error(outcome.error):
                    console.print(f"\n[bold red]Fatal prediction error:[/bold red] {outcome.error}")
                    aborted = True
                else:
                    log.warning("Prediction failed for %s: %s", row.post_id, outcome.error)
                prog.update(task, advance=1)
                continue
            prediction: ModelPrediction = outcome.result
            if outcome.record is not None:
                queries.insert_llm_call(db, outcome.record)
            queries.insert_prediction(db, prediction)
            if prediction.is_success:
                item.predicted = True
                stats.predictions += 1
                predicted_ids.append(row.post_id)
                _set_status(db, batch_id, item, "predicted")
            else:
                stats.prediction_errors += 1
                _set_status(db, batch_id, item, "prediction_error")
            prog.update(task, advance=1)
    await asyncio.gather(*tasks, return_exceptions=True)
    if aborted:
        return predicted_ids
    return predicted_ids


async def _judge_batch(
    db: Database,
    config: Config,
    post_ids: list[str],
    model: str,
    judge_models: list[str],
    stats: TracerStats,
    console: Console,
) -> None:
    if not post_ids:
        return
    item_by_id = {item.post_id: item for item in stats.items}
    judges: dict[str, Judge] = {m: make_judge(m, config) for m in judge_models}
    for judge in judges.values():
        queries.register_prompt(
            db,
            judge.prompt_id,
            "judge",
            JUDGE_SYSTEM_PROMPT,
            JUDGE_USER_TEMPLATE,
            "1.0",
        )

    judge_tasks: list[_JudgeTask] = []
    for judge_model, judge in judges.items():
        preds = queries.predictions_needing_judgment_for_post_ids(
            db, post_ids, model, judge_model
        )
        for pred in preds:
            judge_tasks.append(
                _JudgeTask(
                    post_id=pred.post_id,
                    prediction_id=pred.prediction_id,
                    prediction=pred.prediction,
                    ground_truth=pred.ground_truth,
                    judge=judge,
                )
            )

    console.print(
        f"\n[bold]Tracer judge:[/bold] {len(judge_tasks)} judgments across "
        f"{len(judges)} judges"
    )

    async def judge_one(task: _JudgeTask):
        return await task.judge.judge(
            task.prediction, task.ground_truth, task.post_id
        )

    tasks, queue = await _fan_out(
        judge_tasks,
        judge_one,
        catchable=(OpenAIError, AnthropicError, LlmJsonParseError),
    )
    fatal_judges: set[str] = set()
    with make_progress() as prog:
        prog_task = prog.add_task("tracer judge", total=len(judge_tasks))
        for _ in range(len(judge_tasks)):
            outcome = await queue.get()
            judge_task: _JudgeTask = outcome.item
            item = item_by_id[judge_task.post_id]
            if outcome.error is not None:
                if is_fatal_llm_error(outcome.error):
                    fatal_judges.add(judge_task.judge.model_id)
                    console.print(
                        f"\n[bold red]Fatal judge error from "
                        f"{judge_task.judge.model_id}:[/bold red] {outcome.error}"
                    )
                else:
                    log.warning(
                        "Judge %s failed on %s: %s",
                        judge_task.judge.model_id,
                        judge_task.post_id,
                        outcome.error,
                    )
                stats.judgment_errors += 1
                prog.update(prog_task, advance=1)
                continue
            result = outcome.result
            if outcome.record is not None:
                queries.insert_llm_call(db, outcome.record)
            queries.insert_judgment(
                db,
                judge_task.prediction_id,
                result.verdict.value,
                result.reasoning,
                judge_task.judge.model_id,
                judge_task.judge.prompt_id,
            )
            item.judged += 1
            stats.judgments += 1
            prog.update(prog_task, advance=1)
    await asyncio.gather(*tasks, return_exceptions=True)


def _db_summary(
    db: Database, batch_id: str, predict_model: str
) -> tuple[int, int, int, int, int]:
    post_ids = queries.batch_meme_ids(db, batch_id)
    if not post_ids:
        return 0, 0, 0, 0, 0
    placeholders = ",".join("?" * len(post_ids))
    consensus = db.conn.execute(
        f"""SELECT COUNT(*) FROM ground_truths
            WHERE post_id IN ({placeholders})""",
        post_ids,
    ).fetchone()[0]
    predictions = db.conn.execute(
        f"""SELECT COUNT(*) FROM predictions
            WHERE post_id IN ({placeholders})
              AND model_id = ?
              AND error IS NULL""",
        (*post_ids, predict_model),
    ).fetchone()[0]
    prediction_errors = db.conn.execute(
        f"""SELECT COUNT(*) FROM batch_memes
            WHERE batch_id = ?
              AND stage_status = 'prediction_error'""",
        (batch_id,),
    ).fetchone()[0]
    judgments = db.conn.execute(
        f"""SELECT COUNT(*) FROM judgments j
            JOIN predictions p ON p.id = j.prediction_id
            WHERE p.post_id IN ({placeholders})
              AND p.model_id = ?
              AND p.error IS NULL""",
        (*post_ids, predict_model),
    ).fetchone()[0]
    return len(post_ids), consensus, predictions, prediction_errors, judgments


async def run(
    db: Database,
    config: Config,
    fetch: int = 12,
    target_consensus: int = 5,
    predict_model: str = "gpt-5.5",
    subreddits: list[str] | None = None,
    time_filters: list[str] | None = None,
    judge: bool = False,
    judge_models: list[str] | None = None,
    batch_id: str | None = None,
    console: Console | None = None,
) -> TracerStats:
    """Run a bounded fetch → gates → consensus → prediction smoke test."""
    console = console or Console()
    batch_id = batch_id or _new_batch_id()
    subreddits = subreddits or list(ingest_pipe.DEFAULT_SUBREDDITS)
    time_filters = time_filters or list(DEFAULT_TIME_FILTERS)
    stats = TracerStats(batch_id=batch_id)
    params = {
        "fetch": fetch,
        "target_consensus": target_consensus,
        "predict_model": predict_model,
        "subreddits": subreddits,
        "time_filters": time_filters,
        "judge": judge,
        "judge_models": judge_models,
    }
    queries.create_batch(
        db,
        batch_id=batch_id,
        kind="tracer",
        params_json=json.dumps(params, sort_keys=True),
        notes="tracer rows are unreviewed and not leaderboard eligible by default",
    )
    console.print(f"[bold]Tracer batch:[/bold] {batch_id}")

    posts = await _fetch_new_posts(
        db, config, batch_id, fetch, subreddits, time_filters, stats, console
    )
    if not posts:
        console.print("No new posts inserted for tracer batch.")
        return stats

    consensus_ids = await _run_gates_and_consensus(
        db, config, batch_id, posts, target_consensus, stats, console
    )
    stats.missing_images_excluded = queries.auto_exclude_missing_images(
        db, consensus_ids
    )
    if stats.missing_images_excluded:
        consensus_ids = [
            post_id
            for post_id in consensus_ids
            if db.conn.execute(
                """SELECT 1 FROM memes m
                   LEFT JOIN reviews r ON r.post_id = m.post_id
                   WHERE m.post_id = ?
                     AND m.local_image_path IS NOT NULL
                     AND m.local_image_path <> ''
                     AND (r.post_id IS NULL OR r.status != 'excluded')""",
                (post_id,),
            ).fetchone()
            is not None
        ]
        console.print(
            f"  Auto-excluded {stats.missing_images_excluded} consensus memes "
            "with missing images"
        )
    predicted_ids = await _predict_batch(
        db, config, batch_id, consensus_ids, predict_model, stats, console
    )
    if judge:
        await _judge_batch(
            db,
            config,
            predicted_ids,
            predict_model,
            judge_models or config.judge_models,
            stats,
            console,
        )

    console.print("\n[bold green]Tracer complete[/bold green]")
    inserted, consensus, predictions, prediction_errors, judgments = _db_summary(
        db, batch_id, predict_model
    )
    stage_counts = queries.batch_stage_counts(db, batch_id)
    console.print(
        f"  Batch:            {batch_id}\n"
        f"  Inserted:         {inserted}\n"
        f"  Consensus found:  {consensus}\n"
        f"  Missing images:   {stats.missing_images_excluded}\n"
        f"  No consensus:     {stage_counts.get('no_consensus', 0)}\n"
        f"  Predictions:      {predictions}\n"
        f"  Prediction errors:{prediction_errors}\n"
        f"  Judgments:        {judgments}"
    )
    return stats
