# Bounded backfill source inventory

Issue [#4](https://github.com/montagovian/basedBench/issues/4), September 20, 2026.

## Completed inventory

**100 new candidate posts are frozen locally; 68 have a valid image and at least
three usable comments to take into the next checks.** No item has been accepted
into the benchmark. Collection used no model calls and cost $0 in model usage.

| Result | Count |
| --- | ---: |
| Qualifying metadata discovered | 108 |
| Selected candidates | 100 |
| Selected from ExplainTheJoke / explainitpeter | 78 / 22 |
| Existing-corpus or original-release post-ID overlap | 0 |
| Valid downloaded images | 73 |
| Missing images, all HTTP 404 | 27 |
| Successful comment requests | 100 |
| Candidates with at least one usable comment | 98 |
| Candidates with fewer than three usable comments | 6 |
| Image plus at least three usable comments | 68 |

The failures overlap: one candidate has both a missing image and fewer than
three comments. That leaves **32 candidates with an asset/evidence shortfall**.
Keep them in the inventory with their reasons; they were not replaced to improve
the apparent retrieval yield. The 27 missing images also have a changed or empty
live image URL. Reddit marks 22 of those posts deleted; the other five have empty
live image URLs without that deletion category. There were no source-date or
subreddit mismatches.

The two accessible communities returned 258 distinct metadata records over four
successful pages (260 rows including two deliberate pagination overlaps).
ExplainTheJoke supplied 86 qualifying posts and explainitpeter supplied 22.
Both ended with a short valid page; neither hit the ten-page cap. The third
community's failed discovery is the material coverage gap described below.
Eight otherwise qualifying posts remain outside the fixed 100-candidate sample.

All seven source days appear in the sample: June 20–26 counts are respectively
14, 20, 15, 17, 9, 13 and 12. The source community mix reflects the access gap and
selection rule, not a representative sample of all three communities.

The run retained 2,920 usable comments and 16,883,195 bytes of validated images.
Thirteen responses explicitly contain unexpanded comments. All threads remain
samples because replies were excluded regardless of whether a `more` marker
appeared. One candidate has an NSFW flag; this is metadata, not a substitute for
the visual policy checks in #5. Moderation/removal metadata is likewise not an
automatic content-policy verdict.

The main run recorded 107 JSON request attempts: 104 HTTP 200 responses and the
three HTTP 429 refusals. Image requests and authentication are tracked separately
from that JSON count. Initial access probes are preserved separately under
`data/backfill/source-probes-v1/`.

Inventory ID:
`dcecec6dc89aa1a89b92a6a44ecf4c0fe531c3ad6fe0dbb04ca11da2c03a0190`.

Implementation and results are committed locally, not pushed. The final
manifest was verified by an offline replay that loaded no credentials, made no
network requests and left the report unchanged. The baseline still matches the
read-only database audit, and exported release-image membership matches all 519
snapshot IDs. **358 tests passed**: 357 in the sandbox, plus the existing local
HTTP-server test rerun with loopback binding permitted outside the sandbox.

## Handoff

- **#5:** test publication policy with visual evidence and the existing human
  controls. Missing images defer; metadata flags alone do not decide suitability.
- **#6:** compare the 73 available images against the legacy corpus and one
  another. New post IDs do not establish new images or new joke families.
- **#7/#8:** consume this immutable inventory, preserve all 100 outcomes, defer
  asset/evidence shortfalls, and evaluate the 68 presently usable candidates.
  Three comments do not establish consensus. Keep incomplete-thread scope and
  the missing-community caveat in the pilot report.
- **#9:** before wider collection, resolve or explicitly retain the discovery
  access gap. Account for the 131 cached posts beyond the release's newest
  source date, gaps within the older archive, and the June 27–present period.

## Scope and plan frozen before collection

Inventory up to **100 new post IDs** from **June 20–26, 2026 UTC**, inclusive
(`2026-06-20T00:00:00Z <= created_utc < 2026-06-27T00:00:00Z`). Use the existing
three communities: ExplainTheJoke, PeterExplainsTheJoke and explainitpeter.
This is the first full week after the newest post in the local archive. It is a
small, chronological pilot slice; the intervening and subsequent periods remain
part of the larger backfill rather than silently disappearing from its scope.

The inventory has a **$0 model budget and makes no model calls**. It does not
change the corpus database, produce answers, admit items, or publish anything.
The later admission pilot should start with a proposed **$1 total model cap** for
these at most 100 candidates, reserving each call's maximum possible cost before
sending it and stopping/deferring when that cap is insufficient. That is a planning
ceiling for #7/#8, not a promise to finish all candidates for $1 or authorization
to increase the cap. Luna remains the intended LLM; JEV comparisons are optional
within the same cap. Prices and actual request bounds must be frozen there.

Discovery inspects at most ten pages of 100 metadata records per community:
3,000 returned metadata rows before retries, with timestamp overlap. This is
separate from the 100-candidate asset/comment limit. Preserve score >=10,
reported comments >=3 and direct-image criteria from the existing ingestion
workflow. Retain NSFW flags as evidence for #5, without treating them as final
policy decisions. Exclude post IDs already in the frozen local archive.

Select candidates by a fixed SHA256 ordering of seed plus post ID within each
community, then round-robin across communities until the ceiling or available
pool is exhausted. This provides repeatable community coverage without choosing
by apparent joke quality. It is not a proportional sample of Reddit traffic.
Do not silently replace selected items when their assets or evidence fail.

## What is recorded

The implementation is `src/basedbench/pipeline/source_inventory.py`, a standalone
module with `prepare` and `run` commands. All operational artifacts stay under
ignored `data/backfill/`. Preparation reads SQLite in a read-only transaction,
freezes release membership and archive post IDs/source dates, and records code,
baseline, plan and inventory hashes. Completed collections have a file manifest;
replaying a completed run verifies its files and makes no network requests.

Discovery logs every public response and failed attempt with its request window.
Descending pagination includes the previous boundary second and deduplicates
post IDs. A saturated timestamp, malformed page, request failure or page cap has
an explicit stop reason. A short valid page means only that this archive API
returned fewer than requested; **it does not prove complete historical Reddit
coverage**. HTTP 403/429 responses no longer become empty lists in the legacy
PullPush client either.

Requests are sequential, with three seconds between JSON calls and up to three
attempts for transport failures, HTTP 429 or server errors. Retry-After values
above 30 seconds stop that request rather than being ignored. Completed request
records, including failures, are reused on resume. A deliberately fresh fetch
needs a new inventory directory. Authentication secrets and token responses are
never recorded. Interrupted read-only GETs may be repeated.

For each selected candidate, record its source date, original archive metadata,
existing-corpus/release overlap, live metadata discrepancies, downloaded image
hash/dimensions/format/frame count, and comment-retrieval outcome. Image requests
use the existing HTTPS host allowlist, reject redirects, stream up to 20 MiB per
image, and validate the image with Pillow.

Comments use authenticated Reddit requests with top sort, limit 100 and depth 1.
Preserve the raw response, usable comment IDs/text/scores, filtered bot/moderator/
deleted counts, reported thread size and unexpanded `more` markers. Replies and
`morechildren` are not fetched: **a successful request is a sample, not a complete
thread**. Fewer than three usable comments remains a visible evidence gap. Three
comments and an image only establish availability; they do not establish three
agreeing explanations or benchmark suitability.

## Reproduction

```sh
uv run python -m basedbench.pipeline.source_inventory prepare \
  data/backfill/inventory-june20-26-v1 \
  --start 2026-06-20 --end 2026-06-27 --ceiling 100 --max-pages 10
uv run python -m basedbench.pipeline.source_inventory run \
  data/backfill/inventory-june20-26-v1
```

Read `report.json` for summary counts, `candidates.json` for selected evidence,
`discovery.json` for qualifying metadata and pagination outcomes, and
`baseline.json` for the original release/archive audit. Raw requests and images
are local artifacts, not public repository contents.

## Original-release coverage audit

The read-only audit and the existing export agree on the 519 release members and
snapshot ID `ad24bf870ce6285d`. The snapshot was created July 15, 2026 UTC and its
recorded dataset push happened that day. Its actual source posts range from
**September 28, 2023 to June 6, 2026**. None of the release or archive rows lack a
source date.

| Community | Release members | Newest release source post (UTC) | Existing archive posts | Newest archived source day |
| --- | ---: | --- | ---: | --- |
| ExplainTheJoke | 228 | June 6, 2026, 16:22:50 | 2,324 | June 19, 2026 |
| PeterExplainsTheJoke | 238 | June 5, 2026, 22:49:26 | 2,973 | June 19, 2026 |
| explainitpeter | 53 | June 1, 2026, 05:22:27 | 589 | June 19, 2026 |

The archive contains 5,886 posts; its latest retrieval was June 20. It already
contains **131 posts newer than the newest release member**: 44 ExplainTheJoke,
48 PeterExplainsTheJoke and 39 explainitpeter. Those cached posts remain available
for later admission work. Their presence does not establish that the intervening
period was collected exhaustively.

The broader work therefore retains three distinct coverage questions: the older
archive and its unadmitted candidates, this June 20–26 pilot slice, and the
subsequent June 27–present period. Only the middle slice is fetched here. The
original release and existing human judgments remain unchanged.

## Access findings

The initial probe confirmed Reddit OAuth authentication and live comment
retrieval. PullPush returned metadata for ExplainTheJoke and explainitpeter,
but refused the PeterExplainsTheJoke query with HTTP 429. The main inventory's
three attempts for that community all returned the same refusal, whose body
explicitly says the service does not provide free scraping resources for agents
and advertises paid access. No paid service was purchased and no workaround was
attempted. Treat this as a discovery-access gap, not zero posts in that community.

[Reddit's API documentation](https://www.reddit.com/dev/api/#GET_comments_{article})
describes comment listing parameters; our archived responses are the evidence
for the access and availability findings above. Provider documentation or a
successful endpoint does not prove a complete historical archive.
