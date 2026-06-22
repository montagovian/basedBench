"""Pydantic models for basedBench data structures."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════
# Identifiers
# ═══════════════════════════════════════════════════════


def dataset_version(pairs: list[tuple[str, str]]) -> str:
    """Compute a content-addressed dataset version.

    First 16 hex chars of SHA256 over sorted (post_id, explanation) pairs.
    """
    sorted_pairs = sorted(pairs, key=lambda p: p[0])
    hasher = hashlib.sha256()
    for post_id, explanation in sorted_pairs:
        hasher.update(post_id.encode())
        hasher.update(explanation.encode())
    return hasher.hexdigest()[:16]


def display_index(n: int) -> str:
    """Human-readable meme index: meme_00001, meme_00002, etc."""
    return f"meme_{n:05d}"


def is_anthropic_model(model_id: str) -> bool:
    """Return True if this model should use the Anthropic API."""
    return model_id.startswith("claude")


def is_openrouter_model(model_id: str) -> bool:
    """Return True if this model should use OpenRouter's provider namespace."""
    return "/" in model_id


# ═══════════════════════════════════════════════════════
# Reddit
# ═══════════════════════════════════════════════════════


class RedditComment(BaseModel):
    comment_id: str
    author: str = ""
    body: str
    score: int
    is_moderator: bool = False
    created_utc: str | None = None


class RawPost(BaseModel):
    post_id: str
    subreddit: str
    title: str
    image_url: str | None = None
    permalink: str
    score: int
    created_utc: str | None = None
    retrieved_at: str
    comments: list[RedditComment] = Field(default_factory=list)


# ═══════════════════════════════════════════════════════
# Consensus / Curation
# ═══════════════════════════════════════════════════════


class ConsensusResult(BaseModel):
    has_consensus: bool
    agreeing_comment_ids: list[str] = Field(default_factory=list)
    selected_explanation: str | None = None
    confidence: float
    reasoning: str
    num_agreeing_comments: int
    avg_comment_score: float
    total_comments_analyzed: int


class CuratedMeme(BaseModel):
    meme_id: str  # display_index string
    post_id: str
    subreddit: str
    title: str
    image_url: str | None = None
    local_image_path: str | None = None
    permalink: str
    ground_truth_explanation: str
    consensus_confidence: float
    source_comment_ids: list[str] = Field(default_factory=list)
    num_agreeing_comments: int
    avg_comment_score: float
    created_utc: str | None = None
    curated_at: str


# ═══════════════════════════════════════════════════════
# Predictions
# ═══════════════════════════════════════════════════════


class ModelPrediction(BaseModel):
    post_id: str
    dataset_version: str
    model_id: str
    prediction: str
    latency_ms: int | None = None
    token_count: int | None = None
    timestamp: str
    error: str | None = None

    @classmethod
    def success(
        cls,
        post_id: str,
        dataset_version: str,
        model_id: str,
        prediction: str,
        latency_ms: int,
        token_count: int,
    ) -> ModelPrediction:
        return cls(
            post_id=post_id,
            dataset_version=dataset_version,
            model_id=model_id,
            prediction=prediction,
            latency_ms=latency_ms,
            token_count=token_count,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    @classmethod
    def failure(
        cls,
        post_id: str,
        dataset_version: str,
        model_id: str,
        error: str,
    ) -> ModelPrediction:
        return cls(
            post_id=post_id,
            dataset_version=dataset_version,
            model_id=model_id,
            prediction="",
            timestamp=datetime.now(timezone.utc).isoformat(),
            error=error,
        )

    @property
    def is_success(self) -> bool:
        return self.error is None


# ═══════════════════════════════════════════════════════
# Judgments
# ═══════════════════════════════════════════════════════


class JudgeVerdict(str, Enum):
    CORRECT = "correct"
    INCORRECT = "incorrect"

    @property
    def score(self) -> float:
        return 1.0 if self == JudgeVerdict.CORRECT else 0.0

    @classmethod
    def parse(cls, s: str) -> JudgeVerdict:
        try:
            return cls(s.lower())
        except ValueError:
            from basedbench.errors import LlmJsonParseError

            raise LlmJsonParseError(f"invalid verdict: {s}")


class ScoredPrediction(BaseModel):
    post_id: str
    model_id: str
    dataset_version: str
    prediction: str
    ground_truth: str
    verdict: JudgeVerdict
    judge_reasoning: str
    judged_at: str


class ModelMetrics(BaseModel):
    model_id: str
    total_evaluated: int
    correct: int
    incorrect: int
    accuracy: float
