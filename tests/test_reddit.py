"""Tests for Reddit client helpers and image utilities (no network calls)."""

from __future__ import annotations

from pathlib import Path

import pytest

from basedbench.reddit.client import _is_image_url
from basedbench.reddit.images import _extension_from_url, find_local_image


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
