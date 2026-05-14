"""LLM judge — binary verdict on whether a prediction matches the ground truth."""

from __future__ import annotations

import time
from dataclasses import dataclass

import openai
from openai import AsyncOpenAI
from pydantic import BaseModel

import basedbench
from basedbench.errors import LlmJsonParseError, OpenAIError, is_fatal_llm_error
from basedbench.llm import prompts
from basedbench.llm._retry import openai_retry
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


class LlmJudge:
    """Compares predictions against ground truth and emits a binary verdict."""

    def __init__(self, api_key: str, model: str) -> None:
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model
        self._prompt_id = prompts.prompt_id("judge", JUDGE_SYSTEM_PROMPT, JUDGE_USER_TEMPLATE)

    @property
    def prompt_id(self) -> str:
        return self._prompt_id

    async def judge(
        self, prediction: str, ground_truth: str, post_id: str
    ) -> tuple[JudgeResult, LlmCallRecord]:
        user_prompt = (
            f"Ground Truth Explanation:\n{ground_truth}\n\n"
            f"Model's Explanation:\n{prediction}"
        )

        record = LlmCallRecord(
            role="judge",
            post_id=post_id,
            model=self._model,
            system_prompt=JUDGE_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            prompt_version=self._prompt_id,
            session_id=basedbench.SESSION_ID,
            latency_ms=0,
        )

        start = time.monotonic()
        try:
            async for attempt in openai_retry():
                with attempt:
                    response = await self._client.chat.completions.create(
                        model=self._model,
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
        text = ""
        if response.choices:
            text = response.choices[0].message.content or ""
        record.response = text

        try:
            parsed = _JudgeResponse.model_validate_json(text)
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
        return JudgeResult(verdict=verdict, reasoning=parsed.reasoning), record
