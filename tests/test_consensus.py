"""Tests for ConsensusDetector — exercise the 10-stage validation with a mocked OpenAI client."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from basedbench.config import Config
from basedbench.llm.consensus import ConsensusDetector
from basedbench.schemas import RawPost, RedditComment


def _config() -> Config:
    return Config(
        reddit_client_id="x",
        reddit_client_secret="y",
        openai_api_key="z",
        min_agreeing_comments=3,
        min_avg_comment_score=10.0,
        min_comment_score=5,
        max_comments_for_consensus=10,
    )


def _post(*, comments: list[RedditComment]) -> RawPost:
    return RawPost(
        post_id="p1",
        subreddit="memes",
        title="t",
        permalink="/r/memes/comments/p1/t",
        score=100,
        retrieved_at="2025-01-02T00:00:00Z",
        comments=comments,
    )


def _comment(cid: str, body: str, score: int) -> RedditComment:
    return RedditComment(comment_id=cid, author=f"u_{cid}", body=body, score=score)


def _mock_response(text: str) -> SimpleNamespace:
    """Shape the SDK's response object enough for our code to read .choices[0].message.content."""
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))]
    )


def _wire(detector: ConsensusDetector, payload: dict) -> AsyncMock:
    create = AsyncMock(return_value=_mock_response(json.dumps(payload)))
    detector._client.chat.completions.create = create  # type: ignore[attr-defined]
    return create


@pytest.mark.asyncio
async def test_too_few_qualifying_comments_skips_llm():
    detector = ConsensusDetector(_config())
    create = AsyncMock()
    detector._client.chat.completions.create = create  # type: ignore[attr-defined]

    post = _post(
        comments=[
            _comment("c1", "high", 50),
            _comment("c2", "low", 2),  # below threshold
        ]
    )

    result, record = await detector.detect_consensus(post)

    assert not result.has_consensus
    assert "qualifying comments" in result.reasoning
    assert record is None
    create.assert_not_called()


def _three_good_comments() -> list[RedditComment]:
    return [
        _comment("c1", "great", 50),
        _comment("c2", "great", 40),
        _comment("c3", "great", 30),
    ]


@pytest.mark.asyncio
async def test_successful_consensus():
    detector = ConsensusDetector(_config())
    explanation = (
        "The joke references the SpongeBob SquarePants episode 'Krabby Patty Creature "
        "Feature' where SpongeBob becomes addicted to a special sauce — playing on the "
        "absurdity of cartoon characters acting like drug addicts."
    )
    _wire(
        detector,
        {
            "reasoning": "All three comments name the SpongeBob episode",
            "has_consensus": True,
            "agreeing_comment_ids": ["c1", "c2", "c3"],
            "selected_explanation": explanation,
            "confidence": 0.9,
        },
    )

    result, record = await detector.detect_consensus(_post(comments=_three_good_comments()))

    assert result.has_consensus
    assert result.selected_explanation == explanation
    assert result.num_agreeing_comments == 3
    assert result.avg_comment_score == pytest.approx(40.0)
    assert record is not None
    assert record.verdict == "consensus"


@pytest.mark.asyncio
async def test_low_confidence_rejected():
    detector = ConsensusDetector(_config())
    _wire(
        detector,
        {
            "reasoning": "Sort of agreement",
            "has_consensus": True,
            "agreeing_comment_ids": ["c1", "c2", "c3"],
            "selected_explanation": "a" * 200,
            "confidence": 0.4,
        },
    )

    result, record = await detector.detect_consensus(_post(comments=_three_good_comments()))

    assert not result.has_consensus
    assert "Confidence too low" in result.reasoning
    assert record is not None and record.verdict == "no_consensus"


@pytest.mark.asyncio
async def test_short_explanation_rejected():
    detector = ConsensusDetector(_config())
    _wire(
        detector,
        {
            "reasoning": "ok",
            "has_consensus": True,
            "agreeing_comment_ids": ["c1", "c2", "c3"],
            "selected_explanation": "too short",
            "confidence": 0.9,
        },
    )

    result, _ = await detector.detect_consensus(_post(comments=_three_good_comments()))

    assert not result.has_consensus
    assert "too short" in result.reasoning


@pytest.mark.asyncio
async def test_vague_phrase_rejected():
    detector = ConsensusDetector(_config())
    _wire(
        detector,
        {
            "reasoning": "ok",
            "has_consensus": True,
            "agreeing_comment_ids": ["c1", "c2", "c3"],
            "selected_explanation": (
                "This meme is just absurd humor that everyone can relate to and the "
                "joke is pretty self-explanatory at this point in internet culture."
            ),
            "confidence": 0.9,
        },
    )

    result, _ = await detector.detect_consensus(_post(comments=_three_good_comments()))

    assert not result.has_consensus
    assert "vague phrase" in result.reasoning


@pytest.mark.asyncio
async def test_avg_score_too_low_rejected():
    detector = ConsensusDetector(_config())
    # All comments meet min_comment_score (5) but avg < 10
    post = _post(
        comments=[
            _comment("c1", "x", 6),
            _comment("c2", "x", 6),
            _comment("c3", "x", 6),
        ]
    )
    _wire(
        detector,
        {
            "reasoning": "ok",
            "has_consensus": True,
            "agreeing_comment_ids": ["c1", "c2", "c3"],
            "selected_explanation": "a" * 200,
            "confidence": 0.9,
        },
    )

    result, _ = await detector.detect_consensus(post)

    assert not result.has_consensus
    assert "Average comment score too low" in result.reasoning
