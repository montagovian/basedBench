# BasedBench roadmap and work backlog

Updated September 20, 2026. This is the short work index; detailed plans and
experiment reports remain the design record. IDs below are local backlog IDs,
not GitHub issue numbers. No external tickets have been created.

## Current direction

The next milestone is **a bounded, reproducible pilot of the newer-content
backfill**, with a report showing what was admitted, what was deferred, why, and
what processing cost. A suggested initial ceiling is 100 candidates; choose the
source window and spending cap before execution. This is a development candidate
set, not publication or a claim that unattended admission is validated.

Move exact imitation of discretionary historical rejections off the critical
path. Some valid items can reasonably be omitted from a curated collection.
Historical disagreement is not automatically a dataset defect. Prioritize
incorrect answers, unsupported interpretations, content exclusions, missing
assets and excessive duplication, while tracking usefulness and coverage.

Human feedback remains unchanged. In particular, an explicit negative value
label remains a negative in its original experiment; it does not become a
positive because the project now gives that experiment less weight.

The first implementation priority is **BB-01**, answer construction/validation.
BB-02, preparing a bounded source inventory, can proceed independently. Existing
ingestion and tracer commands provide starting points, but have not yet been
qualified as the new admission workflow.

## Ready and next

| ID | Work item | Status | Done when | Depends on |
| --- | --- | --- | --- | --- |
| BB-01 | Check and repair the actual joke explanation | Ready | Known answer defects and positive controls are evaluated for the explanation's supported meaning, rather than only whether consensus exists; bounded repair proposals are separately verified against comments and images; a report distinguishes repair success, false alarms and unresolved cases. | Existing regression cases and component feedback |
| BB-02 | Prepare a bounded backfill source inventory | Ready | Release source coverage and the requested date window are explicit; source access is checked; candidate IDs, available images/comments, overlap and retrieval gaps are recorded; the pilot's candidate ceiling and cost plan are concrete. | None; use existing unreviewed material for plumbing where helpful |
| BB-03 | Make publication checks usable in the pilot | Next | Current exclusions, specific content findings and unresolved boundaries are recorded separately; known positive/negative controls are tested with visual evidence; boundary cases can defer without blocking the batch. | Existing content feedback; no automatic adoption of AfterDark rules |
| BB-04 | Identify exact copies and repeated joke families | Next | Candidate images are checked against the legacy corpus and one another; known duplicate families are caught; a redundant copy has a separate reason from an intrinsically defective item; uncertain family matches remain visible. | BB-02 inventory for fresh-candidate checks |
| BB-05 | Assemble the resumable admission pilot | Next | Each candidate has versioned content and answer checks, suitability findings, duplicate findings, accept/reject/defer status and technical-error state; total spending and escalation are bounded; reruns preserve provenance and avoid repeating paid work. | BB-01, BB-03, BB-04 |
| BB-06 | Run and assess the first newer-content batch | Next | A frozen candidate batch is processed with the prepared policy and cap; the report shows specific defects, disagreements, coverage, deferrals, duplicates and cost per usable item; raw artifacts stay local and the limits of new-content quality evidence are explicit. | BB-02, BB-05 |

BB-01 has a concrete existing gap: `pipeline/consensus_eval.py` currently sets
`passed` by comparing only `has_consensus` with its expected Boolean. A run can
therefore pass while producing the wrong explanation. The current curation
experiments check stored answers but do not yet constitute a tested generation,
repair and verification workflow.

BB-05 should preserve suitability findings without requiring perfect agreement
with every historical tough reject. The pilot policy still needs an explicit
minimum standard and a deferral path. No model agreement, confidence score or
absence of a detected defect should be reported as independent proof of quality.

## After a useful pilot

| ID | Work item | Done when | Depends on |
| --- | --- | --- | --- |
| BB-07 | Expand chronological backfill with coverage accounting | Resumable date batches account for discovered content, missing periods, processing outcomes and budget; policy changes create new versions. | BB-06 and an explicit decision to expand |
| BB-08 | Freeze and evaluate the candidate release | Membership, images, explanations and policy versions are immutable; automated versus human admission provenance is preserved; legacy and new-set results are reported separately; an honest evaluation design accounts for prior test exposure. | BB-06 for preparation; BB-07 for the larger release |
| BB-09 | Define a small tag vocabulary and coverage report | Existing tags are inventoried; a bounded set gets definitions and versioned assignments; missing tags are not treated as negatives; coverage can be inspected without imposing a new selection rule. | Can follow BB-06; not a prerequisite for the pilot |

Details: [backfill plan](automated-backfill-plan.md),
[classifier plan](classifier-experiments-plan.md),
[tagging plan](tagging-taxonomy-plan.md).

## Parked ideas

| ID | Idea | Revisit when |
| --- | --- | --- |
| BB-10 | Further value-prompt optimization, GEPA, or task-specific classifier adaptation | A pilot exposes consequential selection errors and there is a coherent target to optimize; exact imitation of discretionary rejects alone is insufficient justification. |
| BB-11 | BasedBench AfterDark | There is a concrete decision about an opt-in collection, its boundaries and separate reporting. Current borderline cases do not establish that policy. |
| BB-12 | Topical memes as a knowledge-recency probe | The core release is in hand; retain event-date evidence and distinguish knowledge needed from context already supplied by the image. Breadcrumb only. |

Changing prediction judges and recurring automatic ingestion also remain later
work. They should not delay the first useful backfill batch.

## Completed foundation

- Frozen historical corpus, provenance/history audit and comparison harness.
- Word-count, TF-IDF, frozen-encoder and JEV/LLM diagnostic comparisons.
- Review gallery and 28 completed multidimensional human reviews, plus earlier
  conversational corrections and unresolved judgments.
- [Enriched-label comparison](curation-enriched-results.md): 140 calls, about 8¢.
- [Value prompt/evidence comparison](curation-value-experiment.md): 224 calls,
  about 1.2¢; the best default verdicts caught one of five value negatives while
  keeping 17 positives. This is completed research, not a production-quality gate.

No new-content backfill has been completed as part of these experiments.

## Proposed ticket workflow

Use **GitHub Issues in the existing repository** for actionable work and its
status. A repository search on September 20 found no open issues. Keep the
approved plans and experiment reports in `docs/` as the supporting record.

Start with the six Ready/Next items above. Add Later/Parked items as idea tickets
when useful; their presence must not imply they block the pilot. A simple
Ready / In progress / Done view is enough, with a separate parked category.
No standalone project-management product is required for this scope.

Each ticket needs the problem/outcome, a short completion checklist, dependencies,
and links to relevant plans or results. Experiments also need a hypothesis,
comparison, success measure and cost cap. Update the ticket when work produces
a result, including a negative result; finishing an experiment does not require
its hypothesis to succeed.

Once external tickets exist, use their status as the work-tracking source of
truth and replace the local IDs here with links. Avoid maintaining two competing
status lists. Keep raw corpus data, images and private operational logs out of
public issue bodies.
