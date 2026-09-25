# Authorized chronological backfill — June 27 through July 26, 2026

September 23, 2026. Parent: [#9](https://github.com/montagovian/basedBench/issues/9).
Children: [#33 collection](https://github.com/montagovian/basedBench/issues/33),
[#34 processing](https://github.com/montagovian/basedBench/issues/34).

## Objective and authorization

Execute the first larger chronological backfill and report actual source coverage,
recoverable development candidates, defects, holds and costs. The user approved
June 27 00:00 UTC through July 27 00:00 UTC exclusive, two accessible communities,
and at most 1,000 new qualifying post IDs. They increased the model-call allowance
to **$10 if needed**. This plan freezes $10 as the total hard ceiling, not a target.
No collection or inference has started at plan creation.

This is operational expansion, not another checker-tuning experiment. The hypothesis
is that the existing staged workflow can recover useful candidate answers over a
consecutive interval within the cap. Compare coverage, processing yield and cost
with the preserved June 20–26 pilot descriptively; sampling and model differences
prevent a controlled quality comparison. Do not estimate an independent error rate
from model agreement. Do not promote any failed experimental checker.

## Constraints and non-goals

- Use ExplainTheJoke and explainitpeter via existing permitted access. Preserve
  PeterExplainsTheJoke as an explicit known access gap; never request it. Stop a
  source after explicit refusal or an excessive Retry-After. Do not buy access or
  bypass access controls. A service-wide refusal stops that service entirely.
- Select qualifying novel IDs by source timestamp then ID in ascending UTC daily
  partitions. Existing pilot filters remain score >=10, comments >=3 and a direct
  image URL. Count discoveries, filter exclusions, ID overlap, selection, asset
  retrieval, component outcomes and answer availability separately. Missing assets
  and missing comments are outcomes, not permission to substitute later posts.
- Preserve all existing data, immutable releases, human feedback and original
  dirty UI files. Read SQLite using mode=ro and a transaction. Never write the
  corpus, publish a dataset, merge PRs, or relabel automation as human validation.
- New additive modules leave the old pilot and experiment code unchanged so old
  frozen code hashes and results remain reproducible. New artifacts live under
  the original workspace's data/backfill/chronological-june27-july26-v1/.
- No new human queue, prompt tuning, capacity escalation, recurring ingestion or
  further date-window extension. Raw sources and operational logs remain private.

## Shared interfaces and immutable artifacts

All JSON uses existing canonical_json/digest/file_hash helpers. New directories
refuse overwrite; resumptions verify plan/code/input hashes and reuse records.
Each executable holds a nonblocking process lock. Completed replay makes zero
network/model calls. Preparation and run are separate commands.

1. `chronological_inventory.prepare(database, output, *, snapshot, start, end,
   ceiling=1000, prior_inventories=[])` and async `run(output, ...)` produce the
   existing inventory shape: plan.json with inventory_id, baseline.json containing
   archive posts and release_ids, selection.json, candidates.json, report.json,
   and manifest.json with inventory_id and relative file hashes. candidates.json
   rows retain post_id/title/subreddit/created_utc/source_date/image_url, image
   retrieval records, comment_retrieval and source_mismatches. Add daily coverage,
   source stops, prior-pool IDs, checkpoint summaries and unattempted partitions.
   Prior inventory input is the frozen June 20–26 inventory; the 18 audit identities
   already belong to the archive. Check prior manifests and exclude their IDs.
2. `chronological_duplicates.prepare(database, inventory, output, known_families,
   *, prior_inventories=[])` and `run(output, model_cache)` produce plan.json with
   audit_id/inventory_id, inputs.json and report.json with audit_id, edges and one
   disposition per new candidate. Edge schema follows duplicate_audit: left/right,
   status, evidence, release_members and scope. All old archive and prior pilot
   items form the comparison pool, and all new items compare with each other.
   Preserve exact-byte/pixel matches separately from uncertain image/crop/text
   retrieval. Near matches never become confirmed duplicate families automatically.
3. `chronological_admission.prepare_inventory(inventory, duplicates, output,
   *, budget_usd=10)` and async `run(output, *, budget_usd, api_key='', client=None,
   stop_after_new_calls=None)` produce frozen cases/assets/plan, requests/calls,
   report.json and results-manifest.json. Up to 1,000 cases share ONE run budget,
   with independent per-component evidence and existing pilot outcome shape.
   No batch can obtain a fresh allowance from the same authorization.

## Retrieval and spending policy

Use at most three total attempts for transient GET failures. Respect Retry-After
(including HTTP dates), or wait 10 then 30 seconds. Values above 60 seconds stop
the source; explicit denials/refusals are terminal on their first occurrence.
Image 404s are terminal. Record every public attempt without authorization headers
or token bodies. Apply existing HTTPS host/size checks and fully decode images.
Comments remain top-level samples with unexpanded-thread counts and no claim of
complete history. Stop at 1,000 selected IDs; retain unvisited dates as unattempted.
Persist per-day progress and seven-day checkpoint summaries; resume reuses evidence.

Select **gpt-6-luna**, Responses API, medium reasoning, standard/default service,
no tools, no fallback, no SDK retries, at most one repair and six calls per fresh
candidate. Reuse the pilot's content-policy-v2, answer-eval-v3 and minimum
suitability prompts as a separately versioned development workflow. Do not alter
old modules or old benchmark model configurations. Parse the new model identity
explicitly, using the same response schemas/citation validation and separate
content/answer/suitability decisions; never spoof a response's model identity.

Official model pricing checked September 23 at
https://developers.openai.com/api/docs/models/gpt-6-luna:
per million tokens input $0.10, cached $0.01, cache writes $0.125, output $0.50;
above 272K input tokens apply 2x input/cache and 1.5x output. Reserve the entire
1,050,000-token context at long-context write rates plus the full output cap
before each request, following the existing conservative Luna 6 bound. Actual
validated usage releases the excess. Unknown/interrupted requests retain the
full reservation and are never silently repeated. Store a versioned persistent
ledger/markers; account all generation/check/repair calls against $10. Stop
dispatch on fatal errors, allowance violations or inability to reserve the next
request; report affected cases explicitly. No priority/regional endpoint premium.

## Work packages and ownership

- Primary: plan/issues, branch, preservation inventory, integration, authorized
  execution, outcome inspection, report/docs/roadmap, final tests and commits.
- Collector (Sol): only chronological_inventory.py and test_chronological_inventory.py.
  Own resumable chronological coverage and refusal-safe source/asset retrieval.
- Duplicate adapter (Luna): only chronological_duplicates.py and
  test_chronological_duplicates.py. Own prior-pool inclusion and honest local
  image/text retrieval, using cached encoder with no network downloads.
- Admission (Sol): only chronological_admission.py and test_chronological_admission.py.
  Own model-6 parsing, staged processing, $10 shared ledger and zero-call replay.
  Reuse pilot schemas/helpers without mutating global model configuration.

These modules are independent through the artifact contracts above. Dependencies
are the existing synced all-extras environment, Reddit credentials, current OpenAI
key and pinned local encoder cache. Credentials must never enter artifacts/output.

## Validation and decision rule

Focused mocked tests must cover daily boundaries/order/ceiling, prior ID exclusion,
no request to the refused community, terminal and excessive Retry-After handling,
interrupted resume, manifest tampering, exact/uncertain duplicate distinctions,
all-pool coverage, returned-model and citation validation, whole-run cost reservation,
unknown-cost resume, no repeated calls, and denial/fatal stop. Integrate and run the
full pytest suite before paid execution. Preserve real run manifests and verify a
completed offline replay. Verify all preexisting files are unchanged.

Stop collection on end date, ceiling, service refusal or integrity failure; do not
fill failed partitions with a different interval. Stop models at the shared cap
or fatal failure. If no usable source candidates are obtainable, finish with the
specific recorded blocker and zero model spend rather than manufacture progress.
Inspect a deterministic sample of available accepts and deferrals against images
and source evidence; inspection is development analysis, not human gold. Report
all selected IDs even when no stages ran. Keep all automatic accepts as development
candidates. No release membership change is part of this milestone.

Done means the bounded run reaches its declared end/ceiling/stop, source and spend
ledgers reconcile, preservation and replay checks pass, meaningful code is committed,
and results state actual counts, costs, inspected defects and remaining gaps.
