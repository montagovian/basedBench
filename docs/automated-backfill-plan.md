# BasedBench next major version: automated curation and backfill

Prepared September 18, 2026. Status: agreed direction and proposed implementation
plan. No classifier experiments or new backfill runs have been performed for
this proposal.

Companion plans for separate review:

- [Classifier experiments](classifier-experiments-plan.md): staged comparisons
  of encoders, label-conditioned classifiers, LLMs, and multimodal approaches.
- [Tag vocabulary and assignment](tagging-taxonomy-plan.md): discover useful
  categories, apply them consistently, and evolve them across releases.

## Objective

Build the next major BasedBench release primarily from content accumulated
since the original release, with no routine human inspection required to admit
individual items. Use the existing human-reviewed corpus to develop and evaluate
the decisions that make this possible.

The first milestone is automated curation. Jev is a candidate component, and
improving prediction judges remains valuable, but the immediate bottleneck is
deciding which newly collected memes deserve to enter the evaluation set.

Success means admitting a useful volume and range of new items at a measured
historical error rate, with explicit evidence for each decision and no review
queue that must be cleared before processing can continue. New-content quality
claims must reflect the evidence actually available.

The benchmark continues to ask whether a model **gets the joke**: identifies the
relevant references and reconstructs the intended setup, implication, contrast,
irony, wordplay, or other mechanism. It does not ask for a psychological theory
of amusement or a judgment of aesthetic quality. Predictor inputs remain the
image alone.

## Why this is the next step

