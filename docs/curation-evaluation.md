# Learning from your BasedBench decisions

We are testing whether a classifier can make useful choices about which memes
belong in BasedBench, using your earlier approvals and rejections as examples.
The first two models are not reliable enough to admit new memes automatically.

## What we have done

We recovered 519 approved memes and 1,396 exclusions recorded as `other`. Eleven
of those exclusions have no local image, so the experiments use **1,904 examples:
519 approved and 1,385 rejected**. We are provisionally treating `other` as manual
rejections; that still needs confirmation.

An exclusion tells us that an item was rejected overall. It does not reliably
tell us whether the problem was a bad explanation, an unsuitable joke, a broken
image, or something else. We have not invented separate labels for those reasons.

We copied the images, original explanations, comments, and decisions into a fixed
local dataset. That prevents later edits in the review app from silently changing
an experiment. We found one explanation that differs from the original logged
version. The exact text shown when you reviewed an item was not tracked, so we
cannot promise perfect reconstruction of that moment.

Duplicate images stay together when examples are assigned to different uses.
There are eight groups, containing 17 items, where similar images or identical
explanations received conflicting decisions. We preserve those decisions. More
work is needed to identify different images that express the same underlying joke.

## What the models tried to learn

Each model learned from 1,332 examples and then made choices on 286 different
practice examples. Those practice examples contain **78 memes you approved and
208 you rejected**. The models receive the original explanations and comments;
they do not receive your decision or later reviewer notes, and they do not see
the image in these first two experiments.

The first model learns which words and phrases tend to appear in accepted memes.
The second uses a small pretrained text encoder, MiniLM, to represent the meaning
of the explanation and comments. We keep the encoder unchanged and train a small
classifier to connect those representations to your decisions.

MiniLM normally cuts off long inputs. We instead split long text into pieces,
read every piece, and combine the results. That avoids losing the end of a long
comment thread, although combining separate pieces can miss relationships across
them. This is one small encoder experiment, not a verdict on all encoders.
[Model description](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2).

## What happened

We care about two things: **are the selected memes good, and does the model find
enough of the good ones?** A useful curator needs to do both.

| Model and setting | Memes selected | Of those, you approved | Of your 78 good memes, it found |
| --- | ---: | ---: | ---: |
| Accept everything | 286 | 78 (27.3%) | 78 |
| Word-count model, cutoff 0.5 | 38 | 10 (26.3%) | 10 |
| Encoder, cutoff 0.5 | 110 | 36 (32.7%) | 36 |
| Encoder, stricter cutoff 0.7 | 19 | 7 (36.8%) | 7 |
| Encoder, cutoff 0.8 | 1 | 1 | 1 |
| Encoder, cutoff 0.9 | 0 | No selections to assess | 0 |

The cutoff controls how strong a model's recommendation must be before an item
is selected. A score of 0.8 does **not** mean we have established an 80% chance
that you would approve that item.

The encoder finds more approved memes at the default decision cutoff, but most
of its selections are still historical rejections. When we compare the same
number of selections—each model's top 38—the encoder gets 12 right and the
word-count model gets 10 right. That is only a modest difference in this practice
run. It is not evidence that we have solved automated curation.

The single success at cutoff 0.8 is also too little evidence to trust. A setting
that selects one good meme has shown one good choice, not reliable performance
across new content. A setting that selects nothing adds nothing to BasedBench,
and gives us no selections whose quality we can assess.

We are trying settings on practice examples to guide development. We will need a
properly reserved set of fresh examples to check the chosen approach before
making strong claims about how well it works.

## Correction about the reserved examples

The first smoke test used one division of examples. I then changed that division
to give the groups similar proportions of approvals and rejections. I initially
said the 286 examples reserved in the second version were untouched. That was
incorrect across the whole experiment history:

- 203 had been used to train the first model.
- 41 had been scored in the first model's practice check.
- Only 42 stayed unused in both versions.

The current split is now fixed. A history audit records those earlier uses, and
new encoder reports carry the audit status. All 286 reserved examples were left
out of the encoder experiment, preserving the remaining 42. That small remainder,
with joke-family grouping still unfinished, is not a qualified final evaluation.
The history audit can only vouch for the runs supplied to it; it cannot rule out
unknown earlier use or overlap with a pretrained model's training data.

