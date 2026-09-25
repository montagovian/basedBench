# Explanation calibration before larger experiments

September 22, 2026. The approved next step is a bounded human calibration round,
followed by a more informative model comparison under a **$10 total ceiling**.
Tracked in [#20](https://github.com/montagovian/basedBench/issues/20) and
[#21](https://github.com/montagovian/basedBench/issues/21), respectively.
Human collection is **complete**: all 50 cases have saved judgments. See the
[results](explanation-calibration-results.md). The separate paid comparison
follows the frozen feedback; packet preparation and human analysis cost $0.

## The question

**Is this explanation good enough to grade whether another model got the same
joke? If not, what material connection is missing or wrong?**

The review distinguishes ready, material defect and cannot judge. Optional
reason tags distinguish missing/wrong connections, unsupported interpretations,
source-support shortfalls and optional improvements. Readiness is independent
of preference: both answers may be acceptable, including when one is richer.
Neither simplicity nor familiarity makes an explanation defective. No new
suitability or humor-theory requirement is introduced.

Assistant inspection flags remain development hypotheses. Existing human
judgments remain in their original files and experiments. This round adds
versioned judgments about these exact answer texts; it does not silently
supersede old labels or change membership in the benchmark.

## Frozen local packet

`data/curation/explanation-calibration-v1/`

- **20 targeted cases:** the complete frozen #18 packet, retaining useful
  positives and historical human-ready examples as well as suspected defects.
- **30 random cached cases:** sampled by a fixed hash order from 79 unreviewed,
  answer-bearing archive posts dated June 7 onward. All have cached images and
  a uniquely recoverable original generation context. Prior review/evaluation,
  recorded local exposure and known-family exclusions leave 78 eligible rows.
  One distinct known family is selected per random case.
- **Seven pairs:** original versus an already saved, schema-valid proposed
  repair; the other 43 cases have one answer. No draft is regenerated or edited
  for this review. A repair's model verification may have failed; human review
  remains independent of that status. A/B order and case order are hash-shuffled.
- **Zero new API calls / $0.** Random answers were generated previously by
  GPT-5.4 mini. That provenance is recorded, not a new model choice.

Images, answer texts, source comments, original provenance, eligibility ledger,
selection seed, rubric, source hashes and implementation hashes are frozen.
Packet ID: `7c94462be3c2cf03439c66c8fd9e9e653abcbea46f92d08b1f5b019abdd58b5a`.
The local selection ledger records all 79 eligibility decisions and the exact
files searched for prior exposure. Family exclusions use identical decoded
images, identical stored explanations, recorded retrieval edges and known
families; candidate edges are conservative exclusions, not duplicate gold.

The random portion is **fresh to this human review, not an untouched test set**.
It is conditional on successful legacy generation, available cached assets and
no previous review row. Duplicate-retrieval exposure persists and semantic
families are incompletely known. Do not infer full archive admission yield or
modern Luna generation quality from this conditional sample. Targeted and
random results must remain separately reported; do not pool them into a headline
accuracy estimate.

## Review and resume

```sh
uv run python -m basedbench.calibration_review serve \
  data/curation/explanation-calibration-v1 --port 9876
```

Open `http://127.0.0.1:9876/`. The page starts at the first case without saved
judgments for every displayed answer. Choose any fields you can judge, and use
**Save feedback** or **Save & next**. Both-acceptable is a convenience choice;
optional preference never marks the other explanation defective. Use **Cannot
judge yet** freely. A note about the concrete missing/wrong connection is more
useful than a demand for general elaboration.

Source comments are optional and hidden until requested. Revealing them appends
the current draft checkpoint, preserving what was judged before exposure.
Model identities, model opinions, old labels and sampling strata stay hidden.
Drafts survive navigation in browser storage; durable saves append revisions to
this packet's `events.jsonl`, with packet/input/rubric hashes, time, exposure,
revision conflict detection and idempotent retry handling. Partial feedback is
kept without inferring absent labels. No source answer, historical feedback,
database record or frozen model run is rewritten.

Preparation is intentionally non-overwriting:

```sh
uv run python -m basedbench.calibration_review prepare \
  data/curation/explanation-calibration-NEW
```

The live archive and exposure ledger can change, so a future packet is a new
sample, not a reconstruction of this frozen packet. Use the saved manifest and
selection ledger to audit this one. A never-served preparation preflight is
retained separately under `data/review-preflight/`; it contains no feedback.

## Analysis after human review

1. Freeze a feedback snapshot with exact event revisions. Keep unclear/blank
   judgments unresolved; report completion and comment exposure explicitly.
2. Report targeted and random results separately: original answers ready,
   materially defective, unresolved; concrete defect categories; and whether
   each proposed repair fixes a human-confirmed defect, introduces a defect,
   or merely changes preference. Seven pairs are not seven known defects.
3. Separate intrinsic answer errors from insufficient source support. A
   plausible answer with too little consensus is an evidence hold, not proof
   that the joke is wrong. Do not treat optional detail as required coverage.
4. Describe conflicts with older judgments without overwriting either. Use
   this round to clarify the rubric and choose a small set of concrete failure
   examples, not to fit every discretionary historical rejection.
5. Freeze recipes before the fresh validation portion of the
   [larger comparison](calibrated-comparison.md). This 50-case round is
   calibration/development evidence throughout.

## Preparation verification

All 461 tests pass: 459 in the sandbox and the two localhost HTTP tests outside
it because local socket binding is restricted there. A disposable browser packet
verified both-acceptable plus a separate preference, pre-reveal draft logging,
save-and-next, durable feedback after reload and single-answer navigation. The
real 50-case page was opened without entering any assistant judgments.

All **11,217** protected source files match their before hashes, including the
database, historical feedback, prior frozen runs and the user's unrelated app
and helper-test edits. Frozen #16–#19 experiment implementation hashes still
match their plans. The private verification record is
`data/backfill/calibration-verification-v1.json`. No new paid calls occurred.
