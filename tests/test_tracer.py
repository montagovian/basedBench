"""Tests for the bounded tracer bullet pipeline."""

from __future__ import annotations

from io import StringIO
from types import SimpleNamespace

import pytest
from rich.console import Console

from basedbench.db import Database
from basedbench.db import queries as q
from basedbench.llm.judge import JudgeResult
from basedbench.llm.record import LlmCallRecord
from basedbench.pipeline import tracer
from basedbench.schemas import ConsensusResult, JudgeVerdict, ModelPrediction

from .conftest import sample_post


def _record(role: str, post_id: str, prompt_id: str) -> LlmCallRecord:
    return LlmCallRecord(
        role=role,
        post_id=post_id,
        model="fake-model",
        system_prompt="system",
        user_prompt="user",
        prompt_version=prompt_id,
        session_id="test-session",
        latency_ms=1,
        response="{}",
    )


class _FakeSafetyGate:
    prompt_id = "fake_safety"

    def __init__(self, config) -> None:
        pass

    async def check(self, post):
        return SimpleNamespace(keep=True, category="ok"), _record(
            "safety_gate", post.post_id, self.prompt_id
        )


class _FakeQualityGate:
    prompt_id = "fake_quality"

    def __init__(self, config) -> None:
        pass

    async def check(self, post):
        return SimpleNamespace(passes=True, reasoning="ok"), _record(
            "quality_gate", post.post_id, self.prompt_id
        )


class _FakeConsensusDetector:
    prompt_id = "fake_consensus"

    def __init__(self, config) -> None:
        self._model = config.consensus_model

    async def detect_consensus(self, post):
        return (
            ConsensusResult(
                has_consensus=True,
                agreeing_comment_ids=[c.comment_id for c in post.comments],
                selected_explanation=f"Ground truth for {post.post_id}",
                confidence=0.9,
                reasoning="ok",
                num_agreeing_comments=len(post.comments),
                avg_comment_score=20.0,
                total_comments_analyzed=len(post.comments),
            ),
            _record("consensus", post.post_id, self.prompt_id),
        )


class _FakePredictor:
    prompt_id = "fake_prediction"

    async def predict(self, meme, dataset_version):
        return (
            ModelPrediction.success(
                meme.post_id,
                dataset_version,
                "gpt-test",
                f"Prediction for {meme.post_id}",
                10,
                5,
            ),
            _record("prediction", meme.post_id, self.prompt_id),
        )


class _FakeJudge:
    model_id = "judge-test"
    prompt_id = "fake_judge"

    async def judge(self, prediction, ground_truth, post_id):
        return (
            JudgeResult(verdict=JudgeVerdict.CORRECT, reasoning="matches"),
            _record("judge", post_id, self.prompt_id),
        )


async def _fake_fetch_new_posts(
    db,
    config,
    batch_id,
    fetch,
    subreddits,
    time_filters,
    stats,
    console,
):
    posts = [sample_post(f"trace{i}") for i in range(1, 4)]
    for position, post in enumerate(posts, start=1):
        assert q.insert_meme(db, post) is True
        stats.inserted += 1
        for comment in post.comments:
            if q.insert_comment(db, post.post_id, comment):
                stats.comments += 1
        q.update_meme_image_path(db, post.post_id, f"/tmp/{post.post_id}.png")
        q.add_batch_meme(db, batch_id, post.post_id, position)
        stats.items.append(tracer.TracerItem(post_id=post.post_id, title=post.title))
    return posts


@pytest.mark.asyncio
async def test_tracer_scopes_predictions_and_judgments(monkeypatch, db: Database):
    # A global unreviewed row with ground truth should remain untouched. This is
    # the failure mode the tracer exists to avoid.
    global_post = sample_post("global_backlog")
    q.insert_meme(db, global_post)
    for comment in global_post.comments:
        q.insert_comment(db, global_post.post_id, comment)
    q.upsert_ground_truth(
        db,
        "global_backlog",
        "Global ground truth",
        0.9,
        [],
        3,
        10.0,
        "model",
        "prompt",
    )

    monkeypatch.setattr(tracer, "SafetyGate", _FakeSafetyGate)
    monkeypatch.setattr(tracer, "QualityGate", _FakeQualityGate)
    monkeypatch.setattr(tracer, "ConsensusDetector", _FakeConsensusDetector)
    monkeypatch.setattr(
        tracer, "_build_predictor", lambda model, config: _FakePredictor()
    )
    monkeypatch.setattr(tracer, "make_judge", lambda model, config: _FakeJudge())
    monkeypatch.setattr(tracer, "_fetch_new_posts", _fake_fetch_new_posts)

    config = SimpleNamespace(
        consensus_model="fake-consensus",
        judge_models=["judge-test"],
    )
    stats = await tracer.run(
        db,
        config,
        fetch=3,
        target_consensus=2,
        predict_model="gpt-test",
        judge=True,
        batch_id="batch-test",
        console=Console(file=StringIO()),
    )

    assert stats.inserted == 3
    assert stats.consensus_found == 2
    assert stats.predictions == 2
    assert stats.judgments == 2
    assert q.batch_stage_counts(db, "batch-test") == {
        "not_processed_target_met": 1,
        "predicted": 2,
    }

    predicted_posts = db.conn.execute(
        "SELECT post_id FROM predictions ORDER BY post_id"
    ).fetchall()
    assert [r[0] for r in predicted_posts] == ["trace1", "trace2"]
    assert q.find_prediction_id(db, "global_backlog", "gpt-test") is None

    reviews = db.conn.execute("SELECT post_id, status FROM reviews").fetchall()
    assert reviews == []
