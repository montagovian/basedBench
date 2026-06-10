"""Tests for the multi-judge flow: factory, per-judge queries, agreement math."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from basedbench.db import Database
from basedbench.db import queries as q
from basedbench.llm.judge import (
    AnthropicJudge,
    LlmJudge,
    make_judge,
)
from basedbench.pipeline import judge as judge_pipe
from basedbench.schemas import ModelPrediction
from rich.console import Console

from tests.conftest import sample_post


def _setup_validated_meme(db: Database, post_id: str = "post1") -> None:
    post = sample_post(post_id)
    q.insert_meme(db, post)
    for c in post.comments:
        q.insert_comment(db, post_id, c)
    q.upsert_ground_truth(
        db, post_id, "ground truth", 0.9, ["c1", "c2"], 5, 42.0,
        "gpt-5.4-mini", "prompt_v1",
    )
    q.upsert_review(db, post_id, "validated")


def _make_config(
    anthropic_key: str | None = "sk-ant-xxx",
    judge_models: list[str] | None = None,
):
    """Build a Config without touching env. Avoids .env loading complications."""
    from basedbench.config import Config

    if judge_models is None:
        # default that doesn't require an anthropic key, so callers can omit it
        judge_models = (
            ["gpt-5.4-mini", "claude-sonnet-4-6"]
            if anthropic_key
            else ["gpt-5.4-mini"]
        )
    return Config(  # type: ignore[call-arg]
        reddit_client_id="x",
        reddit_client_secret="y",
        openai_api_key="sk-xxx",
        anthropic_api_key=anthropic_key,
        judge_models=judge_models,
    )


# ───────── factory routing ─────────


def test_make_judge_routes_openai_models():
    cfg = _make_config()
    j = make_judge("gpt-5.4-mini", cfg)
    assert isinstance(j, LlmJudge)
    assert j.model_id == "gpt-5.4-mini"


def test_make_judge_routes_anthropic_models():
    cfg = _make_config()
    j = make_judge("claude-sonnet-4-6", cfg)
    assert isinstance(j, AnthropicJudge)
    assert j.model_id == "claude-sonnet-4-6"


def test_make_judge_requires_anthropic_key_for_claude():
    # Config itself is valid (no claude in judge_models), but ad-hoc calls
    # to make_judge for a claude model should still fail without a key.
    cfg = _make_config(anthropic_key=None, judge_models=["gpt-5.4-mini"])
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        make_judge("claude-sonnet-4-6", cfg)


def test_make_judge_rejects_unknown_provider():
    cfg = _make_config()
    with pytest.raises(ValueError, match="Unknown judge model"):
        make_judge("llama-99", cfg)


def test_config_allows_claude_judge_config_without_key_until_construction():
    from basedbench.config import Config

    cfg = Config(  # type: ignore[call-arg]
        reddit_client_id="x",
        reddit_client_secret="y",
        openai_api_key="sk-xxx",
        anthropic_api_key=None,
        judge_models=["gpt-5.4-mini", "claude-sonnet-4-6"],
    )

    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        make_judge("claude-sonnet-4-6", cfg)


# ───────── per-judge `predictions_needing_judgment` ─────────


def test_predictions_needing_judgment_per_judge(db: Database):
    _setup_validated_meme(db, "post1")
    q.insert_prediction(
        db, ModelPrediction.success("post1", "v1", "gpt-5.5", "cats", 1, 1)
    )
    q.register_prompt(db, "vJ", "judge", "s", "u", "1.0")
    pid = q.find_prediction_id(db, "post1", "gpt-5.5")

    # No judgments yet — every judge needs it.
    needed_gpt = q.predictions_needing_judgment(db, judge_model="gpt-5.4-mini")
    needed_claude = q.predictions_needing_judgment(db, judge_model="claude-sonnet-4-6")
    assert {p.prediction_id for p in needed_gpt} == {pid}
    assert {p.prediction_id for p in needed_claude} == {pid}

    # First judge runs — only the other should be needed now.
    q.insert_judgment(db, pid, "correct", "ok", "gpt-5.4-mini", "vJ")
    assert q.predictions_needing_judgment(db, judge_model="gpt-5.4-mini") == []
    assert {
        p.prediction_id
        for p in q.predictions_needing_judgment(db, judge_model="claude-sonnet-4-6")
    } == {pid}

    # Second judge runs — neither needed.
    q.insert_judgment(db, pid, "incorrect", "no", "claude-sonnet-4-6", "vJ")
    assert q.predictions_needing_judgment(db, judge_model="gpt-5.4-mini") == []
    assert q.predictions_needing_judgment(db, judge_model="claude-sonnet-4-6") == []


# ───────── per-(target, judge) judgment counts + agreement ─────────


def test_judgment_counts_split_by_judge(db: Database):
    _setup_validated_meme(db, "post1")
    _setup_validated_meme(db, "post2")
    q.insert_prediction(db, ModelPrediction.success("post1", "v1", "gpt-5.5", "a", 1, 1))
    q.insert_prediction(db, ModelPrediction.success("post2", "v1", "gpt-5.5", "b", 1, 1))
    q.register_prompt(db, "vJ", "judge", "s", "u", "1.0")
    pid1 = q.find_prediction_id(db, "post1", "gpt-5.5")
    pid2 = q.find_prediction_id(db, "post2", "gpt-5.5")

    # Two judges, with one agreement and one disagreement.
    q.insert_judgment(db, pid1, "correct", "", "gpt-5.4-mini", "vJ")
    q.insert_judgment(db, pid1, "correct", "", "claude-sonnet-4-6", "vJ")
    q.insert_judgment(db, pid2, "correct", "", "gpt-5.4-mini", "vJ")
    q.insert_judgment(db, pid2, "incorrect", "", "claude-sonnet-4-6", "vJ")

    counts = {(c.model_id, c.judge_model): c for c in q.get_judgment_counts(db)}
    assert counts[("gpt-5.5", "gpt-5.4-mini")].correct == 2
    assert counts[("gpt-5.5", "gpt-5.4-mini")].incorrect == 0
    assert counts[("gpt-5.5", "claude-sonnet-4-6")].correct == 1
    assert counts[("gpt-5.5", "claude-sonnet-4-6")].incorrect == 1

    agreement = q.get_judge_agreement(db)
    by_model = {a.model_id: a for a in agreement}
    assert by_model["gpt-5.5"].judged_by_multiple == 2
    assert by_model["gpt-5.5"].agreements == 1
    assert by_model["gpt-5.5"].rate == 0.5


def test_agreement_excludes_solo_judged_predictions(db: Database):
    """A prediction with only one judge shouldn't count toward agreement at all."""
    _setup_validated_meme(db, "post1")
    q.insert_prediction(db, ModelPrediction.success("post1", "v1", "gpt-5.5", "a", 1, 1))
    q.register_prompt(db, "vJ", "judge", "s", "u", "1.0")
    pid = q.find_prediction_id(db, "post1", "gpt-5.5")

    q.insert_judgment(db, pid, "correct", "", "gpt-5.4-mini", "vJ")

    agreement = q.get_judge_agreement(db)
    by_model = {a.model_id: a for a in agreement}
    assert by_model["gpt-5.5"].judged_by_multiple == 0
    assert by_model["gpt-5.5"].agreements == 0


