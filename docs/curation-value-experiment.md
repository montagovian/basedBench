# Value-prompt experiment · September 20, 2026

**Completed:** all 224 calls succeeded, costing **$0.01208172** (about 1.2¢).
The best default verdicts caught one of five value failures while retaining all
17 positives. Literal descriptions did not improve that result. Detailed
findings follow the frozen design below.

The user approved trying the [inferred prompts](curation-prompt-hypotheses.md).
This round is limited to JEV's benchmark-value judgment, with a **$0.10 shared
execution cap**. It does not alter human labels, content policy, answer checks,
or the review gallery.

## Frozen comparison

Four questions are tested against two evidence conditions, giving **224 calls**
on the same 28 reviewed items:

| Question | Original explanation and comments | Same text plus literal image observation |
| --- | --- | --- |
| Previous clear-rules value question | Control | Evidence-only change |
| Useful missing connection | Prompt change | Prompt and evidence change |
| Supported intended payoff | Prompt change | Prompt and evidence change |
| Combined requirements | Prompt change | Prompt and evidence change |

The three draft prompts are used verbatim, including their common instructions
and revised answer descriptions. All conditions ask one native Choice question
with pass/fail/uncertain options. No labeled examples, curator notes, identities
of the reviewed cases, or historical admission decisions are supplied.

The control copies the previous clear-rules value question and candidate text
exactly, removing the content and answer questions. Its wording still refers to
three independent checks in the inherited common instructions. This is a fixed
control for the new one-question comparisons, not an exact replay of the earlier
three-question request. Results will be compared with the earlier saved value
verdicts to identify any difference from that change.

Every item gets one assistant-written observation with visible text and a scene
description, linked to a verified image hash. These were written before the
new calls but with knowledge of earlier feedback. They are not blinded or human
gold, and they contain selected text rather than exhaustive OCR. JEV receives
these descriptions, not the images themselves. The same description is used
across all four questions; original comments and explanations remain unchanged.

## Measures and hypotheses

Of the 28 items, 17 have explicit positive value labels and five have negative
labels. Six lack a settled value label and are reported separately. An overall
rejection does not change a positive component label: the horse/paper-cut example
remains a positive value control.

Measure definite negative catches, positive retention, uncertainty and errors
separately. Inspect the time-freezing, Santa and seafood examples as the leading
hypothesis cases; the spelling riddle tests the minimum-value clause. Preserve
the time-machine counterexample even if every prompt passes it. The earlier
Cobain exception remains qualitative context outside these 28 targets.

The anticipated failure mode is stricter questions rejecting legitimate easy
items such as freezer bags. More rejections alone are not an improvement. The
test does not select or deploy a confidence threshold. These are development
results on examples that informed the hypotheses, not independent validation.

## Execution and verification

Frozen request allowances sum to **$0.059173464**, below the $0.10 cap. The
existing shared budget reserves before dispatch, accounts for unknown requests,
and never repeats completed or interrupted calls automatically. Requests use
pinned `jev-1.13.0`, concurrency four and no transport retries. All four text
conditions run before the four conditions with observations; all requests are
frozen before either stage.

Source experiment: `data/curation/enriched-v1/`.
Inputs: `docs/experiments/curation-value-prompts-v1.json` and local
`data/curation/value-inputs/observations-v1.json`.
Outputs: `data/curation/value-prompts-v1/`.
Experiment identity:
`3aef2a163fed9ebc9df6a9c997936efd3462c30c971e4a74ae0a9572129c6724`.

```sh
uv run python -m basedbench.pipeline.curation_value run \
  data/curation/value-prompts-v1 --budget-usd 0.10
```

The runner freezes source identities, gold labels, prompt text, observations,
request hashes and code hashes. Four added tests check the evidence comparison,
label exclusion, cap validation, observation identity, score validation and
resumption without repeating interrupted requests. The full suite had 317
passes and one sandbox-only localhost bind failure; the blocked test then passed
with localhost access before dispatch, for 318 passing tests in total. Provider costs exclude the work of
preparing observations, so they are not a production captioning cost estimate.

## Results

All eight conditions retained **17/17 positive value labels**, including the
freezer bags, knight, RCA cables and horse/paper-cut controls. None produced a
provider or parsing error. This round measures the value check alone; these are
not overall admission decisions.

| Prompt | Caught negatives with original text | Caught negatives with added observations |
| --- | ---: | ---: |
| Previous clear rules | 0/5 | 0/5 |
| Useful missing connection | 1/5 | 0/5 |
| Supported intended payoff | 0/5 | 0/5 |
| Combined | 1/5 | 1/5 |

