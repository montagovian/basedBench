# Small model-capacity comparison

September 22, 2026 · [#23](https://github.com/montagovian/basedBench/issues/23).
User-approved follow-up to the completed
[focused screen](focused-connection-results.md).

## Question and frozen conditions

Does GPT-6 Sol improve the concrete misses, ready-answer retention and judgment
stability of GPT-6 Luna when the checker instructions and evidence are identical?
Use the existing **simple** checker from #21/#22 for both models. The failed
connection-audit prompt/schema is not part of this comparison. Change only the
model ID between paired requests: `gpt-6-luna` and `gpt-6-sol`.

Reuse exactly #22's 20 exposed original cases: nine human repair originals,
six human-ready originals and five assistant-inspected cases without human
labels. Keep the same six repeat identities (quiz names, closet, XM8,
Sonic/Minecraft, domino, decoded rebus). This produces **52 calls maximum**,
26 per model. Rerun Luna concurrently as the comparison baseline; old responses
remain historical evidence. No new case selection, human judgments, repairs,
answer generation or broad validation is included.

Both models receive medium reasoning, high-detail images, standard service,
the same simple structured output, a 4,000-token output limit, no tools and
no automatic retries. Only original image, comments and answer enter requests.
Human labels/notes and alternate answers remain absent. Source support stays
separate from adequacy, and the three-substantive-comments rule is unchanged.
Do not optimize suitability or turn assistant flags into human gold.

## Prices and stopping rules

The official [Sol model page](https://developers.openai.com/api/docs/models/gpt-6-sol)
and [pricing page](https://developers.openai.com/api/docs/pricing), checked
September 22, list standard Sol input/cached/write/output rates of
**$2/$0.20/$2.50/$10 per million tokens**. Corresponding Luna rates are
$0.10/$0.01/$0.125/$0.50. Long prompts above 272K tokens cost twice the input/
cache rates and 1.5 times the output rate. Account metadata access is checked
before inference. Both models support image input and structured output.

The hard ceiling is **$10 total**, including every attempted call and failure.
Scaling the preceding simple-Luna run's usage suggests about 40 cents for this
comparison; actual usage may differ. The current vision multiplier table omits
these two new models, so reserve the entire documented 1.05M context at the
long-context cache-write rate plus maximum output: **$5.31 per Sol request**
and **$0.2655 per Luna request**. Release the excess only after usage settles.
The budget permits at most one such Sol reservation at a time, with at most
three total concurrent requests. A conservative reservation can stop the run
before actual spending reaches $10; retain that coverage shortfall, if any.

Freeze inputs, requests, prices, sample, code and criteria before calls. Stop
new dispatch on unknown usage, a fatal provider error or an allowance violation.
No retries, alternate models, prompt changes or cap increases follow an
unfavorable output. Preserve all prior artifacts, feedback and unrelated edits.
No further GPT-5.5 curation calls are authorized or needed.

## Readout and next decision

Carry forward the explicit development targets from #22:

1. Fail all three primary defects (quiz decodings, closet specificity, XM8
   contrast) on both checks, with rationales that match the actual defect and
   image. A verdict supported by a mistaken identity or invented payoff is
   not a successful fix.
2. Retain all six human-ready originals and all three ready repeats on answer
   adequacy; legitimate evidence holds remain separate.
3. Fail at least eight of nine human repair originals on the first check.
4. No technical errors or unknown costs; at most one adequacy flip across six
   repeats, and no more flips than the concurrent Luna baseline.
5. Inspect every disagreement, all primary rationales and all five unlabeled
   stress cases for invented image payoffs and inappropriate source counts.
   Keep those assistant observations separate from human evidence.

Report raw counts, original human strata, repeats, model-specific usage/cost,
all errors and any incomplete work. These selected, repeatedly exposed cases
are diagnostic development evidence, not population accuracy or a held-out
generalization result. Neither automatic pass counts nor this comparison's
agreement with human labels establishes cost per new human-usable item.

Stop after this frozen comparison, including a negative result. If Sol improves
the joint quality tradeoff, assess whether selective use warrants a separately
planned broader validation. If it does not, record the limit and choose the
next data/workflow question explicitly. No automatic admission promotion,
release publication or #9 expansion follows.
