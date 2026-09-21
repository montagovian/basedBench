# Bounded backfill source inventory

Issue [#4](https://github.com/montagovian/basedBench/issues/4), September 20, 2026.

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
sending it and stopping/defering when that cap is insufficient. That is a planning
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
