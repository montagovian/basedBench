# Jev comment selection: initial human-review findings

September 24, 2026. [Issue #41](https://github.com/montagovian/basedBench/issues/41),
[draft PR #42](https://github.com/montagovian/basedBench/pull/42),
[frozen protocol](jev-evidence-ranking-plan.md),
[model-run results](jev-evidence-ranking-results.md).

**Plain Jev ranking is the most promising of these methods, but this partial
review does not meet the predeclared follow-up screen.** The stronger practical
finding is that retaining the clue is insufficient: the reader also needs fewer
irrelevant comments and a complete explanation near the top. Duplicate grouping
does not reliably accomplish that. This analysis made zero provider calls and
does not change the methods, ratings or previous outputs.

## What was reviewed

The user saved ratings for **13/16 families**: nine of twelve sampled families
and all four diagnostics. Three sampled cases remain unreviewed; no judgments are imputed. The exact snapshot contains 17 journal events: 14 feedback saves and
three method reveals. One case was saved twice with identical substantive
feedback and is counted once. All 13 selected judgments precede revelation of
their own case's method identities. No source/reference opening was recorded
in the app before these judgments; external inspection is unknown.

The exact notes, IDs, revisions and exposure history remain private and unchanged.
Latest feedback before case-specific method reveal supplies the main analysis.
There are no post-reveal rating revisions in this snapshot. The snapshot is fixed
at the final recorded save on September 24, 23:30:03 UTC; later events would need
a new analysis snapshot.

## Sampled families: the primary comparison

Counts below concern the **nine reviewed sampled families**, not all twelve
selected families or the full 81-family model run.

| Method | Full clue retained | Misleading = yes | Misleading = unsure | Selected best button |
| --- | ---: | ---: | ---: | ---: |
| Saved order | 8/9 | 5/9 | 1/9 | 1 |
| Jev ranking | 9/9 | 4/9 | 1/9 | 2 |
| Jev ranking + collation | 9/9 | 5/9 | 1/9 | 2 |

Four cases have a tie selection. The five remaining button choices contain one
important qualification: the rank and collate lists are exactly identical,
and the note explicitly calls them equally preferable to saved order. Preserve
the original collation-button choice, but do not treat it as evidence for a
unique collation advantage. The sensitivity accounting is **two unique ranking
choices, one unique collation choice, one unique saved-order choice, one shared
rank/collate preference, and four ties**. No preference between nonwinning methods
is inferred from the best-button choice.

Both Jev arms satisfy the smaller raw-count comparisons against order, but the
frozen screen also requires **at least eight decisive sampled preferences**.
There are only **five**, one of which does not distinguish rank from collation.
The screen is therefore **not met**. This is a preliminary signal with missing
reviews and many ties, not a demonstrated failure or a demonstrated quality win.
Skipped cases are not assumed random, and no population accuracy or significance
claim follows.

The field is literally named `misleading`, but several notes use it to flag
irrelevance, riffs, incompleteness or poor prioritization. These counts must not
be presented as factual-error rates. Likewise a tie can mean all lists are good
or all are poor; the notes distinguish those cases.

## Diagnostics, kept separate

All four diagnostic families retained the clue under all three methods. Recorded
misleading counts are 2/4 for order, 2/4 for rank and 3/4 for collate. Best-button
counts are order 2, rank 2, collate 0. One order choice is qualified by
identical order/rank lists and an explicit note that both are good; the diagnostic
preferences are thus two unique ranking choices, one unique order choice and one
shared order/rank preference. They cannot fill the sampled screen's quota.

Across all 13 reviews, descriptive totals are full clue retained 12/13 for order
and 13/13 for each Jev arm; misleading marked yes 7/13, 6/13 and 8/13 respectively.
This pooled view is not the primary comparison because diagnostics were selected
for known failure modes.

## Implementation lessons

The exact notes and case-linked qualitative audit remain private. Aggregate
findings suggest four distinct follow-up targets:

- Finding a substantive explanation behind reactions can improve a reading list.
- Presence of the needed clue does not make every additional comment useful.
  The current packer has a word ceiling but no usefulness cutoff or sufficient-
  information stopping rule.
- Duplicate grouping can suppress useful detail. A source pointer can be relevant
  without being the most complete first explanation. These are assistant design
  hypotheses supported by inspecting the frozen outputs, not verified new labels.
- Ranking all relevant comments and selecting a short reading list are different
  objectives. A fixed word cap can make a reader's preferred combination infeasible.

The interface also cannot express two preferred lists tied above the third.
Future review designs should allow a preferred subset or ordered tiers and show
exact duplicate lists as such. Preserve the current recorded answers; do not
retrofit new votes. Case-specific notes and method critiques are available only
in the private report and audit artifacts.

## Decision and next boundary

This is enough feedback to identify concrete design problems without requiring
the user to fill every skipped case. It is insufficient to claim the predeclared
success criterion or promote either method.

For a separately proposed follow-up, distinguish **comment relevance**, **which
comments belong first**, and **when enough information has been selected**. A
short sufficient explanation can be better than a list filled toward its maximum
size. Source pointers and alternative readings may be useful supporting evidence
without deserving the first position. These are hypotheses for a future design,
not changes to this frozen run and not grounds for automatic retuning.

Keep #41 open for the user's review of this interpretation and explicit closure
direction. #43's VLM demonstration proposal remains separate. No new training,
inference, source retrieval, benchmark admission, database update or promotion
occurred.

## Reproducibility

Private snapshot: `data/backfill/evidence-ranking-human-review-v1/`. It contains
the exact journal and packet, a hashed snapshot manifest, deterministic summary,
and separately labeled assistant observations. The helper validates packet IDs,
event/request uniqueness, revision chains, exposure chronology and rating coverage.
Skipped cases and unsure ratings remain explicit. Four focused tests cover these
boundaries, revisions, identical selections and separation of diagnostic counts.
The full regression suite passes: 711 tests, with one existing skip.

```sh
uv run python -m basedbench.evidence_ranking_feedback \
  --snapshot /path/to/basedBench5/data/backfill/evidence-ranking-human-review-v1
```

The original model-run replay continues to verify all 81 outputs and 516 protected
artifacts without credentials or new calls. Human feedback remains outside that
immutable model-run manifest.
