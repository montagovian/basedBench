# What to optimize next in Jev

September 24, 2026. [Issue #40](https://github.com/montagovian/basedBench/issues/40),
following the completed [#38 experiment](jev-decomposition-results.md).
This is a zero-provider-call data investigation and experiment proposal.

## Recommendation

Use GEPA's `optimize_anything` to evolve a constrained Jev decision program.
The promising change is to identify the concrete information each meme requires,
then check whether the answer covers it. Generic adequacy questions often approve
an answer that names the right topic but misses the relation that makes the joke.
The optimization target should include corrected-answer pairs, evidence roles,
ready retention and repair detection. A simple calibrated-score control belongs
in the comparison; improvements must not be credited to GEPA merely because the
original combined model used an arbitrary 0.5 cutoff.

## What the audit covered

The quantitative audit accounts for all 99 exact versions in 86 known groups.
The qualitative audit inspects every human-repair version and every combined-model
false rejection: 34 versions in 27 groups. The primary agent additionally viewed
seven images directly alongside their answers, observations, comments and notes:
Harry Potter, Nothing wordplay, XM8, R.E.M., philosophers, SCP, and the four-panel
song rebus. Existing human judgments are unchanged; diagnoses below are assistant
hypotheses grounded in those records.

The matched comparison contains 77 ready and 17 repair versions. Those repairs
represent only 14 groups. All 18 repairs, including the held image, span 15 groups.
This is enough for useful search and case diagnosis, but a much smaller independent
negative class than the headline 99 cases suggests. Three repair versions have
blank explanatory notes; other notes explicitly question the intended reading
or benchmark fit. Preserve those distinctions instead of inventing error reasons.

The net change from broad to combined conceals substantial reversals:

| Human label | Newly correct | Newly wrong | Unchanged correct | Unchanged wrong |
| --- | ---: | ---: | ---: | ---: |
| Ready | 8 | 14 | 53 | 2 |
| Repair | 5 | 1 | 1 | 10 |

Always passing would score 81.9% raw accuracy while catching no repairs. Raw
accuracy alone is therefore an unsuitable search objective.

Six families have both a repair and a ready version with identical images,
comments and observations. The combined model orders the ready version higher in
four of six, but at 0.5 correctly accepts the ready version and rejects the repair
in only one family. R.E.M. and Bowsette move in the wrong score direction after
human-approved correction. These controlled contrasts are valuable training
feedback; each entire family must stay together in every split.

## Concrete targets from the data

| Case | Observed failure | Change worth testing |
| --- | --- | --- |
| Harry Potter / Snape | The image and comments rank a sarcastic comeback above heroic achievements. The answer explains only the original exchange, yet the generic connection predicates and broad verdict endorse it. | Compare the answer to a specific required relation from the source, not just the named scene. |
| Nothing wordplay | The answer gives the complete word decoding and direct comments support it. The combined model rejects it at 0.091. | Recognize completed decoding and make irrelevant requirements explicitly inapplicable. Keep ease separate from answer quality. |
| R.E.M. | A joking comment supplies an unrelated parody that enters the defective explanation; the selector ranks that comment first. | Distinguish a comment explaining the meme from a commenter making a new joke. |
| XM8 | The answer recognizes the comparison template but omits the case-specific reason requested in the human note. | Separate template recognition from the instantiated comparison; do not require every disputed historical detail. |
| Four-panel song rebus | The stored answer covers the four decoding steps, while the image description misdescribes the tennis detail and the combined model rejects the answer. | Track individual decoding steps and distinguish fallible visual observation from established contradiction. |
| Philosophers | Generic descriptions pass even though the human feedback requires named referents and the reply's implication. | Keep reference identification, implication, and actual answer coverage separate. |
| SCP | The repair label has no written reason; the answer largely follows the supplied comments. | Preserve the label but avoid supplying an invented failure rationale to a reflector. |

These cases argue against treating all input additions as equally useful. More
comments can add riffs, alternative readings and incidental facts. More questions
can repeatedly measure the same generic impression. The current question bank
has no explicit applicability output; a low result can mean either "not needed"
or "needed but missing." Its `specific_punchline` feature exceeds 0.5 on every
one of the 94 matched cases, including every repair. Counting that feature as
present cannot distinguish this cohort's defects.

The matrix's mean omission score has more descriptive rank separation than any
single atomic feature (repair-oriented AUC 0.782 on these same exposed cases).
That motivates investigating omissions at the evidence-unit level; it is not a
validated new classifier or proof that every additional comment detail matters.

## A cheap control before GEPA

An exhaustive sweep of attainable cutoffs on the frozen combined scores finds a
post-hoc point retaining 67/77 ready versions and catching 5/17 repairs, compared
with the broad native Choice's 67/77 and 2/17. The point falls exactly on a ready
case's score. It was selected using all the outcomes and must not be presented as
a prospective gain. A coarse 0.05 threshold grid missed this point, demonstrating
why the exact score frontier matters.

The [plan](jev-optimization-plan.md) predeclares one separate offline calibration
control: inner grouped folds choose the cutoff; the saved outer folds evaluate
it. Its output stays separate from the original experiment. This is a control
for the next search, not permission to repeatedly tune outer-fold performance.

That single control is complete. The refitted outer scores match the frozen
scores exactly; only cutoffs chosen inside each training fold change decisions.

| Method | Ready passed / 77 | Repair caught / 17 | Repair groups caught / 14 |
| --- | ---: | ---: | ---: |
| Broad native Choice | 67 | 2 | 2 |
| Frozen combined, 0.5 | 61 | 6 | 5 |
| Training-only nested calibration | 64 | 7 | 6 |

The calibration restores three ready answers (cabbage, the attractiveness parody,
and the four-panel song rebus) and catches one additional repair. That additional
repair is the fashion/Israel case whose human note questions whether the comments
establish a single ground truth. It is a recorded-label gain with a substantive
qualification, not clean evidence of recovering a missing joke connection.
The calibrated method still rejects three more ready versions than the broad
check, and still correctly separates only one of the six repaired-answer pairs.
This suggests both a calibration opportunity and a remaining representation
problem. No threshold or original output was replaced.

## Why GEPA fits, and what must be pinned

`optimize_anything` is an interface within GEPA. Its evaluator can return a score
plus diagnostic feedback, allowing a reflection model to revise a text artifact.
Here that artifact can be a JSON decision policy containing Jev questions and
aggregation choices. Jev remains the fast typed evaluator; it does not have to
generate its own replacement program. The published GEPA research motivates this
approach but does not establish gains on this task.
[Official introduction](https://gepa-ai.github.io/gepa/blog/2026/02/18/introducing-optimize-anything/),
[GEPA paper](https://arxiv.org/abs/2507.19457).

The checked release is `gepa==0.1.4`. Its source uses `GEPAConfig` and
`EngineConfig`; current main-branch docs instead describe `OptimizeAnythingConfig`
and `test_set`. Pin and smoke-test the released interface rather than mixing
those examples. Keep final evaluation outside the optimizer.
[Tagged release implementation](https://github.com/gepa-ai/gepa/blob/v0.1.4/src/gepa/optimize_anything.py),
[release](https://github.com/gepa-ai/gepa/releases/tag/v0.1.4),
[current-main API](https://gepa-ai.github.io/gepa/api/optimize_anything/optimize_anything/).

A metric-call limit is not a dollar cap on nested Jev requests. In the tagged
release, an ordinary callable reflection model can report zero tracked cost;
use our own reservation ledger for all provider calls and count final evaluation
within that same cap. Reflection feedback exposes label-derived information even
when raw label fields are omitted. Validation participates in candidate selection
and cannot double as the final independent test.
[Tagged LM wrapper](https://github.com/gepa-ai/gepa/blob/v0.1.4/src/gepa/lm.py),
[tagged API and evaluator](https://github.com/gepa-ai/gepa/blob/v0.1.4/src/gepa/optimize_anything.py).

## Proposed decision program

1. **Read evidence before the candidate answer.** Split supplied comment text into
   bounded, traceable units with exact offsets and full source context. Jev makes
   separate choices about a unit's role and whether it supplies information
   essential to this particular meme. Roles include core decoding, background,
   a new joke/riff, a competing reading, irrelevant reaction, and unresolved.
   This stage cannot see the candidate answer, reducing answer-induced agreement.
2. **Check concrete coverage.** For each potentially essential unit, compare the
   unchanged answer with the stated decoding step or relation. Use covered,
   missing, contradicted, not applicable, and unresolved outcomes. Keep a machine
   observation's uncertainty distinct from contradictory evidence. A competing
   reading is not automatically an answer defect.
3. **Combine in fixed code.** GEPA may revise the generic question/role definitions,
   bounded selection thresholds, and a small set of declared combination rules.
   It cannot modify labels, scoring code, splits, source text or the candidate
   answer, read arbitrary files, or execute generated code. The final trace must
   identify which source-backed connection caused a pass, failure or deferral.

The initial compiler should support up to 64 evidence units and 384 typed
questions per case across bounded parallel batches. This leaves room for more
fine-grained decisions without making an unbounded cross-product. Keep the
existing Jev request-size, count and budget guards; a bound exceeded is an
explicit hold, not silent deletion of inconvenient evidence. Hash the policy,
input and every exact request so identical stage-one work can be reused across
answer versions without leaking decisions between different policies.

Candidate JSON and human-readable failure traces are the optimization artifacts.
Training feedback should expose useful case-specific errors, not merely a scalar
aggregate; raw human notes and assistant hypotheses must remain distinguishable.
No specific meme IDs or answer lookup tables may enter the evolved policy.

## Finite experiment and decision

Use the five saved outer family folds; for each fold, all search, reflection,
selection and cutoff fitting operate inside its training families. Use fixed
inner grouped splits for training and adaptive validation. No outer-fold cases,
notes, outcomes or diagnostic traces enter that fold's reflector. This protocol
prevents direct optimization leakage, but the dataset is already exposed to the
human/assistant design process. Report it as development evidence. Outer repair
counts are only 2, 2, 4, 3 and 3 groups; no promotion claim can rest on them.

Compare the frozen broad check, frozen combined model, the training-only
calibration control, the unoptimized evidence-unit seed, and GEPA's selected
policy. Corrected pairs count by family as an additional diagnostic, not as six
extra independent test examples. Score ready retention and caught repairs
separately, with uncertainty/holds retaining their denominators. Do not reward
rejecting all answers or deferring on everything.

Proposed hard limits: **$5 total**, at most **six candidate proposals per outer
fold / 30 total**, **1,200 case-policy evaluations**, **500,000 typed Jev questions**,
and **4,000 provider requests**, stopping at the first applicable limit. Reserve
$1 of the cap for the final outer evaluations and accounting; search cannot spend
that reserve. Reserve their worst-case request/evaluation allowances as well.
Reflection is expected to dominate cost, but its exact model and
rate must be frozen before authorization and launch. Count cache hits separately;
an evaluator invocation is not necessarily one provider call. No new image-helper
calls or external-reference retrieval are part of this first comparison.

A useful development result must catch at least three additional repair versions
across at least two distinct families versus the broad baseline, retain at least
67/77 ready versions with no increase over ten ready rejections, and decide at
least 90% of the 94 matched known versions. GEPA must also be compared with the
calibrated and unoptimized controls before crediting it with improvement. Inspect
all changed decisions. Stop after this finite comparison rather than continuing
until these targets happen to be reached. If it works, the next milestone is a
small independent human-reviewed chronological cohort, not production promotion.

## Artifacts and next implementation boundary

Private artifacts live under `data/backfill/jev-optimization-groundwork/`:
`error-audit.{json,md}`, `signal-audit.{py,json,md}`, `visual-audit.json`,
`optimizer-research.md`, and the separate `threshold-control` files. The original
99 case records, human notes, observations, requests, calls and outputs remain
frozen. No package was installed and no external model was called for groundwork.

The next implementation is a pinned GEPA adapter, deterministic candidate
compiler, fixed grouped evaluator, proposer-visibility guard, shared reservation
ledger, cache and replay tests, and a readable before/after trace. Then freeze a
launch manifest with the exact reflection model, price, inputs and approved cap.
A paid run's reflection would use training-label-derived feedback, which expands
beyond the earlier authorization that kept human labels and notes local; that
payload and destination need explicit authorization before dispatch. Groundwork
does not authorize a paid run, close #38/#40, merge the draft PR, or change the
active checker.
