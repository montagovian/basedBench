# Enriched-label experiment results · September 20, 2026

All **140 calls completed successfully** under the approved **$1 total cap**.
Estimated cost, including reported prompt-cache writes, was **$0.08019**.
The [frozen comparison](curation-enriched-experiment.md) tested three JEV prompts
and matching Luna text/image prompts on the same 28 reviewed memes.

The central problem remains: **every variant passed all five items Alex marked
as not worthwhile**. Examples produced one useful JEV content-policy correction,
but did not teach the value filter the intended selection standard. Luna's image
check found the known answer defect and surfaced other plausible omissions.
None of these workflows is ready for unattended admission.

## What the numbers mean

There are 13 definite accepts and 8 definite rejects. The other seven cases are
one answer repair and six undecided; they are reported separately below.

| Method | Kept Alex's 13 accepts | Let Alex's 8 rejects through | Of its accepted items, share Alex approved |
| --- | ---: | ---: | ---: |
| JEV, old rules | 12 | 8 | 12/20 = 60% |
| JEV, clearer rules | 12 | 8 | 12/20 = 60% |
| JEV, clearer rules + examples | 12 | 7 | 12/19 = 63% |
| Luna, text + examples | 11 | 7 | 11/18 = 61% |
| Luna, image + examples | 10 | 8 | 10/18 = 56% |

These percentages apply only to the 21 settled decisions in this diagnostic
sample. They do not estimate precision across the backfill. Cases were reviewed
before the criteria were drafted; keeping a candidate and its known copies out
of its own reference examples does not create an independent validation set.
One run per variant also does not separate small changes from model variability.

The old-rules control uses the earlier criteria without the earlier overall-label
references, so comparisons with older runs are not a controlled prompt replay.
Within this run, clearer JEV rules changed **zero of 84 component verdicts**.
Adding examples changed one: the popsicle/blue-nails sexual visual joke correctly
moved from content pass to fail. JEV with examples and Luna text agreed on 22/28
overall decisions; Luna text and image agreed on 19/28. Agreement is not evidence
of correctness when both methods tend to accept nearly everything.

## Why the value filter still misses the target

All five variants missed all five explicit value failures. JEV's three variants
and Luna image kept all 17 positive value labels; Luna text kept 16 and deferred
on Freddie Mercury. Luna text did reject two value-*unresolved* cases, the snails
and the war-planning chat. Those are not confirmed correct rejections.

There is a concrete problem in our question definition. The revised instructions
ask whether a joke is worthwhile, but the retained answer descriptions still say
that a recoverable joke or reference passes, and reserve failure mainly for no
useful task beyond description or unavailable private context. Several negative
examples do contain recoverable jokes. The models' explanations show that they
are often answering that narrower question:

| Alex's value failure | Luna's reason for passing it | What this suggests |
| --- | --- | --- |
| Time-freezing snap (`1tuhwml`) | Snapping to stop time prevents another snap to restart it. | The model identifies the intended paradox; we have not encoded why this is an insufficient benchmark item. |
| “Nothing” starts with N and ends with G (`1dysnfg`) | It is a clear wordplay riddle. | Alex's note says “too easy”; the prompt explicitly allows easy jokes. Difficulty and minimum value need a consistent boundary. |
| Seafood-diet/stroke comic (`1t20u4d`) | The familiar pun is interrupted by garbled speech from a stroke. | It recovers the same mechanism Alex found too slight. This disagreement is about suitability, not simply comprehension. |
| Santa with goth women (`1pvbmxh`) | Wholesome Santa contrasts with sexualized wishes. | The image itself is a juxtaposed scene; the model readily supplies a possible narrative. This is a useful example for requiring an identifiable intended payoff. |
| Time-machine role reversal (`1dze07r`) | Meaningful historical intervention contrasts with trivial pyramid bragging. | Again, the model finds an interpretable contrast. A negative label without its reason provides limited guidance on the desired boundary. |

This is partly a specification problem, not evidence that Alex should change
these labels or that JEV cannot learn the task. The five rejected items do not
necessarily share one reason. A blanket ban on easy jokes or absurdity would
also conflict with accepted examples.

Raising a score threshold is not a demonstrated fix for value. With examples,
JEV assigned the five negatives pass scores of **0.87–0.96**, overlapping the
positives' **0.70–0.98**. The saved scores rank positives above negatives only
about 55% of the time, counting ties halfway. These are model scores, not measured
probabilities; this small development sample cannot establish a production cutoff.

## Content rules also need a more precise boundary

The frozen rule excludes explicit sexual acts and exposed sexual anatomy while
allowing mild innuendo. Luna passed the K-pop tongue-markings joke specifically
because it implied sexual anatomy without showing it. With the image, it also
passed the popsicle illusion because it saw an ordinary object rather than an
actual sexual act. Both are content failures in Alex's feedback.

This suggests the rule needs to distinguish mild innuendo from a joke whose
central meaning is sufficiently explicit to exclude, even without literal nudity.
It does not establish a universal “sexual reference fails” rule: Alex accepted
the Rainbolt/Alabama meme, which JEV rejected in all three variants.

Of the two definite content failures, JEV with examples and Luna text caught one;
the other three variants caught neither. Among the 23 content passes, JEV wrongly
failed Rainbolt, and Luna text wrongly failed the Chinese urban-legend meme based
on violent descriptions in its evidence. Seeing that image corrected Luna's
judgment to pass. Luna image passed all 23 positives, but also both negatives.

The three policy-boundary cases stay unresolved. An AfterDark track remains an
idea, not an adopted policy or a reason to turn them into settled labels.

## What the image check added

The original images were inspected alongside the stored explanations and Luna's
reasons for these cases. These observations are review suggestions, not edits to
the human gold labels:

