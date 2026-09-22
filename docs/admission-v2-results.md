# Duplicate evidence integration results

September 22, 2026 · [Issue #19](https://github.com/montagovian/basedBench/issues/19)

**The bordered copy now blocks automatic uniqueness in admission v2.** Offline
replay changes only its two members from accept to defer; the other 98 outcomes
are unchanged. This completes the [bounded integration](admission-v2.md), with
**zero new provider calls and $0 new model cost**.

## Version and outcome changes

The wrapper retains the original answer, content and suitability components and
changes only duplicate evidence to `duplicate-evidence-union-v2`. It preserves
every original audit edge and evidence record, adding the measured image-window
links and both semantic views. All new retrieval stays at candidate status.

| Frozen development outcome | Original v1 | New v2 replay |
| --- | ---: | ---: |
| Accept | 43 | 41 |
| Reject | 1 | 1 |
| Defer | 56 | 58 |

`1ue5z6v` and `1uczut7` now have aspect-window and supported-explanation evidence
and defer for an unresolved duplicate match before reaching model checks. Their
original accepts and answers remain untouched. This holds two records for a
future one-representative decision; it does not establish that both memes should
be discarded or that their explanations are wrong.

The replay reuses **187** original call records after verifying exact request,
input, experiment and response provenance. The original run made 195 calls; eight
saved calls belong to the two newly blocked candidates and are not needed by this
replay. There is no provider client in the wrapper. If a necessary historical call
is absent, it defers rather than requesting one. Historical spending remains
visible as inherited cost, never counted as new spending.

## Evidence and coverage

The merged graph has **74 pairs versus 39 originally**. All original evidence and
adjudication statuses survive, including TF-IDF links, exact-copy identity and
recorded families. Of the 35 added pairs, 34 are historical diagnostic links and
one is the fresh bordered pair. New retrieval does not convert a crop or semantic score into
confirmed redundancy. The Magic Johnson/Freddie possible family link lost by
supported-text replacement remains present through the original text view.

Expanded image evidence retains the experiment's **56-post packet** scope.
Semantic retrieval retains its **52 queries against 2,634 records**. Among the
100 pilot candidates, 27 belong to that packet, 25 have static images assessed
there and 25 have semantic comparison queries. Per-candidate coverage is explicit;
this is not a new full-corpus crop audit or a general-recall result. Missing and
animated images are not made assessed by semantic links.

Published exact identities retain their distinct routing; unpublished counterparts
and possible families cannot become published-copy exclusions. Same-template/topic
false matches remain candidates requiring adjudication. Existing human disagreement
guards are exercised by regression tests and remain unchanged.

## Decision and verification

Carry this versioned evidence-union interface forward. Before wider use, run the
expanded retrieval against the actual new batch and its comparison pool; this
packet overlay cannot establish coverage for unseen candidates. Keep explicit
family/copy adjudication and representative selection separate.

This replay inherits v1's answer weaknesses and does not promote
[#18's unsuccessful checker](claim-comparison-results.md). The 41 automatic
accepts are development outcomes, not a newly validated release or an authorization
to expand #9. No keepers, splits, human labels, old outcomes or publication
membership changed.

Local artifact: `data/backfill/admission-june20-26-v2`, with cases, merged graph,
frozen plan/source hashes, outcomes and a reused-call ledger. Offline replay
preserved all six non-lock files byte-for-byte. The shared preservation audit
confirmed 11,085 prior files unchanged. All 455 tests pass across the sandbox suite
and the separately executed localhost test.

```sh
uv run python -m basedbench.pipeline.admission_v2 prepare \
  --output data/backfill/admission-june20-26-v2
uv run python -m basedbench.pipeline.admission_v2 run \
  data/backfill/admission-june20-26-v2
```