The [launch post](https://www.montagovian.com/basedbench.html) describes the ambition
to turn BasedBench into a dynamic benchmark, and identifies filtering as the
main obstacle. Approximately 2,000 memes were reviewed to obtain 519 accepted
items. Roughly 1,400 were rejected for lacking a meaningful joke, being trivial,
or otherwise failing to suit the task.

That review work is a potential training and evaluation resource. The September
18 local database inspection found:

| Resource | Count | Proposed use |
| --- | ---: | --- |
| Validated items | 519 | Positive historical admission labels |
| Exclusions recorded as `other` | 1,396 | Candidate negative admission labels, after provenance checks |
| Explicit legacy quality auto-exclusions | 2,212 | Weak labels and diagnostic cases, separate from human decisions |
| Explicit safety auto-exclusions | 206 | Safety diagnostics, not human suitability labels |
| Ground truths without a review | 498 | Unlabeled replay material, not gold references |

The `other` count closely matches the launch account, but the review table has
no explicit actor field. Confirm provenance before treating all those rows as
human labels. Preserve uncertainty rather than reconstructing an authoritative
reason from a model's guess.

The existing code also mixes some suitability rules into consensus: a post can
be marked as having no consensus because it is only one-step decoding or pure
scrambled nonsense. The new design should represent agreement and suitability
separately. People can agree about a meme that does not belong in BasedBench.

## The decisions we need to automate

An item is admitted only after all required checks pass. Classifiers should
return individual findings and supporting evidence, not just an opaque quality
score.

| Decision | Question | Evidence |
| --- | --- | --- |
| Publication suitability | Does it satisfy the existing publication policy? | Text and image-aware checks |
| Consensus | Do qualifying comments support the same interpretation? | Comment roles, supporting IDs, contradictions, deterministic counts |
| Explanation fidelity | Does the proposed ground truth accurately express that interpretation? | Source comments, claim support, consistency with the image |
| Benchmark suitability | Does it present a meaningful, nontrivial, fairly scorable understanding task? | Image, grounded explanation, supplied-context requirements |
| Contribution to the set | Does it add useful coverage without excessive repetition? | Accepted corpus, duplicate candidates, content categories |

Benchmark suitability should expose at least these dimensions:

- **Meaningful understanding:** a specific reference, implication, relationship,
  or mechanism must be recovered to get the joke.
- **Nontrivial understanding:** the item meets the intended curation standard
  for humans; reproduce the distinctions present in historical decisions before
  inventing a new hardness threshold.
- **Answerability:** the supplied image contains the necessary setup. Cultural
  knowledge is allowed; a missing caption, missing panel, or unavailable private
  backstory is a different issue.
- **Scorability:** equivalent correct explanations can be accepted and material
  misunderstandings can be distinguished. A precise-looking gloss is insufficient
  if the item itself supports unresolved alternative readings.

Difficulty and model success should be recorded separately. The launch includes
204 examples solved by all five tested models. Current model failure is neither
a prerequisite for admission nor proof that an item is valuable. Avoid selecting
the main set using the performance of the models it will rank.

Contribution is a corpus-level decision. A good individual item can still be
redundant with already selected items. Record this reason separately from an
intrinsic defect so the item can be reconsidered for another release.

## What hands-off operation means

The proposed runtime flow is:

```text
Collect and validate assets
  -> publication checks
  -> recover consensus and draft a grounded explanation
  -> verify evidence and image consistency
  -> assess benchmark suitability
  -> apply duplication and corpus-selection rules
  -> accept / reject / defer
  -> freeze accepted content for prediction, judging, and release preparation
```

- **Accept:** required checks pass under a frozen, calibrated policy.
- **Reject:** evidence supports a specific exclusion under that policy.
- **Defer:** uncertainty, conflicting evidence, or incomplete processing prevents
  a supported decision. A bounded retry, additional evidence retrieval, or
  stronger automated assessment may resolve it; otherwise it stays outside the
  release while processing continues.

Deferral is not a mandatory human-review queue and is not a negative training
label. Technical failures remain distinguishable from semantic uncertainty.
Optional audits and manual overrides remain possible, but neither is a required
per-item runtime dependency.

An automated admission must not masquerade as a human validation. Store the
decision's origin and policy version explicitly. Snapshot eligibility must
support both historical human approvals and qualified automated admissions,
while preserving their different provenance.

## Milestone 1: recover and evaluate the historical curation policy

Create a frozen local corpus of inputs, decisions, and provenance. Keep working
data under `data/`; do not commit images, raw comments, review rows, or call logs.

1. Identify human decisions, automated decisions, unresolved provenance, and
   unreviewed items. Exclude known technical failures from suitability labels.
2. Preserve the original overall decision. Separate any recorded reason from a
   model-inferred explanation of that decision.
3. Check which inputs were available at review time. A corrected explanation
   created later may not explain an earlier rejection. Where the historical
   input cannot be reconstructed, mark that limitation.
4. Group duplicate images and repeated joke families before splitting. Reserve
   distinct development, calibration, and final-test partitions. Use review or
   source chronology for an additional temporal check where sample size permits.
5. Freeze exact inputs, labels, groups, splits, and versions in a manifest.

The initial prediction target is **the historical overall admission decision**.
A rejection could reflect suitability, a wrong gloss, a broken image, or another
issue. An undifferentiated rejection is not gold supervision for every component
classifier. Component evaluation needs the corresponding explicit labels or
separately identified reference cases.

Historical examples can support prompt development, retrieved examples,
threshold calibration, and supervised classifiers. Keep retrieval indexes and
training data confined to the development partition. Never supply historical
decisions, review reasons, or subsequent model scores as classifier input when
they are the target or would be unavailable for a fresh candidate.

**Deliverable:** a reproducible curation evaluation corpus, with a provenance
report and untouched test partition. This starts from existing decisions and
does not require a new annotation campaign.

## Milestone 2: compare classifiers and admission workflows

Use one evaluation harness for the following candidates:

| Candidate | Role in the experiment |
| --- | --- |
| Current pipeline decisions | Historical operational baseline |
| Current and updated general-purpose LLMs | Direct and decomposed classification baselines |
| Jev | Focused classification using explicit criteria and available evidence |
| Simple supervised classifier | Test what historical labels support with a modest model, such as embeddings plus a linear classifier |
| Automated cascade | Test whether bounded escalation improves the quality/coverage tradeoff |

Jev's documented interface supports request-defined questions and typed answers.
Using historical data to improve criteria and calibrate decisions does not depend
on custom Jev training. Do not assume a fine-tuning capability as a prerequisite.
[TypeSafe primitives](https://docs.typesafe.ai/primitives)

Keep model substitution and workflow redesign as separate experiments. Compare
backends on identical evidence first; then compare direct admission decisions
with decisions decomposed into the checks above. Apply comparable development
effort to each candidate. Image-aware verification and any generated image
descriptions are additional model contributions that must be measured, including
their errors and cost.

Use a generative model where interpretation proposals or explanation writing
are necessary. Classify whether comments support those proposals, validate IDs,
and count eligible support in code. Verify the final explanation after writing;
selecting the right evidence does not prevent unsupported additions during
generation. Jev's documented limitations make precise questions and direct
evidence particularly important. [Jev limitations](https://docs.typesafe.ai/model-jaggedness/jev-1.13)

For every decision, retain model and policy versions, input hashes, outcomes,
probabilities where available, evidence IDs, error/abstention state, latency,
usage, and escalation history. Store audit detail locally.

The main report should expose:

| Measure | Meaning |
| --- | --- |
| Historical acceptance precision | Fraction of automatically accepted labeled items that humans accepted |
| Positive retention | Fraction of human-accepted items that the policy automatically accepts |
| Coverage and deferral | How much of the candidate pool reaches each outcome |
| End-to-end defects | Wrong explanations, unsupported consensus, visual mismatch, or other known admission failures |
| Slice coverage | Which reference types, joke mechanisms, sources, and periods are lost or retained |
| Total cost and throughput | All preparation, verification, retries, and fallback calls per admitted item |

Report quality versus coverage, with uncertainty grouped by meme/joke family.
Measure final cascade behavior on the cases it actually escalates. A confident
score or several agreeing models is a signal to evaluate, not a substitute for
reference labels. Do not multiply component probabilities to claim a verified
end-to-end correctness rate.

Historical decision agreement measures imitation of past curation, not proof
that every historical decision or explanation was correct. Use existing gloss
failures and consensus feedback to test distinct known defects. Repair the
current consensus evaluation gap: matching `has_consensus` alone must not count
as evidence that an explanation is correct.

Set acceptable error, useful yield, and operational cost targets after the pilot
and before opening the final test. Avoid selecting an arbitrary confidence
threshold and calling it a quality guarantee. If evidence is insufficient,
retain a provisional result rather than claiming the target was established.

**Deliverable:** a held-out comparison and a versioned admission policy, including
the evidence for its threshold and the conditions that cause deferral.

## Milestone 3: backfill newer content with a frozen policy

Define the desired source-date interval explicitly. The published 519-item
snapshot was created July 15, 2026, but its newest included source post is June
6. The local archive contains posts through June 19, with its latest retrieval
on June 20. A snapshot date alone is therefore not the correct discovery cursor.

Use the original release's source coverage and the desired launch-to-present
scope to choose the interval, allowing overlap and deduplication where needed.
The repository already supports date-range ingestion through PullPush discovery
and Reddit comment retrieval; current availability and coverage still need an
implementation-time check.

Process bounded chronological batches with persistent progress and explicit
completion state. Record source coverage, fetched candidates, missing assets,
failed requests, stage outcomes, and reasons. A failed archive request or
pagination limit must not silently become “no posts in this period.” Reruns
should resume or reproduce work without silently replacing historical decisions.

Freeze the policy before the first evaluation batch. Changes discovered during
backfill get a new version and a fresh evaluation; do not silently tune against
the same results used to claim success. Enforce bounded spending and escalation
so uncertain cases cannot produce an unlimited loop.

Monitor acceptance and deferral rates, evidence strength, category coverage,
duplicate rates, visual-check failures, and cost across dates. Fresh posts can
also be reposts of old jokes; record freshness and novelty separately.

Existing human labels establish performance on historical material. Without
new human inspection, drift signals and automated agreement on newer content
do not independently establish its error rate. The release should state that
limitation. A bounded future audit could strengthen the evidence, but it is not
a required step in the normal admission path.

**Deliverable:** a reproducible backfilled candidate release with frozen content,
automated admission provenance, deferred items retained locally, and a batch
coverage and quality report.

## Release comparison and later work

Preserve the legacy 519-item release and its published results. Report performance
on the legacy set, the new backfill, and any combined release separately.
Evaluate scoring changes on fixed memes and predictions so their effects can be
distinguished from changes in dataset composition.

A new release manifest should freeze image hashes, ground-truth text, membership,
policy versions, and relevant scoring versions. IDs that later resolve to mutable
records are insufficient. Public documentation must distinguish human-validated
legacy items from automatically admitted additions and continue to omit private
operational data.

Judge replacement, richer diagnostic tags, and recurring ingestion follow the
curation milestone. A successful bounded backfill provides the foundation for
later scheduled runs using the same admission policy and reporting.

The next implementation task is to build the frozen historical curation corpus
and common evaluation harness. Use its results to decide which classifiers and
which automated admission workflow earn a place in the backfill pipeline.
