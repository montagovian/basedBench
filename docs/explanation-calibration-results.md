# Human explanation calibration results

September 22, 2026 · [#20](https://github.com/montagovian/basedBench/issues/20)

All **50 cases / 57 answer texts** have saved human judgments: 50 feedback events
and 17 source-comment reveals. The exact journal, event revisions, answer hashes
and images are frozen separately in
`data/curation/explanation-calibration-feedback-v1/`. Original feedback and prior
experiments remain unchanged. Preparing and analyzing this round made no new
model inference calls.

| Original answer | Random cached (30) | Targeted (20) |
| --- | ---: | ---: |
| Ready | 25 | 12 |
| Material defect / repair | 4 | 8 |
| Cannot judge yet | 1 | 0 |

Do not pool these into an accuracy estimate: targeted cases were selected for
known questions; random cases were conditional on successful legacy generation,
available cached assets and no old review row. All are now exposed calibration
material. Readiness is not a separate human certification of three substantive
supporting comments.

## What the human judgments resolve

Of seven original/repair pairs, **four repairs fix a human-confirmed defect**
(Harry Potter, state puns, Freddie Mercury and R.E.M.); **two pairs are both
acceptable** (Sonic/Minecraft and domino), with a preference for the rewrite;
and **neither quiz-name answer is adequate**, because neither explains all the
puns. Model verification status is not substituted for these judgments.

Concrete missing connections remain worth pursuing. Human notes call for the
meme's overall joke rather than only its referenced scene, the actual decoding
of wordplay, the visible face rather than a vague object placeholder, necessary
Resident Evil 4 context, and the reason for the XM8 contrast rather than just
its template name. Another random case is marked repair without a note; do not
invent a human-provided rationale for it.

The calibration also limits earlier assistant hypotheses. The dog-supplement,
algae and sub-5 explanations are judged ready. The sub-5 note specifically
separates uncertainty about benchmark suitability from an explanation that fits
the clearest comments. These are not human-confirmed explanation defects. Existing
source-support questions remain separate; do not reinterpret readiness as a vote
on the three-comment rule.

The Israel/fashion answer is marked repair with a note about disagreement and
lack of a stable ground truth. The random Mystique case remains unclear because
multiple interpretations lack enough support. The two-cows case is marked repair
but the note expresses uncertainty and questions benchmark fit. Keep the selected
labels and the qualifying notes together; report evidence/fit ambiguities rather
than recoding them as certain factual errors. XM8 was an assistant positive
control previously, and is a human repair here; preserve both provenances without
treating the earlier inspection as gold.

## Duplicate misses

Both human duplicate flags were confirmed by separate image inspection:

- `1u84irh` / `1uacbk6`: the same monitor-snapping four-panel meme with different
  image bytes.
- `1u6zome` / `1u6zl2d`: the same police/YouTube-curfew image, with versus without
  a Reddit footer.

These were missed by the review packet's limited known-family exclusions.
**50 reviewed posts represent 48 currently known families; the random portion
contains 28.** Keep every human judgment. Report post-level counts above and
family-weighted results alongside them, with each detected pair totaling one
family. This does not choose publication keepers or certify the absence of more
families. Fresh sampling needs a broader local image pass against the review
packet and other known exposures before it can be called family-separated.

## Consequence for the comparison

The immediate target is concrete explanation adequacy with source support
reported separately. Use a simpler checker that can say an answer gets the joke
while still holding it for insufficient evidence. Preserve the old combined
Luna gate as a baseline and compare operational acceptance as well as the new
separate findings; the baseline did not provide a fully separate adequacy label.

The user's subsequent GPT-6 Luna suggestion updates the third condition to the
newer Luna model, not an assumption that higher price means better quality.
[The executable comparison plan](calibrated-comparison.md) preserves GPT-5.6
Luna with the old checker and with the simpler interface, allowing the interface
and model-version changes to be assessed separately. No suitability tightening,
label rewriting or automatic backfill expansion follows from this calibration.
