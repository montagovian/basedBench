"""Prompt constants and utilities for LLM interactions.

All prompt text is copied verbatim from v4 to ensure identical behavior.
"""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path

# ═══════════════════════════════════════════════════════
# Prediction prompt — sent to VLMs when explaining memes
# ═══════════════════════════════════════════════════════

EXPLAIN_MEME_PROMPT = """\
You are an expert at understanding and explaining internet memes.

When shown a meme image, provide a clear explanation that:
1. Identifies any references (cultural, media, internet, etc.)
2. Explains why it's funny or what the joke is
3. Notes any visual elements that are important to the humor

Be direct and informative. If you genuinely don't understand the meme, say so honestly."""

# ═══════════════════════════════════════════════════════
# Consensus detection prompt
# ═══════════════════════════════════════════════════════

CONSENSUS_SYSTEM_PROMPT = """\
You are an expert at analyzing Reddit comments to determine if there is a clear consensus explanation for a meme.

Given a set of Reddit comments about a meme, determine if there is genuine consensus about what the meme means and why it's funny.

STRICT CRITERIA - Only mark has_consensus as true if ALL of these are met:
1. At least 3 comments substantially agree on the SAME specific explanation
2. The explanation answers WHY it's funny, not just WHAT it references
3. The humor mechanism is clear (pun, irony, subverted expectation, absurdist juxtaposition, cultural reference, etc.)

REJECT (has_consensus: false) if:
- Comments only identify a reference without explaining the humor
- The explanation is shallow or could apply to many memes
- Fewer than 3 substantive comments agree
- Comments disagree on the core humor mechanism
- The meme relies on "you had to be there" humor with no transferable explanation

IMPORTANT: Include SPECIFIC references in the explanation:
- Exact names of people, characters, or public figures
- Specific show names, movie titles, game names
- Twitter/social media handles if referenced
- Specific events, dates, or incidents
- Exact quotes or catchphrases

Respond in JSON format:
{
  "reasoning": "Your analysis of the comment agreement...",
  "has_consensus": true/false,
  "agreeing_comment_ids": ["id1", "id2", "id3"],
  "selected_explanation": "The consensus explanation if found, null otherwise",
  "confidence": 0.0-1.0
}"""

CONSENSUS_USER_TEMPLATE = """\
Subreddit: r/{subreddit}

Comments ({count} total):
{comments}"""

# ═══════════════════════════════════════════════════════
# Judge prompt — binary verdict
# ═══════════════════════════════════════════════════════

JUDGE_SYSTEM_PROMPT = """\
You are a strict judge evaluating whether a model's meme explanation matches the ground truth.

Compare the model's explanation to the ground truth and determine if the model correctly understood the meme.

CORRECT if the model:
- Identifies the SAME core joke mechanism (pun, irony, reference, etc.)
- Names the SAME specific people, events, or references mentioned in ground truth
- Demonstrates understanding of WHY it's funny, not just WHAT is shown

INCORRECT if the model:
- Misses specific names, events, or references that the ground truth mentions
- Provides only a generic understanding without the specific target
- Gets the wrong interpretation entirely
- Gives a literal description without understanding the humor
- Identifies the right general area but misses the specific joke

CRITICAL: If the ground truth mentions a SPECIFIC person, event, show, or reference by name, the model MUST identify it to be correct. A generic understanding is NOT sufficient.

Respond in JSON format:
{
  "reasoning": "Your detailed comparison...",
  "verdict": "correct" or "incorrect"
}"""

JUDGE_USER_TEMPLATE = """\
Ground Truth Explanation:
{ground_truth}

Model's Explanation:
{prediction}"""

# ═══════════════════════════════════════════════════════
# Quality gate prompt — text-only pre-filter
# ═══════════════════════════════════════════════════════

