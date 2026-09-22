# First newer-content admission assessment

Issue [#8](https://github.com/montagovian/basedBench/issues/8). The frozen batch
contains 100 candidates from June 20–26, 2026. The pipeline uses Luna, the
prepared component versions and a $1 cap. It creates development candidates;
it does not publish a release or change existing human labels.

The completed run produced **43 automatic accepts, one rejection and 56
deferrals**, for **$0.2331608 (about 23.3¢)** across 195 Luna calls. Assistant
inspection of all 54 candidates that reached models found no concrete issue
in 30 accepted rows and flagged 13. The decision is to fix specific answer,
suitability and duplicate weaknesses before expanding the date window.

## Outcomes and spending

The first stopping point gives an exclusive accounting of all 100 candidates:

| First stopping point | Candidates | Result |
| --- | ---: | --- |
| Evidence/source checks | 32 | Defer |
| Duplicate checks, after evidence passed | 14 | Defer |
| Content checks | 3 | One reject, two policy-boundary deferrals |
| Answer construction/checks | 8 | Defer |
| All checks passed | 43 | Accept for development |

Of 54 content checks, 51 passed. All 51 then attempted answer construction:
four declined for insufficient evidence; three proposals failed the evidence
check; one produced an inconsistent verifier response that failed validation.
The remaining 43 passed answer and suitability checks. Suitability rejected or
deferred **none of the 43 answers it saw**, despite the inspection concerns
below. No fresh case entered the repair branch, so this batch adds no evidence
about repair effectiveness; the earlier selected control exercise did.

The single content rejection is the Pringles/gloves/sponges sexual-device meme.
The two content deferrals are the slow-Wi-Fi/porn reaction and British-politics
coyote comparison. The latter relies on uncertain interpretation as well as
policy application. These few cases do not validate category-wide precision.

There are 28 candidates with a technical-error marker: **27 inherited
image-retrieval failures plus one answer-response validation failure**. There
were no provider failures, pending requests, unknown-usage calls or allowance
violations. All 195 returned model IDs are `gpt-5.6-luna`. Conservative cost
accounting was $0.23319005 against the frozen $1 ceiling.

All batch model spending, including deferred and rejected items, works out to:

- **$0.00542 per automatic accept** (about 0.54¢; 43 rows).
- **$0.00777 per provisionally usable development candidate** (about 0.78¢;
  30 inspected accepts with no concrete issue found).

“Provisionally usable” is an operational definition for this audit, not human
validation, release approval or an accuracy estimate. The 13 flagged rows
include four suitability concerns, three incomplete/mistaken explanations,
two overconfident intent readings, one evidence-count concern, one citation
cleanup issue and two members of one missed duplicate pair. That grouping is
exclusive for counting; detailed flags overlap. Several could become useful
after repair, clarification or selection of one duplicate representative.
Costs exclude prior development, collection infrastructure and this assistant
inspection; they are usage-based estimates, not provider invoices.

## What the inspection is testing

An automatic accept means that every frozen admission check passed. It is not
independent evidence that the explanation is correct. The assistant inspects
the saved images, generated explanations and supplied comment evidence, with
notes stored separately from automatic decisions. This is a development audit,
not fresh human gold or an accuracy estimate. It tests whether the answer
recovers the intended joke, not whether it supplies a theory of humor.

The useful distinction is between an explanation defect, unresolved evidence,
an evidence-rule inconsistency and mechanical cleanup. A flagged item is not
automatically a bad meme. No historical discretionary rejection is relabeled.

## Specific weaknesses in accepted explanations

**A description of context can pass as a joke explanation.** An uncaptioned
historical photo (`1ufp0ob`) receives a church/dictatorship interpretation even
though the supplied comments do not clearly establish an intended punchline.
A lawsuit headline (`1ubia3x`) receives an explanation based on comments
correcting the headline, which the model treats as the original post's intended
joke. These are suitability/evidence concerns, not objections to easy jokes or
text screenshots. The image needs a recoverable connection of its own; knowing
the surrounding facts is not sufficient.

The Haaland/Holland dinner anecdote (`1udm14c`) and celebrity-paparazzi collage
(`1ug8i86`) expose the same boundary between explaining an observation and
recovering a joke. By contrast, the uncaptioned battery photo (`1udmcvg`) is
deferred because the evidence identifies the object without establishing a
punchline. That contrast is a useful development control.

**Calling something wordplay does not decode it.** The quiz-team names
(`1ueh8cd`) pass with an answer that calls them puns without explaining the
names' sound-alike phrases. The long two-cows graphic (`1udr4rh`) passes with a
description of the format that leaves many individual references unexplained.
The state-puns cartoon (`1ucl7ul`) receives only its final connection and gives
Maryland a possessive “Mary's land” interpretation where the supplied decoding
uses “merry land.” This is missing or mistaken task content, not an aesthetic
judgment about joke quality. A verifier should identify the required connections
from image and evidence before asking whether a proposed answer covers them.

**Supporting comments do not necessarily establish consensus.** For the
Israel/2000s-fashion meme (`1udlwwn`), several comments support absurd blame,
but others propose materially different intentions. The model chooses “mocking
people who blame Israel for everything” as settled meaning. The sub-5 meme
(`1ubvmoj`) likewise calls the post parody while the evidence permits a sincere
reading. A correct account of the visible joke can sometimes remain neutral
about the author's intention. Otherwise the competing interpretations should
remain unresolved. Counting a supportive subset is not a disagreement check.

**The evidence-count rule is applied inconsistently.** Some plausible answers
are held because only two comments give the relevant explanation. Conversely,
the dog-supplement/cocaine pun (`1ubuulz`) passes with “Oh my sweet summer child”
counted as supporting evidence. That reaction does not explain the joke. The
generated answer itself fits the image: the concern is an unsupported claim
that the frozen evidence requirement was met. Do not confuse this with a
demonstrated wrong answer or silently loosen the requirement after the run.

**Mechanical cleanup and verifier errors need separate accounting.** The
Diogenes/square explanation (`1udqk4m`) gets the core connection but appends raw
comment IDs. A two-cows content rationale imports a comment's labor-camp
rewrite into its description of the actual image. An inconsistent Lily/Thanos
verifier tries to pass while marking a claim as supported by a minority
comment; schema validation defers that item. The latter protects the outcome,
but still exposes verifier fallibility.

These are findings about supplied evidence and interpretations. This inspection
does not independently fact-check every political, legal, scientific or
historical assertion in memes and comments. Explanations should attribute a
meme's claim rather than turn it into an unqualified real-world fact.

## Coverage and limits

The denominator includes all 100 frozen candidates. Of these, 32 have an
evidence/source shortfall, 20 have an unresolved duplicate finding, and six have
both. Thus 46 stop before model spending and 54 can reach the content check.
The source inventory has 27 unavailable images, partial top-level comment
threads and a discovery-access gap for the third planned community. It is not
an exhaustive sample of that week's memes.

Duplicate holds are unresolved retrieval findings, not 20 confirmed redundant
memes. The earlier image inspection includes both actual copies and same-topic
false alarms. Some archived matches are outside the published release, which
also differs from a redundant published copy. The frozen batch preserves those
holds rather than silently adjudicating them from this assessment.

The assistant also found a missed fresh-copy pair: `1ue5z6v` and `1uczut7`
contain the same children-on-phones photo and “beyond cooked” caption. Both
were automatically accepted. One has broad nonuniform side borders, which the
uniform-border trimming did not remove. The saved image hash distances are
28 and 23 against thresholds of 8, and the saved comment-embedding similarity
is 0.5115 against a 0.65 retrieval threshold. Both routes missed the pair.
This demonstrates one duplicate miss, not an estimate of overall recall.
Both rows receive a duplicate flag, although one representative could remain
useful; neither explanation is thereby wrong.

Topic descriptions in the local summary are overlapping assistant annotations
of inspected cases. They help identify what the pilot exercised; they are not
the formal tag vocabulary in #11 or estimates of source-population prevalence.
This run contains no new human judgments, and its examples now have development
exposure. Release selection and evaluation splits still need separate work.

| Community | Frozen candidates | Accept | Reject | Defer |
| --- | ---: | ---: | ---: | ---: |
| ExplainTheJoke | 78 | 34 | 0 | 44 |
| explainitpeter | 22 | 9 | 1 | 12 |

Every day in June 20–26 contributed automatic accepts: respectively 7/14,
7/20, 7/15, 8/17, 3/9, 5/13 and 6/12 candidates. Among the 54 inspected cases,
29 involve media/culture references, 13 politics/history, 12 science/technology,
11 wordplay and eight everyday/social situations; categories overlap. The
accepted set includes successful rebus, Gumball, time-travel-calendar and
literature-stereotype explanations, alongside the flagged examples. Content
policy and source access also affect this coverage, so counts are not a
measurement of the underlying communities' topic mix.

## Recommended next decision

Revise the answer/suitability checks and duplicate retrieval before expanding
chronological backfill.
Track these separately in [#16](https://github.com/montagovian/basedBench/issues/16)
(answer/suitability evidence) and [#17](https://github.com/montagovian/basedBench/issues/17)
(duplicate retrieval). Expansion [#9](https://github.com/montagovian/basedBench/issues/9)
remains contingent on a later decision after these results.
Use a small development comparison that tests explicit connection coverage,
competing interpretations and substantive comment support. Keep successful
simple puns, reference jokes and ordinary text screenshots as retention controls.
Handle citation debris as a mechanical output issue. Preserve the existing
frozen run and compare a separately versioned experiment against it.

Add the side-border pair as a duplicate regression case alongside the earlier
same-topic false matches. Test broader image retrieval and a second comparison
using supported new explanations, with explicit family/copy adjudication. Do
not simply lower thresholds and convert all retrieved pairs into exclusions.

Predeclare the comparison, success measures and a small total spending cap.
Report both defects caught and good cases lost. The examples in this report are
development cases; an apparent improvement on them needs a separate unseen
check before supporting unattended admission. The pilot does not justify a
larger model, broad prompt optimization, policy changes or automatic publication.

## Local artifacts and reproduction

- `data/backfill/admission-june20-26-v1`: frozen inputs, assets, requests,
  responses and automatic outcomes. Experiment
  `693a5150d40e61b740c85048211686e658bdc04949cde678a36106a9f7a1de61`.
- `data/backfill/admission-june20-26-analysis-v1`: separate assistant inspection,
  accounting summary, preservation/replay checks and read-only casebook.
- [Admission workflow](admission-pilot.md): component and budget contracts.

Rebuild the assessment without provider calls:

```sh
uv run --no-sync python -m basedbench.pipeline.admission_report \
  --run data/backfill/admission-june20-26-v1 \
  --output data/backfill/admission-june20-26-analysis-v1 \
  --inspection data/backfill/admission-june20-26-analysis-v1/assistant-inspection.json
```

The casebook keeps automatic outcomes and assistant observations separate and
links every case to its supplied comments and answer/check history. Raw corpus
material stays in ignored local directories.

## Verification

All **424 tests passed**, including nine report/accounting cases. The final
casebook was checked in the browser: all 100 rows, 43 accepts and the 13 flagged
accepts filter correctly, and images and inspection text render together.
An offline replay with a client that fails on attempted provider calls made
**zero calls** and left all **466 saved run files** byte-for-byte unchanged
(excluding the run lock). Frozen input and result manifests validate.

The corpus database, review events, reassessment feedback and historical
examples retained their pre-run hashes. All 100 fresh cases still have no human
labels; inspection notes remain a separate artifact. Code and report changes
are committed locally and remain unpushed.
