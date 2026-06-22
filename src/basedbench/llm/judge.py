"""LLM judges — binary verdict on whether a prediction matches the ground truth.

Two implementations (OpenAI, Anthropic) share an interface so the pipeline can
run multiple judges per prediction to surface judge-family bias.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol

import anthropic
import openai
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI
from pydantic import BaseModel

import basedbench
from basedbench.config import Config
from basedbench.errors import (
    AnthropicError,
    LlmJsonParseError,
    OpenAIError,
    is_fatal_llm_error,
)
from basedbench.llm import prompts
from basedbench.llm._retry import anthropic_retry, openai_retry
from basedbench.llm.prompts import JUDGE_SYSTEM_PROMPT, JUDGE_USER_TEMPLATE
from basedbench.llm.record import LlmCallRecord
from basedbench.schemas import JudgeVerdict


class _JudgeResponse(BaseModel):
    reasoning: str = ""
    verdict: str


@dataclass
class JudgeResult:
    verdict: JudgeVerdict
    reasoning: str


class Judge(Protocol):
    model_id: str
    prompt_id: str

    async def judge(
        self, prediction: str, ground_truth: str, post_id: str
    ) -> tuple[JudgeResult, LlmCallRecord]: ...


def _user_prompt(prediction: str, ground_truth: str) -> str:
    return (
        f"Ground Truth Explanation:\n{ground_truth}\n\n"
        f"Model's Explanation:\n{prediction}"
    )


def _new_record(model: str, post_id: str, user_prompt: str, prompt_id: str) -> LlmCallRecord:
    return LlmCallRecord(
        role="judge",
        post_id=post_id,
        model=model,
        system_prompt=JUDGE_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        prompt_version=prompt_id,
        session_id=basedbench.SESSION_ID,
        latency_ms=0,
    )


def _normalize_json_response(text: str) -> str:
    """Accept plain JSON plus common fenced-JSON wrappers from OpenAI-compatible APIs."""
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if (
            len(lines) >= 3
            and lines[0].strip().startswith("```")
            and lines[-1].strip() == "```"
        ):
            stripped = "\n".join(lines[1:-1]).strip()
    if stripped.startswith("{"):
        return stripped
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end > start:
        return stripped[start : end + 1].strip()
    return stripped


def _parse_verdict(text: str, record: LlmCallRecord) -> JudgeResult:
    try:
        parsed = _JudgeResponse.model_validate_json(_normalize_json_response(text))
    except ValueError as e:
        record.error = f"judge response parse: {e}"
        raise LlmJsonParseError(f"judge response: {e}") from e

    try:
        verdict = JudgeVerdict.parse(parsed.verdict)
    except LlmJsonParseError as e:
        record.error = str(e)
        raise

    record.verdict = verdict.value
    record.reasoning = parsed.reasoning
    return JudgeResult(verdict=verdict, reasoning=parsed.reasoning)


class LlmJudge:
    """OpenAI-backed judge."""

    def __init__(self, api_key: str, model: str) -> None:
        self._client = AsyncOpenAI(api_key=api_key)
        self.model_id = model
        self.prompt_id = prompts.prompt_id("judge", JUDGE_SYSTEM_PROMPT, JUDGE_USER_TEMPLATE)

    async def judge(
        self, prediction: str, ground_truth: str, post_id: str
    ) -> tuple[JudgeResult, LlmCallRecord]:
        user_prompt = _user_prompt(prediction, ground_truth)
        record = _new_record(self.model_id, post_id, user_prompt, self.prompt_id)

        start = time.monotonic()
        try:
            async for attempt in openai_retry():
                with attempt:
                    response = await self._client.chat.completions.create(
                        model=self.model_id,
                        messages=[
                            {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                            {"role": "user", "content": user_prompt},
                        ],
                        temperature=0.0,
                        max_completion_tokens=2000,
                        response_format={"type": "json_object"},
                    )
        except openai.OpenAIError as e:
            record.latency_ms = int((time.monotonic() - start) * 1000)
            record.error = str(e)
            raise OpenAIError(
                str(e),
                fatal=is_fatal_llm_error(e),
                code=getattr(e, "code", None),
            ) from e

        record.latency_ms = int((time.monotonic() - start) * 1000)
        text = response.choices[0].message.content or "" if response.choices else ""
        record.response = text
        usage = getattr(response, "usage", None)
        if usage is not None:
            record.prompt_tokens = getattr(usage, "prompt_tokens", None)
            record.completion_tokens = getattr(usage, "completion_tokens", None)

        result = _parse_verdict(text, record)
        return result, record


class AnthropicJudge:
    """Anthropic-backed judge. Same interface as LlmJudge."""

    def __init__(self, api_key: str, model: str) -> None:
        self._client = AsyncAnthropic(api_key=api_key, timeout=120.0)
        self.model_id = model
        self.prompt_id = prompts.prompt_id("judge", JUDGE_SYSTEM_PROMPT, JUDGE_USER_TEMPLATE)

    async def judge(
        self, prediction: str, ground_truth: str, post_id: str
    ) -> tuple[JudgeResult, LlmCallRecord]:
        user_prompt = _user_prompt(prediction, ground_truth)
        record = _new_record(self.model_id, post_id, user_prompt, self.prompt_id)

        start = time.monotonic()
        try:
            async for attempt in anthropic_retry():
                with attempt:
                    response = await self._client.messages.create(
                        model=self.model_id,
                        max_tokens=2000,
                        system=JUDGE_SYSTEM_PROMPT,
                        messages=[{"role": "user", "content": user_prompt}],
                    )
        except anthropic.AnthropicError as e:
            record.latency_ms = int((time.monotonic() - start) * 1000)
            record.error = str(e)
            raise AnthropicError(
                str(e),
                fatal=is_fatal_llm_error(e),
                code=getattr(e, "code", None),
            ) from e

        record.latency_ms = int((time.monotonic() - start) * 1000)
        text = ""
        for block in response.content:
            if getattr(block, "type", None) == "text":
                text = block.text
                break
        record.response = text
        usage = response.usage
        if usage is not None:
            record.prompt_tokens = usage.input_tokens
            record.completion_tokens = usage.output_tokens

        result = _parse_verdict(text, record)
        return result, record


class OpenRouterJudge:
    """OpenRouter-backed judge using OpenRouter's OpenAI-compatible API."""

    def __init__(self, api_key: str, model: str) -> None:
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
            default_headers={
                "HTTP-Referer": "https://github.com/basedbench/basedbench",
                "X-Title": "basedBench",
            },
        )
        self.model_id = model
        self.prompt_id = prompts.prompt_id("judge", JUDGE_SYSTEM_PROMPT, JUDGE_USER_TEMPLATE)

    async def judge(
        self, prediction: str, ground_truth: str, post_id: str
    ) -> tuple[JudgeResult, LlmCallRecord]:
        user_prompt = _user_prompt(prediction, ground_truth)
        record = _new_record(self.model_id, post_id, user_prompt, self.prompt_id)

        start = time.monotonic()
        try:
            async for attempt in openai_retry():
                with attempt:
                    response = await self._client.chat.completions.create(
                        model=self.model_id,
                        messages=[
                            {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                            {"role": "user", "content": user_prompt},
                        ],
                        temperature=0.0,
                        max_tokens=2000,
                        response_format={"type": "json_object"},
                    )
        except openai.OpenAIError as e:
            record.latency_ms = int((time.monotonic() - start) * 1000)
            record.error = str(e)
            raise OpenAIError(
                str(e),
                fatal=is_fatal_llm_error(e),
                code=getattr(e, "code", None),
            ) from e

        record.latency_ms = int((time.monotonic() - start) * 1000)
        text = response.choices[0].message.content or "" if response.choices else ""
        record.response = text
        usage = getattr(response, "usage", None)
        if usage is not None:
            record.prompt_tokens = getattr(usage, "prompt_tokens", None)
            record.completion_tokens = getattr(usage, "completion_tokens", None)

        result = _parse_verdict(text, record)
        return result, record


def make_judge(model_id: str, config: Config) -> Judge:
    """Route model_id to the correct provider implementation."""
    if model_id.startswith("gpt-") or model_id.startswith("o"):
        return LlmJudge(config.openai_api_key, model_id)
    if model_id.startswith("claude-"):
        if not config.anthropic_api_key:
            raise ValueError(
                f"ANTHROPIC_API_KEY required for judge model {model_id!r}"
            )
        return AnthropicJudge(config.anthropic_api_key, model_id)
    if "/" in model_id:
        if not config.openrouter_api_key:
            raise ValueError(
                f"OPENROUTER_API_KEY required for judge model {model_id!r}"
            )
        return OpenRouterJudge(config.openrouter_api_key, model_id)
    raise ValueError(f"Unknown judge model provider: {model_id!r}")
