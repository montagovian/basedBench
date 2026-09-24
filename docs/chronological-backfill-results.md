# Chronological backfill results

September 23, 2026 local date. Parent: [#9](https://github.com/montagovian/basedBench/issues/9).
Implementation: [draft PR #35](https://github.com/montagovian/basedBench/pull/35),
stacked on the immutable-release foundation in #32. See the
[authorized plan](chronological-backfill-plan.md) and
[operations guide](chronological-backfill-runbook.md).

## Collection

The authorized window was June 27 00:00 UTC through July 27 00:00 UTC exclusive,
with a 1,000-new-post ceiling and up to $10 total in model calls. The actual run
selected **251 new posts from June 27 through July 15** before the archive service
explicitly refused agent access when the collector first queried July 16. The collector
stopped archive requests immediately, without retries or a different endpoint.
Previously selected posts continued through the permitted image/comment retrieval.

| Measure | Observed result |
| --- | ---: |
| Distinct archive posts returned | 688 |
| Excluded by unchanged score filter | 307 |
| Excluded without a direct image URL | 126 |
| Excluded by archived comment-count filter | 4 |
| Selected new IDs | 251 |
| ExplainTheJoke / explainitpeter selected | 182 / 69 |
| Available images / terminal image 404s | 224 / 27 |
| Comment samples with usable comments / empty after filtering | 248 / 3 |
| Fewer than three usable comments | 14 |
| Image and at least three usable comments, without source mismatch | 214 |

The 27 source mismatches are unavailable live image URLs paired with archived
URLs whose images return 404. These are retained outcomes, not replacement slots.
All available images are static JPEGs (194) or PNGs (30). Four cases with too few
comments also lack an image, so availability failures must not be summed as if
they were disjoint. Evidence availability does not establish three supporters of
the same reading, answer correctness, content clearance, usefulness or novelty.

Of the 60 planned day/community partitions for the two selected communities,
38 returned a short valid archive page, one failed with the explicit refusal,
and 21 remained unattempted. A short archive page establishes only the endpoint's
observed response, not complete historical Reddit coverage. PeterExplainsTheJoke
was never requested and remains a separate known access gap. The older archive,
the June 20–26 pilot, and July 16 onward are not represented as complete history.

All 251 selected IDs are unique, chronological, within the approved dates, and
absent from both the existing archive and earlier pilot. The source-request log
contains 290 JSON requests with 290 total attempts: 289 HTTP 200s and the single
HTTP 429 refusal.
Image requests are counted separately. Comments remain partial top-level samples;
no replies or morechildren expansion was performed.

Inventory ID: `554125068a4161fb4c8576440a3c51a83a0fcb0c643fc27d783510c88012c148`.
Selection digest: `aa4b5aab430baddc903f6326d59cc6c481d5e0fbf0f952ac9450d7914d15d7e9`.
Completed inventory replay returned the identical report without network access.

## Duplicate audit

The comparison pool includes the 5,886 archived identities, the prior 100-post
pilot, and all 251 new identities. The known-family input preserves three earlier
groups and adds only the two subsequently human-flagged, image-inspected pairs.
Its five groups contain ten existing archive IDs; unresolved #26 overlap holds
remain separate. Exact byte/pixel matches and uncertain image/crop/text retrieval
have distinct evidence. Crops are searched among bounded coarse image neighbors,
not as an exhaustive all-pair family audit.

The completed local audit found **two confirmed exact-byte matches**, both to
unpublished archive items, and **83 uncertain pairs**. The pair methods overlap:
43 near-image, 24 crop-window, 52 MiniLM and one TF-IDF match, plus the two exact
matches. These are retrieval findings, not 83 confirmed duplicate families.
Candidate dispositions are 159 with no match found, 71 with uncertain matches,
two with exact-copy matches and 19 unassessed because an image is unavailable
and no other match was retrieved. Absence of a match does not prove novelty.

The comparison pool has 5,390 usable archived images, 73 prior-pilot images and
224 fresh images; 479 archive images are missing and 17 are unsupported animations.
Text retrieval covers 2,880 identities, including 97 from the prior pilot and
246 fresh identities, with 222,698 packed tokens and zero omitted tokens. The
five supplied older families are preserved as diagnostic labels; their pairs do
not involve fresh queries and therefore were **not reassessed** in this run.
They do not provide a new recall estimate.

The audit incurred zero API cost, and its completed replay returned the identical
report. Its main runtime cost was repeated full-image decoding for 11,943 crop
pairs; caching decoded images is a future performance improvement, not a change
to this frozen run.

Audit ID: `938eeac04912212839c818ffc4b3af134617a530a9335580bdf878454bc58b76`.

## Admission processing

The frozen admission run retains all 251 identities. Source-evidence preflight
passes 214 and defers 37. Duplicate routing separately passes 178 and defers 73;
nine duplicate holds overlap preflight deferrals, leaving **150 eligible for
model calls and 101 stopped before models**. Exact matches outside the published
release are not automatically rejected, but additional uncertain links remain
holds. No published exact-copy rejection was found.

The run completed with **94 automatic development accepts, nine rejections and
148 deferrals**. Every selected identity has a recorded outcome. The disjoint
processing flow is:

| First stopping point / completed path | Identities | Result |
| --- | ---: | --- |
| Source-evidence preflight | 37 | Defer |
| Duplicate hold after passing preflight | 64 | Defer |
| Content check | 19 | Nine rejects, ten deferrals |
| Answer stage | 37 | Defer |
| All model checks passed | 94 | Development accept |

Among the 150 identities that reached models, content passed 131. Generation
proposed 120 drafts and reported insufficient evidence for 11. Answer checks
retained 94 candidates, deferred four unresolved answers and rejected 22 outputs
as technically invalid. Four answers received the single permitted repair;
three repaired versions passed. All 94 answers reaching minimum suitability
passed it. These outcomes neither qualify release membership nor establish
independent human consensus.

The 49 recorded technical-error identities comprise 27 unavailable/mismatched
source images and 22 model-stage deferrals. Six provider responses reached the
2,400-token output cap. Sixteen completed answer-check responses said `pass`
while also flagging unsupported material claims, which the existing validator
rejects as inconsistent. These technical findings are separate from a judgment
that the underlying answer is wrong. No call was retried or escalated.

| Community | Selected | Accept | Reject | Defer |
| --- | ---: | ---: | ---: | ---: |
| ExplainTheJoke | 182 | 75 | 6 | 101 |
| explainitpeter | 69 | 19 | 3 | 47 |
| Total | 251 | 94 | 9 | 148 |

There were **503 API calls**: 150 content, 131 generation, 120 initial answer
checks, four repairs, four repair verifications and 94 suitability checks.
All 503 returned the requested `gpt-6-luna` model and `default` service tier;
497 responses completed and six were incomplete at the output cap. No identity
used more than six calls or one repair. Provider response IDs are unique.

Saved token usage reconciles independently to **$0.354214875 estimated cost**
and **$0.354362125 conservatively accounted cost**, against the single $10 cap.
There are zero unknown-usage calls, zero pending requests and no allowance
violation. Estimated API cost per automatic accept is approximately $0.00377;
this is not cost per independently qualified release item. Completed replay
without an API key returned the identical report and made zero API calls.

Experiment ID: `5ad682c483f5ca5b9edf510e2a556db7c4713cbba3c8bff025491e42e45fb9c9`.
Report SHA-256: `c35d20903d30e5c171acee03e9f9be8a89df4156e5c7f7a6f89b5aabffc34c76`.

## Descriptive comparison with the earlier pilot

| Measure | Preserved June 20–26 pilot v1 | This chronological run |
| --- | ---: | ---: |
| Selected identities | 100 | 251 |
| Available images | 73 | 224 |
| Identities reaching models | 54 | 150 |
| Automatic accepts / rejects / deferrals | 43 / 1 / 56 | 94 / 9 / 148 |
| Model | GPT-5.6 Luna | GPT-6 Luna |
| API calls | 195 | 503 |
| Estimated API cost | $0.2331608 | $0.354214875 |

These are different dates, source coverage, comparison pools and model versions;
the table describes operational yield and cost, not a controlled quality gain.
The later zero-call v2 replay of the older pilot remains separately frozen at
41 accepts, one rejection and 58 deferrals.

## Outcome inspection

The predeclared sample contains 12 accepts, six deferrals and four rejections.
Assistant inspection is complete for all 22, including all 21 available images;
one deferred source image is unavailable. Raw reviewer notes and the primary
assistant's integration remain separate, with disagreements preserved. None of
these judgments changes a frozen outcome or creates a human label.

Among the 12 accepted answers, integrated inspection finds ten adequate, one
material setup error and one unresolved reference omission. In `1uh5qe5`, the
answer gets the exponent pun but changes the birthday roles: the image says a
parent turns 20 and their daughter turns one, while the answer says the dad turns
one. In `1urdvvt`, the answer explains the visible Shrek comic premise but omits
the animated edit described by commenters. Whether that omission misses the core
joke needs human judgment; the static source cannot verify the animation. These
are development findings, not a measured error rate for the 94 accepts.

The India/suburban-environment case (`1uuk1h2`) illustrates a reviewer disagreement:
the first inspection flagged source support and suitability, while integration
found at least three substantive comments supporting the core contrast between
private wealth and shared surroundings. Disagreement with a caption's factual
claim does not necessarily mean disagreement about its intended reading. The
minimum suitability rule was not tightened to exclude social comparison or easy
inferences.

All ten sampled deferrals/rejections lack a candidate answer, so answer adequacy
is unassessed. The six deferrals retain missing-image, duplicate-family or
source-support uncertainty. Two text-retrieved duplicate holds share themes or
references with their counterparts; this inspection does not confirm a duplicate
family or automatically clear the holds. One initial reviewer missed an available
archive counterpart; integration records the correction and image inspection.

Two of the four sampled content exclusions have direct rendered-slur anchors.
The other two warrant human policy judgment: `1urfac1` depends on whether a
football-riot stereotype establishes the existing hate/dehumanization exclusion;
`1uvg6gb` uses a literal flood-control word whose derogatory homonym appears in
comment interpretations. These are potential over-exclusions, not confirmed
false rejections. The automatic outcomes and original reviewer positions remain
unchanged, and no policy revision or tuning run follows this inspection.

At the user's request for material to validate, a private standalone worksheet
now presents this same 22-case sample at
`data/backfill/chronological-june27-july26-v1/human-validation-v1/index.html`.
It embeds images, proposed answers, source comments and available duplicate
counterparts, with separate answer/support/content/suitability/duplicate fields.
Automatic reasons are collapsed and assistant notes are omitted. Exported notes
retain exact user input and frozen provenance without writing the corpus or
release. Human feedback has not yet been received. Browser inspection verified
rendering, navigation, note retention and the missing-image case; temporary test
text was cleared. This optional worksheet is not a new mandatory review queue.

## Validation and artifacts

The full suite passes **580 tests**. The release audit passes Git hygiene,
secret scanning, Bandit, dependency checks, database checks and immutable-export
privacy checks. One Bandit false positive on a suitability `pass` verdict mapping
received a line-specific B105 annotation; no scan was disabled. Legacy status,
cleanup preview and compatibility export also pass on a disposable database copy.
The compatibility export contains 519 memes/images, 2,785 historical predictions
and 10,660 judgments; its privacy audit passes. These historical counts are not
new frozen-content evaluation scores.

Runtime evidence is private under
`data/backfill/chronological-june27-july26-v1/`: frozen inventory, source request
records, image/comment outcomes, known-family provenance, validation logs and
the inspection sampling plan. The inspection plan was frozen before model calls:
up to 12 accepts, six deferrals and four rejections, ordered within each outcome
by a fixed digest. Assistant inspection remains development analysis, not human
gold or an independent population error estimate.

The database, original human feedback, previous runs, immutable 519-item release,
and unrelated UI edits remain unchanged: the final hash check matches **all
26,994 protected preexisting files**. The run adds zero release members. No dataset
publication, merge, automatic release adoption or new mandatory human-review queue
occurred. The run's completed replay, independent cost reconciliation and final
preservation evidence are saved under its private `validation/` directory.