QUALITY_GATE_SYSTEM_PROMPT = """\
You are evaluating whether internet content qualifies as a meme with genuine humor, suitable for a meme understanding benchmark.

You will see top Reddit comments from a meme post. Determine whether this content contains real humor that can be meaningfully explained and tested.

The benchmark tests whether a model can EXPLAIN a meme. Most memes that have a real joke belong here, INCLUDING jokes built on cultural references, templates, tropes, lyrics, scenarios, comparisons, irony, and absurd-but-meaningful juxtaposition. Recognizing a reference and then understanding the situation/incongruity it sets up is exactly the skill being tested — those PASS.

There is ONE narrow class to exclude: memes where the entire joke is that a known phrase/slogan/format has been scrambled or word-swapped into NONSENSE, and the humor comes purely from the nonsense itself — i.e. the complete explanation is "it's an absurd/random variation of <reference>, the joke is that it's nonsensical" with NO specific situation, point, or new meaning to recover. Once you name the source phrase there is genuinely nothing left to understand, so the meme cannot discriminate between strong and weak models.

FAIL if ANY of these are true:
- It's just an observation, opinion, relatable statement, or factual description with no punchline.
- The ENTIRE joke is that a recognizable phrase/format was scrambled, swapped, or randomized into nonsense, and the explanation amounts to "it's an absurd/nonsensical take on <reference>" — with no specific scenario, target, or new meaning created by the alteration. (E.g. taking "women want me, fish fear me" and swapping words to "women want fish, me fear me" — the joke is purely that it's now nonsense.)

Otherwise PASS. When unsure whether a meme has a specific point beyond "it's now nonsense," lean PASS — a human reviewer makes the final call downstream.

Respond in JSON:
{
  "reasoning": "Brief analysis. If failing, confirm the joke is PURELY that a reference was scrambled into nonsense with nothing specific to recover. Otherwise state the specific thing a reader must understand.",
  "passes": true/false
}"""

QUALITY_GATE_USER_TEMPLATE = """\
Subreddit: r/{subreddit}

Comments ({count} total):
{comments}"""

# ═══════════════════════════════════════════════════════
# Safety gate prompt — content-appropriateness pre-filter
# ═══════════════════════════════════════════════════════

SAFETY_GATE_SYSTEM_PROMPT = """\
You are deciding whether a Reddit meme post is appropriate to include in a publicly-released dataset for meme understanding research.

EXCLUDE only if the content would embarrass the dataset's authors when published. Specifically:
- Explicit sexual content, nudity, pornographic references
- Slurs, hate speech, racist or antisemitic tropes
- Content that glorifies violence against identifiable people or groups
- Doxxes or harasses a private individual by name
- Sexualizes or depicts minors in any way

KEEP everything else, INCLUDING:
- Mildly suggestive jokes, innuendo, dirty humor
- Dark humor, gallows humor, jokes about death/depression
- Political commentary, even harsh political satire
- Crude language, profanity
- Edgy or transgressive jokes that punch sideways or up

This is a research dataset about meme understanding — being too prudish destroys the cultural signal. Default to KEEP. Only exclude when content is genuinely "I don't want to be associated with this."

Respond in JSON:
{
  "keep": true/false,
  "category": "short tag for why (e.g. 'explicit_sexual', 'slur', 'glorifies_violence', 'doxx', 'minor_sexualization', or 'keep')"
}"""

SAFETY_GATE_USER_TEMPLATE = """\
Subreddit: r/{subreddit}
Title: {title}

Top comments ({count} total):
{comments}"""

# ═══════════════════════════════════════════════════════
# Vague phrases (low-quality explanation indicator)
# ═══════════════════════════════════════════════════════

VAGUE_PHRASES: list[str] = [
    "absurd humor",
    "random humor",
    "no clear meaning",
    "is from the show",
    "it's relatable",
    "it's just",
    "everyone can relate",
    "pretty self-explanatory",
]


# ═══════════════════════════════════════════════════════
# Prompt ID hashing
# ═══════════════════════════════════════════════════════


def prompt_id(role: str, system: str, user_template: str) -> str:
    """Generate a deterministic prompt_id by hashing the prompt content.

    Returns the first 16 hex chars of SHA256(role + system + user_template).
    """
    hasher = hashlib.sha256()
    hasher.update(role.encode())
    hasher.update(system.encode())
    hasher.update(user_template.encode())
    return hasher.hexdigest()[:16]


# ═══════════════════════════════════════════════════════
# Image encoding helper
# ═══════════════════════════════════════════════════════


_MIME_BY_EXT = {
    "png": "image/png",
    "gif": "image/gif",
    "webp": "image/webp",
}


def load_image_base64(path: Path) -> tuple[str, str]:
    """Read an image file and return (base64_data, mime_type).

    Mirrors v4 behavior: jpg/unknown extensions are reported as image/jpeg.
    """
    data = path.read_bytes()
    b64 = base64.standard_b64encode(data).decode("ascii")
    ext = path.suffix.lstrip(".").lower()
    mime = _MIME_BY_EXT.get(ext, "image/jpeg")
    return b64, mime
