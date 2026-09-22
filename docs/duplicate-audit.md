# Duplicate and joke-family audit

Issue [#6](https://github.com/montagovian/basedBench/issues/6).

The pilot now has a read-only duplicate audit. It distinguishes an exact copy,
a possible repeat and an item it could not assess. None of those is a finding
about whether the meme is good, safe or correctly explained.

## What the check does

- Compare every available fresh image against the archived images and the other
  fresh images. Equal file bytes or equal full decoded pixels establish a copy.
  Re-encoding a PNG without changing its pixels still counts as an exact copy.
- Search original and border-trimmed views using perceptual hashes. Rank nearby
  images by pixel difference after resizing. Border removal and resizing are
  retrieval aids: they can discard meaningful differences, so these matches
  remain candidates even when the similarity is very high.
- Compare stored legacy explanations with up to five substantive fresh comments,
  using both word/phrase overlap (TF-IDF) and the pinned local MiniLM encoder.
  The encoder reads long text in chunks without dropping tokens. These methods
  retrieve possible repeated jokes; neither determines that two jokes are equal.
- Preserve the matching post IDs, image hashes, compared crops, distances,
  text-similarity scores, comment IDs and published-release membership. Matches
  against excluded historical items are visible; they do not automatically
  eliminate a fresh candidate.

Both image and text retrieval retain up to five matches **per query, per pool**
(legacy and fresh). Exact matches are uncapped. Image retrieval requires both
64-bit hash distances at most eight; text similarity floors are 0.35 for TF-IDF
and 0.65 for MiniLM. These are exploratory retrieval settings, not calibrated
probabilities or production acceptance thresholds.

Fresh comment selection uses at least 40 characters, excludes moderator comments,
and sorts by score then comment ID. It is a bounded evidence sample, not a
consensus determination. It omits titles and curator labels. Legacy explanations
may themselves be defective. Neither shared topic nor shared template establishes
a repeated punchline. The semantic comparison should be repeated on supported
candidate explanations once the answer workflow has produced them.

## Consequences for admission and later splits

An exact match establishes that two records contain the same image, **not which
record to keep**. Release membership, explanation correctness, content policy,
image quality and later collection policy still matter. In particular, matching
an excluded historical record does not mean the joke is already published.

The report's `copy_found`, `review_matches`, `no_match_found` and `not_assessed`
values are duplicate-component findings, not accept/reject decisions. Per-item
image status remains explicit even where text retrieved a match. Missing images
must still defer in the admission workflow. No match found does not prove novelty.

`split_audit(assignments, edges)` joins confirmed copies and previously reviewed
families into indivisible groups, including links through unassigned members.
An unresolved similarity link crossing those groups' proposed splits holds the
split for adjudication; it does not silently merge families. Once reviewed,
same-joke pairs can become confirmed edges and different-joke pairs can be removed
from the pending constraints, retaining their evidence and decision provenance.
The existing frozen evaluation splits are not rewritten. This is a scoped audit,
not proof that the entire archive is free of family leakage.
With no proposed assignments, split readiness is unassessed (`null`), not a pass.

For #7/#8, consume the frozen report by audit ID, retain each match and its
published-membership evidence, and distinguish potential redundancy from intrinsic
suitability. Do not call the old `auto_exclude_duplicate_images` helper: its rule
of excluding matches to any reviewed item is not the new pilot's admission policy.
Retain uncertain pairs outside automatic admission until a bounded decision rule
can resolve them. Deferral need not create a mandatory human queue.

## Reproduce locally

Raw images, frozen evidence, vector arrays and match records stay under ignored
`data/`. The database is opened read-only. The audit does not write reviews,
answers, release membership or human feedback, and it makes no network requests
or paid inference calls. MiniLM must already be present in its pinned local cache.

```sh
uv run --no-sync python -m basedbench.pipeline.duplicate_audit prepare \
  --inventory data/backfill/inventory-june20-26-v1 \
  --output data/backfill/duplicate-audit-v1
uv run --no-sync python -m basedbench.pipeline.duplicate_audit run \
  --output data/backfill/duplicate-audit-v1
```

Preparation verifies the source inventory manifest and freezes the read-only
archive records, fresh comment sample, image fingerprints, thumbnails and known
family controls. It records source/code hashes, model revision, library versions
and retrieval settings. Rerunning uses those frozen records and thumbnails,
verifies their hashes, and recomputes the local retrieval; it does not collect
new evidence. Changed code or inputs require a new run directory.

The model is `sentence-transformers/all-MiniLM-L6-v2`, revision
`1110a243fdf4706b3f48f1d95db1a4f5529b4d41`, loaded locally on CPU. The existing
chunked encoder implementation is reused; there is no fitting to review labels.
