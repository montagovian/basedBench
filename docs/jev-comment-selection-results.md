# Jev comment selection follow-up: filtering loses a needed explanation

September 24, 2026. [Issue #41](https://github.com/montagovian/basedBench/issues/41),
[draft PR #42](https://github.com/montagovian/basedBench/pull/42),
[frozen protocol](jev-comment-selection-plan.md).

**Do not adopt either new policy.** The relevance filter removes the two explicitly
unwanted comments from the full retained lists, but also removes one of seven
explicitly praised explanations. Pairwise ordering does worse than the simpler
pointwise ablation on the exposed development checks. This is a useful negative
result, not a demonstrated improvement or a reason to keep tuning these cases.

## Comparison and completed run

The same 81 families / 760 comments were processed once. The baseline reuses v1's
cached full ranking, now displayed as up to three whole comments plus an expandable
remainder. The two new arms use the same fixed relevance/noise filter: one orders
by individual explanation/completeness scores, the other by both directions of
every pairwise first-read comparison. Useful overlapping explanations are not
collapsed. There is no word ceiling or truncation; reading costs differ.

- 249 new Jev calls, 13,128 binary decisions, **$0.100736118**.
- Cumulative #41 spending: **$0.176127462 / $1**, including v1.
- All 81 families completed; no invalid responses, abstentions, pending calls or retries.
- Credential-free replay reproduces every list and verifies 589 frozen artifacts.
- The old run still reproduces all 81 outputs / 516 artifacts. Its human journal
  remains byte-identical to the prior snapshot.

No human labels, notes or references entered the requests. No new images,
OpenAI calls, source retrieval, answer generation, database or membership changes.

## Explicit-feedback checks

The private inventory was frozen before outputs: seven explicitly praised comment
IDs, two explicitly unwanted comments, one incomplete-first constraint, and one
ambiguous exclusion note that was not converted into individual negative labels.
Each has exact local event/quote provenance. Pack-level misleading or clue ratings
were not turned into comment-level truth labels. Cases used to design the method
are exposed development data; these tiny counts do not estimate general accuracy.

| Check | Cached rank, new display | Filter + pointwise | Filter + pairwise |
| --- | ---: | ---: | ---: |
| Praised comments retained anywhere | 7/7 | 6/7 | 6/7 |
| Praised comments in initial three | 5/7 | 6/7 | 4/7 |
| Unwanted comments absent from initial three | 2/2 | 2/2 | 2/2 |
| Unwanted comments excluded from full list | 0/2 | 2/2 | 2/2 |
| Incomplete-first constraint satisfied | 0/1 | 1/1 | 0/1 |

The predeclared development rule is **not met**. Both new methods lose a praised
comment. The baseline already excludes both unwanted comments from its initial
three under the new display, so neither new method improves that particular
metric. Only pointwise improves the ordering constraint. The pairwise arm places
two fewer praised comments in the initial three than pointwise, and one fewer
than baseline. Retention and top-three inclusion are separate objectives.

## What the data revealed

Independent inspection of 13 families and 111 full source comments finds that a
direct explanation of wordplay is assigned
high relevance and completeness, yet a higher riff score triggers a hard veto.
An extended imagined dialogue survives instead. This is a semantic distinction
failure between explaining the meme's joke and making another joke, not merely
a shortage of comparisons or a failure to fit a length budget.

Across the run, 12 comments in nine families simultaneously score at least .60
on relevance, .70 on explanation, and .70 on reaction/riff noise. These are
descriptive model-score conflicts, not 12 confirmed human errors. They show why
combining independently plausible answers with a hard veto can discard useful
material even when another question recognizes its explanatory content.

The two empty lists warrant separate scrutiny: source comments contain apparent
name-based wordplay and a compact slang decoding, respectively. These are
assistant inspection findings, not new human labels. Empty lists are valid
technical outputs, but are not evidence that the source contains nothing useful.

In the incomplete-pointer diagnostic, pointwise ordering puts the specific
explanation first; pairwise ordering instead promotes generic template pointers.
There is no basis to prefer the additional comparison machinery on these checks.
Useful overlapping explanations remain in the full lists, but keeping them does
not ensure that the reader's preferred three become the first three.

## Reading length and coverage

| Descriptive statistic | Cached rank | Pointwise | Pairwise |
| --- | ---: | ---: | ---: |
| Comments in initial lists | 243 | 198 | 198 |
| Comments retained in full lists | 760 | 280 | 280 |
| Empty lists | 0 | 2 | 2 |
| Words in initial lists | 11,303 | 10,502 | 9,282 |
| Words in full retained lists | 20,256 | 12,853 | 12,853 |

Pointwise and pairwise have identical initial ordered lists in 49/81 families;
baseline matches them in 12/81 and 10/81 respectively. Shorter lists and fewer
words are workload measures, not quality evidence. The cached baseline here is
repacked from its full ranking, so its numbers must not replace v1's original
word-budget comparison or its recorded human ratings.

## Human review and decision

The frozen eight-case page compares baseline against pairwise, as planned: four
previous problem cases followed by four newly reviewed families. The simpler
pointwise ablation remains in the analysis; it was not silently substituted into
the planned review after seeing the result. No new human feedback is assumed.
The page shows up to three whole comments and an expandable remainder, asks about
first-comment usefulness and irrelevant extras, and supports A/B/tie/neither/unsure.
Factual concerns belong in a separate optional note. Method identity is revealed
only after a saved judgment, with exposure and later revisions recorded.

The observed regression is already enough to reject adoption; completing all
eight reviews is not a prerequisite for that decision. Human review can clarify
whether the specific failure interpretation is right. Preserve this fixed run and
stop here. A future proposal should reconsider hard exclusion of purported riffs
and establish how to distinguish a concise decoding from a reaction; merely
adding pairwise questions or tuning the cutoff on these same cases is unsupported.
Keep #41 open for human review and explicit closure approval. #38/#40 remain open;
VLM #43 is separate. No automatic follow-up run or promotion.

## Reproduction and validation

Implementation committed before dispatch at `6dcc345`. Full regression suite:
742 passed, one existing skip. Focused runner checks also pass after adding the
analysis-code hash to the frozen manifest. Browser verification covered a
separate fixture's save/reload/reveal and the actual review's image and two-column
layout. No fixture ratings were written into the actual journal.

Private model root: `data/backfill/comment-selection-v2/`. Private feedback
inventory and analysis: `comment-selection-v2-anchors/` and
`comment-selection-v2-analysis/` alongside that root. Raw text, images, requests,
responses, exact feedback, anchor provenance and case-linked reports stay local.
Public documentation contains only aggregate outcomes and generic lessons.

```sh
uv run python -m basedbench.pipeline.comment_selection_run replay --root /path/to/comment-selection-v2
uv run python -m basedbench.comment_selection_feedback \
  --anchors /path/to/comment-selection-v2-anchors/anchors.json \
  --outcomes /path/to/comment-selection-v2/outcomes.json \
  --output /path/to/comment-selection-v2-analysis/anchor-results.json
uv run python -m basedbench.comment_selection_review --root /path/to/comment-selection-v2 --port 8796
```
