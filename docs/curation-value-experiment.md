# Value-prompt experiment · September 20, 2026

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
passes and one sandbox-only localhost bind failure; the blocked test is rerun
with localhost access before dispatch. Provider costs exclude the work of
preparing observations, so they are not a production captioning cost estimate.
