# Historical curation evaluation

This implements the first execution slice of the
[automated backfill plan](automated-backfill-plan.md): recover historical inputs,
freeze a local corpus, and establish a reproducible admission baseline. It does
not yet replace human review in the ingestion pipeline.

## Run locally

No API keys or network calls are required after installing dependencies.

```bash
uv sync --extra curation
uv run --extra curation basedbench curation build \
  --db data/basedbench.db \
  --project-root . \
  --output data/curation/historical-v1
uv run --extra curation basedbench curation baseline \
  data/curation/historical-v1 \
  --output data/curation/runs/tfidf-v1
```

Use a new output directory for each corpus or run. Commands refuse to replace
existing outputs. All records, images, model weights, and predictions belong
under ignored `data/`; commit reusable code and aggregate methodology only.

The builder opens an existing SQLite database read-only and reads all selected
rows in one transaction. It runs no migrations, changes no reviews, and loads no
credentials. Assets are copied into the corpus; subsequent work does not depend
on mutable image paths in the live database.

## Evidence and labels

The initial candidates are `validated` reviews and exclusions with the exact
reason `other`. Known automated exclusions, technical errors, and unreviewed
items are not manufactured into human suitability labels.

`other` defaults to **inferred manual** provenance. Pass
`--other-confirmed-manual` only after establishing that these are manual
decisions. This annotation describes provenance, not an inferred reason for
rejection. A historical exclusion remains an overall admission label; it does
not imply independently verified failures of consensus, explanation, or safety.

For each candidate, the builder requires exactly one successful consensus call
within two seconds of the ground truth's generation timestamp and no later
than the review. Ambiguous or missing calls, invalid responses, and missing or
unreadable images go to `quarantine.jsonl`, outside the training/evaluation set.

Model inputs use the original logged explanation and comment prompt, with author
names removed from comment headers. They never substitute later corrected
explanations or today's comment scores. The complete original prompts and response
remain in a separate provenance object in the local record. Review labels,
reasons, generation metadata, and later model scores are excluded from feature
construction through an explicit input allowlist.

There are two remaining reconstruction limitations: the exact text displayed
at review time was not versioned, and image bytes are frozen as found now rather
than proven identical to the historical image. The manifest states both. A
difference between the original and current gloss is counted explicitly.

## Grouping, splits, and integrity

Image bytes are grouped by SHA-256. Conservative near-image matches also require
aspect ratio difference at most 0.02, dHash distance at most 4, aHash distance at
most 2, and mean pixel difference at most 4 on resized images. Identical
normalized explanations and explicit family overrides join groups transitively.

An optional `--families path.json` accepts a map of post IDs to shared joke-family
IDs. Unknown IDs are rejected. Image similarity and identical explanations do
**not** establish complete semantic joke-family isolation; grouping remains
provisional until that work is complete.

Groups are indivisible. A deterministic greedy allocation targets 70% development,
15% calibration, and 15% final test while balancing both labels. Larger groups
are placed first, followed by seeded hash order. Previously examined consensus
regressions, eval cases, and gate-feedback cases, including their whole groups,
are confined to development. Conflicting labels within a group are counted and
preserved rather than silently relabeled.

`manifest.json` records file hashes, builder/fingerprint code hashes, Pillow
version, grouping method, seed, label provenance, source inventory, split counts,
and limitations. The corpus ID hashes this content, excluding creation time.
`examples.jsonl` separates model `input` from `label` and `provenance`; every input
has its own hash. `assets/` contains the frozen image bytes. The loader verifies
the manifest and payloads and rejects duplicate IDs, input hash mismatches,
missing image assets, or groups crossing split boundaries.

## Baseline and result contract

The first baseline is word unigram/bigram TF-IDF followed by logistic regression
with balanced class weights, `C=1`, and a fixed random seed. The vocabulary and
classifier are fitted only on development. Only calibration is scored; the
command deliberately has no final-test option. The baseline sees the original
explanation and comment evidence, with no access to image pixels.

Every result records the post and input hash, model/version, score, decision,
diagnostics, error, and available latency/cost. Scores are backend-specific and
are not assumed calibrated. High scores accept, low scores reject, and the
interval between the thresholds defers. Errors also defer and retain an error
field. The corpus still has only the two historical labels.

Each run saves the trained estimator, normalized per-item decisions, a JSON
report, and a readable Markdown report. Parameters, package versions, evaluator
source hash, model hash, training/evaluation ID hashes, and batch timings are
recorded. Accept-all and reject-all controls accompany precision, positive
retention, false accepts/rejects, deferrals, errors, and Brier score.

The acceptance threshold sweep is exploratory calibration. Zero accepted items
means undefined precision and zero positive retention, not perfect accuracy.
Reported Wilson intervals assume independent items; they do not correct for
family dependence or threshold selection and cannot qualify a release.

## Execution checkpoint: September 18, 2026

The current local corpus (`historical-v2`) includes 1,904 of 1,915 candidate
decisions: 519 accepted and 1,385 rejected. Eleven exclusions have no local image
path and are quarantined. There are 1,886 image/explanation groups; eight groups
containing 17 examples have conflicting decisions. One current explanation
differs from the recovered original. Twenty-seven previously examined examples
are assigned to development with their groups.

| Partition | Accepted labels | Rejected labels | Total |
| --- | ---: | ---: | ---: |
| Development | 363 | 969 | 1,332 |
| Calibration | 78 | 208 | 286 |
| Final test | 78 | 208 | 286 |

`historical-v1` and its baseline were initial smoke-test artifacts using an
unstratified hash split. Version 2 supersedes them with the documented stratified
allocation. Neither run scores final-test examples. Results are provisional
pending confirmation of `other` provenance and semantic family grouping.

On version 2's calibration split, TF-IDF at an acceptance threshold of 0.5
accepts 38 items, including 10 historical positives: **26.3% precision and
12.8% positive retention**. Accepting everything gives 27.3% precision. The
model accepts nothing at the tested thresholds of 0.7 or higher; with the
default 0.9/0.1 thresholds, all 286 items defer. This fixed configuration does
not support unattended admission. It does not settle the performance of other
text classifiers or more informative representations.

The next comparison is a frozen text encoder on the same evidence, with explicit
handling of comment lengths and checkpoint pinning. More complex classifiers
should earn their place through better precision at useful retention; the
baseline and corpus alone do not establish readiness for unattended admission.
