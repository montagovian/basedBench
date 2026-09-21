# Answer-quality development results

September 20, 2026 · [Issue #3](https://github.com/montagovian/basedBench/issues/3)

**The workflow is implemented and tested. Asking for evidence for individual
claims helped Luna catch all four selected known defects, but it also challenged
more ready answers and approved a repair containing a new unsupported claim.**
It is useful for proposing and studying corrections; these results do not
justify unattended replacement of benchmark answers.

The complete work cost **$0.12845, about 13¢**, below the $1 total cap. It used
119 new provider calls across two prompt variants and a parser-corrected replay.
No live ground truths, human labels or release membership were changed.

## What was compared

The frozen set contains 14 answer variants from 13 posts: four known faulty
answers, eight explicit positive controls and two disputed historical references.
One positive control is the corrected version of the defective golf answer, so
these are not 14 independent memes. Several positive controls also have known
completeness disputes. They retain their human labels.

The first Luna workflow checks the answer against the image and comments,
attempts at most one repair, and verifies the proposal in a fresh call. A second
branch generates an answer from the evidence alone and checks it the same way.
JEV provides a text-only original-answer comparison.

The revised Luna prompt first describes the visible setup and intended
connection, then records evidence for each important answer claim and any
missing core details. This addresses the first run's tendency to let support for
one clause justify an unsupported extra clause.

| Original-answer check | Known defects caught | Ready labels passed | Ready labels failed | Ready labels deferred | Ready-label output errors |
| --- | ---: | ---: | ---: | ---: | ---: |
| JEV, text only | 0/4 | 8/8 | 0/8 | 0/8 | 0/8 |
| Luna, first image check | 3/4 | 6/8 | 1/8 | 1/8 | 0/8 |
| Luna, claim-evidence check, corrected parser | 4/4 | 3/8 | 3/8 | 1/8 | 1/8 |

“Failed a ready label” measures disagreement with that label, not independently
confirmed model error. In particular, the Kylie objection appears well founded.
The table excludes the two disputed references from binary scoring and reports
all abstentions/errors instead of quietly dropping them.

This is a selected development comparison, with one sample per request and a
revision informed by the same cases. The differences are not a generalization
estimate or a controlled measurement of JEV versus Luna capability: evidence
modalities, prompts and output formats differ.

## What happened to the known defects

The final workflow flags all four. Three original-answer repair proposals pass
its separate verification step and address the flagged defect on inspection:

- **Freddie Mercury:** connect the purported sleepover to the infection
  insinuation. The new answer frames this as the meme's implication, not an
  established account of an actual infection.
- **Harry Potter:** restore the central comparison—classmates rank his comeback
  above his heroic achievements. The repair also describes the retort as turning
  Snape's demand for respectful address into apparent respect for Harry, although
  its wording could be clearer.
- **R.E.M.:** remove the altered song title imported from a side comment, and
  explain the person literally inserted into the corner of the band photo. The
  first repair removed the extra title but missed this visible connection; the
  revised prompt recovered it.

**Golf:** the final checker identifies the sexual elaboration as a minority
comment, while the shared core concerns golf skill and the narrator's boast.
It also marks insufficient evidence, so the repair branch conservatively stops
with the original unresolved. The separate fresh-generation branch produces a
clean golf explanation. For the paired corrected-answer case, generation first
reintroduced the sexual embellishment; verification caught it and the single
repair removed it. This illustrates both a recurring generation error and a
useful verification catch.

These inspections are assistant analysis of the images, comments and frozen
notes. They are not new human annotations or independent validation.

## Overreach and remaining failures

The detailed checker challenges three ready answers:

- **Kylie Jenner:** the proposed repair connects the pregnancy setup to the
  imagined baby's lips. This appears to address a real omission, but the ready
  label remains unchanged.
- **Sonic/Minecraft:** it demands the specific proposed replacement pictured
  at bottom right. The richer explanation is plausible; whether the broader
  casting/redesign comparison was already sufficient remains a tolerance issue.
- **Domino chain:** it demands the precise initiating photo reference. The
  repair then calls the kneeling man Hunter Biden, although the image's label
  describes the initiating event and does not establish that identity. The
  verifier approves this new unsupported claim. This is a concrete reason not
  to replace a ready answer merely because the model prefers a longer one.

The Oprah example defers because the model finds only two substantive supporting
comments under the retained three-comment rule. That is insufficient evidence
under the experiment's rule, not a finding that the existing answer is wrong.

Two final outputs are invalid and remain visible errors: the elevator checker
says pass while identifying an unsupported material claim, and the Rowling
repair proposes an answer without three distinct supporting citations. Neither
is promoted to a successful repair or quietly counted as a quality verdict.
All provider requests completed; these are output-validation failures.

The **Brazil** disputed reference remains a substantial blind spot: the workflow
approves the popular men-and-compliments reading and even attributes an
absurdism-only comment as support for it. The **Rowling** fresh answer continues
to mix the image's premise with comment-side wordplay. Neither disputed reference
is treated as settled gold. Thirteen fresh-answer branches receive model
approval, which plainly does not establish thirteen correct answers.

## Engineering and reproducibility

- Originals, labels, images, comments, prompt/model versions and provenance are
  frozen separately from proposals and model judgments.
- Every adaptive request is saved and bounded before dispatch. One repair per
  branch; no automatic retries; interrupted requests are not silently repeated.
- The legacy consensus report now explicitly reports Boolean agreement rather
  than implying explanation correctness. Technical failures cannot pass negative
  controls. Seeding preserves manual adjudications and does not use a flagged
  faulty answer as its own expected correction.
- **341 tests passed**: 340 in the sandbox and the localhost HTTP test separately
  outside its socket restriction. Completed real runs also replayed offline with
  zero provider requests and unchanged results.

The first implementation is commit `4619c31`; the evidence-map revision is
`0c67555`; parser correction and exact-request reuse are `32aab22`.
Version 2 initially imposed an unintended three-citation quota on every
individual fact, causing 12 output-validation errors. Version 3 removed that
per-fact quota while retaining support for the shared reading. It reused all
52 version-2 responses with exact request/input matching and made only four new
calls to complete newly reachable repair branches. The source responses remain
unchanged. This is the same prompt variant with corrected parsing, not a third
prompt experiment.

| Recorded run | New provider calls | Reused calls | New estimated cost |
| --- | ---: | ---: | ---: |
| First workflow, including JEV | 63 | 0 | $0.047719226 |
| Claim-evidence workflow | 52 | 0 | $0.075513040 |
| Corrected-parser continuation | 4 | 52 | $0.005216600 |
| **Total** | **119** | **52** | **$0.128448866** |

The conservative accounting total is $0.128464616, including cache-write
allowances. Every call had reported usage and stayed within its reservation;
no interrupted requests remain. Local artifacts live under
`data/curation/answer-eval-v1`, `answer-eval-v2`, `answer-eval-v3`, and
`answer-eval-sources-v1`. The offline `analyze.py` checks identities, frozen
evidence, request hashes, models, usage, source replays and cost totals.
See [the workflow and commands](answer-quality-evaluation.md).

## Roadmap consequence

Issue #3's bounded implementation and diagnostic experiment are complete.
Neither prompt is promoted as an unattended admission policy. Continue with
[#4, the source inventory](https://github.com/montagovian/basedBench/issues/4),
and carry the false alarms, verifier misses and output errors into
[#7, pilot integration](https://github.com/montagovian/basedBench/issues/7).
The pilot must retain deferral/error states and evaluate real answer defects
separately from curator disagreement and model approval.
