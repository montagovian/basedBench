# Checking and repairing joke explanations

Implementation and development experiment for [issue #3](https://github.com/montagovian/basedBench/issues/3).

## Focused second version

The first run completed 63 calls for $0.04772. Luna caught three of four known
defects; JEV caught none. Luna also disagreed with Kylie's ready label and deferred
the Oprah answer for insufficient substantive comments. Inspection found that
some model-verified outputs still imported a minority interpretation or omitted
an essential visual detail. These are concrete reasons to test a focused revision.

Version 2 requires the checker to describe the visible setup and intended
connection, then map each important answer claim to its supporting evidence.
It records missing core details and distinguishes shared comments from minority
elaborations. A global pass cannot override an explicitly unsupported claim or
missing core detail in that same response. Citation IDs still require semantic
inspection; these consistency checks cannot prove entailment.

Repeat the same frozen cases with Luna and the same bounded repair/generation
branches. Do not repeat the unchanged JEV comparison. Cap this follow-up at
**$0.90**, so combined spending with the completed first run stays below the
original $1 total. This is a development revision informed by the first run,
not a fresh validation set. Keep both versions and their results separate.

The initial version-2 parser also demanded three citations for every individual
claim, which incorrectly discarded useful checks of answers whose overall
interpretation had three supporting comments. Version 3 removes that extra
per-fact quota while retaining the requirement for three comments supporting
the shared reading. Its prompts and response schema are unchanged from version 2.
It reuses completed responses only when both the full request and candidate input
match exactly. Source responses and usage remain intact, with hashed provenance;
replayed calls have zero new charge. Only newly reachable repair branches make
additional requests. Its $0.75 cap is below the remaining total budget.

## What this tests

An answer can name the right celebrity, song or film and still miss the joke.
This workflow checks whether the written answer connects the actual setup to
the payoff supported by the image and comments. Consensus, support,
completeness and visual consistency form one judgment.

For each case, Luna checks the original answer. A concrete, repairable defect
allows one rewrite, followed by a fresh verification call. The verifier sees
only the evidence and proposed answer, without the previous verdict, repair
rationale or human label. Unresolved competing readings defer instead of
forcing a rewrite. A second branch generates an answer from the evidence alone,
checks it, and permits the same single repair attempt. JEV optionally provides
a text-only check of the original answer as a cheap comparison.

A generated answer is a proposal. A successful verification means only that
the model approved it in a separate call; the calls can share blind spots.
Neither result changes the live answer, human feedback or admission status.
The experiment report keeps technical errors separate from unresolved evidence.

## Frozen first experiment

Use 14 answer variants from 13 previously inspected posts:

- Four known defects: Freddie Mercury, Harry Potter, R.E.M., and the historical
  golf-club answer with its unsupported sexual elaboration.
- Eight positive controls, including the corrected golf answer. Kylie Jenner,
  Sonic/Minecraft and the domino-chain example retain their human ready labels
  despite previously noted completeness disputes.
- Two disputed regression references, Brazil and Rowling's house, reported
  separately. Preserve their original annotations; do not manufacture reconciled
  binary gold from a conflicting or unverified reference.

This is a deliberately selected development sample, including a same-post
before/after pair. It estimates neither corpus-wide precision nor performance
on an unseen test set. No examples or curator notes are supplied as inference
references. Case notes are frozen for subsequent inspection of the outputs.

The hypothesis is that image-grounded answer checks catch missing connections
and imported commenter jokes, and that bounded repair can fix some of those
defects while preserving good answers. Compare defect detection, missed
defects, disagreement with positive labels, deferrals, model-verified repairs,
unresolved cases, fresh-generation outcomes and cost. Inspect the proposed
repairs against the images and frozen case notes before calling them successful.

Use **GPT-5.6 Luna**, medium reasoning, at most 2,400 output tokens per call,
and **a $1 total cap** shared across every stage and the JEV baseline. There
are at most 112 calls (seven Luna stages and one JEV check per answer variant),
usually fewer because repair branches are conditional. No automatic retries.
The existing conservative token allowances reserve cost before dispatch;
unknown-cost interrupted requests retain their reservation and are not repeated.
Current Luna rates were checked against the
[official model page](https://developers.openai.com/api/docs/models/gpt-5.6-luna)
on September 20, 2026, including the cache-write premium.

## Running a version

Prepare a JSON array of cases using the `Case` schema in
`src/basedbench/pipeline/answer_eval.py`. Each case contains a stable case/post
identity, explanation, original comment evidence, image hash, gold source,
notes and provenance. Different answer variants of one post need distinct case
IDs. Store raw data and image assets locally under `data/`.

```sh
uv run python -m basedbench.pipeline.answer_eval prepare \
  data/curation/answer-eval-sources-v1/cases.json \
  data/curation/historical-v2/assets \
  data/curation/answer-eval-v3 --budget-usd 0.75 \
  --reuse-from data/curation/answer-eval-v2
uv run python -m basedbench.pipeline.answer_eval run \
  data/curation/answer-eval-v3 --budget-usd 0.75
```

Preparation freezes case labels, input bytes, image bytes, prompts, model IDs,
implementation hashes, prices, stage limits and the cap. Execution freezes each
adaptive request before dispatch and checks its bound. Responses, token usage,
citations, proposals and outcomes are checkpointed. Re-running the same command
replays finished calls; changed evidence, code or requests require a new version.
`report.json` contains the detailed results and denominators.
The first run used commit `4619c31`; later code versions intentionally cannot
resume it. Its completed real requests were replayed offline with zero provider
calls and identical results before the second version was prepared.
The optional `--reuse-from` argument imports only exact matching completed
requests into a new experiment version. Omit it for a fresh comparison.

## Legacy evaluator corrections

`consensus-eval` retains its historical database format, but its output now
explicitly reports **Boolean matches, with explanation correctness unevaluated**.
Transport/parse errors cannot count as correct no-consensus decisions. The new
answer workflow evaluates the written meaning rather than inferring correctness
from a matching `has_consensus` value.

Seeding new regression references no longer substitutes the flagged bad answer
when no correction exists. It also preserves later manual adjudications rather
than overwriting them on a reseed. Existing database references remain unchanged;
the first experiment records their conflicts explicitly.
