# Learning from your BasedBench decisions

We are testing whether a classifier can make useful choices about which memes
belong in BasedBench, using your earlier approvals and rejections as examples.
The models tried so far have not demonstrated reliable automatic admission.
JEV is now connected and very cheap to run, but neither it nor GPT-5.5 reproduced
your historical choices well in the first comparison.

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

Each of the first two models learned from 1,332 examples and then made choices on 286 different
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

## What happened with JEV and GPT-5.5

We gave three classifiers the same written criteria and the same eight historical
examples: four approvals and four rejections. JEV and one GPT-5.5 variant received
the explanation and comments. A second GPT-5.5 variant also received the image.
This is a different way of learning the task from fitting the earlier classifiers
on all 1,332 development examples, so it does not isolate architecture alone.

An eight-example development trial checked that the APIs worked. We then kept the
criteria unchanged and compared all three on **80 practice examples: 23 historical
approvals and 57 rejections**. Your decisions on those examples stayed hidden from
the classifiers. We also looked up the earlier models' results on these same 80.

| Method | Memes selected | Of those, you approved | Of your 23 approved memes, it found |
| --- | ---: | ---: | ---: |
| Accept everything | 80 | 23 (28.8%) | 23 |
| Word-count model, cutoff 0.5 | 11 | 3 (27.3%) | 3 |
| Frozen MiniLM encoder, cutoff 0.5 | 36 | 11 (30.6%) | 11 |
| GPT-5.5, text | 69 | 20 (29.0%) | 20 |
| GPT-5.5, text and image | 75 | 22 (29.3%) | 22 |
| JEV, text | 60 | 19 (31.7%) | 19 |

The central finding is that **all three API classifiers accepted most examples,
including most historical rejections**. Finding more approved memes mostly came
from admitting more of everything. The small differences in percentages do not
establish a winner. Rejecting all 80 would select none of the 23 approved memes.
None of the API classifiers deferred an example, despite
having that option. There were no failed or invalid responses in either run.

Selecting only high-scoring items did not solve this. At a score cutoff of 0.9,
GPT with text selected 28 items, of which 10 were approved; GPT with images selected
42, of which 14 were approved; JEV selected 11, of which three were approved.
Those scores are not trustworthy estimates of how likely you are to approve an
item. These are exploratory settings on practice data, not final-test results.

Images changed eight decisions: three moved toward the historical decision and
five moved away. They can supply useful evidence without automatically producing
better admission judgments. Reading the actual images and model responses revealed
two concrete patterns:

- A ramen meme contained a racial slur in the image that was absent from the
  supplied explanation. The image model caught it and rejected the item under the
  experiment's publication rule. The text model accepted it.
- In a Kurt Cobain meme, the supplied explanation focused on identifying him in
  a dark picture. The actual setup contrasts a claim about musicians never touching
  guns with his death. The image model's reasoning recovered that contrast, yet it
  accepted the item without flagging that the supplied reference explanation missed
  the setup. It effectively repaired the answer in its own head.

The second pattern is a useful lead: **understanding the meme is not enough if the
benchmark's stored answer still misses the joke**. A candidate may be salvageable
after rewriting its explanation, but that is different from approving the current
image-and-explanation pair. These observations do not establish why you originally
rejected either item, and we have not changed the historical labels.

JEV did demonstrate an operational advantage. On the 80-example comparison it
averaged about **0.16 seconds per request**, versus about **6.3 seconds** for each
GPT variant. JEV's calls cost about **$0.02**; GPT text cost **$1.88**, and GPT with
images cost **$2.16**. The main comparison plus the development trial cost about
**$4.50** in total, estimated from reported usage and published prices. This counts
the classification experiment, not the earlier cost of collecting comments or
generating explanations. It does not establish production throughput.

This was one direct JEV admission question, with eight references. It does not
settle whether narrower questions, better examples, or a classifier trained on
the full corpus could work well.

## Correction about the reserved examples

The first smoke test used one division of examples. I then changed that division
to give the groups similar proportions of approvals and rejections. I initially
said the 286 examples reserved in the second version were untouched. That was
incorrect across the whole experiment history:

- 203 had been used to train the first model.
- 41 had been scored in the first model's practice check.
- Only 42 stayed unused in both versions.

