# Chronological expansion proposal — not launched

September 23, 2026. Parent: [#9](https://github.com/montagovian/basedBench/issues/9).
This is a concrete proposal following release engineering, not spending or
collection authorization. The earlier $1 pilot budget does not transfer.

## Proposed bounded scope

- Source interval: June 27, 2026 00:00 UTC inclusive to July 27, 2026 00:00 UTC
  exclusive, the next 30 days after the June 20–26 pilot. No claim that the
  archive before June 27 is complete.
- Sources: ExplainTheJoke and explainitpeter through permitted existing access.
  Retain PeterExplainsTheJoke as an explicit coverage gap until a permitted source
  is available; do not retry its known refusal of agent access or buy access as a
  workaround. No paid data service is included.
- Candidate ceiling: 1,000 unique newly discovered IDs, ordered by source time
  then post ID, processed in daily partitions with seven-day checkpoints.
  Check IDs and image/joke-family retrieval against the legacy and all earlier
  development pools. Record exact copies, uncertain family overlap and novel
  candidates separately. Do not silently replace missing images or skipped rows.
- Retrieval retry policy: at most three total attempts for transient failures,
  respecting Retry-After; otherwise 10 then 30 seconds. Stop a source if a
  Retry-After exceeds 60 seconds or access is explicitly refused. HTTP 404 and
  permanent denials are terminal recorded gaps. Comment retrieval remains partial
  unless coverage is actually established.
- Proposed model-call spending ceiling: **$5 total**, including generation,
  verification, repair, retry, and escalation costs. Paid calls must reserve their
  maximum allowed cost before dispatch, stop before exceeding the ceiling, and
  resume only from a versioned ledger. No extra capacity tier is implied. The
  exact policy/model configuration still needs to be selected and frozen before
  this proposal can execute; no previously unsuccessful checker is promoted.

## Purpose and stopping rule

Measure operational coverage, recoverable development candidates and cost over a
larger consecutive interval. This does not establish an independent fresh error
rate from agreement among models, and it does not authorize dataset publication.
Keep accepts labeled as development automation outcomes until the release gate
has evidence for qualified automation. Deferrals stay local without a mandatory
human-review queue. Human-ready versions remain separate from all other gates.

Stop on the end date, candidate ceiling, spend ceiling, source refusal, or a
systemic integrity problem; do not automatically extend the run or tune prompts
on its outcomes. Report discovered/retrieved counts, failed periods and assets,
partial comments, duplicate/overlap holds, policy outcomes, missing stages and
costs with separate denominators. Policy changes start a new artifact version.

## Decisions still open

The user has not selected this interval, $5 ceiling, source plan, 1,000-item limit
or model/policy configuration. No requests or calls have been made under this
proposal. #9 stays open and unlaunched. A new assignment can accept or revise this
bounded scope; release engineering alone does not answer the admission-quality
question or establish the missing source coverage.
