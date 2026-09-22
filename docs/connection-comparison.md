# Source-first explanation development comparison

Issue [#16](https://github.com/montagovian/basedBench/issues/16). Predeclared
September 22, 2026, before model calls. This is a separate experiment, not an
admission-policy update. Frozen runs and all human judgments remain unchanged.

## Hypothesis and fixed packet

Establishing essential joke connections, substantive comment contributions and
competing readings before inspecting an answer will expose concrete omissions
and unsupported intent without imposing a stronger taste/difficulty threshold.
Compare saved baseline answers/checks with `connection-eval-v1`. The
[selection](experiments/connection-packet-v1.json) fixes 28 cases: 22 from the
pilot and six historical controls. There are 11 pilot inspection hypotheses
(including one mechanical citation case), two evidence/task controls, nine
retention controls (including the two duplicate images), three human defect
controls and three human ready/tolerance controls. These are selected exposed
development cases; assistant hypotheses are not gold labels. The duplicate pair
is two rows but one joke. Historical annotations are copied verbatim for reporting.

First, Luna sees only the image and original comments and maps essential
connections, every supplied comment's contribution and any competing readings.
Next, it evaluates the existing proposal as written using the raw evidence and
that fallible map. Each mapped connection requires a coverage judgment, including
`not_required` for map overreach. A concrete repairable defect permits one rewrite
and one fresh check without the earlier critique/verdict. The verifier shares
the source-first map, so its errors can be correlated. No generation of an
answer for the object-only control, no model fallback, no prompt search.

The three-substantive-comment rule remains unchanged. This does not impose
three citations per fact, nor count reactions or keywords as explanations.
Neutral attribution can resolve disputes about sincerity when the mechanism is
shared. Unresolved task/evidence status is a hold, not an intrinsic rejection.
Mechanical removal applies only to bracket groups entirely consisting of known
comment IDs, with leftovers blocked from clean output. Raw prose is preserved.

## Measures and stop conditions

Report original-answer verdicts, concrete omissions/wrong decodings caught,
support/intent changes, suitability holds, retained good cases, disagreements
with original human ready labels, proposal/verification errors, repairs inspected
against the image/comments, and all costs. Do not score assistant hypotheses as
human accuracy. Report whether a hypothesis was contradicted on inspection.

The development success target is to catch all three multi-part decoding
hypotheses, avoid counting the dog-pun reaction as substantive evidence, address
both unsupported-intent hypotheses (neutral repair or justified hold), retain at
least eight of nine pilot retention rows and at least two of three historical
ready controls, and introduce no inspected material defect in a verified repair.
Task-boundary flags have no desired rejection quota. Failure of these targets is
an informative result; do not tune until they pass. Unseen evaluation is required
before any unattended admission claim.

Use **GPT-5.6 Luna only**, medium reasoning, at most 5,200 output tokens for
the map and 3,600 for subsequent calls, at most four calls/case (112 total),
**$0.25 total**. Rates are inherited from the frozen pilot accounting (20¢/million
input, 2¢ cached input, 25¢ cache-write bound, $1.20 output); these are estimates,
not invoices. Reserve conservative input/output cost before every call; unknown
usage retains its reservation. No automatic retries. Stop spending at the cap,
including if the packet is incomplete; do not increase it. A single run is planned.

## Reproduction

```sh
uv run python scripts/prepare_connection_packet.py \
  --output data/backfill/connection-packet-v1
uv run python -m basedbench.pipeline.connection_eval prepare \
  data/backfill/connection-packet-v1 data/backfill/connection-eval-v1
uv run python -m basedbench.pipeline.connection_eval run \
  data/backfill/connection-eval-v1 --budget-usd 0.25
```

Each run freezes the packet, assets, prompts, code hashes, prices, request bounds,
requests, raw responses and usage. Offline replay verifies result hashes and
reuses calls. Baseline inputs, response artifacts and human feedback are hashed
before and after. Local inspection and a results report follow the completed run.
