"""Anthropic VLM predictor — Claude vision via the official SDK."""

from __future__ import annotations

import time
from pathlib import Path

import anthropic
from anthropic import AsyncAnthropic

import basedbench
from basedbench.errors import AnthropicError, ImageNotFoundError, is_fatal_llm_error
from basedbench.llm import prompts
from basedbench.llm._retry import anthropic_retry
from basedbench.llm.prompts import EXPLAIN_MEME_PROMPT
from basedbench.llm.record import LlmCallRecord
from basedbench.schemas import CuratedMeme, ModelPrediction

USER_PROMPT = "Please explain this meme."
# Anthropic enforces the 10 MB limit against the base64 payload, not just the
# raw image file. Keep raw bytes below the post-encoding expansion threshold.
ANTHROPIC_MAX_IMAGE_BYTES = 7 * 1024 * 1024


class AnthropicPredictor:
    """Generates meme explanations using a Claude vision model."""

    def __init__(self, api_key: str, model: str) -> None:
        self._client = AsyncAnthropic(api_key=api_key, timeout=120.0)
        self._model = model
        self.prompt_id = prompts.prompt_id("prediction", EXPLAIN_MEME_PROMPT, USER_PROMPT)

    @property
    def model_id(self) -> str:
        return self._model

    async def predict(
        self,
        meme: CuratedMeme,
        dataset_version: str,
    ) -> tuple[ModelPrediction, LlmCallRecord | None]:
        if not meme.local_image_path:
            raise ImageNotFoundError(meme.post_id)
        image_path = Path(meme.local_image_path)
        b64, mime = prompts.load_image_base64_under_limit(
            image_path,
            ANTHROPIC_MAX_IMAGE_BYTES,
        )

        record = LlmCallRecord(
            role="prediction",
            post_id=meme.post_id,
            model=self._model,
            system_prompt=EXPLAIN_MEME_PROMPT,
            user_prompt=USER_PROMPT,
            prompt_version=self.prompt_id,
            session_id=basedbench.SESSION_ID,
            latency_ms=0,
            image_path=str(image_path),
        )

        start = time.monotonic()
        try:
            async for attempt in anthropic_retry():
                with attempt:
                    response = await self._client.messages.create(
                        model=self._model,
                        # Bumped from 4000 → 16000: thinking tokens count
                        # against max_tokens, so reserve room for adaptive
                        # thinking to operate before the visible response.
                        max_tokens=16000,
                        system=EXPLAIN_MEME_PROMPT,
                        # Adaptive thinking at medium effort matches gpt-5.5's
                        # default medium reasoning_effort for a fair eval.
                        # On claude-opus-4-7 this is the only supported
                        # thinking mode (manual budget_tokens returns 400).
                        thinking={"type": "adaptive"},
                        output_config={"effort": "medium"},
                        messages=[
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "image",
                                        "source": {
                                            "type": "base64",
                                            "media_type": mime,
                                            "data": b64,
                                        },
                                    },
                                    {"type": "text", "text": USER_PROMPT},
                                ],
                            }
                        ],
                    )
        except anthropic.AnthropicError as e:
            record.latency_ms = int((time.monotonic() - start) * 1000)
            record.error = str(e)
            if is_fatal_llm_error(e):
                raise AnthropicError(
                    str(e), fatal=True, code=getattr(e, "code", None)
                ) from e
            return (
                ModelPrediction.failure(
                    post_id=meme.post_id,
                    dataset_version=dataset_version,
                    model_id=self._model,
                    error=str(e),
                ),
                record,
            )

        latency_ms = int((time.monotonic() - start) * 1000)
        text = ""
        for block in response.content:
            if getattr(block, "type", None) == "text":
                text = block.text
                break
        usage = response.usage
        completion_tokens = usage.output_tokens if usage else 0
        prompt_tokens = usage.input_tokens if usage else 0

        record.latency_ms = latency_ms
        record.response = text
        record.completion_tokens = completion_tokens
        record.prompt_tokens = prompt_tokens

        return (
            ModelPrediction.success(
                post_id=meme.post_id,
                dataset_version=dataset_version,
                model_id=self._model,
                prediction=text,
                latency_ms=latency_ms,
                token_count=completion_tokens,
            ),
            record,
        )
