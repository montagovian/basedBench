# Material omissions and acceptable concise answers

September 22, 2026 · [#24](https://github.com/montagovian/basedBench/issues/24)
· Follow-up to the [capacity comparison](capacity-comparison-results.md)

**Use the existing human judgments to define the boundary before changing the
checker again.** The approved work reuses 50 reviewed cases / 57 exact answer
judgments and prepares just two unresolved original answers for human review.
Preparation makes zero model calls and costs $0. The admission checker, frozen
experiments, suitability rules and historical labels remain unchanged.

## Working rule

An explanation is adequate when it conveys enough of this meme's intended
meaning to grade another model's understanding. A material defect changes or
leaves unresolved an essential connection: the decoded wordplay, who did what,
the relevant visible referent, or the contrast/implication that makes this
particular meme work. An optional improvement makes an already adequate
explanation more precise, explicit or pleasant to read.

For a proposed omission, identify **what misunderstanding the written answer
still permits and why that matters to grading this joke**. Then check whether
the answer already conveys that meaning through a concise paraphrase. Do not
supply an absent decoding yourself and credit it to the answer. Also do not
require every visible detail, proper name, literal caption or background fact
just because it could appear in a richer answer. Correctly naming a missing
detail does not establish that the detail is essential.

This is assistant-authored development guidance derived from actual judgments,
not a new human annotation, a validated model prompt or a mechanical rule that
settles every case. The exact accepted and defective answer texts constrain its
application. Where the guidance cannot explain both sides of an existing human
pair, revise the guidance rather than silently relabeling the pair.

## What the human anchors establish

| Boundary | Existing human evidence | Consequence for the checker |
| --- | --- | --- |
| Preference versus defect | Sonic/Minecraft and domino: both originals and rewrites are ready; the rewrites are preferred. | A richer alternative is not evidence that the original fails. Preserve both-acceptable outcomes. |
| Naming a pun versus decoding it | Quiz names: both answers need repair; the note requires each pun to be explained. | Saying the names are clichéd puns, or decoding only some, does not satisfy this case. |
| Referenced scene versus whole meme | Harry Potter: original needs repair; rewrite is ready. The note distinguishes the scene explanation from the overall joke. | Explain why the retort outranks the heroic feats, not just the retort's source scene. |
| Visible referent versus placeholder | Closet: original needs repair; the note asks for a person's face in the closet. | Replace an unresolved “figure or object” with the relevant observable referent. The human did not require Pennywise's identity. |
| Template versus particular contrast | XM8: original needs repair; the note requires why the older rifle is cooler. | Naming the template or the two rifles alone does not establish the requested explanation. |
| Necessary context versus encyclopedic detail | Latin and Resident Evil 4 originals need repair, with notes about untranslated text and absent game context. | Supply the caption meaning and the game connection needed for the joke. Do not demand an exhaustive history. |
| Essential sequence versus one decoded item | State puns: original needs repair; the four-part rewrite is ready. | Cover the sequence's essential puns. The accepted rewrite permits “Mary land” or “merry land”; Sol's later preference for only one wording is not human gold. |
| Meme implication versus a comment's extra joke | Freddie Mercury: original needs repair; rewrite is ready. The note calls the lyric parody extraneous. | Recover the pictured implication without promoting a comment-only riff into the meme's meaning or a joke into historical fact. |
| Concision versus suitability | Dog-supplement, algae, sub-5 and decoded-rebus originals are ready. The sub-5 note separately questions benchmark fit. | Do not turn source-support or selection uncertainty into an explanation defect. |
| Accepted text versus assistant reconstruction | R.E.M.: original needs repair; saved rewrite is ready, without a free-text human rationale. | Preserve those exact judgments. A later assistant explanation of the improvement is not a new human requirement. |

These are observations about the saved texts, not universal exceptions for their
topics. For example, accepting the broader domino trigger does not mean all
wrong triggers are harmless; requiring a visible face does not mean every
pictured person needs a proper name. The Sonic rewrite is accepted without
naming Kharrii or explaining the dirt-block reference, further limiting the
stronger model's demands on this example.

## Keep three questions separate

1. **Answer adequacy:** does the written explanation get the intended joke?
2. **Source support:** do at least three distinct supplied comments substantively
   support that same core reading? Directions, reactions, new riffs, background
   mentions and contrary interpretations do not become supporters by repetition.
3. **Selection and publication:** suitability, content policy, duplication,
   usefulness and release membership retain their own decisions.

An adequate answer can have an evidence hold. Conversely, three comments do not
repair an inadequate answer. Human readiness here is not a certification of the
comment count. No new suitability restriction follows from this work.

The full registry retains all qualifying notes: Israel/fashion's repair label
comes with a lack-of-consensus concern; two-cows has an uncertainty/fit note;
Mystique remains unclear; another random repair has no note. Do not recode those
as confidently diagnosed factual errors. The two known duplicate pairs remain
50 posts / 48 families, without deleting either member's feedback.

## Only two new judgments

`data/curation/materiality-boundary-v1/` contains two already exposed cases:

- **Canadians/cans (`1u2ywbz`):** the original decodes Finns/Cans. The remaining
  boundary is whether an explicit description of the pictured cans is needed.
- **Fahrenheit (`1u8dptp`):** the original explains the percentage-temperature
  premise. The remaining boundary is whether the additional “100%” phrasing
  changes adequacy. Comment-only freezing/boiling arguments are not image text.

These selection explanations are assistant hypotheses. They are **not shown in
the review page**, which presents the image and untouched original answer with
the existing neutral rubric. Neither case has a prefilled judgment or a generated
rewrite. Other stress cases remain unadjudicated; this is not an expanded queue.

Use **Good enough to grade**, **Material defect**, or **Cannot judge yet**. A
short note is useful where the answer is defective or a distinction remains
unclear. Optional source comments are hidden until revealed; reveal events
save the draft checkpoint. Do not infer a vote from an unsaved or blank field.
The new append-only journal is separate from the completed 50-case review.

```sh
uv run python -m basedbench.calibration_review serve \
  data/curation/materiality-boundary-v1 --port 9877
```

Open `http://127.0.0.1:9877/`. The existing review on port 9876 remains intact.
Packet ID: `430a66be7d256e5f0d7fc973603ade088213914b577b14020d5c2266c1e74850`.

## Preparation verification

All **485 tests pass**, including seven new provenance/preservation tests and
the two existing local HTTP tests. Both real cases were checked in the browser
for matching images, untouched original explanations and empty feedback fields.
Navigation returned to the first case; no assistant judgment or comment-reveal
event was entered. Save/revision behavior continues to use the existing tested
review interface.

All **18,235 protected prior files** match their before hashes, including the
human journal and snapshot, database, frozen model runs and unrelated app/helper
edits. Earlier calibrated, focused and capacity code/manifests still verify.
The local verification record is `data/backfill/materiality-verification-v1.json`.
Raw anchors, review images and human feedback remain uncommitted.

## Provenance and continuation

The packet's `human-anchors.json` joins every frozen human event to the exact
answer texts displayed in #20, with text hashes, labels, notes, A/B preferences,
strata and family identities preserved. Those anchors are local audit data,
not newly collected judgments and not content exposed by the review API.
The builder checks the original packet, feedback-snapshot and capacity-run
manifests, event/text/label consistency, fixed target identities and assets.
It rejects overwrites, existing human labels and known human-family overlaps.

Reproduce in a new directory only:

```sh
uv run python -m basedbench.materiality_review \
  data/curation/explanation-calibration-v1 \
  data/curation/explanation-calibration-feedback-v1 \
  data/backfill/capacity-comparison-v1 \
  data/curation/materiality-boundary-NEW
```

After actual feedback arrives, freeze a separate snapshot using the existing
`calibration_analysis` workflow, with an explicit duplicate-inspection list
(empty if no duplicate is identified). Preserve unclear judgments as unresolved.
Then record whether these cases clarify or limit the working rule. Do not
merge them into old frozen reports or call this a fresh accuracy estimate.

Any subsequent checker change needs its own frozen recipe and comparison plan.
Retain both accepted originals, all confirmed repair examples, separate evidence
findings, rationale inspection and repeat checks. Examples used to author or
illustrate a prompt are training/development material, including when a model
then agrees with their labels. A later generalization claim requires a separately
frozen fresh human comparison. No paid model experiment or #9 expansion is
included in this calibration step.
