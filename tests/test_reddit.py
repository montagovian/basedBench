"""Tests for Reddit client helpers and image utilities (no network calls)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from basedbench.errors import ImageDownloadError, RedditApiError
from basedbench.reddit.client import RedditClient, _is_image_url
from basedbench.reddit.images import _extension_from_url, _validate_image_url, find_local_image


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://i.redd.it/abc123.jpg", True),
        ("https://i.redd.it/abc123.png?width=640", True),
        ("https://i.imgur.com/abc123.gif", True),
        ("https://example.com/meme.webp", True),
        ("https://reddit.com/r/memes", False),
        ("https://youtube.com/watch?v=abc", False),
    ],
)
def test_is_image_url(url: str, expected: bool):
    assert _is_image_url(url) is expected


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://i.redd.it/abc.jpg", "jpg"),
        ("https://i.redd.it/abc.png?width=640", "png"),
        ("https://i.redd.it/abc.gif", "gif"),
        ("https://i.redd.it/abc.webp", "webp"),
        ("https://i.redd.it/abc.jpeg", "jpeg"),
        ("https://i.redd.it/abc", "jpg"),
    ],
)
def test_extension_from_url(url: str, expected: str):
    assert _extension_from_url(url) == expected


def test_find_local_image_none(tmp_path: Path):
    assert find_local_image(tmp_path, "nonexistent") is None


def test_find_local_image_exists(tmp_path: Path):
    (tmp_path / "test_post.png").write_bytes(b"fake image data")
    found = find_local_image(tmp_path, "test_post")
    assert found is not None
    assert found.name == "test_post.png"


@pytest.mark.parametrize(
    "url",
    [
        "https://i.redd.it/abc.jpg",
        "https://preview.redd.it/abc.png?width=640",
        "https://i.imgur.com/abc.gif",
        "https://i.imgflip.com/abc.jpg",
    ],
)
def test_validate_image_url_allows_known_https_hosts(url: str):
    _validate_image_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "http://i.redd.it/abc.jpg",
        "file:///etc/passwd",
        "https://example.com/cat.gif",
        "https://evil.i.redd.it.example/abc.jpg",
    ],
)
def test_validate_image_url_rejects_unsafe_sources(url: str):
    with pytest.raises(ImageDownloadError):
        _validate_image_url(url)


# ───────── fetch_posts resilience ─────────


def _fake_listing(post_ids: list[str]) -> dict:
    """Build a minimal Reddit /top JSON response."""
    return {
        "data": {
            "after": None,
            "children": [
                {
                    "data": {
                        "name": f"t3_{pid}",
                        "title": f"Title {pid}",
                        "url": f"https://i.redd.it/{pid}.jpg",
                        "permalink": f"/r/test/comments/{pid}/x",
                        "score": 500,
                        "num_comments": 50,
                        "created_utc": 1700000000,
                    }
                }
                for pid in post_ids
            ],
        }
    }


@pytest.mark.asyncio
async def test_fetch_posts_skips_removed_post_with_404_comments():
    """If a post in the listing has been removed (comments endpoint → 404), skip it."""
    from basedbench.config import Config

    cfg = Config(  # type: ignore[call-arg]
        reddit_client_id="x",
        reddit_client_secret="y",
        openai_api_key="sk-xxx",
        anthropic_api_key=None,
        judge_models=["gpt-5.4-mini"],
    )
    client = RedditClient(cfg)
    client._access_token = "fake-token"  # bypass authenticate()

    # Two posts in the listing — first 404s on comments, second succeeds.
    client._get_json = AsyncMock(return_value=_fake_listing(["good_post", "removed_post"]))  # type: ignore[method-assign]

    async def fake_fetch_comments(sub: str, post_id: str):
        if post_id == "removed_post":
            raise RedditApiError(404, '{"message":"Not Found"}')
        return []

    client.fetch_comments = AsyncMock(side_effect=fake_fetch_comments)  # type: ignore[method-assign]

    posts = await client.fetch_posts("test", limit=10)

    # Only the surviving post should be returned; the 404 didn't crash the run.
    assert len(posts) == 1
    assert posts[0].post_id == "good_post"


@pytest.mark.asyncio
async def test_fetch_posts_non_404_api_error_still_raises():
    """A 500 (or other non-404) from the comments endpoint should still bubble up."""
    from basedbench.config import Config

    cfg = Config(  # type: ignore[call-arg]
        reddit_client_id="x",
        reddit_client_secret="y",
        openai_api_key="sk-xxx",
        anthropic_api_key=None,
        judge_models=["gpt-5.4-mini"],
    )
    client = RedditClient(cfg)
    client._access_token = "fake-token"

    client._get_json = AsyncMock(return_value=_fake_listing(["post1"]))  # type: ignore[method-assign]
    client.fetch_comments = AsyncMock(  # type: ignore[method-assign]
        side_effect=RedditApiError(500, "server died")
    )

    with pytest.raises(RedditApiError) as exc_info:
        await client.fetch_posts("test", limit=10)
    assert exc_info.value.status == 500
