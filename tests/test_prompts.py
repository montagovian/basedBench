"""Tests for llm/prompts.py."""

from basedbench.llm.prompts import (
    CONSENSUS_SYSTEM_PROMPT,
    EXPLAIN_MEME_PROMPT,
    JUDGE_SYSTEM_PROMPT,
    VAGUE_PHRASES,
    prompt_id,
)


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


def test_consensus_rejects_pure_scrambled_nonsense():
    prompt = CONSENSUS_SYSTEM_PROMPT.lower()
    assert "scrambled" in prompt
    assert "nonsense" in prompt
    assert "no specific scenario" in prompt


def test_predictor_prompt_targets_getting_the_joke_not_humor_theory():
    prompt = EXPLAIN_MEME_PROMPT.lower()
    assert "what the joke is" in prompt
    assert "getting the joke" in prompt
    assert "why it's funny" not in prompt


def test_consensus_prompt_targets_joke_interpretation_not_humor_theory():
    prompt = CONSENSUS_SYSTEM_PROMPT.lower()
    assert "what joke the meme is making" in prompt
    assert "what a viewer must understand to get the joke" in prompt
    assert "psychological theory" in prompt
    assert "why it is funny" not in prompt
    assert "why the meme is funny" not in prompt


def test_judge_prompt_targets_getting_same_joke_not_humor_theory():
    prompt = JUDGE_SYSTEM_PROMPT.lower()
    assert "gets the joke" in prompt
    assert "what is funny, ironic, contrastive" in prompt
    assert "do not require the model to explain the psychology of amusement" in prompt
    assert "demonstrates understanding of why" not in prompt
    assert "why it's funny" not in prompt
