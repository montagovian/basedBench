# Focused connection-audit results

September 22, 2026 · [#22](https://github.com/montagovian/basedBench/issues/22)
· [Predeclared plan](focused-connection-plan.md)

**Complete; the revised checker does not meet the development targets.**
The 52-call comparison costs **$0.04776797 (4.8¢)**. It makes quiz-name decoding
more consistent but loses human-ready answers, retains the closet miss on a
repeat, and adds a structured-response inconsistency. Do not promote it or
expand backfill. The experiment stops at its declared boundary; no follow-up
prompt edits, retries, repairs or extra model conditions were run.

## Comparison and provenance

Both conditions use GPT-6 Luna, medium reasoning, identical original image/
comment/answer inputs and a 4,000-token output cap. The baseline is #21's simpler
prompt/schema; the challenger adds an explicit list of necessary connections,
their visible cues, recovered meaning, candidate coverage and necessity.
The shared cap is higher than #21's 2,400. Compare these concurrent conditions;
differences from old runs could reflect the cap or stochastic variation.
This run measures a combined prompt/schema intervention, not their separate
effects and not model capacity.

Twenty exposed cases include nine human repair originals, six human-ready
originals and five previously inspected stress cases without human labels.
The human cases retain their original strata: six targeted and three random
repair examples, plus six targeted ready controls. Known families are distinct.
Both conditions repeat three primary defects and three ready controls once.
Human notes and labels inform selection/reporting only, never model requests.
Assistant stress findings remain hypotheses. This is a selected diagnostic
screen, not population accuracy, untouched validation or an admission batch.

## Predeclared criteria

All counts below concern **answer adequacy**, separately from source support.

| Development target | Baseline | Focused checker | Required |
| --- | ---: | ---: | ---: |
| Primary defects failed on both checks | 1/3 | 2/3 | 3/3, with matching rationale |
| Ready originals retained on first check | 5/6 | 4/6 | 6/6 |
| Repeated ready answers retained | 2/3 | 1/3 | 3/3 |
| Repair originals failed on first check | 8/9 | 8/9 | At least 8/9 |
| Adequacy flips across repeats | 1/6 | 2/6 | At most 1, no more than baseline |
| Response-validation errors | 0/26 | 1/26 | Zero |

The baseline's remaining repair original passes adequacy; the focused checker's
remaining repair original is a validation error. Neither is silently removed
from the nine-case denominator. The focused first-check fail count alone hides
the ready-control losses, repeat failures and faulty rationales.

Combined source-gate counts are distinct:

| Human group / first check | Baseline pass / fail / hold / error | Focused pass / fail / hold / error |
| --- | ---: | ---: |
| Nine repair originals | 0 / 8 / 1 / 0 | 0 / 8 / 0 / 1 |
| Six ready originals | 3 / 1 / 2 / 0 | 3 / 2 / 1 / 0 |
| Five unlabeled stress cases | 1 / 2 / 2 / 0 | 2 / 2 / 1 / 0 |

Each condition changes its combined verdict on two of six repeats. Some
changes concern evidence sufficiency rather than answer quality. The human
readiness judgments do not certify three substantive supporting comments.

## Concrete gains and remaining failures

**Quiz-name decoding improves on this exposed example.** The focused checker
flags the missing individual decodings on both checks and gives the actual
name/phrase mappings. This matches the human note. The concurrent baseline
fails once and passes once. It is a useful targeted gain, not proof that
decoding is generally solved.

**The closet requirement remains unstable.** The focused first check objects
to the vague reveal, but the repeat says the generic figure is sufficient.
Its first rationale imports an “IT” identity from a comment, while the human
asked for the visible face in the closet. That extra identity is not human
gold. The baseline passes both checks. The revised structure does not reliably
prevent the model from supplying missing specificity itself.

**XM8 verdicts conceal a factual reversal.** Both conditions fail both checks
for missing the specific old/new comparison. But the focused repeat assigns
the older HK design to the left and newer SIG design to the right, reversing
the pictured rifles. Merely counting its fail verdict would credit a faulty
rationale. The human's requirement to explain why the older rifle is framed
as cooler also goes beyond listing the two identities.

**Ready answers suffer.** Both conditions reject Sonic/Minecraft for omitting
the specific proposed replacement's reference, despite the frozen human
both-acceptable judgment. The focused checker newly rejects the human-ready
algae answer for not explaining the detention-center background. It initially
passes the domino answer, then rejects it on repeat for using the broader
laptop controversy instead of the caption's precise initial event. The baseline
retains domino twice. Dog-supplement, sub-5 and decoded-rebus adequacy remain
passes. None of these outputs changes the original human judgments.

**Extra bookkeeping causes one error.** The focused R.E.M. response correctly
criticizes an unrelated altered phrase in the candidate, but marks every
required connection present while declaring the answer defective. That violates
the frozen consistency contract and remains a technical validation error.
The raw response is preserved; the parser was not loosened and the call was
not retried or counted as a valid success. There were no provider/API failures.

The other shared first-check failures concern missing Latin decoding, the
Resident Evil 4 inventory connection, the Harry Potter meme's overall contrast,
the state-pun sequence and the Freddie Mercury image-specific implication.
Their existence does not compensate for the primary/control failures above.

## All five unlabeled stress cases

These are separate, unblinded assistant observations after execution. They
cannot supply human accuracy labels or validate an automatic admission rule.

| Case | Inspection finding |
| --- | --- |
| Cameron Diaz | Both pass the decoded pun without requiring a redundant statement of the visible setup. No new issue observed. |
| Kevin Rose/Digg | Both pass adequacy and hold source support at two substantive comments. |
| Fahrenheit | The focused checker avoids the baseline's invented freezing/boiling comeback, but still rejects for missing the visible “100%” phrasing. The image contains two pro-Fahrenheit statements; whether that wording is necessary remains unresolved human-wise. |
| Canadians/cans | Both pass adequacy. The focused checker upgrades support by counting a third comment that it explicitly calls a riff, contrary to the frozen rule. This is not a quality gain. |
| Ladder chain | Both flag role attribution and insufficient support. The focused rationale also requires the unsafe-ladder reading from one comment alongside a different story-chain explanation. Its necessity is not established; do not treat it as a human-confirmed omission. |

All four first-check combined disagreements (closet, R.E.M., algae and cans),
every primary rationale and all repeated judgments were inspected. The stress
inspection does not rescue the failed quantitative criteria or establish a
clean set of image-grounded explanations.

## Cost, verification and next step

| Condition | Calls | Estimated model cost |
| --- | ---: | ---: |
| Baseline | 26 | $0.017758665 |
| Focused | 26 | $0.030009305 |
| **Total** | **52** | **$0.047767970** |

The focused condition costs about 69% more in this run. Conservative accounting
is **$0.05156250**, below the frozen $1 cap. All 52 requests returned; zero
retries, unknown-usage calls, pending requests or allowance violations remain.
One response fails validation. Cost per human-usable new item and repair
success are not measured: no new answers or admission items were produced.

All **473 tests pass**: 471 without socket binding and two local HTTP tests.
Offline replay makes zero new calls and preserves all 130 run files. The
preservation check confirms **17,961 prior files unchanged**, including old
runs, database, human feedback and the unrelated app/helper-test edits. The
earlier calibrated runners and their frozen inputs/results still verify.
The predeclared plan and experiment code remain unchanged after launch.

**Stop this prompt/schema variant.** The human data have identified the errors
clearly enough; another broad annotation round is not the immediate need.
A small, separately priced higher-capacity comparison on these same cases is
now more informative than adding more Luna checklist requirements. Keep the
concurrent simple baseline and score rationales, ready retention and repetition,
not just defect verdicts. No such capacity run was launched here. A promising
result would still need broader validation before any #9 expansion decision.

Local artifacts: `data/backfill/focused-connection-v1/` (experiment
`790236c9afdca128f1236df4e61f369278f50b5e77b1e5a5d83ff0d2b05e30a6`),
`data/backfill/focused-connection-analysis-v1/`,
`data/backfill/focused-connection-inspection-v1.json`, and
`data/backfill/focused-connection-verification-v1.json`. Raw feedback, images
and model responses remain local and uncommitted.