- **Freddie Mercury (`1jley2r`):** Luna image correctly failed the stored answer.
  The image includes a purported sleepover and a comment implying it was the
  night of infection. The stored answer gives only a generic public-image/AIDS
  contrast and a lyric parody. Luna text deferred. All JEV variants passed.
  These are interpretations of the meme, not factual claims about an infection.
- **Kylie Jenner (`1t3893k`):** Luna's objection is persuasive. The meme imagines
  a baby with no lips; the stored answer describes a cosmetic before/after joke
  and mentions genetics but never connects those facts to the imagined baby.
  This is worth reviewing as an answer repair. The recorded label remains ready.
- **Hunter Biden/Poland dominoes (`1j5w6z3`):** Luna image demands the specific
  sexual-photo trigger rather than the stored answer's broader laptop controversy.
  The stored answer already explains the escalating political chain. Whether the
  exact initiating detail is essential is a useful tolerance question; automatic
  rejection looks stricter than Alex's current ready label.
- **Sonic/Minecraft casting (`1fpageg`):** Luna image deferred because the stored
  answer omits the proposed replacement shown at bottom right. That visual
  omission exists, but this run does not establish how much specificity is
  required after the answer captures the redesign/casting comparison.

Thus Luna image had one correct answer failure, two failures against ready
labels, and one deferral against a ready label; the other 24 ready answers passed.
Luna text deferred on the known defect and one ready answer, failed another ready
answer, and passed 25 ready answers. JEV passed all 28 answers, including the defect.

There is nevertheless a useful JEV signal to investigate: Freddie was its
lowest-scoring answer in all three variants. Clearer rules gave it 0.39 pass,
0.33 fail and 0.28 uncertain; examples gave 0.45, 0.36 and 0.19. The current
largest-score rule calls both distributions “pass.” A pass score below 0.5 would
have deferred this case without blocking any of the 27 ready answers in those
two variants. That is a retrospective diagnostic on one defect, not a validated
threshold. It supports testing a review route for weak passes.

## Outcomes on the seven unsettled admission cases

“Reject” below is the experiment's mechanical any-check-fails result. An answer
failure should identify a possible repair; it does not prove the meme is unusable.

| Case | Human admission | JEV old / clearer / examples | Luna text | Luna image |
| --- | --- | --- | --- | --- |
| Freddie Mercury | Repair | Accept / accept / accept | Defer | Reject: answer |
| Elevator/skirt | Undecided; content boundary | Accept / accept / accept | Accept | Accept |
| “Succumb to the crumb” | Undecided; content boundary | Accept / accept / accept | Accept | Accept |
| Vaporeon/ID | Undecided; content boundary | Reject / reject / reject: content | Reject: content | Accept |
| Manwich/man-witch | Undecided; value unsure | Accept / accept / accept | Accept | Accept |
| War-planning chat | Undecided; value unsure | Accept / accept / accept | Reject: answer and value | Accept |
| Snail couple | Undecided; value unsure | Accept / accept / accept | Reject: value | Accept |

The horse/paper-cut item (`1ju80zo`) is a separate anomaly: Alex rejected it
overall while marking all three components positive. All methods accepted it.
Its unrecorded selection reason remains unknown; no component label was invented.

## Recommended next experiment

Keep JEV as the inexpensive first method to develop, with Luna available for
image-dependent questions. There is no justification here for returning to a
more expensive model or training on model agreement as if it were human truth.

Before another paid comparison, align the pass/fail descriptions with the
intended questions and assemble a few contrasting examples: easy-but-accepted
versus too-slight, arbitrary scene versus intended payoff, and mild versus
excluded sexual implication. Avoid turning every rejection into “no joke.”
The remaining unknowns are the reason for the time-freeze/time-machine value
rejections and the horse's overall rejection, plus the answer-completeness
tolerance illustrated by Kylie and the dominoes.

Then test shorter, concrete JEV questions and a low-confidence review route on a
small frozen sample with explicit reasons. Confirm promising changes on fresh
unseen examples before expanding. GEPA or another optimizer should come after
the target is coherent; optimizing agreement on these same 28 items would not
demonstrate generalization. This report does not launch another paid run or
change the admission pipeline.

## Reproducibility and cost

| Variant | Estimated dollars, including reported cache writes | Median request time |
| --- | ---: | ---: |
| JEV old rules | $0.00220 | 0.15 s |
| JEV clearer rules | $0.00228 | 0.13 s |
| JEV with examples | $0.00594 | 0.15 s |
| Luna text with examples | $0.04140 | 3.56 s |
| Luna image with examples | $0.02837 | 4.03 s |

Luna image happened to cost less because of cache usage and generated-output
differences; that is not evidence that image requests are inherently cheaper.
The initial report's $0.07172 estimate omits the cache-write premium. The offline
analysis includes the reported write tokens, yielding $0.080186716; the shared
budget conservatively accounts $0.080195116. No allowance was exceeded.

All calls, request hashes, expected models, parsed verdicts, candidate identities,
known-family exclusions and absence of pending requests were checked offline.
No reserved-test targets were used. Frozen input files, feedback and raw response
logs remain unchanged. The implementation's full test suite passed 314 tests
before execution; this follow-up adds analysis and documentation only.

Local artifacts under `data/curation/enriched-v1/`: `plan.json`, `report.json`,
`predictions.jsonl`, `analysis.json`, the reproducible offline `analyze_saved.py`,
and the five directories of frozen requests and recorded calls. They remain
ignored working data. Experiment identity:
`b3e4281b66d42125ada0f4a1bf761cfeda38b4f25a8dbdce86035ca12a1608cb`.
