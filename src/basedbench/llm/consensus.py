"""Consensus detection — decide whether a post's comments agree on a meme's meaning."""

from __future__ import annotations

import json
import time

import openai
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

import basedbench
from basedbench.config import Config
from basedbench.errors import OpenAIError, is_fatal_llm_error
from basedbench.llm import prompts
from basedbench.llm._retry import openai_retry
from basedbench.llm.prompts import (
    CONSENSUS_SYSTEM_PROMPT,
    CONSENSUS_USER_TEMPLATE,
    VAGUE_PHRASES,
)
from basedbench.llm.record import LlmCallRecord
from basedbench.schemas import ConsensusResult, RawPost

MIN_CONFIDENCE = 0.6
MIN_EXPLANATION_LEN = 100


class _ConsensusResponse(BaseModel):
    """LLM's JSON response shape."""

    reasoning: str = ""
    has_consensus: bool = False
    agreeing_comment_ids: list[str] = Field(default_factory=list)
    selected_explanation: str | None = None
    confidence: float = 0.0


class ConsensusDetector:
    """Detects consensus among a post's comments using gpt-4o-mini (or configured model)."""

    def __init__(self, config: Config) -> None:
        self._client = AsyncOpenAI(api_key=config.openai_api_key)
        self._model = config.consensus_model
        self._min_agreeing = config.min_agreeing_comments
        self._min_avg_score = config.min_avg_comment_score
        self._min_comment_score = config.min_comment_score
        self._max_comments = config.max_comments_for_consensus
        self.prompt_id = prompts.prompt_id(
            "consensus", CONSENSUS_SYSTEM_PROMPT, CONSENSUS_USER_TEMPLATE
        )

    async def detect_consensus(
        self, post: RawPost
    ) -> tuple[ConsensusResult, LlmCallRecord | None]:
        """Run the 10-stage consensus check.

        Returns (result, record). `record` is None when no LLM call was made
        (e.g., fewer than 3 qualifying comments).
        """
        qualifying = sorted(
            (c for c in post.comments if c.score >= self._min_comment_score),
            key=lambda c: c.score,
            reverse=True,
        )[: self._max_comments]
        total_analyzed = len(qualifying)

        # Stage 1: enough comments to bother asking?
        if len(qualifying) < 3:
            return (
                ConsensusResult(
                    has_consensus=False,
                    confidence=0.0,
                    reasoning=f"Only {len(qualifying)} qualifying comments (need at least 3)",
                    num_agreeing_comments=0,
                    avg_comment_score=0.0,
                    total_comments_analyzed=total_analyzed,
                ),
                None,
            )

        formatted = "\n".join(
            f"ID: {c.comment_id} | Score: {c.score} | Author: {c.author}\n{c.body}\n---"
            for c in qualifying
        )
        user_prompt = (
            f"Subreddit: r/{post.subreddit}\n\n"
            f"Comments ({len(qualifying)} total):\n{formatted}"
        )

        record = LlmCallRecord(
            role="consensus",
            post_id=post.post_id,
            model=self._model,
            system_prompt=CONSENSUS_SYSTEM_PROMPT,
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
                            {"role": "system", "content": CONSENSUS_SYSTEM_PROMPT},
                            {"role": "user", "content": user_prompt},
                        ],
                        temperature=0.0,
                        max_completion_tokens=2000,
                        response_format={"type": "json_object"},
                    )
        except openai.OpenAIError as e:
            record.latency_ms = int((time.monotonic() - start) * 1000)
            record.error = str(e)
            if is_fatal_llm_error(e):
                raise OpenAIError(
                    str(e), fatal=True, code=getattr(e, "code", None)
                ) from e
            # Transient error after retries — treat this post as no_consensus,
            # let the orchestrator keep going.
            return (
                ConsensusResult(
                    has_consensus=False,
                    confidence=0.0,
                    reasoning=f"OpenAI error: {e}",
                    num_agreeing_comments=0,
                    avg_comment_score=0.0,
                    total_comments_analyzed=total_analyzed,
                ),
                record,
            )

        record.latency_ms = int((time.monotonic() - start) * 1000)
        text = ""
        if response.choices:
            text = response.choices[0].message.content or ""
        record.response = text

        try:
            parsed = _ConsensusResponse.model_validate_json(text)
        except (ValueError, json.JSONDecodeError) as e:
            record.error = f"consensus response parse: {e}"
            return (
                ConsensusResult(
                    has_consensus=False,
                    confidence=0.0,
                    reasoning=f"JSON parse error: {e}",
                    num_agreeing_comments=0,
                    avg_comment_score=0.0,
                    total_comments_analyzed=total_analyzed,
                ),
                record,
            )

        # Stage 2: LLM said no
        if not parsed.has_consensus:
            return self._reject(
                record,
                parsed.reasoning,
                parsed,
                num_agreeing=0,
                avg_score=0.0,
                total_analyzed=total_analyzed,
            )

        # Stage 3: low confidence
        if parsed.confidence < MIN_CONFIDENCE:
            reasoning = (
                f"Confidence too low ({parsed.confidence:.2f} < {MIN_CONFIDENCE}): "
                f"{parsed.reasoning}"
            )
            return self._reject(record, reasoning, parsed, 0, 0.0, total_analyzed)

        # Stage 4: empty explanation
        explanation = (parsed.selected_explanation or "").strip()
        if not explanation:
            parsed.selected_explanation = None
            return self._reject(
                record, "No explanation provided", parsed, 0, 0.0, total_analyzed
            )

        # Stage 5: explanation too short
        if len(explanation) < MIN_EXPLANATION_LEN:
            parsed.selected_explanation = explanation
            return self._reject(
                record,
                f"Explanation too short (< {MIN_EXPLANATION_LEN} chars)",
                parsed,
                0,
                0.0,
                total_analyzed,
            )

        # Stage 6: vague phrases
        lower = explanation.lower()
        vague = next((p for p in VAGUE_PHRASES if p in lower), None)
        if vague:
            parsed.selected_explanation = explanation
            return self._reject(
                record,
                f'Explanation contains vague phrase: "{vague}"',
                parsed,
                0,
                0.0,
                total_analyzed,
            )

        # Stage 7: compute avg score of agreeing comments
        score_by_id = {c.comment_id: c.score for c in post.comments}
        agreeing_scores = [
            score_by_id[i] for i in parsed.agreeing_comment_ids if i in score_by_id
        ]
        avg_score = (
            sum(agreeing_scores) / len(agreeing_scores) if agreeing_scores else 0.0
        )

        # Stage 8: avg score too low
        if avg_score < self._min_avg_score:
            parsed.selected_explanation = explanation
            return self._reject(
                record,
                f"Average comment score too low ({avg_score:.1f} < {self._min_avg_score})",
                parsed,
                0,
                avg_score,
                total_analyzed,
            )

        # Stage 9: not enough comments agreed
        num_agreeing = len(parsed.agreeing_comment_ids)
        if num_agreeing < self._min_agreeing:
            parsed.selected_explanation = explanation
            return self._reject(
                record,
                f"Not enough agreeing comments ({num_agreeing} < {self._min_agreeing})",
                parsed,
                num_agreeing,
                avg_score,
                total_analyzed,
            )

        # Stage 10: success
        record.verdict = "consensus"
        record.reasoning = parsed.reasoning
        return (
            ConsensusResult(
                has_consensus=True,
                agreeing_comment_ids=parsed.agreeing_comment_ids,
                selected_explanation=explanation,
                confidence=parsed.confidence,
                reasoning=parsed.reasoning,
                num_agreeing_comments=num_agreeing,
                avg_comment_score=avg_score,
                total_comments_analyzed=total_analyzed,
            ),
            record,
        )

    @staticmethod
    def _reject(
        record: LlmCallRecord,
        reasoning: str,
        parsed: _ConsensusResponse,
        num_agreeing: int,
        avg_score: float,
        total_analyzed: int,
    ) -> tuple[ConsensusResult, LlmCallRecord]:
        record.verdict = "no_consensus"
        record.reasoning = reasoning
        return (
            ConsensusResult(
                has_consensus=False,
                agreeing_comment_ids=parsed.agreeing_comment_ids,
                selected_explanation=parsed.selected_explanation,
                confidence=parsed.confidence,
                reasoning=reasoning,
                num_agreeing_comments=num_agreeing,
                avg_comment_score=avg_score,
                total_comments_analyzed=total_analyzed,
            ),
            record,
        )
