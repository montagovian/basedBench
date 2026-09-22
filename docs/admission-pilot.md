# Resumable admission pilot

Issue [#7](https://github.com/montagovian/basedBench/issues/7).

The pilot connects the source inventory, duplicate findings, content rules,
answer construction/checks and a minimum suitability check. It produces a local
development-candidate report. It does not edit the corpus database, replace human
judgments, add items to a release or publish anything.

## How a candidate moves through it

1. **Check the evidence.** A missing/unsupported image, source discrepancy or
   fewer than three distinct available comments causes a deferral. Three comments
   permit an assessment; their actual support must still be checked.
2. **Check collection overlap.** An exact copy of a published image is rejected
   as redundant. Uncertain image/joke-family links defer, including possible
   copies within the new batch. An exact match to an unpublished archive record
   can continue: that record does not occupy a place in the published release.
3. **Apply content-policy-v2.** Established excluded content rejects. Unsettled
   rules, missing context and technical failures defer, with distinct reasons.
4. **Construct and check the answer.** New candidates get an answer proposal,
   then an image-and-comment check. Existing answers are checked as written.
   A specific repairable defect permits one repair followed by a fresh check.
   Competing readings or insufficient evidence defer immediately. A failed
   verification also defers; there is no second repair loop.
5. **Check minimum suitability.** Identify the setup and the inference that a
   viewer must recover. Easy jokes, ordinary references, simple puns and text
   screenshots remain eligible. Only transcription alone, a demonstrably
   disconnected supposed joke or indispensable missing private backstory can
   establish a failure. Ambiguous cases defer. This does not try to reproduce
   every discretionary historical rejection.
6. **Record the outcome.** Accept requires every required component to pass.
   Rejection needs an established exclusion, minimal-task failure or published
   exact copy. Missing evidence, uncertainty, errors and insufficient budget
   produce deferrals. Checks not reached are explicitly marked with their
   stopping reason; they never receive invented passing scores.

A repaired answer stays alongside the original and its critique/proposal/check
history. The verifier sees the proposed answer, image and source comments, not
an earlier verdict or the repair critique. Model approval does not constitute
independent validation. In particular, #3 demonstrated that a verifier can
approve a newly introduced unsupported claim.

Known human feedback stays separate from the model inputs and raw results.
Unresolved judgments and direct human/model disagreements defer. A model that
challenges a human-ready original answer cannot automatically replace it. A
model passing an original answer already known to be defective cannot clear that
defect without a checked repair. The uncertainty guard does not turn these
examples into improved blind model scores.

## Bounds, checkpoints and provenance

- **Fresh batch:** at most 100 candidates and a frozen **$1 cap**. **Control
  smoke test:** six selected development examples and a separate **25¢ cap**.
- Luna only, with no automatic model fallback, escalation or API retry. At most
  six calls per fresh candidate: content, generation, check, optional repair and
  verification, suitability. Existing-answer cases need at most five.
- Reserve each request's conservative maximum cost before dispatch, including
  full output limits and the cache-write input rate. The sum of all possible
  stage allowances can exceed the cap; that means some work may defer. It does
  not authorize spending beyond the cap. Actual known usage releases unused
  reservations. A reported allowance violation stops further dispatch.
- Freeze the original evidence, copied assets, selected comments, component
  versions, code hashes, prices and request bounds. Save adaptive requests before
  sending them and compare them on replay. Each response retains model, usage,
  input and request identity.
- A run lock prevents concurrent execution. Each request leaves a pending marker
  before dispatch and saves its response atomically. A crash after response
  persistence resumes from that response. A crash with only a pending marker
  reserves the maximum cost and defers the item without repeating the request.
- Fatal provider failures stop further provider calls, including after restart.
  Already completed stages replay locally. The cap cannot be increased through
  a resume command. Explicit checkpoint stops retain paid work and mark
  incomplete outcomes as deferred until continuation.

The fresh adapter selects up to 20 nonempty, nonmoderator source comments,
sorted by score and ID. It records the selected IDs, original available count
and incomplete-thread scope. Bodies are indented so text resembling a comment-ID
header cannot invent a citation that the parser accepts. Neither authors,
reviewer notes nor human labels enter the model requests.

Prices checked September 21, 2026: Luna input $0.20, cached input $0.02,
cache writes $0.25 and output $1.20 per million tokens. Requests are bounded below
the long-context threshold. See the [official Luna model documentation](https://developers.openai.com/api/docs/models/gpt-5.6-luna).
The model alias and actual returned model IDs are retained; no dated snapshot is
invented. Estimates are not provider invoices. Unknown usage remains visible
and is conservatively reserved.

## Completed control run

The six-case development smoke test made **16 Luna calls**, costing an estimated
**$0.01821925 (about 1.8¢)** within its separate 25¢ cap. Conservative accounting
was $0.01822165. Every response returned `gpt-5.6-luna`; there were no provider or
parsing errors, unknown-usage calls, pending requests or allowance violations.

| Control | Automatic outcome | What happened |
| --- | --- | --- |
| RCA cables / Van Gogh | Defer | The checker agreed the explanation was correct, but found only two substantive supporting comments against the three-comment requirement. The human-ready answer and acceptance label were preserved. |
| Freezer bags | Accept | Starting with no supplied answer, the workflow generated and checked the literal-misunderstanding explanation, then passed minimum suitability. |
| Harry Potter's greatest achievement | Accept after one repair | The checker caught the missing comparison between the sarcastic comeback and Harry's heroic deeds. One repair restored it; the subsequent answer and suitability checks passed. The original explanation and its negative human label remain intact. |
| Spicy ramen | Reject | The visible slur triggered the established content exclusion, agreeing with the human label. No answer or suitability calls followed. |
| Superpowered injury | Defer | The model returned a policy boundary; the unresolved human judgment was also preserved. No answer or suitability calls followed. |
| Time-freezing snap | Defer | The answer check passed and the model found a recoverable suitability task, but the existing human value failure kept this disagreement unresolved. That label was not changed to a positive. |

These are **2 automatic accepts, 1 rejection and 3 deferrals**, not an accuracy
estimate. Duplicate findings for these historical controls are explicitly
isolated passing fixtures so they can exercise the remaining workflow; they do
not establish that the items are absent from the published collection. The
freezer-bags generation variant also does not inherit human validation of its
new wording from a previously reviewed answer.

Assistant inspection of the saved images, explanations and supporting evidence
is recorded separately from model outputs and human gold. It confirms that the
Harry Potter repair added the omitted greatest-achievement framing, but exposes
an inconsistency in the verifier: its setup field calls the quoted comeback
Snape's line, while its joke-connection field correctly attributes it to Harry.
The proposed repair itself attributes the comeback to Harry, although Snape's
demand for respectful address remains implicit. A passing verifier is still
fallible; #8 must inspect accepted explanations and their evidence rather than
treat the pass field as proof.

The RCA control exposes a different cost: a hard evidence-count rule can defer
a correct answer even with two clear, high-scoring explanations. That is a
coverage loss caused by the current requirement, not a demonstrated answer
defect. Preserve this distinction when assessing fresh deferrals; this smoke
test did not change the frozen three-comment rule.

### Resume and preservation checks

The live run deliberately stopped after two calls. Resuming added 14 calls and
left the earlier responses and requests byte-for-byte unchanged. A subsequent
offline replay used a client that would fail on any attempted provider call:
it made zero calls and reproduced every artifact byte-for-byte, including the
report, requests, responses, cases, plan and assets (excluding the run lock).
The corpus database, review events, reassessment feedback and historical examples
also retained their original hashes. Human labels matched the frozen controls;
reviewer notes were absent from all model requests.

**All 415 tests passed**, including 26 admission-pilot cases covering generation,
bounded repair, editorial failures, human disagreements, missing evidence,
published-copy versus unpublished-copy routing, budget exhaustion, fatal
provider stops, checkpoint continuation, mid-request interruption, response
tampering and recovery after a response was saved but its pending marker remained.
Actual interruption during a provider request was tested with a simulated
cancelled request; the live experiment stopped between requests.

## Fresh batch assessed in #8

The 100-candidate June 20–26 inventory is frozen with the integrated policy and
a **$1 admission-model cap**. The completed run made 195 Luna calls for
**$0.2331608**, yielding 43 automatic accepts, one rejection and 56 deferrals.
See the [fresh-batch assessment](backfill-pilot-results.md) for inspection,
coverage, costs and the decision to revise checks before expanding.

| Readiness | Candidates |
| --- | ---: |
| Ready for model checks | 54 |
| Evidence/source shortfall only | 26 |
| Unresolved duplicate match only | 14 |
| Both shortfalls | 6 |
| Total | 100 |

Thus 32 candidates have preflight shortfalls and 20 have unresolved duplicate
matches, overlapping on six: **46 deferred before model spending**. Of the 54
eligible candidates, 43 were accepted, one rejected and ten deferred in later
checks. All 100 remain in the report denominator. The early duplicate
holds include known retrieval false alarms; conservative deferral loses coverage
and is not a finding of intrinsic unsuitability.

Local artifacts:

- `data/backfill/admission-controls-v1`: frozen controls, requests, responses and
  final report; experiment
  `6625a64efef6230443505c8cc71cd2e6268c51b02504398dba4ef5c8e2fa1cd9`.
- `data/backfill/admission-june20-26-v1`: frozen fresh cases/assets/plan and completed results;
  experiment `693a5150d40e61b740c85048211686e658bdc04949cde678a36106a9f7a1de61`.
- `data/backfill/admission-analysis-v1`: checkpoint snapshots, file hashes,
  offline replay verification and separate assistant inspection notes.
- `data/backfill/admission-june20-26-analysis-v1`: fresh assessment, casebook,
  separate inspection notes and identical zero-call replay verification.

Implementation and results remain in local, unpushed commits. Raw artifacts stay
ignored. #7 completed integration and the control exercise; #8 completed the
fresh assessment. Follow-ups #16 and #17 address specific quality and duplicate
gaps before a chronological-expansion decision.

## Commands

All raw artifacts remain in ignored local `data/` directories.

```sh
uv run --no-sync python -m basedbench.pipeline.admission_pilot prepare-controls \
  --output data/backfill/admission-controls-v1 --budget-usd 0.25
uv run --no-sync python -m basedbench.pipeline.admission_pilot run \
  --output data/backfill/admission-controls-v1 --budget-usd 0.25 \
  --stop-after-new-calls 2
uv run --no-sync python -m basedbench.pipeline.admission_pilot run \
  --output data/backfill/admission-controls-v1 --budget-usd 0.25
```

Prepare the fresh batch without making paid calls:

```sh
uv run --no-sync python -m basedbench.pipeline.admission_pilot prepare \
  --inventory data/backfill/inventory-june20-26-v1 \
  --duplicates data/backfill/duplicate-audit-v1 \
  --output data/backfill/admission-june20-26-v1 --budget-usd 1.00
```

Issue #8 ran that prepared batch with the same `run` command and its frozen
`--budget-usd 1.00`, then inspected admissions, exclusions, deferrals, coverage
and cost. Replaying the completed run makes zero model calls. The report is a
development artifact; its accepted rows are not a published benchmark release.

## Limits carried into the fresh assessment

The answer workflow has known overreach and shared verifier errors. The content
check has false deferrals and lacks adequate negative controls for several
categories. Duplicate retrieval has same-topic false matches, uncertain family
boundaries and missing/animated-image gaps. Holding such pairs reduces coverage;
it is not proof that they are bad memes, and it need not create a mandatory human
review queue. Revisit semantic links using supported fresh answers when practical;
this first bounded policy defers the current unresolved links.

The June 20–26 source batch has missing images, partial comment threads and a
community-discovery refusal. Preserve all 100 outcomes and the source gaps.
Controls and historical text have already been used for development; the pilot
cannot claim untouched evaluation data. The eventual release/split design still
needs family and exposure accounting.
