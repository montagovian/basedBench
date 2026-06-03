"""Bounded end-to-end tracer bullet pipeline.

This command intentionally scopes every downstream phase to the batch it just
created. It is for smoke-testing the full shape of the system, not for adding
leaderboard-eligible evaluated rows.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

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
    QUALITY_GATE_SYSTEM_PROMPT,
    QUALITY_GATE_USER_TEMPLATE,
    SAFETY_GATE_SYSTEM_PROMPT,
    SAFETY_GATE_USER_TEMPLATE,
)
from basedbench.llm.quality_gate import QualityGate
from basedbench.llm.safety_gate import SafetyGate
from basedbench.pipeline import ingest as ingest_pipe
from basedbench.pipeline.predict import USER_PROMPT, _build_predictor, _to_curated
from basedbench.reddit.client import RedditClient
from basedbench.reddit.images import ImageDownloader
from basedbench.schemas import RawPost, dataset_version

log = logging.getLogger(__name__)

DEFAULT_TIME_FILTERS = ("day", "week", "month")


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
    quality_excluded: int = 0
    no_consensus: int = 0
    consensus_found: int = 0
    predictions: int = 0
    prediction_errors: int = 0
    judgments: int = 0
    judgment_errors: int = 0
    items: list[TracerItem] = field(default_factory=list)


def _new_batch_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"tracer-{stamp}"


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
    quality = QualityGate(config)
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
        quality.prompt_id,
        "quality_gate",
        QUALITY_GATE_SYSTEM_PROMPT,
        QUALITY_GATE_USER_TEMPLATE,
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
    consensus_ids: list[str] = []
    console.print(
        f"\n[bold]Tracer curation:[/bold] stopping after {target_consensus} consensus rows"
    )

    for post in posts:
        item = item_by_id[post.post_id]
        if len(consensus_ids) >= target_consensus:
            item.status = "not_processed_target_met"
            queries.update_batch_meme_status(db, batch_id, post.post_id, item.status)
            continue

        try:
            safety_result, record = await safety.check(post)
        except (OpenAIError, LlmJsonParseError) as e:
            if isinstance(e, OpenAIError) and is_fatal_llm_error(e):
                console.print(f"\n[bold red]Fatal safety gate error:[/bold red] {e}")
                break
            item.status = "safety_error"
            queries.update_batch_meme_status(db, batch_id, post.post_id, item.status)
            log.warning("Safety gate failed for %s: %s", post.post_id, e)
            continue
        queries.insert_llm_call(db, record)
        if not safety_result.keep:
            item.status = "safety_excluded"
            stats.safety_excluded += 1
            queries.insert_auto_review(
                db, post.post_id, f"safety: {safety_result.category}"
            )
            queries.update_batch_meme_status(db, batch_id, post.post_id, item.status)
            continue

        try:
            quality_result, record = await quality.check(post)
        except (OpenAIError, LlmJsonParseError) as e:
            if isinstance(e, OpenAIError) and is_fatal_llm_error(e):
                console.print(f"\n[bold red]Fatal quality gate error:[/bold red] {e}")
                break
            item.status = "quality_error"
            queries.update_batch_meme_status(db, batch_id, post.post_id, item.status)
            log.warning("Quality gate failed for %s: %s", post.post_id, e)
            continue
        queries.insert_llm_call(db, record)
        if not quality_result.passes:
            item.status = "quality_excluded"
            stats.quality_excluded += 1
            queries.insert_auto_review(
                db, post.post_id, f"auto: {quality_result.reasoning}"
            )
            queries.update_batch_meme_status(db, batch_id, post.post_id, item.status)
            continue

        try:
            consensus_result, record = await detector.detect_consensus(post)
        except OpenAIError as e:
            if is_fatal_llm_error(e):
                console.print(f"\n[bold red]Fatal consensus error:[/bold red] {e}")
                break
            consensus_result = None
            record = None
            log.warning("Consensus failed for %s: %s", post.post_id, e)
        if record is not None:
            queries.insert_llm_call(db, record)
        if consensus_result is None or not consensus_result.has_consensus:
            item.status = "no_consensus"
            stats.no_consensus += 1
            queries.update_batch_meme_status(db, batch_id, post.post_id, item.status)
            continue

        queries.upsert_ground_truth(
            db,
            post.post_id,
            consensus_result.selected_explanation or "",
            consensus_result.confidence,
            consensus_result.agreeing_comment_ids,
            consensus_result.num_agreeing_comments,
            consensus_result.avg_comment_score,
            config.consensus_model,
            detector.prompt_id,
        )
        item.status = "consensus"
        stats.consensus_found += 1
        consensus_ids.append(post.post_id)
        queries.update_batch_meme_status(db, batch_id, post.post_id, item.status)

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
    for idx, row in enumerate(rows, start=1):
        item = item_by_id[row.post_id]
        curated = _to_curated(row, idx)
        try:
            prediction, record = await predictor.predict(curated, ds_version)
        except ImageNotFoundError as e:
            item.status = "prediction_error"
            stats.prediction_errors += 1
            queries.update_batch_meme_status(db, batch_id, row.post_id, item.status)
            log.warning("%s", e)
            continue
        except (OpenAIError, AnthropicError) as e:
            if is_fatal_llm_error(e):
                console.print(f"\n[bold red]Fatal prediction error:[/bold red] {e}")
                break
            raise
        if record is not None:
            queries.insert_llm_call(db, record)
        queries.insert_prediction(db, prediction)
        if prediction.is_success:
            item.predicted = True
            item.status = "predicted"
            stats.predictions += 1
            predicted_ids.append(row.post_id)
        else:
            item.status = "prediction_error"
            stats.prediction_errors += 1
        queries.update_batch_meme_status(db, batch_id, row.post_id, item.status)
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

    console.print(
        f"\n[bold]Tracer judge:[/bold] {len(post_ids)} predictions across "
        f"{len(judges)} judges"
    )
    for judge_model, judge in judges.items():
        preds = queries.predictions_needing_judgment_for_post_ids(
            db, post_ids, model, judge_model
        )
        for pred in preds:
            item = item_by_id[pred.post_id]
            try:
                result, record = await judge.judge(
                    pred.prediction, pred.ground_truth, pred.post_id
                )
            except (OpenAIError, AnthropicError, LlmJsonParseError) as e:
                if is_fatal_llm_error(e):
                    console.print(f"\n[bold red]Fatal judge error:[/bold red] {e}")
                    break
                stats.judgment_errors += 1
                log.warning("Judge %s failed on %s: %s", judge_model, pred.post_id, e)
                continue
            queries.insert_llm_call(db, record)
            queries.insert_judgment(
                db,
                pred.prediction_id,
                result.verdict.value,
                result.reasoning,
                judge.model_id,
                judge.prompt_id,
            )
            item.judged += 1
            stats.judgments += 1


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
    console.print(
        f"  Batch:            {batch_id}\n"
        f"  Inserted:         {stats.inserted}\n"
        f"  Consensus found:  {stats.consensus_found}\n"
        f"  No consensus:     {stats.no_consensus}\n"
        f"  Predictions:      {stats.predictions}\n"
        f"  Prediction errors:{stats.prediction_errors}\n"
        f"  Judgments:        {stats.judgments}"
    )
    return stats
