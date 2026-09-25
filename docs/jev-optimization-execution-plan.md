# Bounded GEPA / Jev execution

September 24, 2026. Related to #40 and #38, both kept open. The user reviewed the
[groundwork](jev-optimization-findings.md) and said “okay i've reviewed and i think
we could give it a try.” This authorizes implementing the proposed finite $5
comparison. Preserve old artifacts, human labels/notes, active policy and release.

Implementation and the first attempt are recorded in the
[run results](jev-optimization-run-results.md). The attempt hit the declared
provider-schema stop before final evaluation; it was not automatically restarted.

## Frozen scope and interfaces

Use the 99 exact source versions and saved observations from the Jev experiment;
fit/search/evaluate only the 94 image-complete known-label cases, with all five
other versions reported as holds/exclusions. Reuse the saved five combined-model
outer folds. Inner training/validation is the first of three StratifiedGroupKFold
splits of each outer train (shuffle, seed 4001); assert all group boundaries.
No outer-test example, label or trace may enter that fold's GEPA search.

The policy is a canonical JSON object: `version=1`; generic strings
`role_instruction`, `need_instruction`, `coverage_instruction`,
`verdict_instruction` (each 50–2500 characters); `essential_threshold`,
`coverage_threshold`, `failure_threshold` in [0.4,0.95]; and
`aggregation` in `hybrid`, `evidence_only`, `broad_guarded`. No other keys.
Reject executable content, case IDs and lookup artifacts. Never execute generated
code. All candidates go through deterministic validation before provider use.

Source units retain comment ID and exact character offsets. Split by newline and
sentence boundaries deterministically, retain full original comment context,
and hold a case rather than truncate if more than 64 units or request limits.
Stage one contains observation and comment units only, never the candidate answer:
choose each unit's role (core_decoding/context/riff/competing/irrelevant/unclear)
and need (essential/helpful/unrelated/unclear). Stage two compares every unit to
the unchanged answer using covered/missing/contradicted/not_applicable/unresolved.
A final typed Choice sees the trace and gives pass/fail/uncertain; fixed code
combines this with essentiality/coverage according to the declared rule.

Retain Jev's 96-question, 30k context and 62k body-byte guards. The case maximum is
384 questions; batch greedily within those guards. Probability parsing reuses the
existing strict typed parser. Each trace is source-linked and replayable.

## Shared Python contracts and ownership

- Compiler agent (Sol): `jev_optimization_policy.py` and its tests. Expose
  `SEED_POLICY`, `parse_policy(str|dict)->dict`, `policy_id(policy)->str`,
  `source_units(case)->list[dict]`, `role_requests(case,policy)->list[dict]`,
  `coverage_requests(case,policy,roles)->list[dict]`,
  `verdict_request(case,policy,roles,coverage)->dict`, and
  `decide(case,policy,roles,coverage,verdict)->dict`.
  Case has `input.explanation`, `comments`, `observation`, `case_id` locally;
  outbound state is an explicit allowlist. Parsed answers are combined dicts from
  old `questions.parse_response`. Unit IDs `u0...`; question IDs `role_u0`,
  `need_u0`, `coverage_u0`, and final `adequacy`. Decide result has `prediction`
  and `trace` (units and source offsets, evidence choices, coverage, reason codes).
- Protocol agent (Sol): `jev_optimization_protocol.py` and tests. Expose
  `prepare(source_root,root)->dict`, `load(root)->(plan,cases_by_id)`,
  `example_sets(plan,cases_by_id,fold_id)->(train,val,test)`; examples contain only
  `case_id`, `partition`, `weight`. Scores use within-partition inverse
  family-size/class-frequency weights normalized to mean one, correct prediction
  earns its weight and uncertain earns zero. Expose `score(example,row,pred)`;
  `feedback(example,row,result)->dict` returns case input/trace plus expected
  pass/fail only for train examples, never exact notes/provenance; val/test info
  empty. `summarize(cases,records)->dict` reports all counts/paired families and
  preserved baseline controls. Prepare/load verifies hashes and never overwrites.
  Plan includes `cases_file`, `source_hashes`, `folds` with `fold`, `train_ids`,
  `val_ids`, `test_ids`, `case_ids`, and fixed budget constants below. Primary
  freezes final code/dependency hashes in a separate execution manifest.
- Ledger/provider agent (Sol): `jev_optimization_io.py` and tests. Expose
  `BudgetStop(Exception)` and `ProviderStore(root,plan,*,openai_client=None,
  jev_client=None,api_key='',jev_api_key='')`; synchronous `jev(body,phase)->dict`
  returns old-parser parsed answers; `reflect(prompt,phase='search')->str`;
  `close()`, `report()`. Hash exact body/provider for durable cache identity.
  Record raw requests/responses privately, reserve before send, reconcile known
  usage, stop on unknown/pending/error, max_retries=0. Shared total $5, search
  cap $4, final reserve $1; max provider calls 4000, question cap 500000,
  search reserves 800 calls and 80000 questions for final. No hidden retries.
