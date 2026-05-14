"""Tests for fatal LLM error classification."""

from __future__ import annotations

import httpx
import openai
import pytest

from basedbench.errors import OpenAIError, is_fatal_llm_error


def _make_rate_limit_error(status: int, code: str | None) -> openai.RateLimitError:
    response = httpx.Response(
        status_code=status,
        request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"),
    )
    body: dict = {"error": {"code": code}} if code else {}
    return openai.RateLimitError("rate limit", response=response, body=body)


def test_insufficient_quota_is_fatal():
    e = _make_rate_limit_error(429, "insufficient_quota")
    assert is_fatal_llm_error(e)


def test_invalid_api_key_is_fatal():
    e = _make_rate_limit_error(401, "invalid_api_key")
    assert is_fatal_llm_error(e)


def test_401_status_is_fatal_even_without_code():
    e = _make_rate_limit_error(401, None)
    assert is_fatal_llm_error(e)


def test_403_status_is_fatal():
    e = _make_rate_limit_error(403, None)
    assert is_fatal_llm_error(e)


def test_plain_rate_limit_is_transient():
    """A real 429 from being too fast should NOT be marked fatal."""
    e = _make_rate_limit_error(429, "rate_limit_exceeded")
    assert not is_fatal_llm_error(e)


def test_wrapper_with_fatal_flag_is_fatal():
    assert is_fatal_llm_error(OpenAIError("anything", fatal=True))


def test_wrapper_without_fatal_flag_is_transient():
    assert not is_fatal_llm_error(OpenAIError("transient"))


def test_random_exception_is_not_fatal():
    assert not is_fatal_llm_error(RuntimeError("totally unrelated"))


def test_500_server_error_is_transient():
    """Server errors are retryable, not fatal."""
    e = _make_rate_limit_error(500, None)
    assert not is_fatal_llm_error(e)


# ─── Consensus + quality gate raise on fatal, swallow on transient ───


@pytest.mark.asyncio
async def test_consensus_raises_on_fatal_error(monkeypatch):
    """A fatal error mid-consensus should propagate, not be silently converted to no_consensus."""
    from unittest.mock import AsyncMock

    from basedbench.config import Config
    from basedbench.llm.consensus import ConsensusDetector
    from basedbench.schemas import RawPost, RedditComment

    config = Config(  # type: ignore[call-arg]
        reddit_client_id="x",
        reddit_client_secret="y",
        openai_api_key="z",
    )
    detector = ConsensusDetector(config)
    fatal = _make_rate_limit_error(429, "insufficient_quota")
    detector._client.chat.completions.create = AsyncMock(side_effect=fatal)  # type: ignore[attr-defined]

    post = RawPost(
        post_id="p1",
        subreddit="memes",
        title="t",
        permalink="/r/memes/comments/p1/t",
        score=100,
        retrieved_at="2025-01-02T00:00:00Z",
        comments=[
            RedditComment(comment_id=f"c{i}", author=f"u{i}", body="x", score=50)
            for i in range(3)
        ],
    )

    with pytest.raises(OpenAIError) as exc_info:
        await detector.detect_consensus(post)
    assert exc_info.value.fatal
