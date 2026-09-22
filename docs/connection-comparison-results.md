# Source-first explanation comparison results

September 22, 2026 · [Issue #16](https://github.com/montagovian/basedBench/issues/16)

**Do not promote the source-first map as an admission gate.** It supports three
useful repairs and retains the selected good examples, but still approves
undecoded wordplay, unsupported intent and miscounted evidence. The bounded
experiment is complete with a negative promotion result. Suitability hypotheses
remain hypotheses; no broader restriction on simple jokes, photos, anecdotes or
text screenshots is adopted.

The [predeclared comparison](connection-comparison.md) used 28 exposed development
cases and **92 GPT-5.6 Luna calls for $0.20008322**, about 20.0¢, within the shared
$0.25 cap. Conservative accounting was $0.20009702. There were no provider
failures, unknown-usage calls, pending requests or allowance violations.

## Versions and denominators

The first pass maps image/comment evidence before seeing the answer, then checks
the answer, permits one bounded repair and verifies it without the earlier
critique. The map remains visible to verification and can transmit its errors.
Every source hypothesis and historical human judgment stays outside model input.
The three-comment rule is unchanged; no alternative quota was tested.

The first schema allowed lists with duplicate/omitted comment IDs and renamed
connection keys. These outputs correctly became technical errors. A separately
declared schema-only continuation reran exactly the 16 cases whose final status
was error, using required keyed objects. Semantic prompts and validators were
unchanged; new responses are new samples, not a controlled semantic ablation.
Valid first-pass successes and unresolved semantic cases were not rerun.

| Run | Cases | Calls | Estimated cost | Final statuses |
| --- | ---: | ---: | ---: | --- |
| `connection-eval-v1` | 28 | 54 | $0.11678960 | 11 model-supported, 16 errors, one evidence-only |
| `connection-schema-v2` | 16 repeated error cases | 38 | $0.08329362 | 13 model-supported, two errors, one unresolved |
| Combined selection: second version for its 16 cases | 28 | 92 total | **$0.20008322** | 24 model-supported, two errors, one unresolved, one evidence-only |

The combined selection has 21 original-answer passes, four failures, two check
errors and one case without an original proposal. Three of the failures receive
model-verified repairs. Those counts are model outcomes, not accuracy or human
approval. The duplicate retention pair contributes two rows but one joke.

## Concrete gains and misses

| Fixed development group | Result after the schema continuation |
| --- | --- |
| Three multi-part decoding hypotheses | State puns caught and repaired; quiz-team names still pass; two-cows response is inconsistent and remains an error |
| Two unsupported-intent hypotheses | Both original overclaims still pass |
| Dog-pun substantive-support hypothesis | Reaction excluded, but an unrelated side joke becomes the third supporting comment |
| Algae pun / two-comment control | New pass counts a different prison reading as shared support; baseline hold stays unchanged |
| Citation cleanup | Known ID brackets removed mechanically; meaning retained |
| Nine pilot retention rows | 9/9 original answers pass after continuation; first pass had four passes and five technical errors |
| Three historical human defect controls | 3/3 original answers fail; Freddie Mercury and Harry Potter repaired, R.E.M. remains unresolved |
| Three historical human ready controls | 3/3 originals pass after continuation; first pass passed two and challenged Sonic/Minecraft before a verifier schema error |

**State puns:** the repair explains all four sound-alike pairs and removes the
unsupported possessive claim about Mary's land. **Harry Potter:** it restores
classmates ranking the retort above heroic achievements and explains the reversal
of Snape's demand for respectful address. **Freddie Mercury:** it restores the
crowded-bed implication and the pictured reply, qualifying the infection story
as the meme's insinuation. Inspection found no new material defect in these three
verified repairs. The Freddie answer still has unnecessary wording about the old
answer; model approval does not make prose ready for publication.

**Quiz-team names:** both map and checker still accept a format-level account
instead of decoding the names. **Two cows:** the map groups national references
rather than explaining the essential individual connections, including the
Irish horse. Its checker marks capitalist variants missing while returning pass;
validation blocks that contradiction. This is a technical hold, not a successful
coverage judgment or repair.

**R.E.M.:** the checker catches the altered title imported from a commenter.
The repair removes it but misses the actual inserted person in the image's
corner. The verifier rejects a different wording flaw while calling the rest
complete. The prior answer-quality experiment had recovered this spatial detail;
the new shared map does not reliably preserve that gain.

**Intent:** the Israel/fashion answer still asserts mockery of people blaming
Israel. The sub-5 map explicitly recognizes the parody/sincerity dispute, yet
passes an answer asserting parody. A neutral shared mechanism in the map does
not neutralize stronger wording in the candidate answer. Both remain concrete
answer-attribution defects to investigate, not proof the underlying memes lack
usable jokes.

**Support:** the dog-pun map correctly excludes the “sweet summer child” reaction,
then counts a Mesa/Boogie amplifier aside toward support for the cocaine reading.
The checker calls that aside unnecessary while retaining its citation. The
candidate meaning remains plausible; the demonstrated problem is enforcement of
the frozen evidence rule. The algae example similarly promotes a competing
whole-country-prison explanation into a third supporting comment. Neither result
authorizes quietly weakening or retrospectively reinterpreting the rule.

## Suitability and retention

The historical photograph and lawsuit headline still receive strong readings
from contextual or corrective comments. Those interpretations warrant caution
about asserted intent; the experiment does not settle their intrinsic suitability.
The celebrity collage's paparazzi commonality is well supported, while its place
in a joke collection remains a separate editorial question. It is retained for
semantic-retrieval comparison, without endorsing admission. The Haaland anecdote
produces map/check disagreements in both versions and remains a technical error.
That does not establish that a simple fame mismatch requires a deeper twist.

The battery control exposes a clearer source error: the map invents a
“spicy pillow” framing from comments for an uncaptioned photo. There is no
original answer, so this branch produces no candidate. Its evidence-only status
must not be counted as a successful suitability rejection.

Retention includes reference jokes, the four-part rebus, calendar wordplay,
ordinary literature text and the children-on-phones caption. Golf and the domino
chain preserve useful tolerance for peripheral details. Sonic/Minecraft flips
from a detail demand in the first pass to a pass on the schema-only resample;
that is sampling/map variability, not proof of a semantic improvement. Its human
ready label is preserved in both. No first-pass disagreement is deleted.

## Decision and artifacts

The predeclared retention targets are met, but the decoding, intent and support
targets are not. **This full workflow does not yet merit an unseen admission
validation run.** A future narrow development change should demonstrate concrete
decoding and neutral attribution, and distinguish actual shared support from
side jokes, before freezing an unseen comparison. Keep ordinary useful items;
do not substitute stricter taste judgments, a larger model, an optimizer or a
human-review backlog for these defects. Expansion in #9 remains a later decision.

Seventeen explanations with model approval and no inspected material meaning or
support defect are supplied to #17's local semantic comparison. That eligibility
is explicit development provenance, not a new gold label or release membership.

Local artifacts are `data/backfill/connection-packet-v1`, `connection-eval-v1`,
`connection-schema-v2` and `connection-analysis-v1`. The last contains all 28
assistant inspections, summary, semantic-comparison export and a read-only casebook
with original comments, both versions' raw proposals/checks and unchanged human
judgments. The casebook was checked in the browser: all 28 images load and both
versions remain visible beside the separate inspection.

Offline replay attempted **zero provider calls** and preserved all **143 first-run
files and 97 continuation files** byte-for-byte, excluding locks. The project
suite has **442 passing tests** across the sandbox run and the separately executed
localhost test. Baseline runs, corpus/feedback records and the user's unrelated
app edits are covered by the shared before/after preservation manifest.

```sh
uv run python -m basedbench.pipeline.connection_report \
  --run data/backfill/connection-eval-v1 \
  --continuation data/backfill/connection-schema-v2 \
  --inspection data/backfill/connection-analysis-v1/assistant-inspection.json \
  --output data/backfill/connection-analysis-v1
```
