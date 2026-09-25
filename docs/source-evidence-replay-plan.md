# Approved retrospective source-evidence replay

September 24, 2026. [Issue #36](https://github.com/montagovian/basedBench/issues/36),
parent #9. The user approved proceeding with the revised
[proposal](source-evidence-policy-proposal.md): reconstruct existing labeled
data, reuse saved results, and complete one comparison within **$1 total model
API spend**. No new bespoke test set or annotation round is required.

## Deliverable, hypothesis and limits

Deliver a reproducible reconstruction of actual human answer judgments, matched
historical checks, one frozen new-policy comparison and a report on answer
regressions, evidence changes, source access and cost. Hypothesis: replacing the
three-comment quota with claim-specific evidence can recover supported answers
without admitting known material answer defects. External sources may improve
reference support independently of the quota change.

This is an exposed-development audit, not a population accuracy estimate or a
release qualification. Preserve every old run, exact human feedback, database,
immutable release and unrelated original app/helper-test edits. No new historical
collection, answer rewriting, prompt tuning, second run, human gold invention,
automatic policy adoption, merge or publication. Old modules stay unchanged.

## Reconstruction and shared contract

Private output root: original workspace
`data/backfill/source-evidence-replay-v1/`. Additive modules live in the isolated
worktree, branch `codex/source-evidence-replay`, stacked on chronological-backfill.

`source_evidence_dataset.prepare(data_root, output)` writes `cases.json`,
`manifest.json` and `report.json`, refusing overwrite. Sources include the four
frozen explanation/materiality/fresh/targeted feedback snapshots and explicit
ground_truth judgments in review-v1 and attributable reassessments. Inventory
other labels but do not reinterpret admission-only or model labels as human
answer quality. Verify available source manifests, events and exact answer/image
hashes; ambiguous/unmatched events are reported, never silently guessed.

Each case is keyed by post ID plus digest of exact `input` (the original
explanation, comment_evidence, image_sha256). Keep distinct answer/evidence
versions. Fields: `case_id`, `post_id`, `input`, `input_sha256`, `image_path`
(absolute verified local path or null), `image_error` (null or explicit hold),
`group_id`, `human` (`quality`: ready/repair/unclear/conflicting; `events`: exact
source-attributed judgments and notes), and `provenance` (source hashes/paths,
answer version and event IDs). Preserve revisions; do not collapse contradictory
independent labels into a convenient verdict. Keep tentative/unclear notes.
All source-backed identities remain in the denominator, including unsupported
animated/missing images; no replacement or silent frame extraction.

`source_evidence_baselines.prepare(data_root, dataset, output)` matches saved
requests/results from the declared existing experiment directories by exact
image bytes, explanation and comment packet. Writes `matches.json`, a report and
manifest. Each match records case_id, source path/hashes, stage, actual model,
prompt/schema/input versions, repetition, parsed findings, and whether its
verdict is joint or separates answer/evidence. Keep all matched repeats and
conditions; choose no favorable result. Cached GPT-6 Luna simple-check results
are the closest comparison, other models/policies are descriptive. Changed
inputs and unverifiable caches remain unmatched. No paid baseline regeneration.

External evidence is a separate `sources.json` list, frozen before dispatch.
Each entry has `source_id`, `post_ids`, `url`, `source_type`, `access_status`,
`retrieved_at`, `title`, `passage` (concise source-grounded summary/excerpt),
`lineage_id`, `discovered_from`, `limitations`, and `support_scope`. Only read,
accessible evidence is supplied to models; unavailable links remain separate
metadata. Source access and page identity must be honest. Useful references are
not hallucinated from a URL. Preserve all references as fallible evidence.

Follow evidence links/identifiable references where they can resolve an essential
claim, prioritizing existing external-reference leads, KYM entries, originals and
documented reference uncertainty. Freeze the selection rationale before model
outcomes. Bound research to three distinct pages/two hops per post and one focused
search if needed, with at most 30 researched posts and no replacements selected
from new verdicts. Shared pages may serve multiple posts. Record unresearched
cases and accessibility limits. No paid data service or access bypass.

## New checker and execution contract

`source_evidence_eval.prepare(dataset, sources, output, *, budget_usd=1.0)` and
async `run(output, *, api_key='', client=None)` freeze requests, copied assets,
code/prompt/schema/pricing/input hashes, jobs, shared allowance and results.

Run `original_evidence` once for every supported image/input case. Run
`external_evidence` only for cases with an accessible relevant source overlay;
unchanged evidence has no duplicate call. Two calls maximum per answer version.
Keep all holds and missing results in the report. Deterministic dispatch by case
hash, with each eligible external pair adjacent, frozen before calls. No repairs,
repeats or retries. The final exact N + E maximum is recorded after reconstruction,
before any paid dispatch. No arbitrary twenty-case subsample.

Requests use an explicit allowlist: image, candidate explanation, source comments
and the arm's external evidence. Human labels, notes, old judgments, membership,
source filenames revealing labels and alternative answer versions never enter
the request. Model tools/browsing are disabled.

Use GPT-6 Luna, medium reasoning, high-detail image, standard/default tier,
3,200 output tokens and concurrency one. The larger output allowance accommodates
explicit claim evidence; it is fixed before outcomes, not tuned after truncation.
Keep answer-quality instructions grounded in the prior simple interface. New
evidence instructions assess visible setup, required reference and this-instance
connection; no comment/source quota, no invented confidence score, no historical
trivia requirement. A merely possible alternative is not automatically a defect.
One directly verified chain can suffice; correlated citations are not independent
witnesses. KYM researched entries are preferred sources, not automatic authority
over arbitrary variants. Content/suitability/duplicates are outside this checker.

Return separate `answer_quality` pass/fail/uncertain and `evidence_status`
supported/insufficient/competing_readings/uncertain, concise concrete defects and
reason, and up to six essential-claim records. Claim record: `claim`, `status`
supported/insufficient/conflicting, `basis` image/comments/external/mixed,
`image_anchor`, `comment_ids`, `source_ids`, `connection`. Validate cited IDs,
available sources, nonempty supporting basis, and logical consistency. No
three-citation constraint. Optional historical context must not become mandatory
answer content. Deterministic combined routing derives from the two decisions;
technical errors remain separate, not answer failures.

Official pricing was checked September 24 at
https://developers.openai.com/api/docs/models/gpt-6-luna: per million input
$0.10, cached $0.01, cache write $0.125, output $0.50; above 272K input tokens
apply 2x input/cache and 1.5x output. Reserve the full 1,050,000-token context at
long-context cache-write rate plus output allowance before each call, reusing
the verified conservative pricing machinery. Settle valid saved usage; unknown
calls retain reservations and stop further dispatch. Validate actual returned
model/tier and token accounting; fatal errors stop. Persist markers before
dispatch, no SDK retries, safe lock, resume never repeats unknown work. One
persistent $1 ledger covers both arms and failures. Stop if the next worst-case
reservation does not fit; report unfinished cases, no new allowance/directory.
Completed replay must work without credentials/network and verify all hashes.

## Ownership and dependencies

- Reconstruction (Sol): `source_evidence_dataset.py` and focused dataset tests.
  Own manifest/event/hash reconciliation and exact answer versions.
- New evaluator (Sol): `source_evidence_eval.py` and focused evaluator tests.
  Own schemas, prompt, blinded payloads, frozen preparation and one-budget runner.
- Baseline adapter (Luna): `source_evidence_baselines.py` and focused matching tests.
  Own read-only provenance-safe reuse of cached model findings.
- Primary: plan/issues, source research/overlay, preservation inventory, integration,
  execution, result analysis/inspection, docs and commits. Own final review of
  schemas, all changed verdicts versus reliable matched baselines, and remaining
  false passes on human-repair answers. No concurrent shared-file editing.

Use existing uv environment and original workspace credentials without logging
keys. No benchmark model configuration changes. Resolve interface issues before
agents diverge; additive modules may import stable existing helpers only.

## Validation and decision rule

Focused tests: exact answer/event reconstruction, deduplication/revisions/conflicts,
missing labels/assets, cached result mismatch/repeats/model distinctions, allowed
citations, single-chain/image-only passes without quotas, contradiction/variant
uncertainty, human-label leakage, immutable manifests, whole-run cost cap,
unknown-call resume, fatal model/tier handling and credential-free replay.
Run the complete suite before paid execution and the existing release/security/
privacy audit where applicable. Independently reconcile saved token usage and
verify protected prior hashes after completion.

Report exact cases, posts, versions, known families, missingness and label strata.
Compare answer predictions against ready/repair labels; unclear/conflicting and
tentative notes stay visible. Report source-support changes without inventing
human source labels. Show same-model exact-input matched comparisons separately
from unmatched cases, other-model baselines and jointly scored historical gates.
Same-input repeats are variability evidence, not additional independent cases.
The new interface changes alongside its policy, so do not attribute all changes
solely to removing a number. External-arm paired differences share the new schema.

Recovery is useful only if known-ready retention and known-defect detection hold
up. Inspect new false passes, newly rejected ready answers and external-source
changes against their actual images and frozen human notes. No improvement claim
from a larger automatic pass count alone. If material regressions remain, report
the policy principle separately from checker reliability and do not silently
promote it. Finish this one milestone even if negative: complete or cap-stopped
run, reconciled costs, preservation/replay pass, readable findings and explicit
adoption recommendation. No further tuning or annotation prerequisite.
