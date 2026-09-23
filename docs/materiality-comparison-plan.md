# Narrow material-omission comparison

September 23, 2026 · [#25](https://github.com/montagovian/basedBench/issues/25)
· Follows [completed targeted feedback](materiality-boundary-results.md)

**Planned; not launched.** Test whether a prompt-only materiality change can
retain the human-ready concise answers while detecting the confirmed missing
decodings, referents and contrasts. Implement and freeze the executable recipes,
requests, provenance, prices and tests before any inference. This document does
not turn existing judgments into proof that the proposed prompt works.

## One change, same simple interface

Use `gpt-6-luna` for both conditions. Keep the existing `SimpleCheck` response
schema and parsing, original image/comments/answer inputs, medium reasoning,
high-detail images, standard service, no tools, `store=false`, disabled
truncation and 4,000 maximum output tokens. No extra connection lists, quotation
contracts, repair generation or model tier is included.

The baseline is the frozen simple checker from #23. The candidate changes only
the paragraph beginning “Pass concise paraphrases” to the following text:

> Judge semantic sufficiency, not exhaustive description. An omission is material
> when it leaves an essential decoding, relation, referent or contrast unresolved,
> or substitutes a different core joke. Before failing, check whether the written
> answer already conveys that meaning through a concise or broader faithful
> paraphrase. In your existing reason field, identify the essential meaning that
> is absent or wrong and why the written answer does not convey it. Identifying
> an unmentioned detail is not by itself a reason to fail. Do not require every
> visible cue, proper name, literal caption, secondary wording or background fact
> when the answer already supplies enough meaning to grade the intended joke.
> Your own inference of an absent essential decoding still does not repair the
> answer. A richer alternative, optional detail, familiarity, easiness, aesthetic
> taste or a theory of humor is not required. Do not claim a defect solely because
> another interpretation is imaginable. Do not assert an author's motive,
> minority embellishment, fictional accusation or joke as established fact.
> Use uncertain when an essential connection or competing core readings cannot
> be resolved.

Keep the other instruction paragraphs, including substantive comment support,
unchanged. Update only the prompt cache identity alongside the instruction
text. This isolates a materiality instruction change rather than combining it
with another schema or source-policy intervention. The candidate is derived
from human development examples, but does not include their texts, labels,
notes, case identities, preferred answers or model findings in requests.

## Fixed diagnostic sample and repetitions

Reuse all 20 #23 identities and original input bytes. Make a **new** versioned
human-label overlay for the two #24 cases; preserve old runs' unlabeled status.

- Nine repair originals: quiz names `1ueh8cd`, closet `1tzz3h1`, XM8 `1udvihp`,
  Latin `1u0jo8z`, Resident Evil 4 `1u9z5ho`, Harry Potter `1mksov2`, state puns
  `1ucl7ul`, Freddie Mercury `1jley2r`, R.E.M. `198kcl9`.
- Eight ready originals: Sonic/Minecraft `1fpageg`, domino `1j5w6z3`, dog
  supplement `1ubuulz`, algae `1ue3n4g`, sub-5 `1ubvmoj`, rebus `1ucsgt3`,
  Fahrenheit `1u8dptp`, cans `1u2ywbz`.
- Three still-unlabeled stress cases: Cameron Diaz `1tyza96`, Kevin Rose
  `1u9gb85`, ladder chain `1tyxtkk`. No assistant gold labels are added.

Repeat both conditions once on the same six #23 cases (quiz, closet, XM8,
Sonic/Minecraft, domino, rebus) and on Fahrenheit and cans. That is **28 requests
per condition / 56 maximum**, with eight repeat pairs per condition. Selection
precedes outputs; no replacement cases or selective retries. Preserve original
selection strata and the new human-review stratum in separate provenance fields.
All 20 cases are exposed development examples with distinct currently known
families; none becomes held out because it has a new human label.

## Ceiling and execution constraints

Proposed hard ceiling: **$1 total**, including attempted calls and failures.
Historical all-Luna runs suggest only a few cents; the ceiling is not a spending
target. Recheck official Luna pricing and account access before launching.
Use conservative reservations before dispatch, at most three concurrent calls,
no automatic retries, and stop new dispatch on unknown usage, fatal provider
errors or an allowance violation. Retain any resulting incomplete coverage.

Create a new local run directory and freeze plan/input/request/code hashes.
Verify that paired bodies differ only in instructions and prompt-cache identity,
and that baseline payloads retain #23's settings and evidence. The newly added
repeat payloads should match their first checks apart from bookkeeping outside
the request. Do not edit the frozen calibrated, focused or capacity runners.
Preserve both human journals, all old artifacts and unrelated working edits.

## Readout and stop rule

Judge answer adequacy separately from combined admission/source-gate outcomes.
The candidate must meet all these development targets:

1. Retain **8/8** ready originals on first check and **5/5** ready repeats,
   including both newly reviewed examples. A source-support hold is separate.
2. Flag quiz, closet and XM8 on **both checks (3/3)**, with rationales matching
   the human defect and actual image. An invented identity or a rifle-side
   reversal is not a successful fix.
3. Flag at least **8/9** repair originals on first check. Inspect reasons;
   label agreement alone is insufficient.
4. Have at most **one adequacy flip across eight repeat pairs**, no more than
   concurrent baseline, with zero technical errors or unknown costs.
5. Inspect every changed verdict, all primary rationales, source-support
   disagreements and all three unlabeled stress cases. Retain image-grounding
   errors and inappropriate comment counts separately from human labels.

Report all planned cases, missing/error outcomes, repeats, cost, rationale
limitations and original strata. Do not drop incomplete cases from denominators.
The older #23 responses are historical evidence; the concurrent baseline is
the comparison. No accuracy or cost-per-new-usable-item claim follows from
checks of these previously exposed answers.

Stop after this single comparison, including a negative result. No automatic
prompt search, extra model condition, repairs, fresh run or cap increase follows.
A promising result supports a separately designed fresh human comparison;
failure records the remaining tradeoff. Neither outcome promotes an admission
checker, changes suitability or authorizes chronological expansion in #9.
