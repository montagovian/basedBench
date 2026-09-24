# Chronological backfill operations

The [execution plan](chronological-backfill-plan.md) records the authorized
June 27–July 26, 2026 UTC window, at most 1,000 new qualifying IDs, and $10 total
model-call ceiling. These additive modules preserve the earlier pilot versions.
Do not use the legacy ingestion or tracer commands for this run.

The commands below show one run directory. Run them from the project whose
private `data/` and `.env` are being used, with the tested code environment.
Preparation makes no paid calls. A prepared directory cannot be overwritten.

```sh
uv run python -m basedbench.pipeline.chronological_inventory prepare \
  data/backfill/chronological-june27-july26-v1/inventory \
  --database data/basedbench.db --snapshot basedBench-519-2026-07 \
  --start 2026-06-27 --end 2026-07-27 --ceiling 1000 \
  --prior-inventory data/backfill/inventory-june20-26-v1

uv run python -m basedbench.pipeline.chronological_inventory run \
  data/backfill/chronological-june27-july26-v1/inventory
```

Read the inventory report before processing. An explicit service refusal ends
archive access and preserves unattempted partitions; it does not authorize another
endpoint, paid service or a fresh directory to bypass the stop. Missing images,
partial comments and source discrepancies stay attached to selected identities.
If no candidates are collected, record the source stop and make no model calls.

```sh
uv run python -m basedbench.pipeline.chronological_duplicates prepare \
  --database data/basedbench.db \
  --inventory data/backfill/chronological-june27-july26-v1/inventory \
  --prior-inventory data/backfill/inventory-june20-26-v1 \
  --families data/backfill/chronological-june27-july26-v1/known-families.json \
  --output data/backfill/chronological-june27-july26-v1/duplicates

uv run python -m basedbench.pipeline.chronological_duplicates run \
  --output data/backfill/chronological-june27-july26-v1/duplicates \
  --model-cache data/curation/models

uv run python -m basedbench.pipeline.chronological_admission prepare \
  --inventory data/backfill/chronological-june27-july26-v1/inventory \
  --duplicates data/backfill/chronological-june27-july26-v1/duplicates \
  --output data/backfill/chronological-june27-july26-v1/admission \
  --budget-usd 10

uv run python -m basedbench.pipeline.chronological_admission run \
  --output data/backfill/chronological-june27-july26-v1/admission \
  --budget-usd 10
```

The duplicate encoder is pinned and loads locally. Exact image copies and
uncertain image, crop and text matches remain distinct. Crops are searched on a
bounded set of coarse image neighbors; this is not exhaustive family detection.
This run's private known-family file preserves the original three groups and the
two subsequently human-flagged, image-inspected pairs. Its adjacent provenance
file binds the original feedback, inspection records and source hashes. Unresolved
overlap findings are not added as confirmed groups.

Admission uses one frozen ledger for every case and stage. The cap is a maximum,
not a target. `--stop-after-new-calls N` can deliberately checkpoint processing;
resume the same output with the same cap. Never allocate another output directory
to obtain another allowance from the same authorization. Unknown or interrupted
paid requests retain their conservative reservations and are not repeated.

Completed `run` commands verify manifests and return their saved reports without
network calls. Changed code or frozen inputs require investigation and a distinct
version; do not edit manifests to conceal changes. Keep all raw sources, images,
model requests/responses, reviewer evidence and logs under private `data/`.

Reports retain the whole selected denominator, technical failures, independent
content/answer/suitability/duplicate findings and actual versus conservatively
accounted model cost. Automatic acceptance does not qualify release membership.
The original database and immutable 519-item release remain unchanged.
