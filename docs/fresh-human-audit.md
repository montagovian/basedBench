# Fresh human audit of cached candidate answers

September 23, 2026 · [#26](https://github.com/montagovian/basedBench/issues/26)
· User-approved follow-up to the
[materiality comparison](materiality-comparison-results.md).

## Question and boundary

Measure how many existing candidate explanations are ready to grade the joke,
which need a material correction, and which remain unclear. Stop tuning against
the same diagnostic examples. This audit creates human evidence about exact
cached answers; it does not promote a checker, generate repairs, change
suitability, publish items or authorize chronological expansion in #9.

**Preparation and collection use zero paid calls / $0.** The answers come from
existing legacy generation, not new GPT-6 Luna inference. Do not imply that
these judgments measure Luna generation quality or validate the failed revision.

## Freeze before inspection

Take all **18 remaining identities** from the original #20 eligibility ledger:
78 eligible cached June 7+ answer-bearing posts, minus the 30 random human-review
identities and all 30 identities selected for #21's subsequent fresh screen.
Exclude the entire prior selection, including its 14 held cases, not just the
16 that reached models. This is a census of that remaining conditional pool,
not a newly sampled archive-wide estimate. No answer-content or checker-outcome
inspection is used to choose the 18 identities.

Freeze the selected identities, seed, original eligibility ledger and prior
selection hashes before additional screening. Validate the source manifests,
read the database without writing it, and retain exact answer, original comment
context, generation-call provenance and image bytes. A missing/changed asset,
ambiguous generation context or newly discovered exposure is a recorded hold,
never a reason to choose a replacement.

Screen against all recorded human/evaluation cases and the selected identities
using existing local retrieval: known/transitive families, identical image or
answer content, full/trim near images, aspect crops against previous human
cases and the top 20 coarse image neighbors, and saved MiniLM links at 0.65.
Retain exposure evidence and candidate retrieval links separately; they are
conservative holds, not human duplicate labels. Include both `post_id` and
`case_id` records and actual dispatched/reference IDs in the exposure ledger.
Pool-membership listings alone are not answer review or model evaluation.
Semantic-family coverage remains incomplete; prior automated retrieval exposure
is recorded. Only unheld cases enter the fresh review gallery. Keep all 18
identities in the overall accounting, with no replacement or extra collection.

## Blinded review

Display each original image and its one untouched explanation in frozen shuffled
order. Hide generator identity, model verdicts, old labels, strata and assistant
criticism. Reuse the existing ready / material defect / cannot judge rubric.
Comments stay hidden until requested; a reveal saves a draft checkpoint before
showing them. Preserve every actual feedback revision in a new packet journal.
Never enter assistant judgments into the live human packet.

The main question is whether the explanation supplies enough meaning to grade
whether another model gets this joke. Concise and simple answers can be ready;
optional details or a preferred rewrite do not make them defective. For a
material defect, a short note naming the missing or wrong connection is useful.

Source support, usefulness/fit and duplicate concerns remain separate. Use the
optional reason and note to record them without changing answer readiness.
A ready answer does not certify three substantive supporting comments, and a
source hold does not prove a plausible explanation wrong. Unfamiliarity is not
a rejection. Do not impose a new suitability threshold or ask the reviewer to
rejudge prior accepted answers.

## Analysis after real feedback

Freeze exact human events and text hashes in a separate snapshot. Preserve
unclear, blank and partial fields; never infer a verdict from an assistant
hypothesis. Report the full 18-case selection, each hold reason, reviewable and
completed counts, ready/repair/unclear answers and pre/post-comment exposure.
Keep optional source/fit/duplicate notes literal and attribute later assistant
interpretations separately. Do not report absent optional fields as passes.

Report answer-ready yield conditional on this remaining cached pool, with
held/unreviewed cases unresolved and the reviewable-case rate separately. This
is not full admission yield: successful legacy generation, cached assets,
previous exclusions and incomplete family screening constrain the population.
Small counts are descriptive, not precise archive accuracy or proof of
unattended quality. Any overlap discovered during review remains recorded,
with its answer judgment preserved and fresh-family interpretation withheld.

The round ends after analysis of the real feedback and a concrete recommendation
about correction work or another separately scoped next step. No paid checker
comparison, prompt search, automatic repair or broader backfill follows by
default. The old frozen artifacts, human journals and unrelated app/helper-test
edits remain unchanged. Raw packets, images and feedback stay local.