This corrects the bookkeeping; it cannot undo earlier exposure. We need to settle
the final evaluation design before claiming readiness for unattended admission.

## What comes next

Both simple word counts and this frozen encoder make too many unwanted selections.
The next useful comparison is a model that can apply explicit inclusion criteria,
with an image-aware option so we can test whether the missing visual evidence
matters. Use the existing practice split for that comparison. Resolve rejection
provenance and joke-family grouping alongside it, and keep the remaining unused
examples out of development.

No new backfill has run, and these experiments do not change live review decisions.
The software tests check that evidence is preserved and experiments stay within
their assigned inputs. Passing those tests does not mean a classifier curates well.

## Running and reproducing the experiments

The commands below are implementation details for rerunning the work. Keep raw
records, images, downloaded models, and results under ignored `data/`. Use a new
output path each time; existing datasets and runs are never replaced.

```bash
uv sync --extra curation --extra encoder
uv run --extra curation basedbench curation build \
  --db data/basedbench.db --project-root . \
  --output data/curation/new-corpus
uv run --extra curation basedbench curation baseline \
  data/curation/new-corpus --output data/curation/runs/new-baseline
```

The database is opened read-only, with no migrations or credential loading. A
candidate requires one successful consensus call within two seconds of its
recorded generation time and no later than its review. Missing or ambiguous
evidence goes to `quarantine.jsonl`, outside training and evaluation. Original
comment scores are retained; author names are removed from model-input headers.
Raw original prompts and responses remain separately in local provenance records.

The corpus contains `examples.jsonl`, `quarantine.jsonl`, image bytes under
`assets/`, and `manifest.json`. Hashes cover inputs, payload files, builder code,
and the corpus contents. The loader verifies them before a run. Grouping uses
exact image hashes, conservative near-image comparisons, identical normalized
explanations, and optional `--families` mappings. Groups are indivisible; known
regression cases stay in development. The current `historical-v2` split is:

| Purpose | Approved | Rejected | Total |
| --- | ---: | ---: | ---: |
| Learn from examples | 363 | 969 | 1,332 |
| Practice comparison | 78 | 208 | 286 |
| Reserved, with history caveat above | 78 | 208 | 286 |

To audit cross-version use, create a JSON history list with `corpus` and `run`
paths relative to that JSON file. The audit verifies each run's corpus identity,
training/evaluation membership hashes, and recorded prediction inputs.

```bash
uv run --extra curation basedbench curation audit-history \
  data/curation/historical-v2 \
  --history data/curation/history-v1.json \
  --output data/curation/history-audit-new.json
uv run --extra curation --extra encoder basedbench curation encoder \
  data/curation/historical-v2 \
  --history-audit data/curation/history-audit-new.json \
  --output data/curation/runs/new-encoder
```

The optional `--history-audit` also works with the word-count baseline. A run
without one is explicitly marked unaudited. Neither command scores the reserved
partition. A run's statement that it did not score that partition is separate
from a history-wide claim that those examples have never been used.

Both classifiers use logistic regression with balanced class weights, `C=1`, and
fixed random seed 0. The word-count baseline fits unigram/bigram TF-IDF on the
learning examples only. The encoder uses `sentence-transformers/all-MiniLM-L6-v2`
at revision `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`, on CPU without gradients.
Each field is split into nonoverlapping chunks of at most 254 content tokens,
wrapped in BERT special tokens. Normalized chunk vectors are averaged with
content-token weights; each field is normalized, then the two are concatenated.
No content tokens are omitted. Only the classifier is trained on these features.

Runs save the classifier, normalized decisions, parameters, source/package
versions, input membership hashes, timings, and reports. Encoder runs also save
features and per-item token/chunk counts. Errors remain visible and leave items
undecided. Acceptance precision is the share of selected items historically
approved; positive retention is the share of all historically approved items
selected. Recorded uncertainty ranges assume independent items and do not account
for related jokes or choosing settings after viewing results.

Current local run IDs are `tfidf-v2` and `minilm-v1`, both on `historical-v2`.
The encoder processed 932,343 content tokens in 5,714 pieces in about 39 seconds;
the local comparison made no paid API calls. Older artifacts remain unchanged,
including their original wording; this document and the history audit correct the
cross-run interpretation.