def test_latest_judgment_per_judge_wins(db: Database):
    """Re-judging with the same judge updates the count (latest row wins)."""
    _setup_validated_meme(db, "post1")
    q.insert_prediction(db, ModelPrediction.success("post1", "v1", "gpt-5.5", "a", 1, 1))
    q.register_prompt(db, "vJ", "judge", "s", "u", "1.0")
    pid = q.find_prediction_id(db, "post1", "gpt-5.5")

    q.insert_judgment(db, pid, "incorrect", "first try", "gpt-5.4-mini", "vJ")
    q.insert_judgment(db, pid, "correct", "second try", "gpt-5.4-mini", "vJ")

    counts = {(c.model_id, c.judge_model): c for c in q.get_judgment_counts(db)}
    # One judgment counted (the latest), and it's correct.
    assert counts[("gpt-5.5", "gpt-5.4-mini")].judged == 1
    assert counts[("gpt-5.5", "gpt-5.4-mini")].correct == 1


# ───────── pipeline run with mocked judges ─────────


class _FakeJudge:
    def __init__(self, model_id: str, verdict: str) -> None:
        self.model_id = model_id
        self.prompt_id = "fake_prompt_id"
        self._verdict = verdict

    async def judge(self, prediction, ground_truth, post_id):
        from basedbench.llm.judge import JudgeResult
        from basedbench.llm.record import LlmCallRecord
        from basedbench.schemas import JudgeVerdict

        record = LlmCallRecord(
            role="judge",
            post_id=post_id,
            model=self.model_id,
            system_prompt="s",
            user_prompt="u",
            prompt_version=self.prompt_id,
            session_id="test",
            latency_ms=1,
            response=self._verdict,
        )
        record.verdict = self._verdict
        return JudgeResult(
            verdict=JudgeVerdict.parse(self._verdict),
            reasoning="fake reasoning",
        ), record


