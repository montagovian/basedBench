"""Predict pipeline: route by model id, run VLM, store prediction."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from rich.console import Console

from basedbench.config import Config
from basedbench.db import queries
from basedbench.db.connection import Database
from basedbench.errors import (
    AnthropicError,
    ConfigError,
    ImageNotFoundError,
    OpenAIError,
    is_fatal_llm_error,
)
from basedbench.llm.anthropic import AnthropicPredictor
from basedbench.llm.openai import OpenAIPredictor
from basedbench.llm.prompts import EXPLAIN_MEME_PROMPT
from basedbench.llm.provider import Predictor
from basedbench.pipeline._progress import make_progress
from basedbench.schemas import CuratedMeme, dataset_version, display_index, is_anthropic_model

log = logging.getLogger(__name__)

USER_PROMPT = "Please explain this meme."


@dataclass
class PredictStats:
    dataset_version: str
    total: int = 0
    successes: int = 0
    errors: int = 0


def _build_predictor(model: str, config: Config) -> Predictor:
    if is_anthropic_model(model):
        if not config.anthropic_api_key:
            raise ConfigError("ANTHROPIC_API_KEY required for Claude models")
        return AnthropicPredictor(config.anthropic_api_key, model)
    return OpenAIPredictor(config.openai_api_key, model)


def _to_curated(row: queries.MemeForPrediction, idx: int) -> CuratedMeme:
    import json as _json

    try:
        comment_ids = _json.loads(row.source_comment_ids)
    except (ValueError, TypeError):
        comment_ids = []
    return CuratedMeme(
        meme_id=display_index(idx),
        post_id=row.post_id,
        subreddit=row.subreddit,
        title=row.title,
        image_url=row.image_url,
        local_image_path=row.local_image_path,
        permalink=row.permalink,
        ground_truth_explanation=row.ground_truth_explanation,
        consensus_confidence=row.consensus_confidence,
        source_comment_ids=comment_ids,
        num_agreeing_comments=row.num_agreeing_comments,
        avg_comment_score=row.avg_comment_score,
        created_utc=row.created_utc,
        curated_at=row.ground_truth_created_at,
    )


async def run(
    db: Database,
    config: Config,
    model: str,
    snapshot: str | None = None,
    include_unreviewed: bool = False,
    console: Console | None = None,
) -> PredictStats:
    console = console or Console()
    predictor = _build_predictor(model, config)

    snapshot_id: str | None = None
    if snapshot is not None:
        info = queries.find_snapshot(db, snapshot)
        if info is None:
            raise ValueError(f"snapshot not found: {snapshot}")
        snapshot_id = info.snapshot_id

    validated_only = not include_unreviewed
    if snapshot_id is not None:
        ground_truths = queries.snapshot_ground_truths(db, snapshot_id)
    elif validated_only:
        ground_truths = queries.validated_meme_pairs(db)
    else:
        ground_truths = queries.get_all_ground_truths(db)

    if not ground_truths:
        hint = (
            "Run `basedbench review` to validate memes."
            if validated_only
            else "Run `basedbench ingest` first."
        )
        console.print(f"No ground truths found. {hint}")
        return PredictStats(dataset_version="", total=0)

    ds_version = dataset_version(ground_truths)
    console.print(f"Dataset version: {ds_version}")

    memes = queries.memes_needing_prediction(db, model, snapshot_id, validated_only)
    console.print(f"{len(memes)} memes need prediction for {model}")
    if not memes:
        if validated_only:
            counts = queries.get_status_counts(db)
            if counts.unreviewed:
                console.print(
                    f"{counts.unreviewed} memes have unreviewed ground truth. "
                    f"Run `basedbench review` to validate, or pass --include-unreviewed."
                )
        console.print("Nothing to do.")
        return PredictStats(dataset_version=ds_version, total=0)

    queries.register_prompt(
        db, predictor.prompt_id, "prediction", EXPLAIN_MEME_PROMPT, USER_PROMPT, "1.0"
    )

    stats = PredictStats(dataset_version=ds_version, total=len(memes))
    with make_progress() as prog:
        task = prog.add_task(f"{model}", total=len(memes))
        for i, row in enumerate(memes, start=1):
            curated = _to_curated(row, i)
            try:
                prediction, record = await predictor.predict(curated, ds_version)
            except ImageNotFoundError as e:
                log.warning("%s", e)
                stats.errors += 1
                prog.update(task, advance=1)
                continue
            except (OpenAIError, AnthropicError) as e:
                if is_fatal_llm_error(e):
                    console.print(
                        f"\n[bold red]Fatal {type(e).__name__}:[/bold red] {e}"
                    )
                    console.print(
                        "[red]Aborting predictions. Fix the API key / billing and rerun.[/red]"
                    )
                    break
                raise

            if record is not None:
                queries.insert_llm_call(db, record)

            if prediction.is_success:
                stats.successes += 1
            else:
                stats.errors += 1
            queries.insert_prediction(db, prediction)
            prog.update(task, advance=1)

    console.print(
        f"\n[bold green]Predict complete[/bold green]: "
        f"{stats.successes} successes, {stats.errors} errors"
    )
    return stats
