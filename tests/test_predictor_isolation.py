"""Regression tests: predictors must NOT pass tools (incl. web_search) to the API.

The benchmark is only meaningful if the model sees only the meme image + a
generic prompt. If the API call ever gains a `tools` parameter (web_search,
function_call, code_interpreter, etc.) the model could look up the joke
externally and the eval collapses. These tests assert that doesn't happen.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from basedbench.llm.anthropic import AnthropicPredictor
from basedbench.llm.openai import OpenAIPredictor
from basedbench.llm.openrouter import OpenRouterPredictor
from basedbench.schemas import CuratedMeme


# Any of these kwargs being present on a predict API call would mean the
# model has external-world reach beyond the image and static prompt.
FORBIDDEN_KWARGS = {
    "tools",
    "tool_choice",
    "functions",
    "function_call",
    "web_search",
    "web_search_options",
}


def _make_meme(image_path: Path) -> CuratedMeme:
    # Write a minimal-but-valid 1×1 PNG so load_image_base64 succeeds.
    png_bytes = bytes.fromhex(
        "89504E470D0A1A0A0000000D49484452000000010000000108060000001F15C4"
        "890000000D49444154789C636060606000000005000158CCD9410000000049"
        "454E44AE426082"
    )
    image_path.write_bytes(png_bytes)
    return CuratedMeme(
        meme_id="1",
        post_id="p1",
        subreddit="memes",
        title="t",
        image_url="https://i.redd.it/p1.png",
        local_image_path=str(image_path),
        permalink="/r/memes/p1",
        ground_truth_explanation="—",
        consensus_confidence=1.0,
        num_agreeing_comments=3,
        avg_comment_score=10.0,
        curated_at="2026-01-01T00:00:00+00:00",
    )


@pytest.mark.asyncio
async def test_openai_predictor_passes_no_tools(tmp_path: Path):
    predictor = OpenAIPredictor(api_key="sk-x", model="gpt-5.5")
    fake_response = SimpleNamespace(
        choices=[
            SimpleNamespace(message=SimpleNamespace(content="ok"))
        ],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
    )
    predictor._client.chat.completions.create = AsyncMock(  # type: ignore[attr-defined]
        return_value=fake_response
    )

    meme = _make_meme(tmp_path / "p1.png")
    await predictor.predict(meme, dataset_version="v1")

    call_kwargs = predictor._client.chat.completions.create.call_args.kwargs  # type: ignore[attr-defined]
    leaked = FORBIDDEN_KWARGS & set(call_kwargs.keys())
    assert not leaked, (
        f"OpenAI predictor passed forbidden kwargs {leaked}; "
        "this would let the model use external tools (web search etc.) "
        "and invalidate the benchmark."
    )


@pytest.mark.asyncio
async def test_anthropic_predictor_passes_no_tools(tmp_path: Path):
    predictor = AnthropicPredictor(api_key="sk-x", model="claude-opus-4-7")
    fake_response = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="ok")],
        usage=SimpleNamespace(input_tokens=10, output_tokens=5),
    )
    predictor._client.messages.create = AsyncMock(  # type: ignore[attr-defined]
        return_value=fake_response
    )

    meme = _make_meme(tmp_path / "p1.png")
    await predictor.predict(meme, dataset_version="v1")

    call_kwargs = predictor._client.messages.create.call_args.kwargs  # type: ignore[attr-defined]
    leaked = FORBIDDEN_KWARGS & set(call_kwargs.keys())
    assert not leaked, (
        f"Anthropic predictor passed forbidden kwargs {leaked}; "
        "this would let the model use external tools (web search etc.) "
        "and invalidate the benchmark."
    )


@pytest.mark.asyncio
async def test_openrouter_predictor_passes_no_tools(tmp_path: Path):
    predictor = OpenRouterPredictor(api_key="or-x", model="x-ai/grok-4.3")
    fake_response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
    )
    predictor._client.chat.completions.create = AsyncMock(  # type: ignore[attr-defined]
        return_value=fake_response
    )

    meme = _make_meme(tmp_path / "p1.png")
    await predictor.predict(meme, dataset_version="v1")

    call_kwargs = predictor._client.chat.completions.create.call_args.kwargs  # type: ignore[attr-defined]
    leaked = FORBIDDEN_KWARGS & set(call_kwargs.keys())
    assert not leaked, (
        f"OpenRouter predictor passed forbidden kwargs {leaked}; "
        "this would let the model use external tools (web search etc.) "
        "and invalidate the benchmark."
    )


@pytest.mark.asyncio
async def test_predictors_only_send_image_and_static_prompt(tmp_path: Path):
    """The user-side message content should be exactly the static prompt + image —
    no title, no comments, no permalink, no ground truth."""
    predictor = OpenAIPredictor(api_key="sk-x", model="gpt-5.5")
    fake_response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
    )
    predictor._client.chat.completions.create = AsyncMock(  # type: ignore[attr-defined]
        return_value=fake_response
    )

    meme = _make_meme(tmp_path / "p1.png")
    # Make the meme's metadata distinctive so we can assert nothing leaks.
    meme.title = "DISTINCTIVE-TITLE-THAT-SHOULD-NOT-APPEAR"
    meme.ground_truth_explanation = "GROUND-TRUTH-SHOULD-NOT-APPEAR"
    meme.permalink = "/r/memes/PERMALINK-SHOULD-NOT-APPEAR"

    await predictor.predict(meme, dataset_version="v1")

    call_kwargs = predictor._client.chat.completions.create.call_args.kwargs  # type: ignore[attr-defined]
    # Recursively stringify the full call to check no leak.
    blob = repr(call_kwargs)
    for forbidden in ("DISTINCTIVE-TITLE", "GROUND-TRUTH-SHOULD", "PERMALINK-SHOULD"):
        assert forbidden not in blob, (
            f"Found '{forbidden}' in OpenAI predict kwargs — meme metadata "
            "is leaking into the predict call"
        )


@pytest.mark.asyncio
async def test_openrouter_predictor_only_sends_image_and_static_prompt(tmp_path: Path):
    predictor = OpenRouterPredictor(api_key="or-x", model="x-ai/grok-4.3")
    fake_response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
    )
    predictor._client.chat.completions.create = AsyncMock(  # type: ignore[attr-defined]
        return_value=fake_response
    )

    meme = _make_meme(tmp_path / "p1.png")
    meme.title = "DISTINCTIVE-TITLE-THAT-SHOULD-NOT-APPEAR"
    meme.ground_truth_explanation = "GROUND-TRUTH-SHOULD-NOT-APPEAR"
    meme.permalink = "/r/memes/PERMALINK-SHOULD-NOT-APPEAR"

    await predictor.predict(meme, dataset_version="v1")

    call_kwargs = predictor._client.chat.completions.create.call_args.kwargs  # type: ignore[attr-defined]
    blob = repr(call_kwargs)
    for forbidden in ("DISTINCTIVE-TITLE", "GROUND-TRUTH-SHOULD", "PERMALINK-SHOULD"):
        assert forbidden not in blob, (
            f"Found '{forbidden}' in OpenRouter predict kwargs — meme metadata "
            "is leaking into the predict call"
        )
