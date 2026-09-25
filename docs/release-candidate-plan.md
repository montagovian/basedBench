# Immutable release candidate plan and shared contract

September 23, 2026. Parent: [#10](https://github.com/montagovian/basedBench/issues/10).
Executes [the handoff](release-candidate-handoff.md) on the existing local pool.

Implementation issues: [#28](https://github.com/montagovian/basedBench/issues/28)
(immutable contract), [#29](https://github.com/montagovian/basedBench/issues/29)
(export/report), [#30](https://github.com/montagovian/basedBench/issues/30)
(candidate assembly), and [#31](https://github.com/montagovian/basedBench/issues/31)
(pre-existing release-gate blockers).

The initial clean checkpoint audit failed: six new secret-scanner false positives,
15 Bandit findings, six vulnerable locked dependencies, and missing optional test
dependencies. The remote checkpoint therefore follows narrow security remediation
and a passing audit; independent implementation proceeds in the isolated checkout.
The findings are recorded without calling the initial audit a pass.

## Problem, deliverable, and boundaries

Legacy snapshot IDs freeze membership/answer hashes but resolve content through
mutable tables and image paths. Deliver a versioned, content-addressed release
directory, verified export, image-only evaluation inputs, and an offline baseline
report with cohort/exposure/coverage accounting. Preserve historical snapshots,
all frozen runs and exact feedback, and the two dirty UI files. No database
adoption of corrections, new model calls, automatic-checker promotion, collection,
dataset publication, merge, tagging, or prompt tuning is included. Budget is $0;
no experiment is launched. Any paid model panel needs an explicit later cap.

Checkpoint committed HEAD `09b1c42` on `backfill-foundation` with a draft PR after
clean-worktree code-publication checks. Implement in that isolated checkout; read
private inputs from the original workspace and keep outputs in its `data/` and
`export/` directories. No raw inputs enter Git or issue bodies.

## Evidence and selection rule

Read the roadmap, pilot and #26/#27 results, backfill plan, readiness policy,
snapshot/export/query/schema/CLI callers, and current #9/#10 issues. Legacy 519
membership remains a separate historical cohort; current bytes can be frozen
now but must not be claimed to reconstruct unrecorded historical image bytes.
Ready versions are six #26 originals (one tentative) plus two exact #27 accepted
proposals. Readiness is not clearance. Retain philosophers, Pride, eight overlap
holds and unqualified automatic admissions outside the candidate if required
clearances remain unknown. Report these limits rather than manufacture yield.

## Architecture and migration

Add an independent `basedbench release` CLI for file-based releases. Legacy
snapshot APIs and their historical consumers retain compatibility; do not mutate
or backfill old snapshot IDs. New release export/evaluation never join the live
database. An explicit adapter prepares a local selection from read-only source
records. This additive migration avoids silently blessing mutable legacy data.

### Contract v1 (settled before parallel implementation)

Module `pipeline/release_snapshot.py` exposes:

- `canonical_bytes(value) -> bytes`: UTF-8 JSON, sorted keys, compact separators,
  `ensure_ascii=False`, no NaN, newline terminator.
- `freeze_release(selection: dict, output_dir: Path, *, source_root: Path) -> dict`:
  validates selection/assets, writes a complete directory atomically, refuses any
  existing destination, returns the manifest. No network or database writes.
- `load_release(path: Path) -> dict`: fully validates schema, structure, digests,
  images, membership and path containment on every read; raises `ValueError` for
  invalid/incomplete/tampered payloads.
- `evaluation_inputs(path: Path) -> list[dict]`: verified `post_id`, `image_path`,
  `image_sha256` only. No title, answer, subreddit or source context to predictors.

Selection has only `name`, `policy_version`, `items`, and optional `evaluation`
(configuration only), with optional `description`. Every item has `post_id`,
`title`, `subreddit`, `ground_truth`, `image_path`, `cohort`, `exposure`,
`admission_origin`, `policy_version`, `answer_readiness`, `source_support`,
`content_status`, `suitability`, `duplicate_status`, `rights_status`,
`answer_provenance`. Cohort: `legacy` or `development`; exposure: `exposed` or
`unknown` (no unsupported unseen label). Origin: `legacy_human_validated`,
`human_curated`, `qualified_automation`, or `unknown`. Unknown states are explicit.
Status values: `pass`, `hold`, `unknown`, except readiness: `ready`,
`ready_tentative`, `repair`, `unclear`, `unknown`; rights: `mixed_rights` or
`unknown`. `answer_provenance` is a JSON object for local hashes/event IDs/version
references; it is private and NEVER copied wholesale to public output. Legacy
items may retain historical unknown gates, explicitly grandfathered by cohort;
development items require ready/ready_tentative and pass for source/content/
suitability/duplicates, mixed_rights, and non-unknown origin. Admission provenance
remains distinct from prediction/judge provenance.

Frozen manifest has `schema_version: "basedbench.release.v1"`, `name`,
`description`, `policy_version`, `evaluation`, `membership_sha256`,
`content_sha256`, and sorted `items`. Items retain selected metadata except
`image_path`; add `image_filename` (safe `post_id` plus extension from decoded format),
`image_sha256`, `answer_sha256`. Images live under `images/`. Membership digest is
SHA256(canonical_bytes(sorted post ID list)); answer digest is SHA256(exact UTF-8
answer); image digest is SHA256(exact copied bytes). Overall digest is SHA256 of
canonical manifest excluding only `content_sha256`. No creation timestamp or
source filesystem path enters the manifest digest. The manifest is canonical
`manifest.json`; validation re-computes everything. Sorting makes input iteration
order irrelevant. Name/config/provenance changes intentionally change the digest.
Invalid/missing images, duplicate/unsafe IDs, empty answers, unsupported states,
symlinks/path escapes, non-finite JSON, unknown schema and partial freezes fail.

Module `pipeline/release_report.py` exposes:

- `build_report(release_dir: Path, evidence: dict | None = None) -> dict`.
- `export_release(release_dir: Path, output_dir: Path, evidence: dict | None = None)
  -> Path` (atomic, refuses overwrite, deterministic bytes).

Evidence envelope: `schema_version: "basedbench.release-evidence.v1"`,
`predictions: []`, `judgments: []`, optional `historical_summary: {}`. Predictions
carry `prediction_id` (string), `post_id`, `model_id`, `prediction`,
`prediction_prompt_id`, `image_sha256`, `input_mode: "image_only"`. Judgments carry
`judgment_id` (string), `prediction_id`, `judge_model`, `verdict`
(`correct`/`incorrect`), `reasoning`, `judge_prompt_id`, `answer_sha256`,
`prediction_sha256` (SHA256 exact prediction UTF-8), `scoring_version`.
Configuration `evaluation` has `model_panel` (list of model IDs),
`prediction_prompt_id` (string or null), `judge_prompt_id` (string or null),
`scoring_version` (string, default `majority-v1`). Absent versions cannot qualify
reuse. Reuse requires exact image/prompt/input-mode match; judging additionally
requires exact answer/prediction/scoring/judge-prompt match. Duplicated evidence
IDs, multiple predictions for one post/model, and ambiguous repeated judge votes
fail explicitly (adapters must choose and freeze a particular historical attempt).
Unmatched rows are counted/explained, never silently treated as correct. Report
per legacy/development/combined cohort and per model: total items, predictions,
missing predictions, judged items, unresolved items, correct, incorrect, scored
denominator, accuracy (null when denominator zero), and multi-judge agreement.
Majority requires >=2 agreeing and strict majority of distinct judges. Preserve
unmatched historical summary under an explicitly unverified legacy section;
historical numbers are not current frozen-content scores. Report evaluated
versions, actual exposure and all limitations. Missing panel can be inferred
from evidence model IDs; adapters should name historical models explicitly.

Public export is an allowlist: normalized memes/predictions/judgments/leaderboard
tables, images, safe release hashes/provenance summary, report, dataset_info and
card. Strip answer_provenance and operational fields recursively by construction.
Never publish arbitrary historical_summary: extract safe numeric summary only
or leave it in local report. Keep permitted successful predictions and individual
judge verdicts/reasoning; exclude unverified records from current scored tables.
Maintain `license: other`, third-party rights and privacy wording. Card must state
composition/origin/exposure truthfully without calling all items human validated.

## Work packages and ownership

1. Primary: plan/issues/checkpoint; CLI `release_cli.py` and registration in
   `cli.py`; integration; README/roadmap/results; clean audit; PR and report.
2. Sol: immutable module `release_snapshot.py` and `test_release_snapshot.py`.
3. Sol: reporting/export module `release_report.py`, `test_release_report.py`.
4. Luna: read-only provenance inventory and candidate adapter
   `scripts/prepare_release_candidate.py`, `test_release_candidate.py`. Inspect
   source artifact schemas, freeze exact accepted answer versions in local
   eligibility ledger, identify missing gates, gather historical counts/version
   evidence. Never infer gate clearance from human answer labels. Use read-only
   SQLite. Adapter generates selection/evidence/held ledger; no model/network calls.

## Validation and done criteria

Test invalid/missing assets, changed answer/image, deterministic reorder,
corruption, atomic failure/overwrite, privacy, exact cache binding, denominator
and judgment agreement, image-only inputs and legacy compatibility. Freeze a
fixture, mutate live source answer/image/database, and prove export/evaluation
unchanged. Run full `uv run pytest` and clean release audit with original DB
read-only, explicit 519 expectation (audit default 500 is stale), candidate export
privacy validation and dry-run duplicate/status checks against a disposable DB
copy if existing commands require a writable connection. No UI changes planned.

Produce named local candidate, selection/held ledger, exact hashes, deterministic
report and actual model coverage. Verify all pre-existing private files and dirty
UI file hashes. Finish with a code PR, report paths, checks and remaining limits;
zero scored coverage must be explicit if historical binding cannot be proven.
Do not declare fresh quality established simply because artifacts are frozen.

## Expansion decision and risks

#9 remains unlaunched: exact interval, sources, candidate ceiling, retries and
fixed spending cap are undecided. Prepare a proposal only after this milestone;
June 27 onward and prior source gaps remain unprocessed. Risks include absent
legacy image bindings, unqualified automation, incomplete historical provenance,
missing assets, and privacy leakage through free-form records. Fail explicitly
or preserve unknown, never infer a successful release gate from answer readiness.

## Integration clarifications

The implemented scorer accepts only `majority-v1`; a new algorithm requires a
versioned implementation rather than an arbitrary label on the current formula.
Reports include an `evidence_sha256` over normalized, sorted evidence and the
private historical summary. Public reports expose this digest without copying
that arbitrary private summary. Copied export images are rehashed before final
publication to the local destination, and every image frame is decoded while
freezing/verifying. Image filenames use the actual decoded format.

The #26/#27 source ledgers use SHA256 of a canonical JSON string, whereas release
answers use SHA256 of exact UTF-8 text. The adapter preserves and verifies both
conventions explicitly, with frozen packet/journal/event references. Legacy
answer pairs must still match their original dataset version; current image
hashes cannot establish historical image identity. Historical prediction counts
and scores are distinguished by dataset version or explicitly labeled as
cross-version member history. Neither type is a current score without image
bindings. Read-only SQLite transactions include committed WAL data.

The original dataset/publication policy remains mixed-rights. Missing proof of
individual ownership and absence of a human label are not new mandatory gates.
Pilot outcomes remain held because the automation has not qualified for release;
the known individual failures/deferrals and unavailable evidence stay distinct.
The bounded expansion draft is in
[chronological-expansion-proposal.md](chronological-expansion-proposal.md), with
all proposed parameters explicitly awaiting a later decision.
