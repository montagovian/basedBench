"""Tests for PullpushClient — date-range Reddit discovery via pullpush.io."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from basedbench.reddit.pullpush import (
    MAX_RESULTS_PER_REQUEST,
    PullpushClient,
    PullpushPost,
    _to_pullpush_post,
)


def _raw(
    pid: str,
    *,
    score: int = 100,
    created_utc: float = 1700000000.0,
    url: str = "https://i.redd.it/abc.jpg",
    is_self: bool = False,
    num_comments: int = 20,
    over_18: bool = False,
) -> dict:
    return {
        "id": pid,
        "subreddit": "ExplainTheJoke",
        "title": f"Title {pid}",
        "url": url,
        "is_self": is_self,
        "permalink": f"/r/ExplainTheJoke/comments/{pid}/x",
        "score": score,
        "num_comments": num_comments,
        "created_utc": created_utc,
        "over_18": over_18,
    }


# ───────── _to_pullpush_post conversion ─────────


def test_converts_image_post():
    pp = _to_pullpush_post(_raw("abc"))
    assert pp is not None
    assert pp.post_id == "abc"
    assert pp.image_url == "https://i.redd.it/abc.jpg"
    assert pp.score == 100
    assert pp.over_18 is False


def test_self_post_has_no_image_url():
    pp = _to_pullpush_post(_raw("abc", is_self=True))
    assert pp is not None
    assert pp.image_url is None


def test_non_image_link_post_has_no_image_url():
    pp = _to_pullpush_post(_raw("abc", url="https://youtube.com/watch?v=foo"))
    assert pp is not None
    assert pp.image_url is None


def test_imgur_link_treated_as_image():
    pp = _to_pullpush_post(_raw("abc", url="https://i.imgur.com/xyz.png"))
    assert pp is not None
    assert pp.image_url == "https://i.imgur.com/xyz.png"


def test_missing_id_returns_none():
    assert _to_pullpush_post({"title": "x"}) is None


def test_missing_created_utc_returns_none():
    raw = _raw("abc")
    del raw["created_utc"]
    assert _to_pullpush_post(raw) is None


def test_over_18_flag_preserved():
    pp = _to_pullpush_post(_raw("abc", over_18=True))
    assert pp is not None
    assert pp.over_18 is True


# ───────── PullpushClient.list_posts ─────────


def _make_client_with_pages(pages: list[list[dict]]) -> PullpushClient:
    """Build a client whose _fetch_page returns the given pages in order."""
    client = PullpushClient(user_agent="test")
    client._fetch_page = AsyncMock(side_effect=pages)  # type: ignore[method-assign]
    return client


@pytest.mark.asyncio
async def test_list_posts_returns_single_page_results():
    pages = [[_raw("a", created_utc=100), _raw("b", created_utc=200)]]
    client = _make_client_with_pages(pages + [[]])  # empty trailing page stops walk

    posts = await client.list_posts("ExplainTheJoke", 50, 300, limit=10)

    assert [p.post_id for p in posts] == ["a", "b"]


@pytest.mark.asyncio
async def test_list_posts_paginates_until_limit():
    pages = [
        [_raw(f"p{i}", created_utc=1000 - i) for i in range(MAX_RESULTS_PER_REQUEST)],
        [_raw(f"q{i}", created_utc=500 - i) for i in range(20)],
    ]
    client = _make_client_with_pages(pages)

    posts = await client.list_posts("test", 0, 2000, limit=110)

    assert len(posts) == 110
    # First page exhausted, then 10 from second page
    assert posts[100].post_id == "q0"
    assert posts[109].post_id == "q9"


@pytest.mark.asyncio
async def test_list_posts_stops_when_pullpush_returns_empty():
    pages = [[_raw("a", created_utc=1000)], []]
    client = _make_client_with_pages(pages)

    posts = await client.list_posts("test", 0, 2000, limit=100)

    assert len(posts) == 1


@pytest.mark.asyncio
async def test_list_posts_rejects_inverted_date_range():
    client = PullpushClient(user_agent="test")
    with pytest.raises(ValueError, match="must be <"):
        await client.list_posts("test", after_unix=2000, before_unix=1000, limit=10)


@pytest.mark.asyncio
async def test_list_posts_walks_back_via_created_utc():
    """Each pagination request should set `before` to the oldest of the prior page."""
    # Two pages worth of MAX_RESULTS_PER_REQUEST posts so pagination actually fires.
    page1 = [_raw(f"a{i}", created_utc=1000 - i) for i in range(MAX_RESULTS_PER_REQUEST)]
    page2 = [_raw(f"b{i}", created_utc=500 - i) for i in range(MAX_RESULTS_PER_REQUEST)]
    page3: list[dict] = []
    client = PullpushClient(user_agent="test")
    fetch_mock = AsyncMock(side_effect=[page1, page2, page3])
    client._fetch_page = fetch_mock  # type: ignore[method-assign]

    posts = await client.list_posts("test", after_unix=0, before_unix=2000, limit=500)

    assert len(posts) == 2 * MAX_RESULTS_PER_REQUEST

    # First call uses the user's before; second call should walk back to
    # (oldest of page1) - 1 = (1000 - 99) - 1 = 900.
    second_call_kwargs = fetch_mock.call_args_list[1].kwargs
    assert second_call_kwargs["before"] == (1000 - (MAX_RESULTS_PER_REQUEST - 1)) - 1