The current split is now fixed. A history audit records those earlier uses, and
new reports carry the audit status. All 286 reserved examples were left
out of the encoder and API experiments, preserving the remaining 42. That small remainder,
with joke-family grouping still unfinished, is not a qualified final evaluation.
The history audit can only vouch for the runs supplied to it; it cannot rule out
unknown earlier use or overlap with a pretrained model's training data.

This corrects the bookkeeping; it cannot undo earlier exposure. We need to settle
the final evaluation design before claiming readiness for unattended admission.

## What comes next

The next useful experiment should target the observed failure: require a model
to judge the supplied explanation as written, and distinguish approval from an
item that needs an explanation repair. That remains a diagnostic inside the joint
ground-truth task; it does not require inventing independent historical labels
for consensus and explanation fidelity. Apply the clearer task to both JEV and
the LLM so a workflow improvement is not confused with a model improvement.

Separately, the overall admission standard is still poorly captured. A classifier
adapted to the full set of historical decisions is an untested option; eight
reference examples are a small sample of that standard. Confirm what the `other`
rejections represent and examine contrasting development examples before treating
those labels as a complete specification. These are follow-up experiments, not
established fixes. Keep joke-family grouping and final evaluation design on the
critical path, and preserve the remaining unused examples.

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

The API comparison uses four accepted and four rejected development examples as
fixed references. It selects target groups without looking at their labels and
keeps whole groups together. The eight-example development trial excludes the
reference groups. The larger comparison selects 80 examples from the existing
practice partition; it does not create another split.

```bash
# If JEV_API_KEY is configured in your interactive shell:
source ~/.zshrc
uv run basedbench curation llm data/curation/historical-v2 \
  --history-audit data/curation/history-audit-v1.json \
  --split development --limit 8 --include-jev \
  --output data/curation/runs/new-api-development
uv run basedbench curation llm data/curation/historical-v2 \
  --history-audit data/curation/history-audit-v1.json \
  --limit 80 --include-jev \
  --baseline-run data/curation/runs/tfidf-v2 \
  --baseline-run data/curation/runs/minilm-v1 \
  --output data/curation/runs/new-api-calibration
```

These commands make paid requests. The adapter reads `OPENAI_API_KEY` and either
`JEV_API_KEY` or `TYPESAFE_API_KEY` from the environment or local `.env`. It does
not write credentials into the run artifacts. Omitting `--include-jev` runs just
the two GPT variants.

GPT uses `gpt-5.5-2026-04-23`, medium reasoning, a strict structured response, and
a 4,096-output-token limit. The image variant adds the original candidate image
at high detail; both variants receive the same text and text-only reference
examples. JEV uses `jev-1.13.0` and a native Choice question with accept, reject,
and defer options. It receives the same text evidence and historical references,
but cannot inspect image pixels or generate a written rationale. This tests one
direct admission question; breaking it into narrower questions remains a separate
experiment. [OpenAI model](https://developers.openai.com/api/docs/models/gpt-5.5),
[TypeSafe API](https://docs.typesafe.ai/api),
[JEV models](https://docs.typesafe.ai/models).

Each run freezes its selected IDs, inputs, references, policy, schema, model
versions, and source-code hash. Calls are saved individually. Resuming identical
settings skips saved calls, and a request interrupted before its result was saved
is marked uncertain rather than automatically repeated. Automatic retries are
disabled. Usage-based costs include reported reasoning tokens; calls without
usage remain explicitly unknown. Failure to produce a valid response leaves an
item undecided. The history auditor records both scored targets and reference
examples, including runs that scored only a subset of a partition.

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

Current local run IDs are `tfidf-v2`, `minilm-v1`, `llm-jev-dev-v1`, and
`llm-jev-cal-v1`, all on `historical-v2`.
The API runs used the adapter committed in `daa01b9`.
The encoder processed 932,343 content tokens in 5,714 pieces in about 39 seconds;
that local comparison made no paid API calls. The API experiments made 264 calls:
24 in development and 240 in calibration. The expanded `history-v2.json` and
`history-audit-v2.json` include all five runs across both corpus versions and
confirm the unchanged reserved-example counts above. Older artifacts remain unchanged,
including their original wording; this document and the history audit correct the
cross-run interpretation.
