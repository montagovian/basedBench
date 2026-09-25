# Fresh-agent handoff: freeze and evaluate a release candidate

## Execution update — September 23, 2026

This handoff has now been executed through the zero-cost existing-pool engineering
milestone. Start future work from [the results](release-candidate-results.md) and
[settled contract](release-candidate-plan.md), not by repeating the checklist below.
[Draft PR #32](https://github.com/montagovian/basedBench/pull/32) is on
`backfill-foundation`; implementation lives in the isolated worktree, leaving the
original dirty app/test files and all prior private artifacts unchanged.

The local candidate freezes 519 legacy items; 118 development identities stay
outside membership, with eight exact human-ready versions preserved. Historical
image bindings are unavailable, so the report separates stored legacy history
from zero current certified score coverage. #10 remains open for the qualified
new cohort/evaluation. The user subsequently authorized #9's June 27–July 26
development backfill with a 1,000-post ceiling and $10 total model-call cap.
Use the [chronological results](chronological-backfill-results.md) and
[execution plan](chronological-backfill-plan.md) for that later work. The original
proposal below is historical, not a pending approval request. No dataset
publication or merge occurred.

The remainder is the original pre-execution handoff record.

Prepared September 23, 2026. The current task produces this handoff and updates global/local agent instructions. The recommended next assignment is a remote checkpoint followed by a working release candidate. No remote checkpoint, release implementation, or new collection run has been performed by this documentation task.

## Copy/paste starter prompt

> Execute `docs/release-candidate-handoff.md`: checkpoint the existing committed work on a remote `backfill-foundation` branch with a draft PR, then implement the #10 release-candidate pipeline. Inspect current Git state and instructions, write a detailed plan, and settle the snapshot schema/API before parallel edits. Create meaningful child issues with `gh`, delegate substantial disjoint work to Luna/Sol, and integrate it centrally. Preserve dirty user files, frozen runs, and human feedback. Before paid expansion under #9, establish its exact date window, source plan, candidate ceiling, retry policy, and fixed spending cap. Finish with a reproducible candidate and baseline report; keep public dataset publication and merging out of scope. Proceed with authorized work without additional routine confirmation.

## Current checkpoint

The working branch is `main`, with pre-handoff baseline `62d2241`. As of the September 23 fetch, `origin/main` was 68 commits behind and had no remote-only commits. The committed diff against `origin/main` spans 121 files (`+22,974/-23`); there was no open PR. Those counts describe the pre-handoff checkpoint; the parent task may add this document and update instructions. Preserve unrelated dirty changes in `src/basedbench/app.py` and `tests/test_app_helpers.py`; do not reset, stash, or discard them. Repository: [montagovian/basedBench](https://github.com/montagovian/basedBench), public. Code pushes are not data backups.

The latest discussion recommends preparing [#10, freeze and evaluate the candidate release](https://github.com/montagovian/basedBench/issues/10), on existing candidates first, then feeding it [#9, chronological backfill](https://github.com/montagovian/basedBench/issues/9). The older roadmap still records the calibration sequence and leaves expansion pending; its larger release depends on #9. This sequencing change moves release engineering forward without promoting an unsuccessful checker. Reuse #10 and #9 as parent issues, update their plans and the roadmap when implementation starts, and create only meaningful child issues. The current documentation task creates no new issue.

### Evidence to carry forward

- The legacy release has 519 human-validated items. Preserve its membership, historical predictions, judgments, and reports. Do not rewrite old snapshots or relabel old runs using newer answers.
- The initial newer-content pilot covered 100 candidates from June 20–26: 43 automatic accepts, one rejection, and 56 deferrals for about 23.3¢, within its specific $1 admission-model cap. That small experiment cap does not authorize or transfer to a larger chronological run.
- The #26 audit found six ready original answers (one tentative), three repair, and one unclear among ten. #27 supplied two exact human-ready proposals (Mamdani and Bowsette); the philosopher proposals remain repair and Pride has no new saved judgment. Eight of ten identities have a ready version; the full 18-item selection retains eight overlap holds. Those holds are retrieval candidates, not confirmed duplicates. See [#26 results](fresh-human-audit-results.md) and [#27 results](targeted-corrections-results.md); do not copy local raw feedback into public artifacts.
- No model checker or answer variant has been promoted. Do not restart a prompt tuning loop, create a broad mandatory human queue, or automatically promote checker output. Manual corrections are curation evidence, not database adoption or model-quality results.
- Existing source coverage is incomplete: the legacy snapshot's newest source post is June 6 despite its July 15 creation date; the local archive extends through June 19; the bounded pilot covers June 20–26; June 27 onward is unprocessed. PullPush discovery returned 429s in the Peter Explains the Joke source check, 27 of 100 pilot image URLs returned 404, and comment retrieval was partial. Never report archive or month completeness where retrieval did not establish it. See [backfill assessment](backfill-pilot-results.md) and [automated backfill plan](automated-backfill-plan.md).
- A human-ready answer does not establish source support, publication/content clearance, image rights, task suitability, or duplicate status. Keep these findings separate. The already inspected and tuned-on pools are exposed development evidence, not unseen holdouts. Earlier cross-run audit found 244 of 286 reserved examples had already appeared in a smoke test; only 42 were unused across both versions. Record actual exposure for any future cohort instead of inheriting a stale holdout label.
- The #27 preparation records a 508-test baseline. Later document analysis did not rerun tests; do not claim a new pass from it. Run `uv run pytest` for release-facing code changes, as required by the repository instructions.

The exact latest local feedback is frozen under `data/curation/fresh-human-audit-feedback-v1/` and `data/curation/targeted-corrections-feedback-v1/`. The available answer versions and their source hashes/event IDs are indexed in `data/backfill/targeted-corrections-feedback-analysis-v1.json`. Read these when selecting versions instead of regenerating or overwriting them. These private artifacts are absent from a fresh Git clone or worktree; use the original workspace's artifacts without committing or relocating them. Preserve the live review journals as well as frozen copies.

## Why snapshot work comes first

Current `pipeline/snapshot.py` derives a version from validated `(post_id, explanation)` pairs and records snapshot membership. `db/queries.py` later resolves snapshot details through current `memes`, `ground_truths`, and image paths. Consequently, an old snapshot can export changed text or fail to export its original image after database edits. A post ID plus a membership hash is not a frozen release artifact. `pipeline/export.py` also builds a card that describes every meme as human-validated and describes the current human review gate; that wording cannot honestly represent an automatically admitted cohort.

Implement a content-addressed release manifest and immutable snapshot payload that freeze, at minimum:

- exact ordered membership and exact answer text;
- copied image bytes and a cryptographic digest per image, with missing or invalid assets represented as explicit blockers rather than silently fetched or substituted at export time;
- answer, image, and membership digests, deterministic overall digest and schema version;
- each item's admission origin (human validation, qualified automation, or other explicitly supported path), decision/policy version, and relevant review/correction provenance;
- relevant prediction prompt, judge/scoring, and evaluation versions used for reported results, separated from admission provenance;
- the fact that newer items are exposed development items and the limits of evidence about their quality.

Retain compatibility for the legacy 519 and its frozen runs. Do not make newer labels mutate historical snapshots, and do not imply old automated or human provenance that cannot be recovered. If legacy provenance is incomplete, encode that uncertainty explicitly and report legacy results as legacy. Keep runtime private records local; publish only the fields allowed by [release readiness](release-readiness.md). The public dataset card must preserve its mixed-rights `license: other` statement and distinguish maintainer-owned materials from third-party media.

## Recommended execution phases

### Phase 0 — remote checkpoint and concrete plan

1. Read the [roadmap](roadmap.md), [pilot results](backfill-pilot-results.md), [#26 audit](fresh-human-audit-results.md), [#27 corrections](targeted-corrections-results.md), [backfill plan](automated-backfill-plan.md), and [release gate](release-readiness.md). Inspect current branch, status, remote, history, PRs, and instructions.
2. When assigned the starter above, checkpoint the existing committed history on `backfill-foundation` and push that branch with a draft PR. Verify the actual diff and run the applicable code-publication checks from [release readiness](release-readiness.md). Its clean-tree check requires a clean isolated checkout; do not achieve it by staging or discarding the user's edits. Keep the main checkout intact, avoid history rewriting/force pushes, and inspect any existing branch/PR before creating a duplicate. The PR should explain the curation infrastructure, completed negative experiments, and limits of admission quality. Attach the PR to the task. Push code, tests, and documentation only; private datasets remain local. Do not merge or publish a dataset.
3. Inspect `pipeline/snapshot.py`, `pipeline/export.py`, `db/queries.py`, schema, and CLI callers. Agree the shared API, serialization, legacy compatibility, and deterministic fixture format before parallel code work.
4. Write the detailed implementation plan under `docs/` and prepare bounded #10 child issues for the snapshot contract, immutable payload/export, and candidate evaluation/report. Record file ownership, dependencies, migration, acceptance criteria, and validation. Use focused commits after the remote checkpoint; avoid micro-issue churn.

### Phase 1 — immutable snapshot foundation (#10)

5. Add versioned immutable content so export/evaluation consume frozen text and image bytes, not mutable DB joins. Create atomically; refuse overwrite or incomplete freezes; make digests independent of iteration order/timestamps.
6. Preserve provenance, including unknown states. Separate policy, answer readiness, source support, duplicates, and admission origin. Keep #26/#27 judgments versioned; do not adopt proposals into live ground truth silently.
7. Read frozen payloads in export/evaluation. Exclude raw comments/authors, reviewer notes, internal prompts, raw provider response envelopes, call logs, request IDs, local paths, and caches. Retain the existing allowed public model predictions and judge verdicts/reasoning; these are benchmark results, not private call logs. Update public claims only when the schema supports them.
8. Cover immutability, digests, overwrite/partial failure, privacy, and legacy compatibility with focused fixtures; never commit local data.

### Phase 2 — assemble and evaluate the release candidate (#10)

9. Freeze a named candidate using the existing eligible pool and exact accepted corrections. Document the membership rule and all held-out cases; readiness alone does not clear other checks. Preserve the tentative ready note as uncertainty and keep philosophers, Pride, and unresolved overlap holds deferred where their blockers remain. Report legacy 519 and newer development cohorts separately; make combined composition explicit. Keep model inputs image-only.
10. Produce a reproducible report with hashes, model/scoring versions, denominators, missing predictions, judge agreement, and exposure. Verify whether cached predictions/judgments match the frozen content and scoring versions before reusing them. Specify the model panel and spending cap before any necessary paid evaluation; do not transfer unrelated experiment budgets. Do not count unresolved judgments as success or call exposed data an unseen test.
11. Verify image hashes and text against the manifest; mutate live DB content after freezing and prove export/evaluation inputs remain unchanged.
12. Run [release checks](release-readiness.md), review rights/card/privacy, keep artifacts under local `export/`, and do not publish as a side effect.

### Phase 3 — decide and scope chronological expansion (#9)

13. After #10 is reviewable, prepare #9's exact interval, sources, expected retrieval, overlap treatment, candidate ceiling, retries, and fixed cap. Account for 429/404/partial-comment gaps; discovery is not retrieval.
14. One month is only a proposal; exact month and spend ceiling are undecided. Do not infer authorization from the old $1 pilot cap. Design resumable, versioned chronological batches with coverage, failures, outcomes, deferrals, duplicates, and cost reporting.
15. For later assigned execution, label automation honestly, retain deferrals locally without a blocking human queue, and state that model agreement does not estimate fresh-item error independently.

### Later work to leave parked

Do not make tagging (#11) a prerequisite for this candidate. Keep further classifier or prompt optimization (#12), AfterDark (#13), and topical-meme knowledge probes (#14) parked as described in the roadmap. Do not add recurring ingestion to this release milestone. Do not change benchmark model IDs because delegation uses different agent models.

## Acceptance criteria

- A frozen snapshot contains exact image bytes, exact answer text, membership, schema/policy provenance, and stable hashes; a later live-database edit cannot change its export or evaluation input.
- Repeating snapshot creation/export with identical inputs yields the same content digest and bytes; changed content creates a distinct version. Partial freezes and accidental overwrites fail clearly.
- Legacy snapshot behavior and all existing historical frozen runs remain readable and unchanged; no prior human label or answer is rewritten.
- New and legacy admission origin is represented truthfully, with unavailable provenance marked unknown. Human answer readiness is not a proxy for source, suitability, rights, or duplicate clearance.
- Public exports pass the release privacy audit, contain no forbidden private operational fields, and describe mixed rights correctly. The card does not call automated admissions human-validated.
- The baseline report is reproducible from frozen content and states cohort, exposure, scoring versions, denominators, and limitations. Legacy 519 and newer development results are separately visible; no claim of an unseen holdout is made for exposed items.
- Meaningful tests cover immutable snapshot behavior, deterministic digest, failure/overwrite behavior, privacy, and legacy compatibility. `uv run pytest` and the release gate pass for release-facing code, with results reported accurately.
- #9 remains unlaunched until its month/date window, source coverage plan, candidate ceiling, and fixed spend cap are explicit. A code checkpoint and draft PR do not constitute dataset publication or promotion of an automatic checker.

## Risks and unresolved decisions

- The currently exported snapshots resolve mutable records; freezing only IDs would preserve the defect.
- The old card's single “human-validated” cohort description cannot describe the future mixed-origin candidate without a schema and wording change.
- Historical admission actor/provenance may be missing. Do not infer it from `reviews.status` alone or from the user's past action without evidence.
- Existing image cache bytes may be absent or differ from source URLs. Freeze the exact bytes used for evaluation, record acquisition/identity evidence, and report gaps; do not silently replace them with later downloads.
- Source coverage is known to be partial. A one-month expansion can still have substantial missingness and is not a complete archive census.
- Newer candidate answers have prior model, assistant, and human exposure. Do not present the candidate as independent holdout evidence.
- Test baselines in the audit documents differ by preparation point (500 and 508 are both documented); current verification must run against the exact implementation revision being delivered.
- The fixed spend cap and exact month for #9 remain undecided. Treat them as required inputs to that later milestone, not implementation defaults.

## Issue and delegation breakdown

Recommended bounded child issues under [#10](https://github.com/montagovian/basedBench/issues/10):

1. **Freeze schema and API contract:** choose manifest fields, versioning, deterministic digest rules, legacy read behavior, and failure semantics.
2. **Immutable snapshot/export implementation:** freeze exact bytes and text, adapt export to frozen content, retain privacy and provenance, and document the public card behavior.
3. **Candidate evaluation and report:** consume frozen content, report legacy and new cohorts separately, quantify exposure, and record reproducible scoring configuration and coverage.

Open/organize any child issues with `gh` and full issue URLs before assigning implementation. For substantial work, write the detailed plan and shared schema/API contracts first, then delegate considerably more implementation to available Luna/Sol agents than earlier curation rounds did. Use the configured agent models (currently `gpt-6-luna` and `gpt-6-sol`) for coding tasks; keep benchmark model IDs and historical result artifacts unchanged.

Delegate only disjoint ownership: for example, Luna can inventory provenance, draft schema/migration docs, or add narrowly scoped fixtures/adapters; Sol can implement snapshot payload persistence or a clearly bounded integration slice. Give each agent the acceptance tests, API contract, owned files, and explicit non-goals. Parallelize only after the interface is agreed; use separate worktrees when edits could overlap. The primary agent owns issue coordination, the cross-cutting design, integration, full review, release checks, and the final report. Do not delegate vague “explore and improve” loops or unbounded model experiments.

Recommended #9 child issues, after its scope is decided, are source coverage and resumable inventory; bounded admission execution and cost ledger; and cohort/coverage reporting against the frozen #10 schema. Keep issue count tied to reviewable deliverables and dependencies.

## Startup checklist for the assigned next agent

- [ ] Identify the assigned scope and any budget or publication limits. The starter prompt above assigns the remote checkpoint and release implementation.
- [ ] Read this handoff plus linked roadmap, pilot, audit, correction, plan, and readiness documents; inspect current Git/worktree state and all local instructions.
- [ ] Preserve dirty files and private data; establish a clean isolated worktree for the code checkpoint and validation, with local artifact access kept separate from Git.
- [ ] Checkpoint the committed history remotely on `backfill-foundation`, open and attach a draft PR, and keep merge/dataset publication separate.
- [ ] Draft a detailed implementation plan and shared manifest/API contract.
- [ ] Create or update a few meaningful GitHub child issues with `gh`, linked under #10; explicitly record #9's undecided date and budget.
- [ ] Delegate substantial disjoint implementation to Luna/Sol after the contracts are stable; integrate and review all changes centrally.
- [ ] Deliver an immutable candidate and reproducible baseline report, run the required checks, and state remaining gaps without overstating evidence.
