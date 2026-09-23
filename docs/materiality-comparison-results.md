# Luna material-omission comparison results

September 23, 2026 · [#25](https://github.com/montagovian/basedBench/issues/25)
· [Frozen plan](materiality-comparison-plan.md)

**Complete: the prompt-only revision does not meet its targets.** All 56 calls
finished for **$0.03853775 (3.9¢)**, with no technical errors. The revision catches
one additional human repair original, but retains no more ready originals and
rejects an additional ready answer on repeat. Stop this variant. Neither checker
is promoted, suitability is unchanged, and #9 remains pending.

## Fixed comparison and human provenance

Both conditions use GPT-6 Luna and the existing simple response schema, medium
reasoning, high-detail images, standard service and 4,000 maximum output tokens.
Only one materiality instruction paragraph and its cache identity differ. All
28 baseline request bodies match the earlier #23 Luna payloads; the two added
repeat identities reuse their original payloads. The concurrent baseline is the
comparison, not a selected historical outcome. There were no retries, repairs,
replacement cases or extra conditions.

All 20 identities are exposed development examples with distinct currently
known families: nine human repair originals, eight human-ready originals and
three unlabeled stress cases. The [two new ready judgments](materiality-boundary-results.md)
are a separate provenance overlay; old runs retain their original unlabeled
status. Human notes and labels are absent from model requests. This sample does
not estimate population accuracy, generalization or cost per newly usable item.

Original selection strata remain intact: targeted contains six repair and six
ready cases; random-cached contains three repair cases; fresh-cached contains
the two newly reviewed ready cases and three still-unlabeled cases. The latter
stratum's historical name does not make these now-exposed examples held out.
Fahrenheit and cans separately record their targeted human-review provenance.

## Predeclared answer-adequacy readout

These counts concern the explanation, independently of comment support.

| Development target | Simple baseline | Materiality revision | Required |
| --- | ---: | ---: | ---: |
| Primary defects failed on both checks | 0/3 | 1/3 | 3/3 with matching rationales |
| Ready originals retained on first check | 6/8 | 6/8 | 8/8 |
| Repeated ready answers retained | 3/5 | 2/5 | 5/5 |
| Repair originals failed on first check | 6/9 | 7/9 | At least 8/9 |
| Adequacy flips across repeats | 1/8 | 1/8 | At most 1, no more than baseline |
| Technical errors / missing calls | 0 / 0 | 0 / 0 | Zero |

The revision's one primary verdict gain is XM8. Its first rationale explains
the older/newer contrast and cooler-looking preference; its repeat chiefly
identifies the older design as favored, leaving why it is cooler implicit.
This is useful partial progress, not three rationale-validated fixes. Both
conditions still pass quiz names and the closet answer twice.

The baseline's adequacy flip is XM8, from pass to fail. The revision's flip is
the human-ready domino answer, also from pass to fail. Equal flip counts hide
different consequences. Both reject Sonic/Minecraft and Fahrenheit twice;
both accept cans and the decoded rebus twice.

| Original stratum / first-check adequacy | Baseline pass / fail | Revision pass / fail |
| --- | ---: | ---: |
| Targeted repair, six | 2 / 4 | 1 / 5 |
| Targeted ready, six | 5 / 1 | 5 / 1 |
| Random-cached repair, three | 1 / 2 | 1 / 2 |
| Fresh-cached, two newly ready | 1 / 1 | 1 / 1 |
| Fresh-cached, three unlabeled | 2 / 1 | 2 / 1 |

All planned cases remain in denominators. Family weighting changes no count
because all 20 currently known families are distinct. No answer-adequacy
uncertain outcomes occurred; the combined holds below concern source support.

## Rationales explain the failed target

**Quiz names and closet remain misses.** Both prompts accept a generic account
of overused quiz-name puns without the human-requested decodings. The revised
prompt also explicitly says the hidden figure needs no more specific
identification. That conflicts with the human request to identify the creepy
face in the lower-right closet. This inspection does not add IT/Pennywise as a
required identity. Both conditions inflate some source counts with reactions,
direction-only hints, irony or new-name riffs.

**XM8 improves, with limits.** The revision identifies the older H&K/newer SIG
contrast on both checks and mentions the older design's appearance on the first.
No rifle-side reversal appears in these outputs. The repeated rationale is less
explicit about the preference, and its third citation supplies terse design
names rather than the reason for favoring one. The first check instead counts a
design-lineage background comment. Neither proves three substantive explanations
of the contrast; independent firearms-history verification was outside the run.

**The human-ready boundary still fails.** Sonic/Minecraft is rejected four times
for omitting the proposed replacement and Steve/dirt-block reference, despite
the human accepting both original and alternate answers. The revision first
explicitly accepts the domino answer's broader laptop-controversy wording, then
rejects that identical text because it omits the exact initiating caption. That
is a false alarm relative to the saved both-acceptable judgment.

**Fahrenheit has an image-grounding error, not just a strict detail demand.**
All four rationales import a Celsius freezing/boiling rebuttal from comments
into a supposedly visible reply. The actual image contains two pro-Fahrenheit
posts, including an earlier quoted insult about Celsius. The retort the models
require is absent. The user's ready judgment remains authoritative; the separate
note questioning joke/benchmark fit does not turn it into an answer rejection.

Both conditions retain adequacy for cans, dog supplement, algae, sub-5 and the
rebus. Both identify useful defects in Latin-caption decoding, RE4 inventory
rules, Harry Potter's heroic-feats/retort contrast, the earlier state puns,
the Mercury sleepover implication and the R.E.M. inset. Those matching labels
do not certify every rationale: for example, the baseline's proposed Tennessee
decoding is imprecise. The Mercury finding describes the meme's implication,
not an established event in a real person's medical history. Exact human
judgments, including both-acceptable answers, remain unchanged.

## Comment support remains separate

| Human group / first check | Baseline combined pass / fail / hold | Revision combined pass / fail / hold |
| --- | ---: | ---: |
| Nine repair originals | 3 / 6 / 0 | 2 / 7 / 0 |
| Eight ready originals | 3 / 2 / 3 | 4 / 2 / 2 |
| Three unlabeled stress cases | 1 / 1 / 1 | 1 / 1 / 1 |

Only XM8 and cans change first-check combined verdict between conditions.
**The extra combined pass for cans is not a valid support improvement:** both
revision checks and the baseline repeat count the third comment's new
AM-computer riff, contrary to the unchanged instruction excluding new jokes.
The baseline first check correctly holds at two substantive supporters. Human
answer readiness does not certify the source count.

Two other first-check source statuses differ without changing the combined fail:
Harry Potter and Fahrenheit. For Harry, the revision excludes a third comment
that calls the line the best comeback without explicitly stating the contrast
with heroic feats. Both detect the answer omission. For Fahrenheit, the
revision first holds at two Celsius counterarguments, then joins the baseline
in counting both sides of the debate as support for one reading. The source
hold does not repair its incorrect visual narrative.

Combined verdicts flip on two baseline repeat pairs (XM8 and cans), versus one
revision pair (domino). The revision's Fahrenheit support status also flips,
hidden by its persistent answer failure. Dog and algae retain source holds in
both conditions. Other cited lists sometimes substantiate only part of a
multi-part joke or count brief mentions; the local inspection preserves those
limitations without inventing human source-support labels.

## Three still-unlabeled stress cases

| Case | Both conditions and inspection |
| --- | --- |
| Cameron Diaz | Accept the explicit phonetic decoding without requiring redundant restatement of the colonoscopy setup; multiple comment decodings are available. |
| Kevin Rose/Digg | Accept the failed-competition account and retain a two-comment hold, excluding biography alone. No independent business-history check or human label is supplied. |
| Ladder chain | Flag the final poster-role misattribution and hold at one chain-explanation comment. This matches the first-person wording under that reading; unsafe-storage and road-stopping alternatives remain unresolved. No human defect label is added. |

All **56 final judgments and all 20 images** were inspected, including every
changed verdict, primary rationale, source-status disagreement and repeat.
These assistant observations are development hypotheses, not additional gold.

## Cost and preservation

| Condition | Calls | Input tokens | Output tokens | Estimated cost |
| --- | ---: | ---: | ---: | ---: |
| Simple baseline | 28 | 71,886 | 24,045 | $0.018784235 |
| Materiality revision | 28 | 75,834 | 25,256 | $0.019753515 |
| **Total** | **56** | **147,720** | **49,301** | **$0.038537750** |

Baseline input includes 52,481 cache-write and 19,321 cached tokens; revision
input includes 55,301 cache-write and 20,449 cached tokens. Output includes
20,676 and 21,757 reasoning tokens respectively. Costs use frozen prices and
returned usage; these are estimates rather than an invoice. Conservative
accounting is **$0.0431155**, below the $1 ceiling. There are no unknown-usage
calls, pending calls, technical errors or allowance violations.

All **491 tests pass**: 489 non-socket tests and two local HTTP tests. Offline
replay makes zero calls and preserves all **140 run files**. Hash checks verify
all **18,257 protected prior files** unchanged, including frozen runs, database,
human journals/snapshots and the unrelated app/helper-test edits. Old calibrated,
focused and capacity code, inputs and results still verify. The new runner and
predeclared plan remain unchanged after launch. No raw artifacts enter git.

## Decision

Close #25 as a completed negative result. Keep simple Luna as a development
baseline; this experiment does not establish an automatic admission checker.
The materiality wording has not resolved either the missing-meaning tradeoff
or the tendency to import comments into the image. More spending is not the
immediate constraint, and another pass over these same cases would add little
evidence about new-item quality.

The recommended next decision is whether to run a **small, separately planned
fresh human audit of candidate answers**, with selection frozen before checker
outcomes and judgments blinded to model criticism. Its purpose would be to
measure useful yield and remaining correction work in a defined candidate pool,
while separating answer readiness, source support, duplicates and joke/fit
concerns. Keep exposed families out of any claimed fresh validation. This is a
recommendation, not a launched annotation queue or an authorization to expand
#9. No further model condition, repair, prompt search or paid call follows #25.

Local artifacts: `data/backfill/materiality-comparison-v1/` (experiment
`97b36eba57e1ed8f4f4bb5df8d75706fbd7a1930dfc25597a8b26bef3b386541`),
`data/backfill/materiality-comparison-analysis-v1/`,
`data/backfill/materiality-comparison-inspection-v1.json` and
`data/backfill/materiality-comparison-verification-v1.json`. Human feedback,
images and raw responses remain local and uncommitted.
