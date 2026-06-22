"""Tests for schemas.py — mirrors v4 schema tests."""

from basedbench.schemas import (
    ConsensusResult,
    JudgeVerdict,
    ModelMetrics,
    ModelPrediction,
    RawPost,
    RedditComment,
    dataset_version,
    display_index,
    is_anthropic_model,
    is_openrouter_model,
)


# ═══════════════════════════════════════════════════════
# Identifiers
# ═══════════════════════════════════════════════════════


def test_dataset_version_deterministic():
    pairs1 = [("a", "explanation_a"), ("b", "explanation_b")]
    pairs2 = [("b", "explanation_b"), ("a", "explanation_a")]
    assert dataset_version(pairs1) == dataset_version(pairs2)


def test_dataset_version_different_for_different_inputs():
    pairs1 = [("a", "explanation_a")]
    pairs2 = [("a", "explanation_b")]
    assert dataset_version(pairs1) != dataset_version(pairs2)


def test_dataset_version_length():
    v = dataset_version([("a", "b")])
    assert len(v) == 16


def test_model_id_is_anthropic():
    assert is_anthropic_model("claude-sonnet-4-5")
    assert is_anthropic_model("claude-3-opus")
    assert not is_anthropic_model("gpt-4o-mini")
    assert not is_anthropic_model("gemini-pro")


def test_model_id_is_openrouter():
    assert is_openrouter_model("x-ai/grok-4.3")
    assert is_openrouter_model("z-ai/glm-5.2")
    assert not is_openrouter_model("gpt-5.5")
    assert not is_openrouter_model("claude-opus-4-8")


def test_display_index():
    assert display_index(1) == "meme_00001"
    assert display_index(42) == "meme_00042"
    assert display_index(99999) == "meme_99999"


# ═══════════════════════════════════════════════════════
# Reddit models
# ═══════════════════════════════════════════════════════


def test_raw_post_roundtrip():
    post = RawPost(
        post_id="abc123",
        subreddit="memes",
        title="test meme",
        image_url="https://i.redd.it/test.jpg",
        permalink="/r/memes/comments/abc123/test",
        score=420,
        created_utc="2025-01-01T00:00:00Z",
        retrieved_at="2025-01-02T00:00:00Z",
        comments=[
            RedditComment(
                comment_id="c1",
                author="user1",
                body="this is funny",
                score=100,
                is_moderator=False,
            )
        ],
    )
    data = post.model_dump()
    restored = RawPost.model_validate(data)
    assert restored.post_id == "abc123"
    assert len(restored.comments) == 1
    assert restored.comments[0].score == 100


# ═══════════════════════════════════════════════════════
# Consensus
# ═══════════════════════════════════════════════════════


def test_consensus_result_roundtrip():
    result = ConsensusResult(
        has_consensus=True,
        agreeing_comment_ids=["c1", "c2"],
        selected_explanation="This meme references X",
        confidence=0.85,
        reasoning="Multiple comments agree",
        num_agreeing_comments=5,
        avg_comment_score=42.0,
        total_comments_analyzed=8,
    )
    data = result.model_dump()
    restored = ConsensusResult.model_validate(data)
    assert restored.has_consensus is True
    assert len(restored.agreeing_comment_ids) == 2
    assert restored.confidence == 0.85


# ═══════════════════════════════════════════════════════
# Predictions
# ═══════════════════════════════════════════════════════


def test_prediction_success():
    pred = ModelPrediction.success(
        "post1", "v1", "gpt-4o", "This meme is about cats", 1500, 200
    )
    assert pred.is_success
    assert pred.error is None
    assert pred.latency_ms == 1500


def test_prediction_failure():
    pred = ModelPrediction.failure("post1", "v1", "gpt-4o", "timeout")
    assert not pred.is_success
    assert pred.error == "timeout"
    assert pred.prediction == ""


def test_prediction_roundtrip():
    pred = ModelPrediction.success(
        "post1", "v1", "gpt-4o", "explanation", 100, 50
    )
    data = pred.model_dump()
    restored = ModelPrediction.model_validate(data)
    assert restored.post_id == "post1"
    assert restored.is_success


# ═══════════════════════════════════════════════════════
# Judgments
# ═══════════════════════════════════════════════════════


def test_verdict_score():
    assert JudgeVerdict.CORRECT.score == 1.0
    assert JudgeVerdict.INCORRECT.score == 0.0


def test_verdict_parse():
    assert JudgeVerdict.parse("correct") == JudgeVerdict.CORRECT
    assert JudgeVerdict.parse("INCORRECT") == JudgeVerdict.INCORRECT
    assert JudgeVerdict.parse("Correct") == JudgeVerdict.CORRECT


def test_verdict_parse_invalid():
    import pytest
    from basedbench.errors import LlmJsonParseError

    with pytest.raises(LlmJsonParseError):
        JudgeVerdict.parse("maybe")


def test_verdict_as_str():
    assert JudgeVerdict.CORRECT.value == "correct"
    assert JudgeVerdict.INCORRECT.value == "incorrect"


def test_model_metrics_roundtrip():
    metrics = ModelMetrics(
        model_id="gpt-4o",
        total_evaluated=100,
        correct=75,
        incorrect=25,
        accuracy=0.75,
    )
    data = metrics.model_dump()
    restored = ModelMetrics.model_validate(data)
    assert restored.accuracy == 0.75
