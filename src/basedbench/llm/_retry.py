"""Shared tenacity retry config for LLM providers.

Skips retries on fatal errors (auth, quota, billing) so we don't waste 3 attempts
on something that will never recover. Transient errors (rate limits, timeouts,
5xx) still get exponential backoff.
"""

from __future__ import annotations

import anthropic
import openai
from tenacity import (
    AsyncRetrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from basedbench.errors import is_fatal_llm_error

# All transient exception types we'll retry on if not fatal.
OPENAI_RETRY_TYPES: tuple[type[BaseException], ...] = (
    openai.RateLimitError,
    openai.APIConnectionError,
    openai.APITimeoutError,
    openai.InternalServerError,
)

ANTHROPIC_RETRY_TYPES: tuple[type[BaseException], ...] = (
    anthropic.RateLimitError,
    anthropic.APIConnectionError,
    anthropic.APITimeoutError,
    anthropic.InternalServerError,
)


def _make_predicate(retry_types: tuple[type[BaseException], ...]):
    def predicate(exc: BaseException) -> bool:
        if is_fatal_llm_error(exc):
            return False
        return isinstance(exc, retry_types)

    return predicate


def openai_retry() -> AsyncRetrying:
    return AsyncRetrying(
        retry=retry_if_exception(_make_predicate(OPENAI_RETRY_TYPES)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=60),
        reraise=True,
    )


def anthropic_retry() -> AsyncRetrying:
    return AsyncRetrying(
        retry=retry_if_exception(_make_predicate(ANTHROPIC_RETRY_TYPES)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=60),
        reraise=True,
    )
