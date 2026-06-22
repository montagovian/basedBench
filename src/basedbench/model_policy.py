"""Model visibility policy for public summaries."""

from __future__ import annotations


_RETIRED_SUMMARY_MODELS = {
    "claude-opus-4-7",
}


def is_active_summary_model(model_id: str) -> bool:
    """Return True if model should appear in active status/leaderboard summaries."""
    return model_id not in _RETIRED_SUMMARY_MODELS