The only definite negative caught was the “nothing starts with N…” riddle
(`1dysnfg`). This matches the explicit isolated-spelling-trick clause. It shows
some responsiveness to the new standard, but does not establish that JEV learned
the broader distinction between a useful inference and a narrated surprise.

The original single-question control still passed all 28 items, matching the
previous three-question run's value verdicts on 28/28. Removing the other checks
did not explain the new rejection.

### The score changes tell a more limited story

| Value-negative case | Control, text | Combined, text | Combined, with observations |
| --- | ---: | ---: | ---: |
| Time machine / Henry Ford / Bass Pro | 0.96 | 0.80 | 0.90 |
| Time-freezing snap | 0.97 | 0.87 | 0.92 |
| Santa/goth women | 0.94 | 0.45 | 0.48 |
| Seafood-diet/stroke | 0.97 | 0.82 | 0.88 |
| “Nothing” riddle | 0.86 | 0.06 | 0.21 |

These are returned **pass scores**, not calibrated probabilities. The default
decision takes the largest of pass/fail/uncertain. Santa remained a pass despite
its sub-0.5 score; the other two choices split the remaining support.

An exploratory review route for pass scores below 0.5 would flag Santa in both
combined variants, in addition to the riddle's existing failure, while retaining
all 17 definite positives. That is **one definite catch plus one possible review
candidate**, not two validated rejections. No threshold was selected or deployed.
Other prompts show why a universal 0.5 rule would be premature: the gap prompt
with original text puts the positively labeled Chinese urban-legend item at
0.49, and the payoff prompt puts the value-positive elevator item at 0.42.

The time-freezing and seafood/stroke cases remain strong disagreements with
the hypothesis. The supplied observations included the exact “you're not
immune” caption and the comic's depicted speech/ambulance sequence. Providing
that evidence did not make JEV treat them as too self-explanatory. This result
does not support missing literal evidence as the sufficient explanation for
those errors. JEV provides no free-text rationale, so its precise reasoning
cannot be recovered from these outputs.

The time-machine case remains a documented counterexample to the inferred
standard, and all variants pass it. The earlier Cobain case was not queried;
it remains an additional qualitative counterexample, not an omitted test error.

### Added observations had mixed effects

The control and payoff questions changed no verdicts with added observations.
The gap question changed the riddle from fail to pass and the unresolved
war-planning-chat item from fail to pass. The combined question changed the
war-planning-chat item from uncertain to pass. No other verdict changed.

Scores sometimes ordered the classes better: the gap question with observations
ranked a positive above a negative in about 79% of the 17 × 5 pairs, counting
ties halfway, versus 50% for the original text control. This exploratory measure
does not rescue its all-pass default behavior or establish an admission threshold.
The combined prompt's analogous figures were about 67% with original text and
64% with observations. Better evidence was not consistently beneficial.

### Six unresolved value labels

K-pop tongue markings, the popsicle, Manwich, the snail tweet and Master Chief
passed every value condition; their missing/unsure value judgments remain
unresolved. The war-planning-chat tweet failed the text-only gap prompt and was
uncertain under the text-only combined prompt; it passed the other six conditions.
None of those outcomes is counted as a correct or incorrect binary judgment.
The content failures on K-pop and the popsicle are separate and unchanged.

## Interpretation and next diagnostic

The inferred standard produced a small improvement without sacrificing known
positives. Most value-negative cases still pass. In particular, the experiment
does not substantiate the hoped-for broad separation of self-explanatory material
from useful missing connections. The observations were assistant-authored after
seeing feedback, so even a larger gain would still require independent checks.

The most informative next diagnostic would ask short, concrete questions about
the residual failures: whether the decisive consequence is already stated in
the caption, whether the explanation mostly narrates visible events, and whether
it adds a supported relation between details. That would reveal whether JEV
disagrees about the observable properties or about converting those properties
into a value decision. Any labels for those new properties would be assistant
annotations, distinct from Alex's existing value judgments. A small matched Luna
comparison could subsequently distinguish a question problem from a JEV-specific
limitation. Neither follow-up was run as part of this experiment.

No new human labeling round is required to formulate those tests. Keep the easy
positive controls and the known counterexamples; do not optimize away cases that
disagree with the hypothesis. Confirm useful changes on fresh data before using
them for hands-off selection.

All 224 request/response identities, expected models, frozen input hashes, saved
verdicts and spending records were verified. No pending requests remain. The
offline `analyze_saved.py` and `analysis.json` under the output directory preserve
the verification, paired changes and exploratory score diagnostics. Median
request times ranged from about 0.13 to 0.16 seconds across conditions.
