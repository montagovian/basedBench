"""Safety gate — content-appropriateness pre-filter for dataset publication.

Runs before consensus. Excludes memes that would embarrass the dataset when
published (explicit sexual content, slurs, hate speech, doxxing, etc.) while
preserving mild edge, dark humor, and political satire. The prompt is explicit
about what NOT to filter so we don't lose the cultural signal.
"""

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
    SAFETY_GATE_SYSTEM_PROMPT,
    SAFETY_GATE_USER_TEMPLATE,
)
from basedbench.llm.record import LlmCallRecord
from basedbench.schemas import RawPost


class _SafetyResponse(BaseModel):
    keep: bool
    category: str = "unspecified"


@dataclass
class SafetyResult:
    keep: bool
    category: str


class SafetyGate:
    """Decides whether a meme is appropriate for inclusion in the public dataset."""

    def __init__(self, config: Config) -> None:
        self._client = AsyncOpenAI(api_key=config.openai_api_key)
        self._model = config.consensus_model
        self._min_comment_score = config.min_comment_score
        self._max_comments = config.max_comments_for_consensus
        self.prompt_id = prompts.prompt_id(
            "safety_gate", SAFETY_GATE_SYSTEM_PROMPT, SAFETY_GATE_USER_TEMPLATE
        )

    async def check(self, post: RawPost) -> tuple[SafetyResult, LlmCallRecord]:
        qualifying = sorted(
            (c for c in post.comments if c.score >= self._min_comment_score),
            key=lambda c: c.score,
            reverse=True,
        )[: self._max_comments]

        formatted = "\n".join(
            f"- ({c.score}) {c.body}" for c in qualifying
        )
        user_prompt = (
            f"Subreddit: r/{post.subreddit}\n"
            f"Title: {post.title}\n\n"
            f"Top comments ({len(qualifying)} total):\n{formatted}"
        )

        record = LlmCallRecord(
            role="safety_gate",
            post_id=post.post_id,
            model=self._model,
            system_prompt=SAFETY_GATE_SYSTEM_PROMPT,
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
                            {"role": "system", "content": SAFETY_GATE_SYSTEM_PROMPT},
                            {"role": "user", "content": user_prompt},
                        ],
                        temperature=0.0,
                        max_completion_tokens=300,
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

        try:
            parsed = _SafetyResponse.model_validate_json(text)
        except ValueError as e:
            record.error = f"safety_gate response parse: {e}"
            raise LlmJsonParseError(f"safety_gate response: {e}") from e

        record.verdict = "keep" if parsed.keep else "exclude"
        record.reasoning = parsed.category
        return SafetyResult(keep=parsed.keep, category=parsed.category), record
