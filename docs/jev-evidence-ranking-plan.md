# Jev evidence ranking and collation

September 24, 2026. Follow-up to #38/#40 and draft PR #39. The user approved
comparing comment order, Jev informativeness ranking, and ranking with collation,
under a **new $1 total cap**. Keep all issues open for human review. Preserve the
original experiments, stopped GEPA attempt, exact human judgments and active code.

## Problem, hypothesis and deliverable

Can narrow Jev decisions give a reader the important clues with less repetition?
Informativeness means contributing a concrete referent, decoding step, relation,
or useful source pointer. It does not establish factual truth, count agreeing
votes, judge benchmark suitability, or reward length/popularity. Existing filtering
failed to improve the final answer judge; directly evaluate evidence packs before
claiming any downstream gain. References to tweets or Know Your Meme remain
unverified pointers. No external fetching or answer generation in this milestone.

Deliver three exact-source evidence packs per family and a saved, blinded review
of 16 families. Freeze sampling before model outputs. Human preferences and clue
retention are required for the quality result; machine scores and text reduction
alone cannot establish improvement. This is exposed development data.

## Frozen data and controls

Use the prior 94 known-label, image-complete versions in 81 families. Choose the
lexicographically first case ID within each family, yielding 760 comments. Keep
the other versions, all five prior exclusions, and the three families with multiple
evidence contexts in the inventory. Never count answer variants as independent
threads. Include a human-ready reference only when its image and comment pool
match the selected case exactly; report other references as unmatched, not gold
for the selected context. References and human labels/notes stay local.

Each pack has the same family-specific maximum words:
`min(250, max(1, ceil(total_source_words / 2)))`, using whitespace-delimited words.
Select whole comments when they fit. An overlong first comment may contribute the
longest whole-sentence prefix that fits; if its first sentence is too long, use
the first budget words. Store exact character offsets and visibly mark partial
comments. Later comments that do not fit are skipped, without silently shortening
each one. Count excerpt words and report actual use; do not pad packs. All three
arms use the same packer and source pool. Saved order is not asserted to be upvotes.

1. `order`: saved comment order under the fixed budget.
2. `rank`: decreasing fixed utility, original index breaks ties.
3. `collate`: remove repeated claims, preserve distinct/competing clues, then pack.

## Typed questions and fixed selection

Per comment, five Noul questions: `useful`, `decodes`, `riff`, `pointer`,
`alternative`. State includes the saved image observation and full comment pool;
questions explicitly point to exact comment ID/text. Never include a candidate
answer, gold label, human reference or prior selection/score. Questions distinguish
a joke explanation from a commenter making another joke. Fixed utility:
`0.60*useful + 0.25*decodes + 0.15*pointer - 0.35*riff` (not calibrated confidence).

For every unordered comment pair (at most 190 per family), ask `same_claim` and
`conflicting` Nouls: do they convey substantially the same decoding information;
do their explanations make incompatible claims? No generated descriptions.
Collation forms deterministic complete-link groups in ranked order: a new member
must have `same_claim >= .8` and `conflicting < .65` against every existing member.
Keep the highest-ranked representative of each group. A conflicting pair never
merges. Prioritize representatives using utility with a `.25` penalty for maximum
same-claim probability against already selected representatives. Keep source IDs,
all pair values and duplicate members for inspection; no majority vote is truth.
Any `pointer >= .6` or `alternative >= .6` representatives appear in corresponding
inspection sections after method reveal, not as asserted verified facts.

