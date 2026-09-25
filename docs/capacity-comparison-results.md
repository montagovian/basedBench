# Sol versus Luna capacity results

September 22, 2026 · [#23](https://github.com/montagovian/basedBench/issues/23)
· [Predeclared plan](capacity-comparison-plan.md)

**Complete: higher capacity improves defect detection and repeat consistency,
but does not meet the joint quality targets.** The 52-call comparison costs
**$0.289412965 (28.9¢)**. Sol flags all nine human repair originals, compared with
six for concurrent Luna, and has no adequacy flips across six repeats. However,
it rejects two of six human-ready originals and still supplies questionable
rationales and source counts. Do not promote it to automatic admission or expand
#9. The experiment stops at its frozen boundary.

## What was held fixed

Both models use the existing **simple checker**, with identical prompts,
schema, image/comment/answer inputs, medium reasoning, high-detail images,
standard service and a 4,000-token output cap. All 26 paired requests differ
only in model ID: `gpt-6-luna` or `gpt-6-sol`. The Luna requests exactly match
#22's simple-baseline requests; its previous outputs remain historical evidence.
No focused connection-audit schema, new generation, repair or retry is included.

The 20 exposed cases are the same nine human repair originals, six human-ready
originals and five unlabeled assistant stress cases used in #22. Human repair
cases retain six targeted and three random-cached identities; all six ready
controls are targeted. Known families are distinct. Each model repeats the same
three primary defects and three ready controls once. Human notes, labels and
alternate answers remain absent from requests.

This is diagnostic development evidence on selected, repeatedly exposed cases,
not population accuracy or held-out validation. The five cases originally drawn
from fresh material are now exposed and still have no human labels. Assistant
inspection below does not create gold labels or alter existing feedback.

## Predeclared readout

All counts in this table concern **answer adequacy**, separate from source support.

| Development target | Luna | Sol | Required |
| --- | ---: | ---: | ---: |
| Primary defects failed on both checks | 0/3 | 3/3 | 3/3, with matching rationales |
| Ready originals retained on first check | 5/6 | 4/6 | 6/6 |
| Repeated ready answers retained | 1/3 | 1/3 | 3/3 |
| Repair originals failed on first check | 6/9 | 9/9 | At least 8/9 |
| Adequacy flips across repeats | 2/6 | 0/6 | At most 1, no more than Luna |
| Technical errors | 0/26 | 0/26 | Zero |

Sol's 3/3 primary verdict count is **not three clean rationale-validated fixes**:
the closet rationale adds an unconfirmed character identity, and the repeated
XM8 rationale does not fully explain the human's requested cooler-design
preference. Human-ready retention independently fails the target. Stability
helps, but also makes Sol's two ready-answer rejections consistent.

The concurrent Luna first check misses quiz decoding, closet specificity and
the XM8 contrast. On repeat it still accepts quiz and closet, changes XM8 to
fail, and changes the human-ready domino answer from pass to fail. Its outcomes
vary from earlier runs despite identical saved requests. Comparisons with old
point estimates are not evidence that either model changed over time.

| Human group / first check | Luna combined pass / fail / hold | Sol combined pass / fail / hold |
| --- | ---: | ---: |
| Nine repair originals | 1 / 6 / 2 | 0 / 9 / 0 |
| Six ready originals | 3 / 1 / 2 | 2 / 2 / 2 |
| Five unlabeled stress cases | 1 / 2 / 2 | 1 / 3 / 1 |

Combined gate verdicts change on four of Luna's six repeats and none of Sol's.
Sol nevertheless changes closet source support from insufficient to supported;
the combined fail verdict hides that change. A human-ready explanation does
not automatically meet the independent three-substantive-comments threshold.

## Which gains survive inspection

**Quiz decoding is a useful gain.** Sol twice identifies the absence of actual
name/phrase mappings and supplies correct examples such as Kriss Akabusi and
the Norfolk & Chance wordplay. That matches the human note. Luna twice accepts
the generic description of clichéd pun names. Sol's comment-support count is
less convincing: irony and other-name riffs do not establish three independent
explanations of the needed decoding.

**Closet specificity is only partially resolved.** Sol twice objects to vague
“figure or object” wording and locates the lower-right closet. It also requires
IT/Pennywise, an identity derived from a comment that the human never required
and that this inspection does not independently establish from the face. On
repeat, Sol counts the direction-only “Look right” comment as the third
substantive supporter. Luna accepts the vague answer twice and similarly
inflates source support on repeat. Neither stable failure nor agreement with
the human's overall repair label validates every part of Sol's rationale.

**The rifle contrast improves.** Sol places the older H&K design on the right
on both checks, avoiding #22's focused-checker reversal. Its first rationale
also says cooler-looking. Its repeat chiefly supplies the older/newer identities,
so it does not fully demonstrate the requested explanation of why the older
rifle is favored. The third supporting comment supplies design-lineage
background rather than explaining that comparison. No independent firearms
history verification was part of this experiment.

**Other repair findings are useful.** Both models identify missing Latin
decoding, the Resident Evil 4 inventory connection, omitted state puns, the
Freddie Mercury image-specific implication and the literal R.E.M. corner gag.
Sol also catches the human-noted Harry Potter contrast between heroic feats
and the celebrated retort; Luna only critiques the direction of the quoted
exchange. The Mercury finding concerns the meme's implication, not evidence
of an actual historical medical event. All raw rationales remain available.

## The acceptance boundary still matters

Both models reject Sonic/Minecraft on both checks for not identifying the
specific bottom-right replacement and dirt-block/Steve reference. Sol rejects
domino twice for using the broader laptop controversy instead of the exact
first-domino caption; Luna passes it once and rejects it once. **The human
accepted both originals.** These remain false alarms relative to the frozen
readiness judgments; greater model confidence does not relabel them.

Both models retain dog-supplement, algae, sub-5 and decoded-rebus adequacy.
Rebus also passes both repeats. Dog and algae retain separate evidence holds;
the models disagree on whether algae has insufficient or competing support.
No stricter suitability requirement is introduced.

## All five unlabeled stress cases

These are unblinded assistant observations, not human accuracy measurements.

| Case | Inspection finding |
| --- | --- |
| Cameron Diaz | Both accept the decoded pun without requiring a redundant restatement of the setup. |
| Kevin Rose/Digg | Both accept adequacy and correctly retain a two-comment support hold. |
| Fahrenheit | Luna imports a freezing/boiling argument from comments into the image. Sol uses the actual “100%” insult, but describes the quoted post as an answering reply despite the displayed quotation order. Both count pro-Celsius counterarguments as support for the same core reading. Whether the missing wording is material remains unadjudicated. |
| Canadians/cans | Luna accepts the Finns/Cans decoding; Sol additionally requires explicit mention of the pictured cans. This may be another unnecessary-detail demand, but has no human false-alarm label. Both exclude the third comment's new AM-computer joke from support. |
| Ladder chain | Both flag role attribution. Sol separates unsafe storage and stopping in the road as competing readings instead of demanding unsafe storage as part of the chain. This is a better-qualified critique, with the required explanation still unadjudicated. |

All 52 judgments were inspected. Five first-check pairs differ in combined
verdict: quiz, closet, XM8, domino and cans. Algae and ladder add source-status
disagreements without changing the combined verdict. Source-count weaknesses
and the remaining image-order error prevent treating the stronger model as an
independent proof that an explanation is grounded.

## Cost and verification

| Model | Calls | Input tokens | Output tokens | Estimated cost |
| --- | ---: | ---: | ---: | ---: |
| GPT-6 Luna | 26 | 67,783 | 20,639 | $0.017039665 |
| GPT-6 Sol | 26 | 67,783 | 13,797 | $0.272373300 |
| **Total** | **52** | **135,566** | **34,436** | **$0.289412965** |

Each model reports 52,481 cache-write and 15,224 cached input tokens. Output
includes reasoning tokens: 17,574 for Luna and 10,676 for Sol. Costs use the
frozen [official model prices](capacity-comparison-plan.md#prices-and-stopping-rules)
and returned usage; they are estimates, not an invoice. Sol costs about **16×**
Luna in this run, although the absolute comparison cost is small.

Conservative accounting is **$0.326219875**, below the $10 ceiling. All 52 calls
completed with zero API/validation errors, unknown-usage calls, retries or
allowance violations. No cost per human-usable new item or repair success is
measured: the run checks existing answers and creates no admissions.

All **478 tests pass**: 476 without socket binding and two local HTTP tests.
Zero-call replay preserves all **131 run files**. Hash verification confirms
**18,098 protected prior files unchanged**, including frozen runs, database,
human feedback and the unrelated app/helper-test edits. Earlier calibrated and
focused runners, inputs and results still verify. The predeclared plan and
experiment code remain unchanged after launch. No raw artifacts enter git.

## Decision and next question

Capacity is no longer untested: it improves sensitivity and repeat stability on
these cases, but does not resolve the distinction between a material omission
and a useful optional detail. Do not replace the admission checker, tighten
suitability or launch #9 from this result. Keep Luna as the inexpensive
development baseline; selective Sol criticism is a candidate for later study,
not a validated routing policy.

The next useful work is to make the **material-omission boundary** explicit
using the existing human-ready and both-acceptable examples alongside the
confirmed repair examples. Use a small targeted human adjudication only where
that record leaves a consequential ambiguity, such as the cans or Fahrenheit
stress cases. A larger general annotation round or another capacity increase
is not the immediate need. Any subsequent checker change should retain these
controls and later face a separately frozen fresh human comparison. No new
experiment, review queue or paid call was launched after this result.

Local artifacts: `data/backfill/capacity-comparison-v1/` (experiment
`8c3fb0d02a0564442ed44a335836657bd1c9064c9ae0923fe085ddac58ee5b32`),
`data/backfill/capacity-analysis-v1/`, `data/backfill/capacity-inspection-v1.json`
and `data/backfill/capacity-verification-v1.json`. Images, feedback and raw model
responses remain local and uncommitted.
