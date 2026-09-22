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

Issue #8 runs that prepared batch with the same `run` command and its frozen
`--budget-usd 1.00`, then inspects admissions, exclusions, deferrals, coverage and
cost. The report is a development artifact; its accepted rows are not a published
benchmark release.

## Limits to carry into #8

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