All model requests use `jev-1.13.0`, 96 questions maximum, the existing 30k
state-plus-largest-question and 62k body-byte guards. Batch greedily without
dropping questions. Use at most 400 calls and 40,000 questions, within $1.
Reserve 64,000 input tokens at $0.042/M before each call; output is free.
No OpenAI calls or new images are sent. Existing approved Jev inputs are narrowed
to comments and saved observations; keys stay local and are never logged.
[Pricing](https://docs.typesafe.ai/models), [Noul](https://docs.typesafe.ai/primitives/noul),
[reranking](https://docs.typesafe.ai/cookbooks/rerank_typesafe),
[passage routing](https://docs.typesafe.ai/cookbooks/classifying_rag_passages).

## Error policy, cache and stopping

This new run declares its handling before dispatch. Valid usage plus a malformed
answer yields a visible **family-level model abstention**: retain the order pack,
mark rank/collate unavailable, and include it in coverage/denominators. Preserve
raw responses and settle known costs. Do not fill missing scores, repair answers,
drop failed families or retry them. Stop the whole run for transport ambiguity,
unknown usage/model identity, budget/call/question ceiling, source or code drift,
or interruption. No automatic retries. Cache exact requests with hashes and
durable reservation checkpoints. Completed replay requires no credentials/network.

## Review and decision rule

Sixteen fixed families: four diagnostic families (R.E.M., Snape, XM8, song rebus)
plus 12 deterministic hash-sampled other families. Diagnostic and sampled results
stay separate. The review assigns A/B/C deterministically per family, with a
balanced rotation of all six method permutations across the 16 cases. Same display
format and budget; method names/model scores hidden until ratings are saved.
Blinding is to method identity, not to the fact that comments may be grouped.

Show the image and three packs. For each pack ask (1) whether it preserves the
needed clue: yes/partly/no/unsure, and (2) whether it includes misleading material:
yes/no/unsure. Then choose the most useful pack, tie, or unsure; optional note.
Saved source context and matched prior-ready explanation are available to inspect;
record whether they were opened. No new semantic labels are inferred from empty
ratings. Persist feedback locally with revision checks, append-only events and
reload; reveal method names only after saving. This is 16 reviews, not a new broad
annotation set. Do not expose the reveal mapping to the frontend before save.
Record method exposure too, so subsequent revised ratings are identifiable as
unblinded; preserve the initial judgment and every revision.

On the 12 sampled families, a follow-up is warranted when at least eight have
decisive preferences, one Jev arm is chosen as most useful at least once and at
least twice as often as order, and its count of full-clue retention is no lower
and misleading-pack count no higher than order. Ties and uncertainty remain visible;
report best-pack counts, not pairwise preferences or significance. A vote for the
third arm says nothing about the relative preference between the other two.
Use the latest judgment saved before method exposure for this screen; report later
revisions separately. Diagnostic examples cannot satisfy this rule.
Before human input, report preparation/coverage/cost only, with effectiveness pending.
Stop after this fixed comparison; no GEPA fitting or repeated tuning.

## Implementation contracts and ownership

Use new modules; never edit frozen `jev_decomposition_*`/`jev_optimization_*` code.

- Compiler/selection agent (Sol) owns `pipeline/evidence_ranking_policy.py` and its
  tests. Exports `comment_requests(case)`, `pair_requests(case)` -> list[body];
  `build_packs(case,scores)` -> dict arms; `word_budget(case)` -> int. `scores` maps
  `useful_c0`, `decodes_c0`, `riff_c0`, `pointer_c0`, `alternative_c0`,
  `same_0_1`, `conflict_0_1` to float. Comment indices reference the original order.
  Packs each have `excerpts` [{comment_id,start,end,text,partial}], `word_count`,
  `budget_words`, `selected_ids`, optional local `groups`/`sections`/`ranking`.
- Ledger agent (Sol) owns `pipeline/evidence_ranking_io.py` and its tests. Exports
  `BudgetStop`, `Store(root,plan,*,client=None,api_key='')`, `call(body)->dict`,
  `report()`, `close()`. Call returns {status:'completed'|'invalid',scores:{id:float},
  errors:[str]}; invalid means no usable scores. Plan fields: `plan_id`,
  `budget_usd=1`, `max_calls=400`, `max_questions=40000`. Durable cached request,
  response, usage and ledger integrity; no credentials needed for replay.
- Review agent (Sol) owns `evidence_ranking_review.py` and tests. Primary provides
  private `review-cases.json`: [{review_id,family_id,case_id,sample_kind,image_path,
  comments,reference_explanation,methods:{A:'order',B:'rank',C:'collate'},
  packs:{A:{...pack},B:{...},C:{...}}}]. Labels/notes are never provider payloads.
  Agent implements local server, safe image routes, saved ratings and reveal;
  primary verifies running browser and preserves all feedback.
- Primary owns protocol/runner `pipeline/evidence_ranking_run.py`, tests, source
  freeze, sampling/review contract, orchestration, preflight, API dispatch,
  credential-free replay, aggregate inspection and docs/issues/PR integration.

Validation covers exact excerpt offsets/budget parity, candidate/label blindness,
nontransitive duplicate groups, conflict preservation, invalid-response abstention,
budget boundaries, pending settlement and cache tampering, immutable inputs,
zero-call replay, server origin/payload validation, rating persistence and reveal.
Commit the implementation before paid dispatch; return a browser-verified review.
