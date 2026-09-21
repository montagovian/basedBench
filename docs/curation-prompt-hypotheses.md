# Inferring the curation standard from existing feedback

These are assistant hypotheses derived from Alex's existing judgments, not
additional human labels. They are concrete enough to test without first asking
Alex to articulate a complete policy. No new model calls have been made.

The strongest hypothesis is: **a good item has a specific missing connection
that an explanation supplies.** Much of the weak material can be accounted for
by reading its caption, narrating its surprising event, or inventing a generic
contrast. This could explain why an easy meme qualifies while another feels
too slight. It is a hypothesis about getting the joke, not a requirement to
explain why humans find something funny.

## Evidence from the actual images

The images were re-inspected, rather than relying only on their stored glosses.

| Contrast | Proposed distinction | Strength of inference |
| --- | --- | --- |
| Time-freezing snap: value fail; freezer bags: value pass | The time-freezing caption already states both the power and lack of immunity. Explaining it largely spells out that consequence. The freezer photo requires inferring that someone misread a product name as a storage instruction; the caption does not disclose that mistake. | Strong candidate distinction, though a short consequence is still an inference. |
| Seafood/stroke: value fail; RCA cables: value pass | The comic depicts the interrupted speech and resulting emergency. Calling that an unexpected stroke does little beyond narrating it. The cable meme needs a mapping between video/audio functions and the depicted people's sensory impairments. | Strong candidate; the comic also subverts a familiar pun, so the test concerns whether that adds enough. |
| Santa/goth women: value fail; chess knight: value pass | Santa beside the women permits several optional stories. The knight's move gives a specific reason the labeled squares have that relationship. | Strong candidate distinction between an available association and a constrained payoff. |
| “Nothing” spelling riddle: value fail; freezer bags: value pass | Both are easy and involve literal meanings. The riddle ends at treating one printed word as a word; the freezer item uses a misunderstanding to explain someone's otherwise odd behavior. | Moderate: this adds a minimum-value preference, supported by Alex's explicit “too easy” note, beyond merely requiring an inference. |
| Grenades quote tweet: value fail; M4M4BEAR: value pass | The quote already states the slang meaning it finds amusing. The plate tweet leaves the “terrible mistake” unexplained until the alternate reading is recovered. | Useful earlier evidence. The quoted founding-fathers post may contain its own joke; assess the complete item rather than treating reference recognition as automatic admission. |

Accepted Euler, RCA cables, Rainbolt and the knight also support **applying a
reference to the particular scene**, rather than merely detecting the presence
of a reference. The accepted freezer bags prevent this from becoming a rule that
requires obscure cultural knowledge or a famous person. Text-only formats can
qualify: the license-plate tweet has a clear missing implication.

## Counterexamples must remain visible

The time-machine meme (`1dze07r`) is a substantial exception. Its lower panel
explicitly has the pharaoh mistake “Bass Pro Shop” for a powerful king, in
addition to the modern/ancient pyramid contrast and the Henry Ford panel. There
is a concrete reference-based joke here. The stored gloss emphasizes a broader
gender-role reversal and misses that specific line. This suggests a possible
answer issue but does not explain Alex's explicit value rejection. Keep both
recorded component labels unchanged and show the mismatch if a new prompt passes
it. Do not invent a rejection rule for this particular image.

The earlier Cobain rejection (`1fpyrrv`) is another counterexample: recognizing
the musician and connecting the gun claim to the referenced death is a real
missing connection. Alex nevertheless found the payoff insufficient and the
explanation muddled. These hypotheses may improve agreement without explaining
every judgment; that is a useful outcome to measure.

The horse/paper-cut item (`1ju80zo`) has positive value feedback despite its
overall rejection. Its horse/euthanasia association should remain a positive
value control. Master Chief has an overall accept but unresolved value; do not
quietly promote it to a component-positive example. The snails, Manwich and other
unresolved judgments likewise stay unresolved.

## Three concrete prompt variants

Exact machine-readable drafts are in
[curation-value-prompts-v1.json](experiments/curation-value-prompts-v1.json).
Each replaces the **instructions and answer descriptions** of the value check;
retaining the old permissive pass description would undermine the test.

1. **Interpretation gap:** does the answer add a useful missing connection beyond
   reading and describing the item? Explicitly distinguishes an inference about
   meaning or intent from spelling out a stated premise, narrating a surprise,
   or solving an isolated spelling trick.
2. **Anchored payoff:** do the important details support a particular intended
   relation, or does the explanation supply an optional story around a random
   pairing? This alone will not catch every self-explanatory joke.
3. **Combined:** requires both. This is the strongest selection hypothesis and
   the one most at risk of rejecting legitimate simple jokes.

The combined prompt's central question is:

> Would a correct explanation supply a useful, specific missing connection for
> this item? Simple jokes qualify when that connection changes how the scene is
> understood. Do not admit an item merely because an explanation can name a
> reference, describe its surprise, point out a spelling trick, or call a
> juxtaposition absurd.

“Isolated spelling trick” is deliberately an experimental preference inferred
from the riddle feedback. It is not an adopted ban on wordplay. The first trial
should show whether that wording also harms positive cases, and remove or narrow
it if it does. An alternate later comparison can omit just that clause.

## A separate content hypothesis

The content feedback suggests an additional distinction: **inviting a specific
sexual visualization or anatomical speculation** versus using a sexual/social
association to deliver another joke. The tongue-markings item directs attention
to the appearance of genitals; the popsicle item invites imagining a sexual act.
Rainbolt uses the cousin setup to make an Alabama/geolocation joke; M4M4BEAR uses
sexual shorthand to explain a mistaken plate reading. This is a more concrete
potential rule than “sexual implication fails.”

It remains provisional. The accepted Oprah/Weinstein item is a necessary
counterexample to test because it has a dark sexual-assault implication. The
elevator, Vaporeon and crumb cases retain their explicit boundary labels. Do not
resolve them by applying an inferred rule. Test content separately from value so
one improvement cannot disguise deterioration in the other.

## How to test this economically

First compare the three value prompts against the previous clear-rules question
using identical evidence and no examples. Keep content and answer checks fixed
or omit them from this component-only diagnostic. Measure catches among the five
settled value negatives and retention among the 17 positives separately. Inspect
the horse and the easy positives explicitly; don't reward reject-all behavior.
Report outputs for the six cases with no settled value label separately.

There is an input limitation to test independently. JEV currently receives a
stored explanation and comments, not necessarily a literal record of what the
meme itself says. The distinction between what is printed and what is inferred
is especially important for the time-freezing example. Its stored gloss already
turns the caption into an explanatory inference, concealing how little was left
for the viewer to supply.

Therefore follow the prompt-only comparison with the same prompts plus a neutral
transcription and description of visible details for **every** target, prepared
consistently without value labels or evaluative wording. Compare the old prompt
with and without that evidence too. Do not add helpful descriptions only to the
rejects, or credit better input to better question wording. Record authorship:
assistant-written observations are additional, potentially biased evidence, not
human gold. Their eventual production cost also belongs in workflow comparisons.

The current 28 are development cases already used to infer these hypotheses.
Document changes before running, treat apparent improvements as development
results, and confirm useful distinctions on fresh examples. The time-machine and
Cobain exceptions should remain in the case analysis even if they lower scores.
No new spending or production-policy change is part of this draft.
