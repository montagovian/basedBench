"""Predictor protocol — uniform interface across LLM providers."""

from __future__ import annotations

from typing import Protocol

from basedbench.llm.record import LlmCallRecord
from basedbench.schemas import CuratedMeme, ModelPrediction


class Predictor(Protocol):
    """A VLM that generates a meme explanation."""

    prompt_id: str

    @property
    def model_id(self) -> str: ...

    async def predict(
        self,
        meme: CuratedMeme,
        dataset_version: str,
    ) -> tuple[ModelPrediction, LlmCallRecord | None]:
        """Generate a prediction for the given meme.

        Returns the prediction (with .error set on API failure) and an optional
        LlmCallRecord. The record is None only when no LLM call was attempted
        (e.g., the image file was missing).
        """
        ...
