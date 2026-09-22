# Direct claim and evidence comparison

Issue [#18](https://github.com/montagovian/basedBench/issues/18).
Predeclared September 22, 2026, before calls. This follows the negative promotion
result in [#16](connection-comparison-results.md). One bounded development
experiment; no suitability change, automatic expansion, or publication.

## Hypothesis and comparison

Directly matching required connections to literal answer spans, and substantive
support to literal comment excerpts, will expose omissions and unsupported intent
that the shared source-first map obscured. Derive the verdict from those findings;
do not ask the model for a contradictory independent pass/fail field. A literal
quote proves only source identity, not semantic support. That remains fallible.

Use the original inputs of 20 cases from `connection-packet-v1`: all seven
decoding/intent/support hypotheses (including the two-comment control), three
historical human defect controls, seven pilot retention cases excluding the
duplicate pair, and three historical human ready controls. Exclude citation
cleanup, the four suitability hypotheses and the object-only control. Keep all
original human judgments and assistant hypotheses separately, outside requests.

Run the existing `answer-eval-v3` original checker and one direct-check variant on
the same original answer/image/comments. This is a fresh paired comparison with
one sample per arm, not a schema resample or independent human evaluation. The
variant explicitly checks essential decoding, literal unsupported/disputed
claims, intent attribution, and whether each supplied comment supports the same
shared reading. Required keyed comment entries prevent missing/duplicate IDs.
Verify quoted answer spans and comment excerpts against their actual sources.
Retain the three-comment rule overall, without requiring three citations per fact.

Allow one variant repair only for a concrete explanation defect with adequate
shared evidence. Verify the repair in a fresh request containing only the new
answer, image and original comments: no prior map, critique, original answer,
verdict or historical labels. Same-model blind spots still apply. A support hold
is not an intrinsic rejection or proof the underlying joke is wrong.

## Success and stop conditions

Catch the three selected decoding defects and both unsupported-intent claims;
hold the two support controls unless inspection establishes three genuinely
substantive comments supporting the same reading. Any contrary assistant
hypothesis must be explained, never silently relabeled as human gold. Retain at
least six of seven pilot positives and two of three human ready controls. Inspect
all checks and repairs for new material errors, false alarms, and exact-source
validation failures. Report baseline/variant differences and historical controls
separately; at most one technical-error case is the reliability target.

Use GPT-5.6 Luna only, medium reasoning, concurrency at most three. Baseline output
limit 2,400 tokens, direct checks 5,200, repair 3,200; at most 80 calls and
**$0.25 total**, with conservative reservation before every call. Prices inherit
the frozen accounting estimates. No retries, fallback, optimizer, adaptive prompt
changes, repeated sampling, or budget increase. Preserve partial results if the
cap or a provider failure stops the run. A negative result completes the experiment.

If targets are met on separate inspection, record a bounded unseen-check plan
before any new-data calls. Otherwise record the remaining defects and stop this
variant; do not tune until selected cases pass. Keep release and broader
chronological backfill decisions separate.

## Reproduction

```sh
uv run python -m basedbench.pipeline.claim_eval prepare \
  data/backfill/connection-packet-v1 data/backfill/claim-eval-v1
uv run python -m basedbench.pipeline.claim_eval run data/backfill/claim-eval-v1
```

Freeze prompts, schemas, code and input hashes, original images, request bounds,
requests, raw responses and cost accounting. Verify zero-call replay and the
before/after preservation manifest. Raw artifacts stay local.