@pytest.mark.asyncio
async def test_pipeline_runs_all_judges_per_prediction(monkeypatch, db: Database):
    _setup_validated_meme(db, "post1")
    q.insert_prediction(db, ModelPrediction.success("post1", "v1", "gpt-5.5", "a", 1, 1))

    fakes = {
        "gpt-5.4-mini": _FakeJudge("gpt-5.4-mini", "correct"),
        "claude-sonnet-4-6": _FakeJudge("claude-sonnet-4-6", "incorrect"),
    }
    monkeypatch.setattr(judge_pipe, "make_judge", lambda m, c: fakes[m])

    cfg = _make_config()
    stats = await judge_pipe.run(
        db,
        cfg,
        judge_models=["gpt-5.4-mini", "claude-sonnet-4-6"],
        console=Console(quiet=True),
    )

    assert stats.per_judge["gpt-5.4-mini"].correct == 1
    assert stats.per_judge["claude-sonnet-4-6"].incorrect == 1

    counts = {(c.model_id, c.judge_model): c for c in q.get_judgment_counts(db)}
    assert ("gpt-5.5", "gpt-5.4-mini") in counts
    assert ("gpt-5.5", "claude-sonnet-4-6") in counts

    agreement = q.get_judge_agreement(db)
    assert agreement[0].model_id == "gpt-5.5"
    assert agreement[0].judged_by_multiple == 1
    assert agreement[0].agreements == 0  # they disagreed


@pytest.mark.asyncio
async def test_pipeline_skips_already_judged_pairs(monkeypatch, db: Database):
    """If a (prediction, judge_model) row already exists, that judge skips it."""
    _setup_validated_meme(db, "post1")
    q.insert_prediction(db, ModelPrediction.success("post1", "v1", "gpt-5.5", "a", 1, 1))
    q.register_prompt(db, "fake_prompt_id", "judge", "s", "u", "1.0")
    pid = q.find_prediction_id(db, "post1", "gpt-5.5")
    q.insert_judgment(db, pid, "correct", "prior", "gpt-5.4-mini", "fake_prompt_id")

    call_log: list[str] = []

    class _Recorder(_FakeJudge):
        async def judge(self, prediction, ground_truth, post_id):
            call_log.append(self.model_id)
            return await super().judge(prediction, ground_truth, post_id)

    fakes = {
        "gpt-5.4-mini": _Recorder("gpt-5.4-mini", "correct"),
        "claude-sonnet-4-6": _Recorder("claude-sonnet-4-6", "incorrect"),
    }
    monkeypatch.setattr(judge_pipe, "make_judge", lambda m, c: fakes[m])

    await judge_pipe.run(
        db,
        _make_config(),
        judge_models=["gpt-5.4-mini", "claude-sonnet-4-6"],
        console=Console(quiet=True),
    )

    # Only claude should have been called; gpt was already judged.
    assert call_log == ["claude-sonnet-4-6"]


# ───────── AnthropicJudge parse path ─────────


@pytest.mark.asyncio
async def test_anthropic_judge_parses_verdict():
    aj = AnthropicJudge(api_key="x", model="claude-sonnet-4-6")
    text_block = SimpleNamespace(
        type="text",
        text=json.dumps({"reasoning": "matches", "verdict": "correct"}),
    )
    response = SimpleNamespace(
        content=[text_block],
        usage=SimpleNamespace(input_tokens=5, output_tokens=6),
    )
    aj._client.messages.create = AsyncMock(return_value=response)  # type: ignore[attr-defined]

    result, record = await aj.judge("p", "g", "pid")
    assert result.verdict.value == "correct"
    assert record.prompt_tokens == 5
    assert record.completion_tokens == 6
