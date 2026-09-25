# Publication content checks for the backfill pilot

Issue [#5](https://github.com/montagovian/basedBench/issues/5), September 21, 2026.
Current policy and implementation version: `content-policy-v2`. The original
comparison remains frozen as `content-policy-v1`.

The pilot needs to identify specific content concerns, decide what the current
rules establish, and leave unresolved items outside the release. This component
only checks publication content. It does not grade whether an explanation gets
the joke, whether the joke is worthwhile or difficult, or whether an image is a
duplicate. Those remain separate checks.

## Results and pilot recommendation

**The revised checker failed all 3 definite exclusions, passed 21 of 23 definite
content passes, and deferred the other 2.** It made no hard false rejection on
these settled labels. Those two deferrals are still losses of valid material for
an unattended batch and must be reported; they are not correct passes.

| Blind model outcome | Old wording | Clarified v1 | Revised v2 |
| --- | ---: | ---: | ---: |
| Clear human passes: model pass | 21/23 | 22/23 | 21/23 |
| Clear human passes: model fail | 1/23 | 1/23 | 0/23 |
| Clear human passes: model defer | 1/23 | 0/23 | 2/23 |
| Clear human failures: model fail | 1/3 | 2/3 | 3/3 |
| Clear human failures: model pass | 2/3 | 0/3 | 0/3 |
| Clear human failures: model defer | 0/3 | 1/3 | 0/3 |
| Unresolved judgments: model pass / fail / defer | 7 / 0 / 1 | 4 / 1 / 3 | 1 / 1 / 6 |
| Technical errors | 0 | 0 | 0 |

The initial control and v1 were paired on identical inputs/schema; v2 is a
follow-up iteration on those same cases. Its improved negative detection and
boundary handling came with additional positive deferrals. Repeated use of the
same small development set means this is not an unbiased performance estimate.

Concrete results:

- **K-pop anatomy-focused joke:** old wording passed it; v1 deferred it; v2
  excluded the intended anatomical focus without requiring literal nudity or
  an explicitly spelled-out anatomical word. This matches the definite fail.
- **Popsicle gag:** both clarified versions excluded the specific sexual-act
  implication carried by the ordinary object. The old wording passed it.
- **Spicy ramen:** all three checks caught the rendered slur.
- **Historical time-travel satire:** the first two checks overextended the
  violence rule. V2 passed it after clarifying fictional historical satire.
- **Freddie Mercury and Oprah/Weinstein:** v2 deferred both despite clear human
  content passes. It overextended the allusive-sexual boundary to non-graphic
  dark humor. Their human labels remain pass. These are explicit residual
  false deferrals, not evidence to rewrite the policy or labels.
- **Six boundary judgments:** v2 deferred the superpowered injury, Sneed/Chuck,
  crumb slogan, childhood-photo age ambiguity, Vaporeon/ID and stairs/elevator
  cases. These are policy-boundary outputs, not claims that the model cannot
  understand the references.
- **Evangelion and neck/back:** v2 respectively failed and passed them. The
  original human lean-fail/lean-pass remain unresolved; the separate preservation
  rule keeps both deferred. All eight unsettled human judgments therefore stay
  outside automatic admission without hiding the blind model's decisions.

Use **v2 as the versioned experimental content component for #7**, retaining its
findings, original model route, human-uncertainty preservation and technical
status. It is ready to integrate into a bounded development pilot. This does not
switch the old production gate or establish general unattended accuracy. Do not
spend more calls trying to perfect these same 34 cases; assess consequential
errors and coverage loss in the later pilot.

The known negatives cover two sexual exclusions and one rendered slur. There are
no adequate human-labeled negative controls for gore, doxxing/private harassment,
real violent advocacy or established minor sexualization in this development
set. Nor are there definitive real-case “needs context” labels here; that route
has contract tests, not a measured recall estimate. Existing source explanations
can also be wrong. #7/#8 must preserve these limitations and should not claim
broad-category validation from the aggregate counts.

Across both runs: **102 new provider calls**, **$0.1154847 estimated model cost**
($0.1155 conservatively accounted), below the original **$0.75 ceiling**. No
unknown-cost requests, pending calls, provider errors, parser errors or allowance
violations remained. There were no new JEV or flagship-model calls.

**378 tests passed.** Both completed versions were replayed with a client that
would fail on any new provider call; reports were unchanged. Frozen evidence,
request hashes, response provenance, model IDs and usage were audited, and human
feedback remained unchanged. Final local artifact hashes are recorded under
`data/curation/content-policy-analysis/`. No raw data, images or call logs are
committed, and the source/report commits remain local and unpushed.

## Working rules

| Content | Decision rule |
| --- | --- |
| Explicit sexual content | Fail established sexual acts or exposed sexual anatomy. The clarified rule also covers a central payoff that simulates a specific sexual act through ordinary objects, or focuses on sexual-anatomy details; literal nudity is not required. |
| Mild innuendo and sexual references | Can pass. Attraction, relationship/hookup references, a taboo premise, ordinary anatomy words, dirty humor and profanity are not blanket exclusions. Distinguish recognizing a sexual premise from a payoff that specifically invites visualizing an act's mechanics or anatomical detail. |
| Slurs or hate | Fail a recognizable identity slur rendered in the meme, hate speech or dehumanizing hate tropes. Quotation within the meme does not erase a slur. A source comment's unrelated slur is not automatically the candidate's content. |
| Gore | Fail visibly graphic gore. A verbal historical/crime reference or disturbing legend does not establish gore in the image. |
| Violence | Fail endorsement/celebration of violence against identifiable people or groups. Distinguish advocacy from dark humor, fictional reversals, historical satire and reporting. A non-graphic fictional time-travel scenario involving a long-dead historical figure is not itself present-day violent advocacy. |
| Private targeting | Fail doxxing or targeted harassment of a private individual. Ordinary public handles and public-figure satire alone do not establish this. |
| Minors | Fail established sexualization of minors. Ordinary childhood imagery is not excluded; do not infer age solely from cartoon style or youthful appearance. |
| Unsettled sexual boundaries | Defer when the central joke belongs to the unresolved categories of sexual-fluid/obscene wordplay, implied exposure, sexual injury, an allusive pornographic reference, or relationship age ambiguity. Calling these mild or non-graphic does not settle their threshold. A separately established exclusion can still fail. |
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

## Initial experiment, frozen before calls

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

The original experiment was prepared and run at commit `7bc7d48` with:

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

## Focused revision, frozen before its calls

The first comparison completed 68 calls for **$0.0733178** estimated usage
($0.073328 conservatively accounted). The old wording passed 21/23 positives,
failed one and deferred one, while catching only one of three exclusions. The
clarified wording passed 22/23 positives, failed one, caught two exclusions and
deferred the third. No clear negative passed the clarified check.

Inspection exposed three remaining instruction problems: fictional historical
satire was classified as violent advocacy; euphemistic anatomical focus was
still treated as a boundary because the anatomy was not named; and some listed
unsettled categories were treated as allowed merely because they were non-graphic.
Version 2 clarifies those distinctions and distinguishes a sexual-scene aftermath
allusion from depiction of an act's mechanics. It contains no target IDs, names or
labeled examples. This is explicitly another development iteration on the same
cases, not a new test set.

Run **only the clarified variant on the same 34 cases**. Inputs, labels, image
resolution, schema, model and reasoning/output limits stay the same. The new
conservative request allowance is **$0.21898625**. Set a remaining-run cap of
**$0.65**: first-run accounted usage plus the entire new cap is $0.723328, below
the original $0.75 total ceiling. No old-wording calls are repeated.

```sh
uv run python -m basedbench.pipeline.content_policy prepare \
  data/curation/review-v1 data/curation/historical-v2/assets \
  data/curation/content-policy-v2 --budget-usd 0.65 --arms clarified
uv run python -m basedbench.pipeline.content_policy run \
  data/curation/content-policy-v2 --budget-usd 0.65
```

Version 2 experiment ID:
`94ded284378e8c685e7075fc693e25349539aee82cac04431685ab619773ad8d`.
The first run's offline replay was verified before updating implementation:
zero new provider calls, identical report, unchanged human feedback.
