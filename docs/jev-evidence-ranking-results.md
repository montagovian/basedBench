# Jev evidence ranking: model run complete, human review pending

September 24, 2026. [Issue #41](https://github.com/montagovian/basedBench/issues/41)
tracks the [frozen comparison plan](jev-evidence-ranking-plan.md). Keep it open
until the user reviews the evidence packs and explicitly approves closure.
The model run finished under its new $1 cap. **Usefulness is not yet established.**

## What ran

The prior 99 answer versions yielded 94 eligible versions in 81 distinct meme
families. One deterministic representative per family contributed 760 saved
comments. Five exclusions and the other versions remain inventoried; three
families have multiple image/comment contexts. Seventy-three representatives have
an exact-context prior human-ready explanation. Two ready versions from different
contexts are explicitly unmatched and never borrowed as reference answers.

The three methods use exactly the same saved pool and maximum reading budget:
saved comment order, Jev informativeness ranking, and ranking with duplicate
grouping and a novelty penalty. Five binary-probability questions per comment and
two per unordered pair produced 11,608 decisions in 213 calls to `jev-1.13.0`.
Only saved image observations and comment IDs/text were sent. Human judgments,
references, candidate answers and notes remained local. No OpenAI calls or new
image descriptions were needed.

All 213 calls settled with valid outputs: **81/81 families completed, zero
abstentions, zero pending calls, estimated cost $0.075391344**. The preflight
reserved a conservative worst-case total of $0.572544. No retry, score correction,
prompt tuning or additional experiment followed the results.

## Output coverage, not a quality score

The source pool contains 20,256 whitespace-delimited words. Summed maximum pack
budgets are 9,762 words per method; each family's cap is identical across methods.
Whole-comment selection and exact prefix truncation can leave unused space.

| Method | Available families | Excerpts | Words shown |
| --- | ---: | ---: | ---: |
| Saved order | 81 | 443 | 9,083 |
| Jev ranking | 81 | 355 | 9,298 |
| Jev ranking and collation | 81 | 365 | 8,707 |

All three ordered excerpt lists are identical in 4/81 families. Ranking and
collation are identical in 30/81, saved order and ranking in 8/81, and saved order
and collation in 4/81. The collation model groups 144 comments as duplicates across
62 families. These are model suggestions, not verified redundancy labels or
evidence that removing those comments helped. Ranking also has no usefulness
threshold: a lower-value comment can still fit later in a pack.

The four diagnostic families were inspected locally by the assistant. Those
notes are hypotheses for later analysis, separate from human ratings, and are
withheld from the review interface to avoid suggesting preferences. Specific
failure hypotheses include losing a distinct decoding step through grouping and
retaining low-value reactions after useful comments. No policy was changed in
response to this inspection.

## Human review

The 16 families were chosen before model outputs: four fixed diagnostics and
12 hash-sampled other families. Fifteen have differing packs; one has three
identical packs. Thirteen have a matched prior-ready explanation available on
request. The saved pool can be incomplete relative to the original Reddit thread.

The local interface presents the image and anonymous A/B/C packs. For each pack,
rate clue retention and misleading material; then select the most useful pack,
tie, or unsure. Save before revealing methods. Opening saved comments, opening
the matched explanation, and revealing methods are recorded separately. Ratings
and revisions persist in an append-only journal. Revised ratings after method
reveal remain distinguishable from blinded judgments. The actual review starts
with zero events; browser save/reveal tests used a separate disposable fixture.

Use the plan's predeclared screen on the 12 sampled families only: at least eight
decisive best-pack preferences, a Jev arm selected at least once and at least twice
as often as saved order, no lower full-clue count, and no higher misleading-pack
count. Report ties, uncertainty and source exposure. These are best-pack counts,
not inferred pairwise preferences or a significance test. Diagnostics cannot
satisfy this screen. Human review is pending; no effectiveness or admission claim
is made.

## Verification and operation

Implementation was committed before paid dispatch at `f4caeac`. The full pytest
regression suite passed, followed by 37 final focused runner, policy, IO and review
tests. Browser checks covered real image rendering and side-by-side packs, plus
save/reload, unavailable packs, method reveal and unsaved-navigation protection
in the separate fixture. Review text is escaped; localhost Host/Origin/token
checks protect feedback writes.

Credential-free replay verified all 81 outputs and aggregate accounting against
516 frozen run artifacts, with no new calls. The source manifests and images
verify; no frozen Jev/GEPA module or previous result was modified. Existing main
worktree UI edits remain untouched. No active checker, database, release membership
or publication changed. Issues #38, #40 and #41 remain open for human review.

Private run: `data/backfill/evidence-ranking-v1` in the main repository. The
human journal is `review-feedback/events.jsonl`, outside the frozen model outputs.
The stopped GEPA run and its review remain separate.

```sh
uv run python -m basedbench.pipeline.evidence_ranking_run replay \
  --root /path/to/basedBench5/data/backfill/evidence-ranking-v1

uv run python -m basedbench.evidence_ranking_review \
  --root /path/to/basedBench5/data/backfill/evidence-ranking-v1 --port 8794
```

Stop at this review milestone. Any downstream answer-generation benefit, source
verification, usefulness cutoff or grouping-policy improvement requires a
separately specified follow-up after the human feedback.
