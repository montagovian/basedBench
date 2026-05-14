"""Quality gate — cheap text-only pre-filter to reject non-meme posts before vision/consensus."""

from __future__ import annotations

import time
from dataclasses import dataclass

import openai
from openai import AsyncOpenAI
from pydantic import BaseModel

import basedbench
from basedbench.config import Config
from basedbench.errors import LlmJsonParseError, OpenAIError, is_fatal_llm_error
from basedbench.llm import prompts
from basedbench.llm._retry import openai_retry
from basedbench.llm.prompts import (
    QUALITY_GATE_SYSTEM_PROMPT,
    QUALITY_GATE_USER_TEMPLATE,
)
from basedbench.llm.record import LlmCallRecord
from basedbench.schemas import RawPost


class _GateResponse(BaseModel):
    reasoning: str = ""
    passes: bool


@dataclass
class GateResult:
    passes: bool
    reasoning: str


class QualityGate:
    """Decides whether a post's comments hint at testable humor."""

    def __init__(self, config: Config) -> None:
        self._client = AsyncOpenAI(api_key=config.openai_api_key)
        self._model = config.consensus_model
        self._min_comment_score = config.min_comment_score
        self._max_comments = config.max_comments_for_consensus
        self.prompt_id = prompts.prompt_id(
            "quality_gate", QUALITY_GATE_SYSTEM_PROMPT, QUALITY_GATE_USER_TEMPLATE
        )

    async def check(self, post: RawPost) -> tuple[GateResult, LlmCallRecord]:
        qualifying = sorted(
            (c for c in post.comments if c.score >= self._min_comment_score),
            key=lambda c: c.score,
            reverse=True,
        )[: self._max_comments]

        formatted = "\n".join(
            f"ID: {c.comment_id} | Score: {c.score} | Author: {c.author}\n{c.body}\n---"
            for c in qualifying
        )
        user_prompt = (
            f"Subreddit: r/{post.subreddit}\n\n"
            f"Comments ({len(qualifying)} total):\n{formatted}"
        )

        record = LlmCallRecord(
            role="quality_gate",
            post_id=post.post_id,
            model=self._model,
            system_prompt=QUALITY_GATE_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            prompt_version=self.prompt_id,
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
                            {"role": "system", "content": QUALITY_GATE_SYSTEM_PROMPT},
                            {"role": "user", "content": user_prompt},
                        ],
                        temperature=0.0,
                        max_completion_tokens=1000,
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
            parsed = _GateResponse.model_validate_json(text)
        except ValueError as e:
            record.error = f"quality_gate response parse: {e}"
            raise LlmJsonParseError(f"quality_gate response: {e}") from e

        record.verdict = "pass" if parsed.passes else "fail"
        record.reasoning = parsed.reasoning
        return GateResult(passes=parsed.passes, reasoning=parsed.reasoning), record
