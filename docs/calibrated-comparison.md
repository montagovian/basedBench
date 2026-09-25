# Bounded comparison after human calibration

September 22, 2026 · [Issue #21](https://github.com/montagovian/basedBench/issues/21).
**Complete; [results and next decision](calibrated-comparison-results.md).**
The experiment used 209 calls for $0.22198508, with no API/validation errors;
neither challenger is promoted. Depends on the
[50-case human calibration](explanation-calibration-results.md). The approved total
ceiling is **$10**, covering all new model calls, retries and failures in this
comparison. Preparing the human review spent $0. Existing experiments remain
frozen; #18's quote-heavy variant is not being promoted.

## Hypotheses and conditions

Human feedback will distinguish actual explanation defects from preferences for
more detail. Removing brittle exact-quotation bookkeeping may improve reliability
without a larger model; a stronger model may add value on reference decoding,
competing interpretations or substantive source support. Test these separately:

| Condition | Purpose |
| --- | --- |
| GPT-5.6 Luna, existing checker | Preserve the inexpensive baseline and its concrete failure cases. |
| GPT-5.6 Luna, simpler checking interface | Measure the interface change at fixed model. |
| GPT-6 Luna, same simpler interface | Measure the newer model at fixed instructions and evidence. |

Luna remains the default. Before the first paid call, record the exact model IDs,
current prices/availability, reasoning settings, prompt/schema hashes, image
handling, input/output limits and worst-case per-request cost. Select one stronger
condition within the approved ceiling; do not conduct an unbounded model search.
The prior restriction on further GPT-5.5 curation calls still applies; this plan
does not assume that model. No stronger-model price or performance claim is made
before verification.

The simplified interface should capture the verdict, a concrete missing/wrong
connection if present, a concise rationale and supporting comment IDs. It should
allow uncertainty about interpretation or evidence without inventing intent.
Avoid exact prose-span/quote identity requirements. Validate structure and IDs;
retain technical failures separately from semantic judgments. Do not loosen the
meaning of substantive support to make a check pass.

## Stages and ceilings

1. **Development screen, at most $3:** after the human snapshot is frozen, run
   all three conditions on the original answers of the 50 calibration cases.
   Select ten cases by a predeclared, family-aware rule spanning ready, defective
   and unresolved examples; repeat each condition once on these to measure
   instability. Up to 180 calls. Report targeted and random strata separately.
   This remains exposed development performance, even with new human labels.
2. **Fresh validation, at most $6:** freeze recipes and a new 30-case sample,
   grouped away from calibration/review families, before viewing outputs. Use
   the existing Luna baseline and the most informative surviving challenger.
   Allow up to 30 generation calls if needed, 60 paired checks and ten total
   one-shot repair attempts, each followed by fresh verification: up to 110 calls.
   Source/asset failures remain in the sample accounting, without replacement.
   Human inspection of fresh outputs must be blinded to condition when comparing
   them. If fresh human labels are unavailable, report routing and case findings
   only; do not call model agreement an accuracy result.
3. **Reserve, at most $1:** at most ten explicitly logged retry/continuation
   calls. Never retry a valid answer just to obtain a preferred verdict. Technical
   failures, unknown billing and incomplete work remain in the report.

Total: at most **300 calls and $10**, whichever stops the run first. The priced
request plan can reduce sample sizes before execution if these bounds cannot
cover the selected model. Never exceed the total cap, silently enlarge it, or
charge a partially started batch as free. Reserve conservative cost before each
request; stop new work when usage/cost is unknown until reconciled. Persist every
request, result and provenance for zero-call replay. No paid call begins while
the initial human calibration is pending.

## Readout and next decision

Measure material-defect detection and defective answers allowed through;
human-ready retention/false alarms; technical error and repeated-verdict rates;
repair success on human-confirmed defects versus unnecessary rewrites; and
actual cost per human-usable unique item. Keep missing assets, source-support
holds, content exclusions and duplicate deferrals separate. Do not infer usable
items from checker pass counts alone. Do not pool conditional calibration and
fresh admission samples or count duplicates as independent successes.

Inspect every disagreement on the small fresh sample, including any originally
ready answer that the challenger rejects. Credit repairs only against human
judgments of the actual answer, with both-acceptable allowed. Preserve sample
sizes and uncertainty rather than suggesting a low error rate is certified.

A useful outcome may be a cheaper reliable interface, selective escalation for
specific confirmed defects, or evidence that the remaining bottleneck is source
support. Choose the next backfill step from that tradeoff. A model-only win,
extra verbosity or success on exposed examples alone does not authorize automatic
publication or establish generalization. Negative results still complete the
bounded experiment and should be recorded on its issue.

## Frozen execution details after the GPT-6 Luna update

The user explicitly requested investigation of GPT-6 Luna after completing the
review. Current official [GPT-6 Luna documentation](https://developers.openai.com/api/docs/models/gpt-6-luna)
and [pricing](https://developers.openai.com/api/docs/pricing), checked September
22, list standard prices of $0.10 input, $0.01 cached input, $0.125 cache writes
and $0.50 output per million tokens. The
[GPT-5.6 Luna page](https://developers.openai.com/api/docs/models/gpt-5.6-luna)
lists $0.20/$0.02/$1.20 for input/cached/output and cache writes at 1.25 times
input. Both exact model IDs returned successfully from this account's read-only
models endpoint. GPT-6 Luna supports image input and structured output through
Responses. Performance remains an experimental question.

The third arm now tests a **model-version upgrade**, superseding the earlier
unspecified stronger-model condition. Keep three conditions and the original
phase/total caps. This run does not measure a more expensive capacity tier.

`data/backfill/calibrated-luna-dev-v1/` freezes all 50 human-reviewed originals,
177 requests, the feedback snapshot identity, code/prompt/schema/input hashes,
prices and bounds. One 49-frame GIF is an input hold for all arms, without
silently choosing one frame or replacing it. The other 49 cases receive three
checks; ten family-distinct cases (five ready, four repair, one unclear) receive
one repeat per condition. Counts retain the animated item; static-only metrics
must disclose that exclusion.

All conditions use `reasoning.effort=medium`, high-detail image input, a 2,400-token
output cap, standard service, no tools/browsing, no automatic retries and at most
three concurrent requests. Human labels/notes and alternate answers are excluded
from request payloads. The simplified schema separates answer adequacy from
substantive comment support; combined acceptance still requires both. Report
combined-gate results alongside separate adequacy findings, since the old schema
is not a fully separate human-readiness check.

The published vision table does not yet specify GPT-6 Luna's image multiplier.
For each GPT-6 request, reserve the entire documented 1.05M context at the
higher long-context cache-write rate, plus the full output allowance; actual
usage releases the excess reservation. GPT-5.6 retains its established image
bound. Unknown usage, unexpected cost or a fatal provider error stops new work.
No assumptions about cached-input savings are needed to stay within the cap.

The fresh phase started after the screen settled, with recipes and sampling
frozen before output inspection. Broader exposure/family screening held 14 of
the 30 preselected cases without replacement; the remaining 16 received paired
checks. The newly confirmed monitor and police/curfew families were included in
the retrieval references. The [result report](calibrated-comparison-results.md)
records all denominators, disagreements, costs and remaining limits. No fresh
human labels, new repairs or expansion decision are inferred from model passes.
