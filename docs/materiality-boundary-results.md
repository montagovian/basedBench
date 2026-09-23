# Targeted materiality feedback results

September 23, 2026 · [#24](https://github.com/montagovian/basedBench/issues/24)
· [Working guidance and review design](materiality-boundary.md)

**Complete: both original explanations are human-ready.** Two saved feedback
events, with no source-comment reveals, are frozen separately in
`data/curation/materiality-boundary-feedback-v1/`. No model calls were made.

| Case | Saved answer judgment | Human note |
| --- | --- | --- |
| Fahrenheit (`1u8dptp`) | Ready | “explanation is fine but not sure this one really counts as a joke” |
| Canadians/cans (`1u2ywbz`) | Ready | No note supplied |

Fahrenheit's note separates adequacy from doubt about the item's joke/benchmark
fit. It is not an answer rejection, an explicit suitability verdict or an
instruction to tighten suitability generally. Cans has an explicit readiness
judgment but no human-authored defect rationale. Preserve that distinction.

## What this changes

For these exact answers, mentioning the Fahrenheit “100%” wording and explicitly
restating that the pictured objects are cans are **not prerequisites for
readiness**. That conclusion follows from accepting the existing texts; it is
not a new human statement that every secondary phrase or visual detail is
optional. The quiz-name decoding, closet referent and XM8 contrast requirements
remain as previously judged.

The working boundary is therefore about missing **meaning**, not exhaustive
description: an answer can convey the necessary connection without enumerating
every cue, proper name or literal caption. A proposed omission must explain what
essential understanding the written answer leaves unresolved. This remains
assistant-authored guidance constrained by the human examples, not a validated
checker or an automatic admission rule.

## Saved model findings against the new judgments

These are retrospective comparisons using unchanged old responses. The human
labels were unavailable in those frozen runs and are not written back into them.

| Case | #22 simple Luna | #22 focused Luna | #23 simple Luna | #23 simple Sol |
| --- | --- | --- | --- | --- |
| Fahrenheit | Fail | Fail | Fail | Fail |
| Canadians/cans | Pass | Pass | Pass | Fail |

All four saved Fahrenheit checks are now false alarms relative to the actual
human readiness judgment. Sol's cans rejection is also a false alarm. The
same-schema Luna checks accepted cans already; another model's stricter critique
does not override the human judgment. These cases support testing the rejection
boundary, without proving that every earlier assistant criticism was correct.

Source support remains independent. For cans, #22's simple checker and both
#23 models reported insufficient support; #22's focused checker reported
supported. The human did not reveal the comments in this review and did not
certify three substantive supporters. Fahrenheit's model support findings also
remain model findings, not human endorsements of their counts or interpretations.

## Provenance and decision

The snapshot preserves exact event revisions, notes, answer hashes and image
bytes. Snapshot ID:
`8a720cc1f07df1e24a09f234c7001d3185f147f9d8f56674fcd7ea79ce0b3502`.
Together with #20, there are now 52 reviewed posts / 59 answer judgments across
50 currently known families. The rounds stay separate; these selected exposed
cases do not supply an accuracy estimate or an untouched validation set.

Verification confirms that the frozen journal is byte-identical to the live
journal at analysis, both answer hashes and labels match their saved events,
and all **18,253 protected prior files** remain unchanged, including both live
human journals, old snapshots, database, frozen runs and unrelated app/helper-test
edits. Earlier calibrated, focused and capacity code/manifests still verify.
No application or test code changed; the prior 485-test baseline is unchanged.
This analysis uses direct artifact-integrity checks and no new inference.

**Close #24 as complete.** The next [bounded comparison, #25](materiality-comparison-plan.md),
will test one narrow material-omission instruction revision against the simple
GPT-6 Luna baseline, keeping schema, inputs and model settings fixed. Reuse the
20 diagnostic identities with the two new labels attributed separately; repeat
both newly accepted controls as well. The proposed ceiling is **56 calls / $1**.
The plan is recorded; no paid comparison was launched by this feedback analysis.
Fresh human validation remains a separate later step if the diagnostic result
is promising. No checker promotion, suitability change or #9 expansion follows.

Local audit artifacts: `data/backfill/materiality-feedback-analysis-v1.json`
and `data/backfill/materiality-feedback-verification-v1.json`. Human feedback,
images and raw responses remain local and uncommitted.
