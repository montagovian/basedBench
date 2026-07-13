"""Meta Model API VLM predictor using the direct HTTP API."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

import basedbench
from basedbench.errors import ImageNotFoundError, MetaError
from basedbench.llm import prompts
from basedbench.llm.openai import (
    PREDICTION_MAX_COMPLETION_TOKENS,
    USER_PROMPT,
    _prediction_output_error,
)
from basedbench.llm.prompts import EXPLAIN_MEME_PROMPT
from basedbench.llm.record import LlmCallRecord
from basedbench.schemas import CuratedMeme, ModelPrediction

DEFAULT_MODEL = "muse-spark-1.1"
_TRANSIENT_STATUSES = {408, 409, 429, 500, 502, 503, 504}
_META_TRUNCATION_REASONS = {"length", "max_tokens", "max_output_tokens"}


def canonical_meta_model_id(model: str) -> str:
    normalized = model.strip().lower()
    if normalized == "muse spark 1.1":
        return DEFAULT_MODEL
    return model.strip()


def _meta_retry() -> AsyncRetrying:
    return AsyncRetrying(
        retry=retry_if_exception(_is_retryable_meta_error),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=60),
        reraise=True,
    )


def _is_retryable_meta_error(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in _TRANSIENT_STATUSES
    if isinstance(exc, httpx.TimeoutException | httpx.NetworkError | json.JSONDecodeError):
        return True
    return False


def _join_url(base_url: str, endpoint: str) -> str:
    return f"{base_url.rstrip('/')}/{endpoint.strip('/')}"


def _error_message(response: httpx.Response) -> str:
    body = response.text.strip()
    if len(body) > 500:
        body = f"{body[:500]}..."
    return f"Meta API error {response.status_code}: {body or response.reason_phrase}"


def _error_code(response: httpx.Response) -> str | None:
    try:
        body = response.json()
    except ValueError:
        return None
    if not isinstance(body, dict):
        return None
    error = body.get("error")
    if isinstance(error, dict):
        code = error.get("code") or error.get("type")
        return str(code) if code is not None else None
    return None


def _is_fatal_response(response: httpx.Response) -> bool:
    return response.status_code in {401, 402, 403, 404, 405}


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(part for part in parts if part)
    return ""


def _extract_text(data: dict[str, Any]) -> str:
    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        choice = choices[0]
        if isinstance(choice, dict):
            message = choice.get("message")
            if isinstance(message, dict):
                text = _content_to_text(message.get("content"))
                if text:
                    return text
            text = _content_to_text(choice.get("text"))
            if text:
                return text

    output_text = data.get("output_text")
    if isinstance(output_text, str):
        return output_text

    output = data.get("output")
    if isinstance(output, list):
        parts: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            text = _content_to_text(content)
            if text:
                parts.append(text)
        if parts:
            return "\n".join(parts)

    return _content_to_text(data.get("content"))


def _finish_reason_value(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("type", "reason", "finish_reason", "stop_reason"):
            reason = value.get(key)
            if isinstance(reason, str):
                return reason
    return None


def _finish_reason(data: dict[str, Any]) -> str | None:
    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        choice = choices[0]
        if isinstance(choice, dict):
            for key in ("finish_reason", "stop_reason", "finish_details"):
                reason = _finish_reason_value(choice.get(key))
                if reason is not None:
                    return reason
    for key in ("finish_reason", "stop_reason", "finish_details"):
        reason = _finish_reason_value(data.get(key))
        if reason is not None:
            return reason
    return None


def _usage_tokens(data: dict[str, Any]) -> tuple[int, int]:
    usage = data.get("usage")
    if not isinstance(usage, dict):
        return 0, 0
    prompt_tokens = usage.get("prompt_tokens", usage.get("input_tokens", 0))
    completion_tokens = usage.get("completion_tokens", usage.get("output_tokens", 0))
    return int(prompt_tokens or 0), int(completion_tokens or 0)


class MetaPredictor:
    """Generates meme explanations using Meta's direct Model API."""

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        base_url: str,
        endpoint: str,
    ) -> None:
        self._api_key = api_key
        self._model = canonical_meta_model_id(model)
        self._url = _join_url(base_url, endpoint)
        self._client = httpx.AsyncClient(timeout=120.0)
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

        payload = {
            "model": self._model,
            "messages": [
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
            "max_tokens": PREDICTION_MAX_COMPLETION_TOKENS,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "User-Agent": "basedBench/5.0.0",
        }

        start = time.monotonic()
        try:
            async for attempt in _meta_retry():
                with attempt:
                    response = await self._client.post(
                        self._url,
                        headers=headers,
                        json=payload,
                    )
                    response.raise_for_status()
                    data = response.json()
        except httpx.HTTPStatusError as e:
            record.latency_ms = int((time.monotonic() - start) * 1000)
            record.error = _error_message(e.response)
            if _is_fatal_response(e.response):
                raise MetaError(
                    record.error,
                    fatal=True,
                    code=_error_code(e.response),
                    status_code=e.response.status_code,
                ) from e
            return (
                ModelPrediction.failure(
                    post_id=meme.post_id,
                    dataset_version=dataset_version,
                    model_id=self._model,
                    error=record.error,
                ),
                record,
            )
        except (httpx.HTTPError, json.JSONDecodeError) as e:
            record.latency_ms = int((time.monotonic() - start) * 1000)
            record.error = str(e)
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
        text = _extract_text(data)
        finish_reason = _finish_reason(data)
        prompt_tokens, completion_tokens = _usage_tokens(data)

        record.latency_ms = latency_ms
        record.response = text
        record.prompt_tokens = prompt_tokens
        record.completion_tokens = completion_tokens

        output_error = _prediction_output_error(
            provider="Meta",
            finish_reason=(
                "length" if finish_reason in _META_TRUNCATION_REASONS else finish_reason
            ),
            max_tokens=PREDICTION_MAX_COMPLETION_TOKENS,
        )
        if output_error is None and not text.strip():
            output_error = "Meta prediction response contained no extracted text."
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
