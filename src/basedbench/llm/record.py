"""LLM call record for tracing/logging."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class LlmCallRecord:
    role: str
    post_id: str
    model: str
    system_prompt: str
    user_prompt: str
    prompt_version: str
    session_id: str
    latency_ms: int
    response: str | None = None
    error: str | None = None
    verdict: str | None = None
    reasoning: str | None = None
    image_path: str | None = None
    completion_tokens: int | None = None
    prompt_tokens: int | None = None
