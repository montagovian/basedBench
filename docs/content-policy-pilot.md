# Publication content checks for the backfill pilot

Issue [#5](https://github.com/montagovian/basedBench/issues/5), September 21, 2026.
Policy and implementation version: `content-policy-v1`.

The pilot needs to identify specific content concerns, decide what the current
rules establish, and leave unresolved items outside the release. This component
only checks publication content. It does not grade whether an explanation gets
the joke, whether the joke is worthwhile or difficult, or whether an image is a
duplicate. Those remain separate checks.

## Working rules

| Content | Decision rule |
| --- | --- |
| Explicit sexual content | Fail established sexual acts or exposed sexual anatomy. The clarified rule also covers a central payoff that simulates a specific sexual act through ordinary objects, or focuses on sexual-anatomy details; literal nudity is not required. |
| Mild innuendo and sexual references | Can pass. Attraction, relationship/hookup references, a taboo premise, ordinary anatomy words, dirty humor and profanity are not blanket exclusions. Distinguish recognizing a sexual premise from a payoff that specifically invites visualizing an act's mechanics or anatomical detail. |
| Slurs or hate | Fail a recognizable identity slur rendered in the meme, hate speech or dehumanizing hate tropes. Quotation within the meme does not erase a slur. A source comment's unrelated slur is not automatically the candidate's content. |
| Gore | Fail visibly graphic gore. A verbal historical/crime reference or disturbing legend does not establish gore in the image. |
| Violence | Fail endorsement/celebration of violence against identifiable people or groups. Distinguish advocacy from dark humor, fictional reversals, historical satire and reporting. |
| Private targeting | Fail doxxing or targeted harassment of a private individual. Ordinary public handles and public-figure satire alone do not establish this. |
| Minors | Fail established sexualization of minors. Ordinary childhood imagery is not excluded; do not infer age solely from cartoon style or youthful appearance. |
| Unsettled sexual boundaries | Defer when inclusion hinges on an unresolved threshold for sexual-fluid/obscene wordplay, implied exposure, sexual injury, an allusive pornographic reference, or a relationship age-ambiguity joke. A separately established exclusion can still fail. |
| Missing context | Defer when a material reference, age, unreadable detail or competing interpretation prevents applying the rule. Knowing the joke but not having a settled policy threshold is a policy boundary instead. |

The distinction around explicit sexual meaning is a **working interpretation of
Alex's existing feedback**. The previous short rule focused on acts and exposed
anatomy, and models interpreted it too literally for two definite human failures.
It is not a new blanket prohibition of sexual references. The unresolved
categories reflect earlier tentative judgments and remain unresolved. No
AfterDark policy has been adopted.

The review rubric and the older production safety prompt differ in wording.
This pilot makes the existing exclusions explicit, retaining targeted-violence,
private-targeting and minor-sexualization exclusions from the older gate. It does
not carry forward the older phrase that could be read as excluding all depictions
of minors; the relevant concern is sexualization. Neither the old gate's vague
embarrassment test nor blanket default-to-keep resolves the known boundaries.
The legacy `SafetyGate` and its behavior have not been switched over to this
module. Integration and release decisions belong to #7/#8.

## Findings and routing

`src/basedbench/pipeline/content_policy.py` exposes typed findings, request
construction, response validation and deterministic routing. Each finding records
its category, a short observation, a specific image/text anchor, cited source
comments where relevant, whether it belongs to the image/intended meaning or
context only, and how the rule applies. These are **model findings**, not verified
facts. A separate derived decision preserves the rationale and findings:

- **Fail:** at least one established exclusion in the candidate. Other unresolved
  concerns remain in the record even when an independent exclusion settles it.
- **Defer — policy boundary:** the content is understood but the rule is unsettled.
- **Defer — needs context:** a material uncertainty prevents judging the content.
- **Pass:** the available image and relevant meaning produced no exclusion or
  unresolved material concern. This is not an overall admission.
- **Defer — technical error:** missing/unusable image, provider refusal/failure,
  interrupted delivery, invalid output or model substitution. Preserve the
  technical status instead of manufacturing a content failure or pass.

A context-only finding cannot by itself exclude a meme. An exclusion in an
inferred meaning needs an actual image/text anchor; comments and stored answers
are fallible context, not a source of automatic verdicts. The parser rejects
invented comment IDs. This checks citation existence, not whether a cited comment
truly supports a claim; semantic verification remains fallible.

Known unresolved human judgments are preserved by a separate post-evaluation
route: a model verdict cannot silently settle them. The raw blind model result
is retained and used for metrics before that preservation rule. Human pass/fail
labels are not fed into the model or used to improve its reported accuracy.
Nothing writes to the corpus database or review events.

## Frozen experiment, specified before calls

Compare two Luna image variants: the previous short content wording versus the
clarified rules above. Both use the same structured-findings schema, context
instructions, original images, stored explanations and comments. No labels,
curator notes, historical membership, target identifiers or labeled reference
examples are in the requests. Only the policy paragraph changes. The control is
a wording comparison, not a rerun of the full legacy ingestion gate.

Include **all 34 gallery cases with explicit content feedback**: 23 clear passes,
3 clear failures and 8 unresolved/tentative judgments. Sixteen cases with no
content-specific judgment are omitted; overall rejection never supplies missing
content gold. The earlier conversational Evangelion lean-fail and neck/back
lean-pass remain unresolved, rather than inflating either settled denominator.

The three definite failures are the K-pop anatomy-focused joke, popsicle gag and
spicy-ramen slur. Positives include sexual/taboo references, dark humor and
politics, so catching exclusions alone is insufficient. Report missed exclusions,
false exclusions, positive/negative deferrals and technical errors separately.
Unresolved-case predictions are reported separately without binary accuracy.

Hypothesis: clarifying the intended sexual focus will catch the two previously
missed sexual exclusions while retaining the 23 explicit content passes. Compare
boundary handling as well; a model's ability to choose a verdict does not settle
the human policy. Criteria were informed by these same examples, so this is a
development regression test, not independent evidence of unattended precision.
There are no adequate labeled negative controls for every other policy category.

Use `gpt-5.6-luna`, medium reasoning, high-detail images, maximum 2,400 output
tokens, no tools, no SDK retries and no fallback model. The
[official Luna documentation](https://developers.openai.com/api/docs/models/gpt-5.6-luna)
was checked September 21: image input and structured outputs are supported;
per-million token rates are $0.20 input, $0.02 cached input, $0.25 cache writes and
$1.20 output. Maximum request sizes remain below long-context pricing thresholds.

**Total spending cap: $0.75**, separate from the proposed later fresh-candidate
admission cap. The prepared 68 calls have a conservative combined allowance of
**$0.4029355**. Reserve maximum cost before dispatch, preserve unknown-cost
interruptions, and never repeat uncertain paid calls automatically. Freeze
requests, images, feedback provenance, implementation, prices, schemas and policy
hashes. A process lock prevents concurrent duplicate execution. Completed calls
are replayed without paying again; fatal provider stops survive resume.

Reproduce with:

```sh
uv run python -m basedbench.pipeline.content_policy prepare \
  data/curation/review-v1 data/curation/historical-v2/assets \
  data/curation/content-policy-v1 --budget-usd 0.75
uv run python -m basedbench.pipeline.content_policy run \
  data/curation/content-policy-v1 --budget-usd 0.75
```

Experiment ID:
`149c7ac00bb00617428c3ed837f8ee9ac3ac39a98a04f2e10b15d46a98dff567`.
Raw evidence, requests and responses remain in ignored local storage. Existing
JEV text-only results are documented in `curation-enriched-results.md`; this
experiment targets the visual policy gap and makes no new JEV calls.
