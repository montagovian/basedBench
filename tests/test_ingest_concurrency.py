"""Tests for the concurrent fan-out helper in pipeline/ingest.py."""

from __future__ import annotations

import asyncio

import pytest

from basedbench.pipeline.ingest import _fan_out
from basedbench.schemas import RawPost


def _post(pid: str) -> RawPost:
    return RawPost(
        post_id=pid,
        subreddit="memes",
        title=f"Title {pid}",
        image_url=None,
        permalink=f"/r/memes/{pid}",
        score=100,
        created_utc="2026-01-01T00:00:00Z",
        retrieved_at="2026-01-02T00:00:00Z",
        comments=[],
    )


@pytest.mark.asyncio
async def test_fan_out_returns_outcome_for_every_post():
    """No work lost: 50 posts in → 50 outcomes out."""
    posts = [_post(f"p{i}") for i in range(50)]

    async def worker(post):
        return ("ok", None)

    tasks, queue = await _fan_out(posts, worker, catchable=(Exception,))
    outcomes = [await queue.get() for _ in posts]
    await asyncio.gather(*tasks, return_exceptions=True)

    assert len(outcomes) == 50
    seen_ids = {o.post.post_id for o in outcomes}
    assert seen_ids == {f"p{i}" for i in range(50)}
    assert all(o.error is None for o in outcomes)


@pytest.mark.asyncio
async def test_fan_out_catches_listed_exceptions():
    """Errors of the catchable types are surfaced via Outcome.error."""
    posts = [_post("ok"), _post("bad")]

    async def worker(post):
        if post.post_id == "bad":
            raise ValueError("nope")
        return ("good", None)

    tasks, queue = await _fan_out(posts, worker, catchable=(ValueError,))
    outcomes = [await queue.get() for _ in posts]
    await asyncio.gather(*tasks, return_exceptions=True)

    by_id = {o.post.post_id: o for o in outcomes}
    assert by_id["ok"].error is None
    assert by_id["ok"].result == "good"
    assert isinstance(by_id["bad"].error, ValueError)
    assert by_id["bad"].result is None


@pytest.mark.asyncio
async def test_fan_out_uncaught_exception_propagates_through_gather():
    """Exceptions NOT in `catchable` should not silently disappear."""
    posts = [_post("p1")]

    async def worker(post):
        raise RuntimeError("not catchable")

    tasks, queue = await _fan_out(posts, worker, catchable=(ValueError,))
    # The worker exception isn't caught → task fails, queue never gets an item.
    # gather with return_exceptions=True surfaces it as a returned value.
    results = await asyncio.gather(*tasks, return_exceptions=True)
    assert any(isinstance(r, RuntimeError) for r in results)


@pytest.mark.asyncio
async def test_fan_out_runs_concurrently_not_serially():
    """50 workers each sleeping 50ms should finish in well under 50×50ms = 2.5s."""
    posts = [_post(f"p{i}") for i in range(50)]

    async def slow_worker(post):
        await asyncio.sleep(0.05)
        return ("done", None)

    import time

    start = time.monotonic()
    tasks, queue = await _fan_out(posts, slow_worker, catchable=(Exception,))
    for _ in posts:
        await queue.get()
    await asyncio.gather(*tasks, return_exceptions=True)
    elapsed = time.monotonic() - start

    # With MAX_INFLIGHT=10 and 50 jobs × 50ms = ~250ms ideal; serial would be ~2.5s.
    # Generous bound to avoid flakes: must be under 1.5s.
    assert elapsed < 1.5, f"concurrency seems broken — took {elapsed:.2f}s"
