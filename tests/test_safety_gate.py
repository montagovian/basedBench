"""Tests for SafetyGate — JSON parsing + pipeline integration."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from basedbench.db import Database
from basedbench.db import queries as q
from basedbench.errors import LlmJsonParseError
from basedbench.llm.safety_gate import SafetyGate, SafetyResult

from tests.conftest import sample_post


def _mock_response(text: str) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
    )


def _make_gate():
    """SafetyGate without env loading."""
    from basedbench.config import Config

    cfg = Config(  # type: ignore[call-arg]
        reddit_client_id="x",
        reddit_client_secret="y",
        openai_api_key="sk-xxx",
        anthropic_api_key=None,
        judge_models=["gpt-5.4-mini"],
    )
    return SafetyGate(cfg)


@pytest.mark.asyncio
async def test_safety_gate_keeps_clean_content():
    gate = _make_gate()
    gate._client.chat.completions.create = AsyncMock(  # type: ignore[attr-defined]
        return_value=_mock_response(
            json.dumps({"keep": True, "category": "keep"})
        )
    )

    result, record = await gate.check(sample_post("post1"))

    assert result.keep is True
    assert result.category == "keep"
    assert record.verdict == "keep"
    assert record.role == "safety_gate"
    assert record.prompt_tokens == 10


@pytest.mark.asyncio
async def test_safety_gate_excludes_with_category():
    gate = _make_gate()
    gate._client.chat.completions.create = AsyncMock(  # type: ignore[attr-defined]
        return_value=_mock_response(
            json.dumps({"keep": False, "category": "explicit_sexual"})
        )
    )

    result, record = await gate.check(sample_post("post1"))

    assert result.keep is False
    assert result.category == "explicit_sexual"
    assert record.verdict == "exclude"
    assert record.reasoning == "explicit_sexual"


@pytest.mark.asyncio
async def test_safety_gate_malformed_json_raises():
    gate = _make_gate()
    gate._client.chat.completions.create = AsyncMock(  # type: ignore[attr-defined]
        return_value=_mock_response("not json")
    )

    with pytest.raises(LlmJsonParseError):
        await gate.check(sample_post("post1"))


@pytest.mark.asyncio
async def test_safety_gate_missing_keep_field_raises():
    """The `keep` field is required — exclusions must be explicit."""
    gate = _make_gate()
    gate._client.chat.completions.create = AsyncMock(  # type: ignore[attr-defined]
        return_value=_mock_response(json.dumps({"category": "keep"}))
    )

    with pytest.raises(LlmJsonParseError):
        await gate.check(sample_post("post1"))


@pytest.mark.asyncio
async def test_safety_gate_defaults_category_when_omitted():
    gate = _make_gate()
    gate._client.chat.completions.create = AsyncMock(  # type: ignore[attr-defined]
        return_value=_mock_response(json.dumps({"keep": True}))
    )

    result, _ = await gate.check(sample_post("post1"))
    assert result.keep is True
    assert result.category == "unspecified"


# ───────── Pipeline integration: idempotency / phase ordering ─────────


def test_safety_excluded_meme_skipped_by_quality_gate(db: Database):
    """A meme excluded by safety must NOT show up in quality-gate's candidate list."""
    post = sample_post("post1")
    q.insert_meme(db, post)
    for c in post.comments:
        q.insert_comment(db, "post1", c)

    # Before any gate runs, both predicates return the meme.
    assert "post1" in q.memes_needing_safety_gate(db)
    assert "post1" in q.memes_needing_quality_gate(db)

    # Safety gate excludes it.
    q.insert_auto_review(db, "post1", "safety: explicit_sexual")

    # Now neither predicate returns it — quality gate skips, no wasted tokens.
    assert "post1" not in q.memes_needing_safety_gate(db)
    assert "post1" not in q.memes_needing_quality_gate(db)


def test_safety_kept_meme_still_visible_to_quality_gate(db: Database):
    """Memes that PASS safety still need quality gating — no review row is written."""
    post = sample_post("post1")
    q.insert_meme(db, post)
    for c in post.comments:
        q.insert_comment(db, "post1", c)

    # Safety pass writes no review row (only failures do).
    # Quality gate should still pick this up.
    assert "post1" in q.memes_needing_quality_gate(db)
