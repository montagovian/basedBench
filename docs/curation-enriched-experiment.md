# Enriched-label comparison · September 20, 2026

Prepared from the completed 28-case review and earlier conversational feedback.
The aim is to learn which change helps: clearer criteria, explicit component
examples, or access to the image. This is a development experiment, not a claim
of unattended admission quality.

## Frozen comparison

| Variant | Criteria | Labeled examples | Candidate evidence |
| --- | --- | --- | --- |
| JEV old rules | Earlier three-check criteria | None | Full original explanation and comments |
| JEV clearer rules | More concrete answer-completeness and task-value questions | None | Same text |
| JEV with examples | Clearer rules | Explicit component judgments | Same text |
| Luna with examples | Same clearer rules | Same examples | Same text |
| Luna with images | Same clearer rules | Same text examples | Same text plus original image |

All five variants score the same 28 candidates: **140 calls**. The old-rules
control removes the earlier overall-labeled reference material; it is not an
exact rerun of that earlier prompt. Comparing the three new JEV variants isolates
the effects of the clearer criteria and explicit examples within this round.

The candidate's historical label, new feedback, curator note, difficulty and
reference-familiarity judgments are not supplied to its classifier. A reference
example includes only its named component label, relevant evidence and curator
note. References for content and task value contain the stored explanation;
ground-truth references also contain their full source comments. Reference images
are not supplied. All candidate text is preserved in every variant.

The content rule and pass/fail/uncertain outputs stay fixed. Ground truth remains
one joint check covering consensus, support, completeness and image consistency.
The task-value question asks for a meaningful inference or reference connection;
it does not automatically exclude simple jokes or any meme format.

## How the feedback is used

The 28 candidates form two fixed groups of 14. A candidate may use labeled
examples from the other group and from the earlier discussion. Known copies of
any candidate in its group are excluded from those examples. Selection is
deterministic, with up to two pass and two fail examples per component; unavailable
negative labels are not invented to fill the quota.

Only explicit, settled component labels qualify. Tentative earlier feedback,
policy-boundary labels, unsure answers and blank fields do not become binary
labels. Overall acceptance does not imply that every component passed. The
three known opposite-label pairs are grouped together; the broader semantic-family
audit remains incomplete. M4M4BEAR has another corpus copy in its existing group,
outside this 50-case feedback pool; it is a different joke from the earlier
NE14 ABJ number-plate prank.

Criteria were developed after reading the feedback. Keeping each candidate out
of its own examples reduces direct leakage but does not turn this into an
independent validation set. The reserved test split is not used.

## What we will measure

- For each component: the pass/fail confusion matrix, good-item retention,
  bad-item detection, abstentions and balanced accuracy. There are only **two
  content failures and one answer defect** among the 28 targets, so those error
  rates have very small denominators.
- For overall admission: agreement on the **21 settled accept/reject decisions**,
  accepted bad items and retained good items. Acceptance precision is explicitly
  conditional on those resolved cases.
- Report the six undecided cases and one answer-repair case separately. Preserve
  uncertainty; do not count them as negatives or silently omit their outcomes.
- Compare paired changes, errors, latency and total cost. Code still combines
  checks using any fail → reject, otherwise any uncertain → defer, otherwise
  accept. The ground-truth result identifies answer-repair candidates; repair is
  not automatic publication.

One overall rejection has pass/ready/worthwhile on all three component questions.
Its reason is not recorded. Preserve that disagreement rather than teaching a
classifier that one of those explicit component labels must be wrong.

## Cost and execution

Prepared conservative request allowances sum to **$0.71681** across all 140 calls;
the proposed shared cap is **$1**. Allowances use text bytes as an upper token
estimate, maximum output tokens, conservative image accounting and no cache
savings. Actual usage is settled as calls finish. Interrupted requests retain
their allowances and are not automatically retried. The cap covers all five
variants together.

Use pinned `jev-1.13.0` and the requested `gpt-5.6-luna`, with no fallback to
GPT-5.5. Pricing was rechecked September 20 against the
[official Luna documentation](https://developers.openai.com/api/docs/models/gpt-5.6-luna)
and [TypeSafe model documentation](https://docs.typesafe.ai/models).

The prepared requests, feedback snapshot, folds, reference selections and hashes
are frozen under `data/curation/enriched-v1/`. Preparation makes no API calls.
The execution command requires the matching explicit spending cap:

```sh
uv run python -m basedbench.pipeline.curation_enriched run \
  data/curation/enriched-v1 --budget-usd 1
```

The existing budgeted transport saves each response and usage report. Source
reviews, frozen corpus files and previous model calls remain unchanged.

## Offline baseline already checked

Twelve of the new reviews overlap the saved API run. Rescoring those saved
predictions costs nothing. On the nine cases with settled task-value labels,
all three decomposed methods passed every case: eight match positive feedback,
and all miss the one negative. Thus 8/9 agreement still provides no evidence that
the value check can reject weak candidates.

JEV's saved answer check matches all 12 new answer judgments, including the one
repair; Luna's text and image checks flag additional answers now marked ready.
This is a small, deliberately targeted subset. Changed agreement after relabeling
is not an improvement to any model. The offline result is saved separately as
`saved-predictions-new-labels.json`.
