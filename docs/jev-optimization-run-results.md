# First bounded GEPA run

September 24, 2026. Related to [#40](https://github.com/montagovian/basedBench/issues/40)
and [#38](https://github.com/montagovian/basedBench/issues/38); both remain open.

**The optimizer is implemented, but this attempt stopped before final evaluation.
We do not yet have evidence that GEPA improves the checker.**

The user approved the finite comparison and then explicitly approved sending
training answer/comment/observation bundles, Jev traces and label-derived expected
pass/fail feedback to OpenAI. Exact human notes and provenance remained local;
validation and outer-test inputs were excluded from reflection. The original
image-caption authorization was not treated as permission for this new payload.

## What ran

The [execution plan](jev-optimization-execution-plan.md) and code commit `ca447e1`
were frozen before dispatch. The implementation pins GEPA 0.1.4, keeps five saved
outer family folds, uses separate training and adaptive validation within each
fold, and reserves final evaluation until all five policies are frozen. Its
maximum is six proposals per fold and $5 total, including Jev and reflection.

The policy classifies source-unit roles before seeing the answer, checks concrete
answer coverage, and combines the typed results in fixed code. Every source unit
retains its comment ID and character offsets. The preflight fit all 94 eligible
cases with no holds; the largest seeded reflection prompt was 20,251 bytes under
the 40,000-byte limit. All five original exclusions remain reported separately.

| Recorded outcome | Count |
| --- | ---: |
| Provider calls attempted | 118 |
| Settled Jev calls | 115 |
| Completed OpenAI reflections | 2 |
| Jev call held after response validation | 1 |
| Completed case/policy evaluations during search | 41 |
| Outer folds completed | 0 |
| Final comparison decisions | 0 |

Settled conservative accounting was **$0.06296571**. Retaining the full $0.002688
reserve for the held call gives **$0.06565371 accounted**, below seven cents.
That call returned token usage, but its output was not accepted as a valid model
decision. Its reservation and raw response are preserved. No request was retried
and no replacement experiment was launched.

## Why it stopped

One Jev coverage answer selected `missing`, with probabilities `covered=0.45` and
`missing=0.44` (the remaining outcomes total 0.11). The
[official Choice contract](https://docs.typesafe.ai/primitives/choice) states that
the selected option has the highest probability. This response violates that
contract. The existing strict parser rejected it, and the frozen experiment's
first-error stopping condition ended the run during the first fold.

The guard behaved as designed. Two proposals and partial adaptive-validation
work cannot support a final accuracy claim. Neither the native selection nor the
probabilities were silently changed to continue the experiment.

## Recommended next protocol

For a subsequent declared run, turn an inconsistent typed response into an
explicit **case-level abstention**, preserve the entire raw response, and count
that abstention in both optimization score and reported coverage. This would let
the comparison measure the model's real reliability without guessing which field
was intended or discarding an inconvenient case. Retain hard stops for unknown
spend, transport ambiguity and manifest drift. Decide this rule before launching
the next run; do not retrofit it into this frozen attempt.

## Verification and review

The implementation passed **666 tests, with one private-data test skipped**.
That private source was separately exercised by the real 94-case preflight.
Installed-GEPA offline tests cover search, training-only feedback, final ordering,
caps, cache integrity and credential-free completed replay. They also cover a
GEPA behavior that catches proposer exceptions: a persistent abort prevents a
swallowed error from issuing another paid call or reporting completion.

The actual failed response reproduces the strict-parser error offline. All source
and baseline hashes still verify. A private stopped-run manifest protects 319
files, including the exact requests, responses, policies, approval and ledger.
The additive review page explicitly shows the technical stop and no invented
comparison table. Original experiment artifacts, human judgments, the active
checker and release membership remain unchanged.
