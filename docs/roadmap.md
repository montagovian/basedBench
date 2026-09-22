# BasedBench roadmap and work backlog

Updated September 22, 2026. This is the short work index; detailed plans and
experiment reports remain the design record. The
[GitHub roadmap tracker](https://github.com/montagovian/basedBench/issues/15)
links all twelve work items. GitHub issues are the source of truth for work
status; this document records direction and scope.

## Current direction

The first bounded newer-content pilot is complete: 100 June 20–26 candidates,
43 automatic accepts, one rejection and 56 deferrals for about 23.3¢, within
the frozen $1 admission-model cap. The bounded follow-ups are complete:
[#16's source-first comparison](connection-comparison-results.md) produced useful
repairs for 20.0¢ but did not meet the decoding/intent/support targets;
[#17's local comparison](duplicate-comparison-results.md) recovered the bordered
copy through image and explanation retrieval at zero paid-call cost. **Do not
promote the answer variant or expand automatically yet.** Preserve useful simple
items and target the remaining concrete explanation defects. See the
[assessment](backfill-pilot-results.md), [#16](https://github.com/montagovian/basedBench/issues/16)
and [#17](https://github.com/montagovian/basedBench/issues/17). This remains a
development candidate set, not publication or proof of unattended quality.

Move exact imitation of discretionary historical rejections off the critical
path. Some valid items can reasonably be omitted from a curated collection.
Historical disagreement is not automatically a dataset defect. Prioritize
incorrect answers, unsupported interpretations, content exclusions, missing
assets and excessive duplication, while tracking usefulness and coverage.

Human feedback remains unchanged. In particular, an explicit negative value
label remains a negative in its original experiment; it does not become a
positive because the project now gives that experiment less weight.

The answer-quality workflow and bounded experiment in
[#3](https://github.com/montagovian/basedBench/issues/3) are complete; see the
[results and remaining limitations](answer-quality-results.md). The bounded
[source inventory](backfill-source-inventory.md) in
[#4](https://github.com/montagovian/basedBench/issues/4) is also complete: a frozen
100-candidate June 20–26 batch with asset failures and a missing-community
coverage gap recorded. The versioned
[content-policy component](content-policy-pilot.md) in
[#5](https://github.com/montagovian/basedBench/issues/5) is also complete for pilot
integration: all three selected exclusions caught, with two false deferrals and
untested-category limits retained. The [duplicate audit](duplicate-audit.md) in
[#6](https://github.com/montagovian/basedBench/issues/6) is complete: all three
known families retrieved, one exact fresh-copy pair and 28 uncertain match pairs
recorded, with concrete same-topic false alarms and asset gaps retained. The
[resumable admission pilot](admission-pilot.md) in
[#7](https://github.com/montagovian/basedBench/issues/7) is also complete: six
controls exercised generation, repair, rejection, deferral and safe continuation
for about 1.8¢. Offline replay was identical and made no API calls; all 415 tests
passed. [#8](https://github.com/montagovian/basedBench/issues/8) completed the fresh
assessment: 54 candidates reached models and 46 deferred before spending.
Inspection found no concrete issue in 30 accepted rows and flagged 13 for
different reasons, including two copies of one missed duplicate. The fresh run
made 195 Luna calls; zero-call replay preserved 466 files. All 424 tests passed.
Use the dedicated `admission_pilot` workflow; legacy ingestion and tracer
commands are not its entry points.

## Pilot work

| Issue | Work item | Done when | Depends on |
| --- | --- | --- | --- |
| [#3](https://github.com/montagovian/basedBench/issues/3) | Check and repair the actual joke explanation | Known answer defects and positive controls are evaluated for the explanation's supported meaning, rather than only whether consensus exists; bounded repair proposals are separately verified against comments and images; a report distinguishes repair success, false alarms and unresolved cases. | Existing regression cases and component feedback |
| [#4](https://github.com/montagovian/basedBench/issues/4) | Prepare a bounded backfill source inventory | Release source coverage and the requested date window are explicit; source access is checked; candidate IDs, available images/comments, overlap and retrieval gaps are recorded; the pilot's candidate ceiling and cost plan are concrete. | None; use existing unreviewed material for plumbing where helpful |
| [#5](https://github.com/montagovian/basedBench/issues/5) | Make publication checks usable in the pilot | Current exclusions, specific content findings and unresolved boundaries are recorded separately; known positive/negative controls are tested with visual evidence; boundary cases can defer without blocking the batch. | Existing content feedback; no automatic adoption of AfterDark rules |
| [#6](https://github.com/montagovian/basedBench/issues/6) | Identify exact copies and repeated joke families | Candidate images are checked against the legacy corpus and one another; known duplicate families are caught; a redundant copy has a separate reason from an intrinsically defective item; uncertain family matches remain visible. | [#4](https://github.com/montagovian/basedBench/issues/4) inventory for fresh-candidate checks |
| [#7](https://github.com/montagovian/basedBench/issues/7) | Assemble the resumable admission pilot | Each candidate has versioned content and answer checks, suitability findings, duplicate findings, accept/reject/defer status and technical-error state; total spending and escalation are bounded; reruns preserve provenance and avoid repeating paid work. | [#3](https://github.com/montagovian/basedBench/issues/3), [#5](https://github.com/montagovian/basedBench/issues/5), [#6](https://github.com/montagovian/basedBench/issues/6) |
| [#8](https://github.com/montagovian/basedBench/issues/8) | Run and assess the first newer-content batch | A frozen candidate batch is processed with the prepared policy and cap; the report shows specific defects, disagreements, coverage, deferrals, duplicates and cost per usable item; raw artifacts stay local and the limits of new-content quality evidence are explicit. | [#4](https://github.com/montagovian/basedBench/issues/4), [#7](https://github.com/montagovian/basedBench/issues/7) |

The legacy `consensus-eval` now explicitly reports Boolean agreement rather than
claiming explanation correctness. The separate `answer_eval` workflow checks
written meanings, generates answers, attempts bounded repairs and verifies them
against images/comments. Its development results expose false alarms and shared
model blind spots; its model approvals are not an unattended quality guarantee.

The [pilot policy](admission-pilot.md) preserves suitability findings without
requiring perfect agreement with every historical tough reject. It defines a
minimum recoverable joke task and retains a deferral path. No model agreement, confidence score or
absence of a detected defect should be reported as independent proof of quality.

## After a useful pilot

The decision from #8 remains to revise before expanding. The bounded experiments
in [#16](https://github.com/montagovian/basedBench/issues/16) and
[#17](https://github.com/montagovian/basedBench/issues/17) are complete. The
[answer results](connection-comparison-results.md) do not justify promoting the
heavier checker or an unseen admission validation yet. The
[duplicate results](duplicate-comparison-results.md) support broader image
retrieval and retaining both text evidence views, with explicit adjudication.
Expansion in #9 still requires a later decision. This does not reopen the frozen
pilot, tighten discretionary suitability, or require a broad human-review queue.

| Issue | Work item | Done when | Depends on |
| --- | --- | --- | --- |
| [#9](https://github.com/montagovian/basedBench/issues/9) | Expand chronological backfill with coverage accounting | Resumable date batches account for discovered content, missing periods, processing outcomes and budget; policy changes create new versions. | [#8](https://github.com/montagovian/basedBench/issues/8) and an explicit decision to expand |
| [#10](https://github.com/montagovian/basedBench/issues/10) | Freeze and evaluate the candidate release | Membership, images, explanations and policy versions are immutable; automated versus human admission provenance is preserved; legacy and new-set results are reported separately; an honest evaluation design accounts for prior test exposure. | [#8](https://github.com/montagovian/basedBench/issues/8) for preparation; [#9](https://github.com/montagovian/basedBench/issues/9) for the larger release |
| [#11](https://github.com/montagovian/basedBench/issues/11) | Define a small tag vocabulary and coverage report | Existing tags are inventoried; a bounded set gets definitions and versioned assignments; missing tags are not treated as negatives; coverage can be inspected without imposing a new selection rule. | Can follow [#8](https://github.com/montagovian/basedBench/issues/8); not a prerequisite for the pilot |

Details: [backfill plan](automated-backfill-plan.md),
[classifier plan](classifier-experiments-plan.md),
[tagging plan](tagging-taxonomy-plan.md).

## Parked ideas

| Issue | Idea | Revisit when |
| --- | --- | --- |
| [#12](https://github.com/montagovian/basedBench/issues/12) | Further value-prompt optimization, GEPA, or task-specific classifier adaptation | A pilot exposes consequential selection errors and there is a coherent target to optimize; exact imitation of discretionary rejects alone is insufficient justification. |
| [#13](https://github.com/montagovian/basedBench/issues/13) | BasedBench AfterDark | There is a concrete decision about an opt-in collection, its boundaries and separate reporting. Current borderline cases do not establish that policy. |
| [#14](https://github.com/montagovian/basedBench/issues/14) | Topical memes as a knowledge-recency probe | The core release is in hand; retain event-date evidence and distinguish knowledge needed from context already supplied by the image. Breadcrumb only. |

Changing prediction judges and recurring automatic ingestion also remain later
work. They should not delay the first useful backfill batch.

## Completed foundation

- [Targeted explanation comparison](connection-comparison-results.md): 28 exposed
  cases, 92 Luna calls, 20.0¢; three useful verified repairs and retained controls,
  with decoding, intent and substantive-support failures still visible.
- [Bordered-copy comparison](duplicate-comparison-results.md): 56 local records,
  20 pair controls, no paid calls; missed copy recovered through image and text,
  with known false matches and a lost semantic family link kept separate.

- [Fresh-batch assessment](backfill-pilot-results.md): 100 candidates, 195 Luna
  calls, 23.3¢; all 54 model-reached cases inspected separately, with clear
  denominators, source gaps, concrete weaknesses and follow-up decisions.

- [Resumable admission pilot](admission-pilot.md): versioned components, bounded
  repair and spending, preserved human judgments and zero-call offline replay.
  Six controls produced two automatic accepts, one rejection and three deferrals;
  the evidence-count restriction and a verifier inconsistency remain visible.
- [Duplicate and joke-family audit](duplicate-audit.md): local image and text
  retrieval, no paid calls; exact-copy evidence is separate from candidate
  family links, publication membership and intrinsic quality.

- [Publication-content findings and routes](content-policy-pilot.md): 102 Luna
  image calls, about 12¢; all three definite exclusions caught by the revised
  check, 21/23 clear passes retained and two deferred too cautiously.
- [Bounded source inventory](backfill-source-inventory.md): 100 fresh candidates
  from June 20–26, with images/comments, source coverage and retrieval gaps
  recorded locally; no model calls or admissions.
- [Answer construction, checks and bounded repair](answer-quality-results.md):
  119 new provider calls, about 13¢; all four selected known defects detected by
  the detailed checker, with false alarms and verifier misses recorded separately.
- Frozen historical corpus, provenance/history audit and comparison harness.
- Word-count, TF-IDF, frozen-encoder and JEV/LLM diagnostic comparisons.
- Review gallery and 28 completed multidimensional human reviews, plus earlier
  conversational corrections and unresolved judgments.
- [Enriched-label comparison](curation-enriched-results.md): 140 calls, about 8¢.
- [Value prompt/evidence comparison](curation-value-experiment.md): 224 calls,
  about 1.2¢; the best default verdicts caught one of five value negatives while
  keeping 17 positives. This is completed research, not a production-quality gate.

Fresh source collection and the first bounded development admission assessment
are complete. No candidate release has been completed.

## Ticket workflow

Use **GitHub Issues in the existing repository** for actionable work and its
status. The [roadmap tracker](https://github.com/montagovian/basedBench/issues/15)
groups six pilot issues, three later work items and three parked ideas. Keep
the approved plans and experiment reports in `docs/` as the supporting record.

Start with the six pilot issues above. Later/Parked titles distinguish future
work and do not imply that those items block the pilot. Close the pilot tracker
when the first batch has been assessed and the next decision recorded; future
issues can remain open. No standalone project-management product is required.

Each ticket needs the problem/outcome, a short completion checklist, dependencies,
and links to relevant plans or results. Experiments also need a hypothesis,
comparison, success measure and cost cap. Update the ticket when work produces
a result, including a negative result; finishing an experiment does not require
its hypothesis to succeed.

Update work status and link implementation/results on the corresponding issue;
avoid maintaining two competing status lists. Keep raw corpus data, images and
private operational logs out of public issue bodies.
