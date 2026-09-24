# Jev as a collection of small decisions

September 24, 2026. [Issue #38](https://github.com/montagovian/basedBench/issues/38).
**Keep the issue open for the user's review and explicit closure approval.**

## Problem, deliverable and scope

Earlier Jev experiments used one or three broad curation decisions. The user
requests a more ambitious investigation of architectures suited to a fast typed
decision model. Deliver one reproducible multi-architecture comparison, measured
cost/latency/question counts, and a local visual review report. The primary target
is answer adequacy: does the unchanged answer get the same joke? Source evidence
is a diagnostic axis, not a substitute label. Content, suitability, duplication,
answer generation, automatic admission and release publication are non-goals.

Use the reconstructed #36 corpus: 99 exact answer/evidence versions, 88 posts,
86 verified known groups, 78 ready / 18 repair / three unclear. Preserve exact
notes and all versions. Hold the animated image rather than selecting a frame.
These are exposed development data. Group-separated fitting prevents direct
train/test overlap, but does not make the examples unseen to the design process.

## Research and design consequences

The official [introduction](https://docs.typesafe.ai/introduction) recommends
atomic questions composed in code. The [parallel-questions recipe](https://docs.typesafe.ai/cookbooks/parallel_questions)
shares state across independent questions; its particular 13-question example
reports lower cost and latency than serial individual requests. Measure the
effect here, without transferring those speedup numbers to our workload.

[Citation checking](https://docs.typesafe.ai/cookbooks/citation_check) separates
verbatim matching from semantic support. Adapt this as a matrix of unchanged
candidate spans against individually identified comments, retaining support,
contradiction and no-relation probabilities. [RAG filtering](https://docs.typesafe.ai/cookbooks/classifying_rag_passages)
motivates a dependent second pass with relevant and conflicting evidence retained.
[Semantic search](https://docs.typesafe.ai/cookbooks/semantic_find) warns that a
Choice must select something even if all choices are bad: include a no-relation
option rather than treating the best-ranked comment as proof.

[Feature discovery](https://docs.typesafe.ai/cookbooks/autoresearch_feature_discovery)
uses Jev answers as numeric features for a supervised model. Adapt that principle
with a fixed feature bank and strongly regularized, group-separated logistic
regression. This corpus is much smaller than its wine example. Do not run an
error-driven feature search across these evaluation labels. [Self-consistency](https://docs.typesafe.ai/cookbooks/consistency_noul_cookbook)
motivates repeated predictions and an explicit abstention band; repeated agreement
is not independent factual evidence or calibrated correctness.

First-hand community implementations provide additional architecture ideas:
[nexibeo's recipes](https://github.com/nexibeo/jev-cookbook) separate specific
predicates from policy decisions and report confident near-misses;
[chr-kelly's cookbook](https://github.com/chr-kelly/jev-cookbook) uses question
recipes and request-shape checks. These are illustrative small experiments,
not proof of suitability for memes. [FActScore](https://arxiv.org/abs/2305.14251)
supports inspecting local supported/unsupported pieces rather than a single
global verdict, but factual support alone cannot measure a missing punchline.
[Selective classification](https://arxiv.org/abs/1705.08500) motivates reporting
error against coverage; its formal guarantees do not transfer to these data.

Current [official model specifications](https://docs.typesafe.ai/models), checked
September 24: pin `jev-1.13.0`, text only, $0.042 per million input tokens, free
outputs; 64k total request tokens and 32k state plus longest question. The
[jaggedness guide](https://docs.typesafe.ai/model-jaggedness/jev-1.13) recommends
short direct conditions, relevant state, and arithmetic/invariants in code.
Existing SDKs may retry by default; use the existing raw HTTP transport with
explicit no-retry behavior. Do not multiply the shared state cost by question
count; retain provider usage and a conservative full-context reservation.

## Frozen experiment design

One finite comparison; no post-result prompt edits, helper regeneration or
automatic second experiment. API budget awaits the user's separate answer
($5 recommended, $10 alternative, or no paid calls). Implement and test while
pending; do not dispatch paid work until supplied. Record the answer in the
execution manifest and this plan before dispatch.

For each supported image, generate one neutral text observation using pinned
GPT-6 Luna, medium reasoning, high image detail, maximum 2,000 output tokens.
The helper sees only image pixels, not the candidate, comments, labels or notes.
Return visible text, scene and uncertainties; do not interpret the joke or judge
answers. Deduplicate only exact image hashes. All image-aware Jev arms receive
the same frozen observation. It is fallible machine evidence, not gold or direct
Jev vision. Helper failures hold all image-aware arms for that image; retain the
text-only control. No hand editing observations after verdicts.

Compare the following, preserving every eligible version:

1. **Broad text control:** one Choice for answer adequacy on candidate and full
   comments; no image observation. Include the animated-image case here only,
   clearly outside matched image-arm denominators.
2. **Broad observation control:** identical adequacy question plus observation.
3. **Atomic bank:** 48 short Noul predicates plus the same broad Choice in one
   request. Cover setup, referents, required decoding, actual connection,
   contradictions, specificity, unsupported additions and ambiguity. Do not
   ask aesthetic humor or make every historical detail mandatory. Use a frozen
   explicit rule in code, and retain the entire feature vector.
4. **Evidence matrix:** four narrow predicates per full comment (substantive
   explanation, contradiction, missing necessary decoding, competing reading),
   plus a three-way support/contradiction/no-relation Choice for every candidate
   span/comment pair. Use deterministic sentence/semicolon spans of the unchanged
   answer, with lossless offsets. Include all supplied comments. Pack bounded
   batches, at most 96 questions each and conservative byte/context checks;
   splitting is recorded rather than silently truncating evidence.
5. **Focused dependent pass:** select up to ten comments in code from the matrix,
   reserving slots for potential contradictions and omissions as well as support.
   Ask the same 48 predicates and broad Choice on that smaller state. Preserve
   selection scores and IDs. Empty evidence remains explicit.
6. **Learned combinations:** fixed logistic regression, C=0.1, balanced classes,
   standardization fitted only inside each training fold. Compare the atomic
   vector alone with atomic + matrix summaries + focused vector. Five fixed
   stratified group folds keep all known-family/post versions together. Weight
   each family's versions inversely during fitting. No hyperparameter search,
   feature selection using evaluation errors, or in-sample score reported as
   an evaluation. Exclude unclear labels from fitting; report them separately.

Fixed probability routes: pass >=0.8, fail <=0.2, otherwise uncertain for learned
scores; also report binary >=0.5 predictions, balanced accuracy, per-class errors,
AUROC where defined and risk/coverage at predeclared 0.5/0.6/0.7/0.8/0.9 thresholds.
The atomic rule and its selected feature IDs must be frozen in code before calls.
Keep source-support findings separate; no comment count becomes an admission
quota and no contradictory/unclear human note gets relabeled.

On twelve known groups selected by stable hash without labels, repeat the atomic
request twice and send the first eight atomic predicates individually with the
identical state. This measures repeat variation and a bounded batch-vs-single
comparison. Report latency as observed serial end-to-end API latency, not model
compute or a general service benchmark. These requests are extra measurements,
not extra independently labeled examples. Freeze exact request/job limits after
preparation and before dispatch.

## Architecture and shared contracts

New additive modules under `src/basedbench/pipeline/jev_decomposition_*`. Worktree
`/private/tmp/basedbench-jev-experiments`, branch `codex/jev-decomposition`, stacked
on #37. Private root `data/backfill/jev-decomposition-v1/` in the original workspace.
Old pipeline modules, original app edits and frozen data are read-only.

Dataset `prepare(source_root, output)` writes `cases.json`, copied `assets/`, and
manifest/report, refuses overwrite, verifies #36 dataset and grouping audit.
Case fields: `case_id`, `post_id`, `group_id`, `human` (unchanged), `input`
(unchanged explanation/comment_evidence/image_sha256), `image_path` (copied
absolute path or null), `image_error`, `comments` [{id,text}], `spans`
[{id,text,start,end}]. No decisions or labels enter request construction.

Question module interfaces: `state_for(case, observation=None, comment_ids=None)`
returns only candidate text, comments and optional observation; `broad_request(state)`,
`atomic_request(state)`, `matrix_requests(state, spans)` return raw native bodies.
`parse_response(body, response)` verifies pinned model, exact question IDs/types,
finite probabilities, Choice argmax and rounded-sum tolerance; returns a flat
mapping from question ID to {value, probabilities, choice, confidence}, with
unneeded fields absent. `select_comments(state, parsed_matrix)` returns IDs and
selection metadata. `summarize_matrix(parsed_matrix)` produces stable numeric
features. `atomic_decision(parsed_atomic)` returns pass/fail/uncertain. Expose
`FEATURE_IDS`, all fixed predicates and routing constants.

Runner owns `plan.json`, frozen `requests/`, `calls/`, observations and one ledger.
Job fields: `job_id`, `case_id` (or image hash for helper), `stage`,
`request_sha256`, request file, dependency IDs. Save raw provider response, usage,
latency, validation error and parsed signals separately. Durable reservation and
pending marker precede each dispatch. Unknown usage or model/context mismatch
halts new work; no retry of an uncertain call. Sequential requests simplify
ledger and service-rate behavior. Dependencies make focus requests deterministic
after matrix outputs; each is hashed and frozen before sending. Snapshot code,
configuration and inputs; replay verifies integrity and never constructs a
network client when all planned work is saved.

Runner's normalized `records.json`: one row per case with identity/group/human,
`arms` mapping names to {state: completed/held/technical_error/missing,
answer_quality, score, features, error, job_ids}, observations, selected comment
IDs, and repeat/batching measurements. All denominators retained. Analysis
`prepare(root, output)` consumes dataset + plan + records and saved calls, refuses
overwrite, produces machine-readable per-case/fold/summary reports and escaped
static HTML with local images, answers, original notes, evidence and signals.

## Ownership and work packages

- Primary: research, plan/issue, generic budgeted runner and helper observation
  requests, integration, paid execution, final preservation and review.
- Data agent (Luna): dataset adapter and tests only; exact source verification,
  grouping, lossless span/comment parsing, copied image holds.
- Questions agent (Sol): question bank, evidence-matrix requests, parsing,
  focus-selection and deterministic aggregation plus tests only.
- Analysis agent (Sol): fixed group-separated learning/metrics and local HTML
  review report plus tests only; no model calls or prompt edits.

Shared API contracts above precede delegation. Agents may propose contract
corrections to primary; changes must be synchronized before integration. No
agent calls paid APIs, edits others' files or changes old artifacts.

## Validation, decision and stopping

Test exact provenance and grouped identities, leakage allowlist, span offsets,
missing/animated images, native types/probability validation, batching limits,
focus retaining conflicting evidence, empty/no-support cases, no family overlap
in folds, training-only preprocessing, budget/resume/unknown-call behavior and
network-free completed replay. Run `uv run pytest`, security/hygiene checks and
inspect the review report in a browser. Inventory prior artifacts before execution
and verify them unchanged afterwards; preserve original working-tree edits.

Success is an informative comparison of architectural alternatives, not forced
promotion. A promising direction should reduce known repair passes without
losing known-ready retention, with useful non-abstained coverage and actual
image-backed explanations for changes. Report full counts and family correlation;
small selected data cannot qualify automatic admission. Finish when the finite
comparison completes or safely stops, costs reconcile, artifacts replay, and
the user receives reviewable wins/failures plus a recommendation. Leave #38
open at that handoff. Human review and explicit closure approval are required.
