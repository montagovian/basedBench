"""OpenRouter VLM predictor using OpenRouter's OpenAI-compatible API."""

from __future__ import annotations

import time
from pathlib import Path

import openai
from openai import AsyncOpenAI

import basedbench
from basedbench.errors import ImageNotFoundError, OpenAIError, is_fatal_llm_error
from basedbench.llm import prompts
from basedbench.llm._retry import openai_retry
from basedbench.llm.openai import (
    PREDICTION_MAX_COMPLETION_TOKENS,
    USER_PROMPT,
    _finish_reason,
    _prediction_output_error,
)
from basedbench.llm.prompts import EXPLAIN_MEME_PROMPT
from basedbench.llm.record import LlmCallRecord
from basedbench.schemas import CuratedMeme, ModelPrediction


class OpenRouterPredictor:
    """Generates meme explanations using an OpenRouter-hosted vision model."""

    def __init__(self, api_key: str, model: str) -> None:
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
            default_headers={
                "HTTP-Referer": "https://github.com/basedbench/basedbench",
                "X-Title": "basedBench",
            },
        )
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
        b64, mime = prompts.load_image_base64_for_openrouter(image_path)
        data_url = f"data:{mime};base64,{b64}"

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
            async for attempt in openai_retry():
                with attempt:
                    response = await self._client.chat.completions.create(
                        model=self._model,
                        messages=[
                            {"role": "system", "content": EXPLAIN_MEME_PROMPT},
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": USER_PROMPT},
                                    {
                                        "type": "image_url",
                                        "image_url": {"url": data_url, "detail": "auto"},
                                    },
                                ],
                            },
                        ],
                        max_tokens=PREDICTION_MAX_COMPLETION_TOKENS,
                    )
        except openai.OpenAIError as e:
            record.latency_ms = int((time.monotonic() - start) * 1000)
            record.error = str(e)
            if is_fatal_llm_error(e):
                raise OpenAIError(
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
        if response.choices:
            text = response.choices[0].message.content or ""
        finish_reason = _finish_reason(response)
        usage = response.usage
        completion_tokens = usage.completion_tokens if usage else 0
        prompt_tokens = usage.prompt_tokens if usage else 0

        record.latency_ms = latency_ms
        record.response = text
        record.completion_tokens = completion_tokens
        record.prompt_tokens = prompt_tokens

        output_error = _prediction_output_error(
            provider="OpenRouter",
            finish_reason=finish_reason,
            max_tokens=PREDICTION_MAX_COMPLETION_TOKENS,
        )
        if output_error is None and not text.strip():
            output_error = "OpenRouter prediction response contained no extracted text."
        if output_error is not None:
            record.error = output_error
            return (
                ModelPrediction.failure(
                    post_id=meme.post_id,
                    dataset_version=dataset_version,
                    model_id=self._model,
                    error=output_error,
                ),
                record,
            )

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
