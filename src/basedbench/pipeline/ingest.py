"""Ingest pipeline: Reddit fetch → image download → safety gate → quality gate → consensus."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from rich.console import Console

from basedbench.config import Config
from basedbench.db import queries
from basedbench.db.connection import Database
from basedbench.errors import (
    ImageDownloadError,
    ImageValidationError,
    LlmJsonParseError,
    OpenAIError,
    is_fatal_llm_error,
)
from basedbench.llm.consensus import ConsensusDetector
from basedbench.llm.prompts import (
    CONSENSUS_SYSTEM_PROMPT,
    CONSENSUS_USER_TEMPLATE,
    QUALITY_GATE_SYSTEM_PROMPT,
    QUALITY_GATE_USER_TEMPLATE,
    SAFETY_GATE_SYSTEM_PROMPT,
    SAFETY_GATE_USER_TEMPLATE,
)
from basedbench.llm.quality_gate import QualityGate
from basedbench.llm.safety_gate import SafetyGate
from basedbench.pipeline._progress import make_progress
from basedbench.reddit.client import RedditClient
from basedbench.reddit.images import ImageDownloader

log = logging.getLogger(__name__)

DEFAULT_SUBREDDITS = ("ExplainTheJoke", "PeterExplainsTheJoke")


@dataclass
class IngestStats:
    new_memes: int = 0
    new_comments: int = 0
    images_downloaded: int = 0
    safety_passed: int = 0
    safety_failed: int = 0
    safety_skipped: int = 0
    gate_passed: int = 0
    gate_failed: int = 0
    gate_skipped: int = 0
    consensus_found: int = 0
    consensus_failed: int = 0


async def run(
    db: Database,
    config: Config,
    limit: int,
    subreddit: str | None = None,
    time_filter: str = "year",
    console: Console | None = None,
) -> IngestStats:
    console = console or Console()
    stats = IngestStats()
    subs = [subreddit] if subreddit else list(DEFAULT_SUBREDDITS)

    # ─── Phase 1: fetch + image download ───
    console.print(
        f"[bold]Phase 1:[/bold] Fetching from Reddit (t={time_filter})..."
    )
    async with RedditClient(config) as reddit, ImageDownloader(config.images_dir) as imgs:
        await reddit.authenticate()
        for sub in subs:
            posts = await reddit.fetch_posts(sub, limit, time_filter=time_filter)
            console.print(f"  r/{sub}: fetched {len(posts)} posts")
            if not posts:
                continue

            with make_progress() as prog:
                task = prog.add_task(f"r/{sub}", total=len(posts))
                for post in posts:
                    if queries.insert_meme(db, post):
                        stats.new_memes += 1
                    for c in post.comments:
                        if queries.insert_comment(db, post.post_id, c):
                            stats.new_comments += 1
                    if post.image_url:
                        try:
                            path = await imgs.download(post.image_url, post.post_id)
                            queries.update_meme_image_path(db, post.post_id, path)
                            stats.images_downloaded += 1
                        except (ImageDownloadError, ImageValidationError) as e:
                            log.warning("Image download failed for %s: %s", post.post_id, e)
                    prog.update(task, advance=1)

    console.print(
        f"  Added {stats.new_memes} memes, {stats.new_comments} comments, "
        f"{stats.images_downloaded} images"
    )

    # ─── Phase 1.4: safety gate ───
    console.print("\n[bold]Phase 1.4:[/bold] Running safety gate...")
    safety_candidates = queries.memes_needing_safety_gate(db)
    console.print(f"  {len(safety_candidates)} memes need safety check")
    if safety_candidates:
        safety = SafetyGate(config)
        queries.register_prompt(
            db,
            safety.prompt_id,
            "safety_gate",
            SAFETY_GATE_SYSTEM_PROMPT,
            SAFETY_GATE_USER_TEMPLATE,
            "1.0",
        )
        aborted = False
        with make_progress() as prog:
            task = prog.add_task("safety gate", total=len(safety_candidates))
            for post_id in safety_candidates:
                post = queries.reconstruct_raw_post(db, post_id)
                if post is None:
                    log.warning("Could not reconstruct post %s", post_id)
                    stats.safety_skipped += 1
                    prog.update(task, advance=1)
                    continue

                try:
                    result, record = await safety.check(post)
                except OpenAIError as e:
                    if is_fatal_llm_error(e):
                        console.print(
                            f"\n[bold red]Fatal OpenAI error during safety gate:[/bold red] {e}"
                        )
                        console.print(
                            "[red]Aborting phase. Fix the API key / billing and rerun.[/red]"
                        )
                        aborted = True
                        break
                    log.warning("Safety gate failed for %s: %s", post_id, e)
                    stats.safety_skipped += 1
                    prog.update(task, advance=1)
                    continue
                except LlmJsonParseError as e:
                    log.warning("Safety gate parse failed for %s: %s", post_id, e)
                    stats.safety_skipped += 1
                    prog.update(task, advance=1)
                    continue

                queries.insert_llm_call(db, record)
                if result.keep:
                    stats.safety_passed += 1
                else:
                    queries.insert_auto_review(
                        db, post_id, f"safety: {result.category}"
                    )
                    stats.safety_failed += 1
                prog.update(task, advance=1)
        if aborted:
            return stats
        console.print(
            f"  Kept: {stats.safety_passed}, Excluded: {stats.safety_failed}, "
            f"Skipped: {stats.safety_skipped}"
        )

    # ─── Phase 1.5: quality gate ───
    console.print("\n[bold]Phase 1.5:[/bold] Running quality gate...")
    gate_candidates = queries.memes_needing_quality_gate(db)
    console.print(f"  {len(gate_candidates)} memes need quality gate")
    if gate_candidates:
        gate = QualityGate(config)
        queries.register_prompt(
            db,
            gate.prompt_id,
            "quality_gate",
            QUALITY_GATE_SYSTEM_PROMPT,
            QUALITY_GATE_USER_TEMPLATE,
            "1.0",
        )
        aborted = False
        with make_progress() as prog:
            task = prog.add_task("quality gate", total=len(gate_candidates))
            for post_id in gate_candidates:
                post = queries.reconstruct_raw_post(db, post_id)
                if post is None:
                    log.warning("Could not reconstruct post %s", post_id)
                    stats.gate_skipped += 1
                    prog.update(task, advance=1)
                    continue

                qualifying = [
                    c for c in post.comments if c.score >= config.min_comment_score
                ]
                if not qualifying:
                    stats.gate_skipped += 1
                    prog.update(task, advance=1)
                    continue

                try:
                    result, record = await gate.check(post)
                except OpenAIError as e:
                    if is_fatal_llm_error(e):
                        console.print(
                            f"\n[bold red]Fatal OpenAI error during quality gate:[/bold red] {e}"
                        )
                        console.print(
                            "[red]Aborting phase. Fix the API key / billing and rerun.[/red]"
                        )
                        aborted = True
                        break
                    log.warning("Quality gate failed for %s: %s", post_id, e)
                    stats.gate_skipped += 1
                    prog.update(task, advance=1)
                    continue
                except LlmJsonParseError as e:
                    log.warning("Quality gate failed for %s: %s", post_id, e)
                    stats.gate_skipped += 1
                    prog.update(task, advance=1)
                    continue

                queries.insert_llm_call(db, record)
                if result.passes:
                    stats.gate_passed += 1
                else:
                    queries.insert_auto_review(db, post_id, f"auto: {result.reasoning}")
                    stats.gate_failed += 1
                prog.update(task, advance=1)
        if aborted:
            return stats
        console.print(
            f"  Passed: {stats.gate_passed}, Excluded: {stats.gate_failed}, "
            f"Skipped: {stats.gate_skipped}"
        )

    # ─── Phase 2: consensus ───
    console.print("\n[bold]Phase 2:[/bold] Running consensus detection...")
    missing = queries.memes_without_ground_truth(db)
    console.print(f"  {len(missing)} memes need consensus detection")
    if missing:
        detector = ConsensusDetector(config)
        queries.register_prompt(
            db,
            detector.prompt_id,
            "consensus",
            CONSENSUS_SYSTEM_PROMPT,
            CONSENSUS_USER_TEMPLATE,
            "1.0",
        )
        with make_progress() as prog:
            task = prog.add_task("consensus", total=len(missing))
            for post_id in missing:
                post = queries.reconstruct_raw_post(db, post_id)
                if post is None:
                    log.warning("Could not reconstruct post %s", post_id)
                    prog.update(task, advance=1)
                    continue
                try:
                    result, record = await detector.detect_consensus(post)
                except OpenAIError as e:
                    if is_fatal_llm_error(e):
                        console.print(
                            f"\n[bold red]Fatal OpenAI error during consensus:[/bold red] {e}"
                        )
                        console.print(
                            "[red]Aborting phase. Fix the API key / billing and rerun.[/red]"
                        )
                        break
                    log.warning("Consensus failed for %s: %s", post_id, e)
                    stats.consensus_failed += 1
                    prog.update(task, advance=1)
                    continue
                if record is not None:
                    queries.insert_llm_call(db, record)
                if result.has_consensus:
                    queries.upsert_ground_truth(
                        db,
                        post_id,
                        result.selected_explanation or "",
                        result.confidence,
                        result.agreeing_comment_ids,
                        result.num_agreeing_comments,
                        result.avg_comment_score,
                        config.consensus_model,
                        detector.prompt_id,
                    )
                    stats.consensus_found += 1
                else:
                    stats.consensus_failed += 1
                prog.update(task, advance=1)

    console.print("\n[bold green]Ingest complete[/bold green]")
    console.print(
        f"  New memes: {stats.new_memes}\n"
        f"  Consensus found: {stats.consensus_found}\n"
        f"  No consensus:    {stats.consensus_failed}"
    )
    return stats
