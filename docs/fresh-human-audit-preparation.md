# Fresh human audit preparation

September 23, 2026 · [#26](https://github.com/montagovian/basedBench/issues/26)
· [Frozen scope and review plan](fresh-human-audit.md)

## Preparation correction, before human review

The first unserved attempt, `data/curation/fresh-human-audit-v1/`, froze the
18 remaining identities but incorrectly classified every non-consensus database
call as prior answer evaluation. All 18 had the legacy `safety_gate` call used
in the original generation pipeline, so every row was held. No review gallery,
packet manifest, feedback event or paid call was produced by that attempt.
Its selection, exposure ledger and screening result remain unchanged.

The corrected preparation distinguishes that original safety screening from
answer-quality evaluation. It records safety-gate exposure explicitly and keeps
all review/evaluation records and calls outside the legacy generation pipeline
as exposure holds. These are cached, previously generated and safety-screened
answers; they are not model-naive images. No safety verdict is used for choosing
among the already frozen 18 identities or for a new human label.

The corrected packet uses a new directory and requires the exact same ordered
identities and unchanged original source hashes from the first attempt. It
refuses to reuse a preparation that has already produced cases, a manifest or
feedback. This is an exposure-classification correction, with no resampling or
quality-based substitution. A regression test covers the distinction.
