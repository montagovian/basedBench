"""Tests for llm/prompts.py — mirrors v4 prompt tests."""

from basedbench.llm.prompts import VAGUE_PHRASES, prompt_id


def test_prompt_id_deterministic():
    id1 = prompt_id("consensus", "system prompt", "user template")
    id2 = prompt_id("consensus", "system prompt", "user template")
    assert id1 == id2
    assert len(id1) == 16


def test_prompt_id_different_for_different_inputs():
    id1 = prompt_id("consensus", "system A", "user A")
    id2 = prompt_id("consensus", "system B", "user B")
    assert id1 != id2


def test_vague_phrase_detection():
    explanation = "This is absurd humor that everyone can relate to"
    lower = explanation.lower()
    has_vague = any(phrase in lower for phrase in VAGUE_PHRASES)
    assert has_vague


def test_no_vague_phrases():
    explanation = (
        "This meme references the SpongeBob SquarePants episode "
        "where he burns Krabby Patties"
    )
    lower = explanation.lower()
    has_vague = any(phrase in lower for phrase in VAGUE_PHRASES)
    assert not has_vague
