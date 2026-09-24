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
explicitly refused agent access on the first July 16 request. The collector
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
absent from both the existing archive and earlier pilot. The run made 290 JSON
requests with 290 total attempts: 289 HTTP 200s and the single HTTP 429 refusal.
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

Budgeted model processing is in progress. Final outcomes, costs and inspection
findings will be recorded here when that stage finishes. No results from an
unfinished stage are inferred.

Experiment ID: `5ad682c483f5ca5b9edf510e2a556db7c4713cbba3c8bff025491e42e45fb9c9`.

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
and unrelated UI edits are outside this task's write scope. No dataset publication,
merge, automatic release adoption or new mandatory human-review queue is included.
