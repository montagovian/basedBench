"""Tests for LlmJudge — verdict parsing with a mocked OpenAI client."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from basedbench.errors import LlmJsonParseError
from basedbench.llm.judge import LlmJudge
from basedbench.schemas import JudgeVerdict


def _mock_response(text: str) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))]
    )


def _judge() -> LlmJudge:
    return LlmJudge(api_key="x", model="gpt-4o-mini")


@pytest.mark.asyncio
async def test_judge_correct_verdict():
    judge = _judge()
    judge._client.chat.completions.create = AsyncMock(  # type: ignore[attr-defined]
        return_value=_mock_response(
            json.dumps({"reasoning": "matches", "verdict": "correct"})
        )
    )

    result, record = await judge.judge("prediction text", "ground truth", "p1")

    assert result.verdict == JudgeVerdict.CORRECT
    assert result.reasoning == "matches"
    assert record.verdict == "correct"
    assert record.role == "judge"
    assert record.post_id == "p1"


@pytest.mark.asyncio
async def test_judge_incorrect_verdict():
    judge = _judge()
    judge._client.chat.completions.create = AsyncMock(  # type: ignore[attr-defined]
        return_value=_mock_response(
            json.dumps({"reasoning": "off topic", "verdict": "incorrect"})
        )
    )

    result, _ = await judge.judge("p", "g", "p1")

    assert result.verdict == JudgeVerdict.INCORRECT
    assert result.verdict.score == 0.0


@pytest.mark.asyncio
async def test_judge_accepts_fenced_json_verdict():
    judge = _judge()
    judge._client.chat.completions.create = AsyncMock(  # type: ignore[attr-defined]
        return_value=_mock_response(
            '```json\n{"reasoning": "same joke", "verdict": "correct"}\n```'
        )
    )

    result, record = await judge.judge("prediction text", "ground truth", "p1")

    assert result.verdict == JudgeVerdict.CORRECT
    assert record.verdict == "correct"


@pytest.mark.asyncio
async def test_judge_accepts_prefaced_json_verdict():
    judge = _judge()
    judge._client.chat.completions.create = AsyncMock(  # type: ignore[attr-defined]
        return_value=_mock_response(
            'The model provided no explanation.\n{"reasoning": "missing", "verdict": "incorrect"}'
        )
    )

    result, record = await judge.judge("prediction text", "ground truth", "p1")

    assert result.verdict == JudgeVerdict.INCORRECT
    assert record.verdict == "incorrect"


@pytest.mark.asyncio
async def test_judge_invalid_verdict_raises():
    judge = _judge()
    judge._client.chat.completions.create = AsyncMock(  # type: ignore[attr-defined]
        return_value=_mock_response(
            json.dumps({"reasoning": "?", "verdict": "maybe"})
        )
    )

    with pytest.raises(LlmJsonParseError):
        await judge.judge("p", "g", "p1")


@pytest.mark.asyncio
async def test_judge_malformed_json_raises():
    judge = _judge()
    judge._client.chat.completions.create = AsyncMock(  # type: ignore[attr-defined]
        return_value=_mock_response("not json at all")
    )

    with pytest.raises(LlmJsonParseError):
        await judge.judge("p", "g", "p1")
