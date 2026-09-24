# Jev comment selection after human review

September 24, 2026. Continuation of [#41](https://github.com/montagovian/basedBench/issues/41)
and draft PR #42, explicitly requested by the user after the partial review.
The [v1 analysis](jev-evidence-ranking-human-results.md) remains a frozen result;
its original follow-up screen was not met. This is a new, bounded development
comparison, not a revised interpretation of the old experiment.

## Problem and deliverable

A useful clue somewhere in a list is insufficient. Reactions and unrelated riffs
can remain, an incomplete pointer can lead, and deduplication or a word ceiling
can remove a reader's preferred explanations. Separate membership from reading
order. Keep overlapping useful explanations. Deliver one new frozen run over the
same 81 families / 760 comments, a pointwise ablation, private explicit-feedback
checks, and a simpler eight-case, two-list local review.

Hypothesis: a relevance filter plus pairwise first-read comparisons improves the
short reading list over cached v1 ranking. Pairwise comparison may add nothing
beyond the filter and new pointwise questions; retain that ablation honestly.
This evaluates getting the meme's joke, not theories of humor or factual truth.

Non-goals: no VLM #43, new image descriptions, answer generation, source retrieval,
GEPA fitting, automatic benchmark admission, database changes, release promotion,
merge or issue closure. No repeated tuning after seeing these outputs. Exact human
notes and judgments stay local; no training labels enter requests.

## Inputs, controls and presentation

Use the exact representative cases from `evidence-ranking-v1`, verified by its
credential-free replay and completion manifest. Preserve its code, all 516 frozen
artifacts and the human snapshot/journal. New modules are `comment_selection_*`;
never add to the old runner's `pipeline/evidence_ranking_*.py` hashing glob.

All arms show up to three whole comments, followed by an expandable remainder.
There is no word ceiling, truncation, padding, or duplicate collapse. Show actual
word counts; these arms do not have equal reading cost. This isolates ranking
from v1's packer but is a changed presentation, not a rerun of v1's original arm.

- `baseline`: cached v1 full ranking, all nonempty comments retained.
- `pointwise`: new relevance filter and fixed pointwise priority.
- `pairwise`: identical filter; order by symmetrized pairwise first-read preference.

## Fixed compiler and policy

Only an allowlisted saved observation (`visible_text`, `visible_scene`,
`uncertainties`) and exact comment IDs/text enter state. Seven binary questions
per comment: `relevant`, `explains`, `complete`, `context`, `pointer`, `reaction`,
`riff`. Questions explicitly distinguish the meme's decoding from commenters
making another joke. Relevance includes a concrete decoding clue, directly useful
background or actionable source pointer; broad topical similarity is insufficient.
Completeness asks whether this comment plus the visible meme supplies the setup
and connection a reader needs. A generic template name or unelaborated pointer is
not complete. A reaction/riff that also contains substantive explanation is not
primarily noise. Overlap with another useful explanation is never a rejection.

Keep nonempty comments when `relevant >= .60` and
`max(reaction, riff) < .70`. Rank pointwise by
`.45*complete + .35*explains + .20*relevant - .10*max(reaction,riff)`;
original source index breaks exact ties. Context/pointer scores are inspection
features, not verified-source status. Empty selection is valid; never fill it.

For every unordered pair, ask both directional questions: is A a better first
comment to read than B for recovering this particular meme's intended joke?
Prefer specific, self-contained decoding to vague pointers, topical background,
reactions or riffs. Do not reward length, popularity or repetition by itself.
Pair score is `(P(A>B) + 1 - P(B>A))/2`. Among retained comments, use mean pair
score (Borda); a singleton gets .5. Break ties by pointwise priority, then source
index. Save directional disagreement and all raw scores for local inspection.
These scores are ordering heuristics, not calibrated probabilities of truth.

Compile every pair before dispatch, independent of membership decisions, so
preflight bounds are exact. Use existing request/body limits, 96 questions max,
pinned `jev-1.13.0`, and the unchanged durable Store. Strictly validate exact score
keys, finite probabilities and complete baseline coverage before selecting.

## Private development checks and human review

An independent inventory extracts only explicit comment-level statements in the
frozen notes: praised IDs, specifically unwanted comments, and first-position
constraints. Each anchor stores its exact event ID and quote locally. Do not turn
pack-level misleading/clue ratings into individual labels. Record ambiguous notes
as excluded. Freeze anchors before new model outputs. Check positive retention,
positive top-three presence, negative exclusion and ordering constraints separately;
report counts and regressions, not a synthetic accuracy score.

These checks are exposed development diagnostics. A promising development result
requires no loss of explicitly praised comments from the full retained list,
fewer explicitly unwanted comments in the initial three than baseline, and fewer
violated first-position constraints. If any fails, report the failure; no tuning
or promotion follows. Compare pairwise with pointwise on the same checks; a tie
or regression is not a reason to prefer the more complicated method.

Freeze the review selection before dispatch: four prior problem cases (the short
wordplay explanation, overlapping useful explanations, mechanism lost through
collation, and incomplete template pointer), plus four hash-sampled families
outside all 16 prior review cases. Development cases and newly reviewed cases
are marked separately. The latter are new to this review, not a certified holdout.
Show baseline versus pairwise, A/B assignment balanced and hidden until save.
The pointwise ablation remains in the private analysis, not a third confusing
column. Show identical initial lists explicitly. Ask which helps the reader get
the joke sooner (A/B/tie/neither/unsure), whether each first comment helps, and
whether the visible three contain irrelevant extras. Optional notes can identify
factual concerns separately. Never reinterpret irrelevance as factual error.
Save locally with revision checks, append-only events and reveal chronology.
No human preference is inferred before review or for skipped cases.

## Budget and stopping

The cumulative #41 ceiling remains **$1**. Prior settled spend is **$0.075391344**;
the new Store cap is **$0.924608656**, checked against the prior frozen ledger.
At most 340 new requests / 20,000 questions; preflight must fit these and the
worst-case reservation bound before dispatch. Reserve 64,000 input tokens at
$0.042/M ($0.002688 per request), output free. Current pinned model and pricing
verified against [TypeSafe models](https://docs.typesafe.ai/models); typed answers
follow [Noul](https://docs.typesafe.ai/primitives/noul). No OpenAI calls or new
images are sent. The existing authorization covers saved comments and image
observations sent to TypeSafe; no labels, notes, references or old scores are sent.

Known usage with malformed answers causes visible family abstention for new arms;
retain baseline, settle cost, never repair or retry. Transport ambiguity, unknown
model/usage, changed frozen inputs/code, pending reservation, or budget ceiling
stops the run. No silent retries. Complete offline replay needs no credentials.
Stop after this fixed run and human-ready report, even if results are negative.
Keep #41 open until the user explicitly approves closure.

## Interfaces, ownership and work packages

- Policy agent (Sol): `pipeline/comment_selection_policy.py` and its tests.
  Exports `comment_requests(case)`, `pair_requests(case)`,
  `build_lists(case, baseline_pack, scores=None)`. Score IDs: feature `*_cN`,
  directional `first_I_J` for every ordered I != J. Baseline pack is v1 rank pack.
  Returns methods baseline/pointwise/pairwise. Each list: status completed or
  unavailable; `excerpts` first three and `extra_excerpts` remainder, exact
  `{comment_id,text,start:0,end:len(text),partial:false}`; `selected_ids`,
  `retained_ids`, `excluded_ids`, `word_count` (first three), `total_word_count`,
  local `ranking`/`pairs`. None scores means new arms unavailable, not empty.
- Feedback agent (Luna): private anchor inventory under
  `data/backfill/comment-selection-v2-anchors/`, plus generic evaluator
  `comment_selection_feedback.py` and synthetic tests. Own no public case-specific
  data. Outputs per-arm anchor counters and private failures, with provenance.
- Review agent (Sol): `comment_selection_review.py`,
  `comment_selection_static/`, tests. Packet contract: list of eight
  `{review_id,family_id,case_id,sample_kind,image_path,comments,methods:{A:...,B:...},
  packs:{A:...list,B:...list}}`, with manifest packet_id/plan_id/cases_sha256/
  image_hashes matching v1 conventions. Images inside new root. No reference
  answers needed. Do not modify old review server or feedback.
- Primary: runner `pipeline/comment_selection_run.py`, tests, plan, prior hashes,
  budget, preflight, calls, offline replay, analysis, integration, browser
  verification, docs/roadmap/issue/PR updates. Own shared contracts and final review.

Validation: exact source preservation, blindness and budget boundaries; empty,
singleton, ambiguous and invalid cases; pair reversal/ties; full-list redundant
positive retention; feedback provenance and no imputed labels; safe local server,
persistence/reveal, separate irrelevance fields; full pytest before dispatch.
Commit implementation before paid calls. Verify old replay and journal hashes
again afterwards. Publish code/tests/aggregate findings only; all raw content,
human anchors and case-specific analyses remain local.
