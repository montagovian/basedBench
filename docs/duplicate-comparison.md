# Bordered-copy retrieval development comparison

Issue [#17](https://github.com/montagovian/basedBench/issues/17). Predeclared
September 22, 2026, before running this comparison. Complete the explanation
comparison in #16 first. **No paid model calls; $0 model cost.**

## Fixed comparison

Preserve `duplicate-audit-v1` and its old outcomes. The regression packet selects
all three recorded families, all three prior archive visual controls, all twelve
prior fresh-pair inspection controls, every exact fresh pair from the audit, the
missed `1ue5z6v` / `1uczut7` pair, and the published animated-image control. Include
available model-supported, assistant-inspected explanations from #16's fixed
28-case packet as additional queries. This deterministic selection does not use
new retrieval outcomes; report its final row/pair counts and excluded explanations.

Compare baseline image retrieval with additional aspect-matched windows. Match
a full image against 100% and 95% scale windows having its aspect ratio in the
other image, at start/center/end positions. Windows retain at least 30% of the
source area. Work at up to 512 pixels per side, preserve original crop coordinates,
keep both existing hash thresholds at eight, and require mean RGB difference at
most 18 for the new windows. Keep the existing top-five-per-pool cap. These
parameters are fixed before the experiment, not tuned to make its cases pass.

The image experiment searches all pairs within this small packet. Its rankings
are therefore not claimed to reproduce a full-corpus image audit. Record the
original full-audit retrieval separately and recompute a packet baseline using
the same comparator and ranking pool as the broader method.

For the semantic comparison, retain the full frozen text pool, MiniLM revision,
0.65 threshold and top-five-per-pool cap. Replace only the text of #16 cases
that are model-supported and have no concrete material explanation defect on
separate assistant inspection. Compare old sampled comments/stored answers with
those explanations. Retain source hashes and development provenance; this is
not human validation or a claim that the old text is gold. No encoder training,
downloads, API requests or threshold search. New links outside the packet remain
unadjudicated and are counted separately.

## Measures and decision

Success means retrieving the bordered copy while retaining the earlier exact
copy and three known families, without upgrading shared templates/topics or
unseen image matches into automatic copies. Report control-pair retrieval by
method, newly retrieved distractor pairs, unresolved links, static/missing/
animated image coverage, semantic changes with their smaller replacement
denominator, local wall/CPU time, and zero paid-call cost. Do not report selected
control performance as corpus precision/recall. A crop match is candidate
evidence even when its pixel difference is tiny; the discarded text may change
the joke. Exact original bytes/pixels retain their separate identity evidence.

Explicit assistant copy/family inspection stays separate from scores and from
historical human labels. Distinguish a published redundant copy from an archived
unpublished counterpart. Record representative-selection options and family
split/exposure implications, without choosing keepers, altering frozen outcomes,
changing splits or publishing. A negative experiment is a completed result.
Any later paid comparison requires its own explicit plan and cap.

```sh
uv run python -m basedbench.pipeline.duplicate_comparison prepare \
  --explanations data/backfill/connection-analysis-v1/supported-explanations.json \
  --output data/backfill/duplicate-comparison-v1
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 uv run python \
  -m basedbench.pipeline.duplicate_comparison run \
  --output data/backfill/duplicate-comparison-v1
```
