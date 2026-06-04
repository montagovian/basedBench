"""Ingest pipeline: Reddit fetch → image download → safety gate → consensus.

The LLM phases run their calls concurrently via a per-phase semaphore. DB writes
stay on the main coroutine to keep sqlite single-threaded and avoid write
contention. Each phase pre-loads the candidate RawPosts upfront (sequential,
fast) so workers only do the network-bound LLM call.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

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
    SAFETY_GATE_SYSTEM_PROMPT,
    SAFETY_GATE_USER_TEMPLATE,
)
from basedbench.llm.record import LlmCallRecord
from basedbench.llm.safety_gate import SafetyGate
from basedbench.pipeline._progress import make_progress
from basedbench.reddit.client import (
    INTER_REQUEST_DELAY,
    MIN_POST_COMMENTS,
    MIN_POST_SCORE,
    RedditClient,
)
from basedbench.reddit.images import ImageDownloader
from basedbench.reddit.pullpush import PullpushClient, PullpushPost
from basedbench.schemas import RawPost

log = logging.getLogger(__name__)

DEFAULT_SUBREDDITS = ("ExplainTheJoke", "PeterExplainsTheJoke")
MAX_INFLIGHT = 10


@dataclass
class IngestStats:
    new_memes: int = 0
    new_comments: int = 0
    images_downloaded: int = 0
    missing_images_excluded: int = 0
    safety_passed: int = 0
    safety_failed: int = 0
    safety_skipped: int = 0
    consensus_found: int = 0
    consensus_failed: int = 0


@dataclass
class _Outcome:
    """Result from one worker call: either a (result, record) or an exception."""

    post: RawPost
    result: Any = None
    record: LlmCallRecord | None = None
    error: Exception | None = None


async def _fan_out(
    posts: list[RawPost],
    worker_fn: Callable[[RawPost], Awaitable[tuple[Any, LlmCallRecord | None]]],
    catchable: tuple[type[Exception], ...],
) -> tuple[list[asyncio.Task[None]], asyncio.Queue[_Outcome]]:
    """Spawn one task per post that runs worker_fn under a shared semaphore.

    Returns the task list and the outcome queue so the caller can consume
    results as they finish (any order). Exceptions in `catchable` are caught
    and surfaced via _Outcome.error; anything else bubbles up via gather().
    """
    sem = asyncio.Semaphore(MAX_INFLIGHT)
    queue: asyncio.Queue[_Outcome] = asyncio.Queue()

    async def worker(post: RawPost) -> None:
        async with sem:
            try:
                result, record = await worker_fn(post)
                await queue.put(_Outcome(post=post, result=result, record=record))
            except catchable as e:
                await queue.put(_Outcome(post=post, error=e))

    tasks = [asyncio.create_task(worker(p)) for p in posts]
    return tasks, queue


async def _fetch_phase_reddit(
    db: Database,
    config: Config,
    subs: list[str],
    limit: int,
    time_filter: str,
    stats: IngestStats,
    console: Console,
) -> None:
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
            await _persist_posts(db, posts, imgs, stats, f"r/{sub}")


async def _fetch_phase_pullpush(
    db: Database,
    config: Config,
    subs: list[str],
    limit: int,
    after_unix: int,
    before_unix: int,
    stats: IngestStats,
    console: Console,
) -> None:
    """Discover posts via pullpush date-range, then fetch comments via Reddit OAuth."""
    console.print(
        f"[bold]Phase 1:[/bold] Fetching via pullpush.io "
        f"({after_unix} → {before_unix})..."
    )
    async with (
        PullpushClient(config.reddit_user_agent) as pp,
        RedditClient(config) as reddit,
        ImageDownloader(config.images_dir) as imgs,
    ):
        await reddit.authenticate()
        for sub in subs:
            qualifying = await pp.list_posts(
                sub,
                after_unix,
                before_unix,
                limit,
                min_score=MIN_POST_SCORE,
                min_comments=MIN_POST_COMMENTS,
                require_image=True,
            )
            console.print(
                f"  r/{sub}: pullpush returned {len(qualifying)} qualifying posts"
            )
            if not qualifying:
                continue

            # For each pullpush post, fetch comments from Reddit OAuth and
            # convert to RawPost. Sequential because Reddit's rate limit is
            # tighter than pullpush's; concurrent would risk 429s.
            posts: list[RawPost] = []
            with make_progress() as prog:
                task = prog.add_task(
                    f"r/{sub} comments", total=len(qualifying)
                )
                for pp_post in qualifying:
                    try:
                        comments = await reddit.fetch_comments(sub, pp_post.post_id)
                    except Exception as e:  # noqa: BLE001
                        log.warning(
                            "Skipping %s — comment fetch failed: %s",
                            pp_post.post_id, e,
                        )
                        prog.update(task, advance=1)
                        continue
                    posts.append(_pullpush_to_rawpost(pp_post, comments))
                    await asyncio.sleep(INTER_REQUEST_DELAY)
                    prog.update(task, advance=1)

            await _persist_posts(db, posts, imgs, stats, f"r/{sub}")


def _pullpush_to_rawpost(
    pp_post: PullpushPost, comments: list
) -> RawPost:
    from datetime import datetime, timezone

    return RawPost(
        post_id=pp_post.post_id,
        subreddit=pp_post.subreddit,
        title=pp_post.title,
        image_url=pp_post.image_url,
        permalink=pp_post.permalink,
        score=pp_post.score,
        created_utc=datetime.fromtimestamp(
            int(pp_post.created_utc), tz=timezone.utc
        ).isoformat(),
        retrieved_at=datetime.now(timezone.utc).isoformat(),
        comments=comments,
    )


async def _persist_posts(
    db: Database,
    posts: list[RawPost],
    imgs: ImageDownloader,
    stats: IngestStats,
    label: str,
) -> None:
    """Insert posts/comments and download images. Shared by both fetch paths."""
    with make_progress() as prog:
        task = prog.add_task(label, total=len(posts))
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


async def run(
    db: Database,
    config: Config,
    limit: int,
    subreddit: str | None = None,
    time_filter: str = "year",
    after_unix: int | None = None,
    before_unix: int | None = None,
    console: Console | None = None,
) -> IngestStats:
    """Run the ingest pipeline.

    Two fetch modes are mutually exclusive:
      - default: Reddit /top with `time_filter` (preset window: hour/day/.../all)
      - date-range: when `after_unix` and `before_unix` are both set, discover
        posts via pullpush.io for that specific window, then fetch comments
        via Reddit OAuth.

    All downstream phases (safety / consensus) are identical regardless of
    fetch mode.
    """
    console = console or Console()
    stats = IngestStats()
    subs = [subreddit] if subreddit else list(DEFAULT_SUBREDDITS)
    use_date_range = after_unix is not None and before_unix is not None

    # ─── Phase 1: fetch + image download ───
    if use_date_range:
        assert after_unix is not None and before_unix is not None
        await _fetch_phase_pullpush(
            db, config, subs, limit, after_unix, before_unix, stats, console
        )
    else:
        await _fetch_phase_reddit(
            db, config, subs, limit, time_filter, stats, console
        )

    console.print(
        f"  Added {stats.new_memes} memes, {stats.new_comments} comments, "
        f"{stats.images_downloaded} images"
    )

    # ─── Phase 1.4: safety gate (concurrent) ───
    console.print("\n[bold]Phase 1.4:[/bold] Running safety gate...")
    safety = SafetyGate(config)
    queries.register_prompt(
        db,
        safety.prompt_id,
        "safety_gate",
        SAFETY_GATE_SYSTEM_PROMPT,
        SAFETY_GATE_USER_TEMPLATE,
        "1.0",
    )
    safety_candidates = queries.memes_needing_safety_gate(
        db, config.consensus_model, safety.prompt_id
    )
    console.print(f"  {len(safety_candidates)} memes need safety check")
    if safety_candidates:
        # Pre-load posts (sequential DB reads, fast) and filter unreconstructable ones.
        safety_posts: list[RawPost] = []
        for pid in safety_candidates:
            post = queries.reconstruct_raw_post(db, pid)
            if post is None:
                log.warning("Could not reconstruct post %s", pid)
                stats.safety_skipped += 1
            else:
                safety_posts.append(post)

        tasks, queue = await _fan_out(
            safety_posts,
            safety.check,
            catchable=(OpenAIError, LlmJsonParseError),
        )

        aborted = False
        with make_progress() as prog:
            task = prog.add_task("safety gate", total=len(safety_posts))
            for _ in range(len(safety_posts)):
                outcome = await queue.get()
                if outcome.error is not None:
                    e = outcome.error
                    if isinstance(e, OpenAIError) and is_fatal_llm_error(e):
                        if not aborted:
                            console.print(
                                f"\n[bold red]Fatal OpenAI error during safety gate:[/bold red] {e}"
                            )
                            console.print(
                                "[red]Aborting phase. Inflight requests will still drain.[/red]"
                            )
                            aborted = True
                        stats.safety_skipped += 1
                    else:
                        log.warning("Safety gate failed for %s: %s", outcome.post.post_id, e)
                        stats.safety_skipped += 1
                else:
                    call_id = None
                    if outcome.record is not None:
                        call_id = queries.insert_llm_call(db, outcome.record)
                    if outcome.result.keep:
                        queries.record_meme_processing_state(
                            db,
                            outcome.post.post_id,
                            "safety",
                            config.consensus_model,
                            safety.prompt_id,
                            "passed",
                            outcome.result.category,
                            call_id,
                        )
                        stats.safety_passed += 1
                    else:
                        queries.insert_auto_review(
                            db, outcome.post.post_id, f"safety: {outcome.result.category}"
                        )
                        queries.record_meme_processing_state(
                            db,
                            outcome.post.post_id,
                            "safety",
                            config.consensus_model,
                            safety.prompt_id,
                            "excluded",
                            outcome.result.category,
                            call_id,
                        )
                        stats.safety_failed += 1
                prog.update(task, advance=1)

        await asyncio.gather(*tasks, return_exceptions=True)
        if aborted:
            return stats
        console.print(
            f"  Kept: {stats.safety_passed}, Excluded: {stats.safety_failed}, "
            f"Skipped: {stats.safety_skipped}"
        )

    # ─── Phase 2: consensus (concurrent) ───
    console.print("\n[bold]Phase 2:[/bold] Running consensus detection...")
    detector = ConsensusDetector(config)
    queries.register_prompt(
        db,
        detector.prompt_id,
        "consensus",
        CONSENSUS_SYSTEM_PROMPT,
        CONSENSUS_USER_TEMPLATE,
        "1.0",
    )
    missing = queries.memes_without_ground_truth(
        db, config.consensus_model, detector.prompt_id
    )
    console.print(f"  {len(missing)} memes need consensus detection")
    if missing:
        consensus_posts: list[RawPost] = []
        for pid in missing:
            post = queries.reconstruct_raw_post(db, pid)
            if post is None:
                log.warning("Could not reconstruct post %s", pid)
                continue
            consensus_posts.append(post)

        tasks, queue = await _fan_out(
            consensus_posts,
            detector.detect_consensus,
            catchable=(OpenAIError,),
        )

        aborted = False
        with make_progress() as prog:
            task = prog.add_task("consensus", total=len(consensus_posts))
            for _ in range(len(consensus_posts)):
                outcome = await queue.get()
                if outcome.error is not None:
                    e = outcome.error
                    if isinstance(e, OpenAIError) and is_fatal_llm_error(e):
                        if not aborted:
                            console.print(
                                f"\n[bold red]Fatal OpenAI error during consensus:[/bold red] {e}"
                            )
                            console.print(
                                "[red]Aborting phase. Inflight requests will still drain.[/red]"
                            )
                            aborted = True
                        stats.consensus_failed += 1
                    else:
                        log.warning("Consensus failed for %s: %s", outcome.post.post_id, e)
                        stats.consensus_failed += 1
                else:
                    call_id = None
                    if outcome.record is not None:
                        call_id = queries.insert_llm_call(db, outcome.record)
                    if outcome.result.has_consensus:
                        queries.upsert_ground_truth(
                            db,
                            outcome.post.post_id,
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
                            outcome.post.post_id,
                            "consensus",
                            config.consensus_model,
                            detector.prompt_id,
                            "consensus",
                            outcome.result.reasoning,
                            call_id,
                        )
                        stats.consensus_found += 1
                    else:
                        if outcome.record is None or (
                            outcome.record.error is None
                            and outcome.record.verdict == "no_consensus"
                        ):
                            queries.record_meme_processing_state(
                                db,
                                outcome.post.post_id,
                                "consensus",
                                config.consensus_model,
                                detector.prompt_id,
                                "no_consensus",
                                outcome.result.reasoning,
                                call_id,
                            )
                        stats.consensus_failed += 1
                prog.update(task, advance=1)

        await asyncio.gather(*tasks, return_exceptions=True)

    stats.missing_images_excluded = queries.auto_exclude_missing_images(db)
    if stats.missing_images_excluded:
        console.print(
            f"  Auto-excluded {stats.missing_images_excluded} consensus memes "
            "with missing images"
        )

    console.print("\n[bold green]Ingest complete[/bold green]")
    console.print(
        f"  New memes: {stats.new_memes}\n"
        f"  Consensus found: {stats.consensus_found}\n"
        f"  Missing images:  {stats.missing_images_excluded}\n"
        f"  No consensus:    {stats.consensus_failed}"
    )
    return stats
