# Focused explanation-connection experiment

September 22, 2026 · [#22](https://github.com/montagovian/basedBench/issues/22).
Follow-up to [#21](https://github.com/montagovian/basedBench/issues/21),
approved by the user's instruction to proceed with the focused next step.

## Question and comparison

Can GPT-6 Luna detect required decoding and visible referents while accepting
concise answers that already get the joke? Compare the frozen #21 simpler
prompt with one revised connection-audit prompt and schema, on the same model,
image, comments and original answer. No human notes, labels, alternative answers
or case-specific hints enter either request. The revised prompt enumerates
necessary connections, ties them to visible cues, and records what the written
answer supplies. Before demanding more detail, distinguish a missing meaning
from repetition of an already explicit visual setup or optional proper name.
Comment-only rebuttals and riffs cannot become the image's intended payoff.

This is one combined prompt/schema intervention, not an ablation separating
those effects. It does not change source support, suitability or admission.
No exact-quotation bookkeeping is added. Both conditions use medium reasoning,
high-detail image input, standard service, no tools and a **4,000-token output
cap**. That shared cap is larger than #21's 2,400 to accommodate the additional
structured findings; compare the concurrently rerun baseline, not only old
outputs. No new generation or repairs are included.

## Frozen diagnostic sample

Twenty previously exposed cases, with distinct currently known families:

- Nine human repair originals: quiz names `1ueh8cd`, closet face `1tzz3h1`,
  XM8 contrast `1udvihp`, Latin `1u0jo8z`, Resident Evil 4 `1u9z5ho`,
  Harry Potter `1mksov2`, state puns `1ucl7ul`, Freddie Mercury `1jley2r`,
  R.E.M. `198kcl9`.
- Six human-ready originals: Sonic/Minecraft `1fpageg`, domino `1j5w6z3`,
  dog supplement `1ubuulz`, algae `1ue3n4g`, sub-5 `1ubvmoj`,
  decoded rebus `1ucsgt3`.
- Five assistant-inspected disagreements from #21: Cameron Diaz `1tyza96`,
  Kevin Rose `1u9gb85`, Fahrenheit `1u8dptp`, Canadians/cans `1u2ywbz`,
  ladder `1tyxtkk`. These have **no human labels** and are stress cases only.

Repeat both conditions once on quiz names, closet face, XM8, Sonic/Minecraft,
domino and the rebus. All selection precedes new outputs. Thus **52 calls
maximum and a $1 total cap**, including failures. No automatic retries,
replacement cases, prompt changes, extra conditions or budget expansion.

The [current official Luna page](https://developers.openai.com/api/docs/models/gpt-6-luna)
was checked September 22: standard prices remain $0.10 input, $0.01 cached,
$0.125 cache writes and $0.50 output per million tokens. Use the existing
conservative full-context reservation ($0.2655 per request at the shared cap),
at most three concurrent calls, settle actual usage, and stop new dispatch on
unknown usage, fatal provider error or cost violation. Freeze input/request/code
hashes and verify old artifacts before starting. Work remains local under a new
ignored `data/backfill/` directory; never rewrite prior calls or feedback.

## Predeclared readout and stopping rule

Report separate adequacy and combined source-gate findings, all counts and
repeats, cost, errors and every changed judgment. Original human strata and
provenance stay available; this selected diagnostic set is not an accuracy
sample or an independent holdout. Never convert assistant stress findings to
human gold. Report whether the following development criteria all hold:

1. The revised checker flags all three primary misses (quiz, closet, XM8) on
   both their first and repeated checks, with a concrete matching rationale.
2. It retains all six human-ready originals and all three repeated ready
   checks on **answer adequacy**, regardless of legitimate support holds.
3. It flags at least eight of nine human repair originals on the first check.
4. No technical errors or unknown spending; at most one adequacy flip across
   six repeats, and no more such flips than the concurrent baseline.
5. Separate assistant inspection finds no invented image payoff in the five
   stress cases, particularly no Fahrenheit/Celsius role reversal. This remains
   an inspection criterion, not a new set of human labels.

Inspect rationales as well as labels; a correct verdict with a spurious reason
does not establish the intended fix. Stop after this comparison regardless of
outcome. A successful screen would justify a separately planned broader
validation; a failure should identify the residual limit rather than launch
another unplanned prompt search. Neither result authorizes expansion of #9.