- Primary: dependency pin/lock and installed API smoke test, GEPA adapter/runner,
  cap on actual case-policy evaluations (1200, reserve 188 for final seed/winner),
  policy/reflection trace visibility, six proposals per outer fold, all-code
  integration, tests, preflight/authorization, finite run, analysis and review.

Contracts are settled before parallel implementation. Agents may propose a
contract correction but cannot edit each other's files or call paid providers.

## Reflection, providers and cost

Pin GEPA 0.1.4 and verify installed signatures before dispatch. Use its released
`GEPAConfig`/`EngineConfig` interface, not current-main docs. Reflection uses
OpenAI `gpt-6-sol`, Responses API, medium reasoning, max_output_tokens=4000,
store=false, service_tier=default, no tools. Standard short-context pricing verified
September 24: $2/M input, $10/M output, cache writes $2.50/M. Reserve conservatively
using UTF-8 input byte count plus overhead at $2.50/M and max output at $10/M;
settle input conservatively at $2.50/M if cache details are unavailable. Limit
reflection input below 40k UTF-8 bytes to stay within reserved short context.
Use TypeSafe `jev-1.13.0`, $0.042/M input and full-context reserve as in #38.
[OpenAI model](https://developers.openai.com/api/docs/models/gpt-6-sol),
[TypeSafe model](https://docs.typesafe.ai/models).

Jev receives answer/comment bundles and saved observations, never human labels or
notes. Reflection receives the policy, training-case input/typed traces and
label-derived success/failure feedback. Exact human notes, provenance, images,
validation examples/notes and outer-test material are excluded from reflection.
The reviewed GEPA design involves this label-derived feedback; the earlier
finite Jev run's image-only OpenAI payload is not reused as its authorization.
Record the current approval against the exact final request manifest; surface
any automatic-review requirement for more explicit payload consent before launch.

## Search and selection

Run five sequential independent searches with at most six proposals each, one
reflective proposer, fixed seed 4001+fold, no crossover or refiner. Correctness is
family/class weighted locally; diagnostics make the deficient decoding/evidence
step visible without raw human notes. GEPA's validation is adaptive, never final.
Each proposal sees one rotating repair family and one ready example, preferring
a corrected ready version from the same training family when available. Sampling
uses training labels locally; no validation or outer-test family is eligible.
This keeps a small six-proposal allowance from mostly seeing the majority class.
The 200-metric-call per-fold GEPA limit supplements the external global ceiling;
only the external ceiling is a strict bound on actual unique case evaluations.

Final native-Choice traces use source offsets, choices and decision-relevant
probabilities; reflection traces use compact columns and rows. All original
comments remain present once, and complete typed probability outputs remain in
the local provider artifacts. This avoids duplicating source text for each unit
while preserving source links. No evidence unit is removed to fit a request.
Final candidate selection from validated candidate scores is fixed: prefer
candidates meeting the broad ready-retention count on the validation set, then
maximize repair catches, then ready passes, then fewer abstentions, then lower
candidate index. If none qualifies, retain the seed. All final outer evaluations
occur only after every fold's search policy is frozen.

Stop on first budget/call/evaluation/question/proposal cap, unresolved usage,
provider error, schema/manifest mismatch or interruption. Preserve partial runs
without pretending they are complete. Keep the external ledger authoritative;
GEPA metric-call/cost limits alone do not bound nested provider spend. Cache
hits do not spend, but actual unique case-policy evaluation accounting remains
visible. Resume may replay saved GEPA state/requests only after identity checks;
completed replay must need neither credentials nor network.

## Acceptance and validation

Test candidate schema/offsets and candidate-blind stage one, invalid probability
responses, family leakage and reflection allowlist, class/family weights, exact
budget boundaries, interrupted/unknown settlement and cache tampering. Run the
full test suite, installed-GEPA fake-reflector smoke, a complete small offline
end-to-end fixture, and final credential-free replay. Freeze request sizes,
source/code/dependency hashes and a representative payload before paid dispatch.

Report original broad, original combined, nested calibration, unoptimized seed
and GEPA outer decisions on identical eligible cases. The development screen is
at least three additional caught repair versions across two families versus broad,
ready passes >=67/77, ready rejections <=10/77, and decided coverage >=90%.
Inspect every changed decision, especially corrected pairs and ambiguous labels;
these remain exposed development data. Return a readable review without automatic
promotion, merge, release change or closing #38/#40.

## Commands and private artifacts

Install with `uv sync --extra curation --extra optimization` (`--extra encoder`
also supplies the dependency required by the full existing test suite). Use
`uv run python -m basedbench.pipeline.jev_optimization_run prepare --source
<frozen-jev-run> --root <new-private-run>` to freeze a new run after tests. The
execution manifest checks source, code, dependency and representative request
hashes. `run --root <new-private-run> --env-file <local-env-file>` runs the finite
comparison; credentials are read locally and never placed in manifests or logs.
`replay --root <completed-private-run>` verifies all final decisions and aggregate
metrics from saved provider responses without credentials or network.

An interrupted or failed fold stays partial and cannot silently restart. Its
requests, raw responses where available, reservations and stop reason remain
available for review. A budget/provider/schema stop does not count as a completed
experiment or justify automatically launching a replacement run.
