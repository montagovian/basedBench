# Data-led Jev optimization groundwork

September 24, 2026. [Issue #40](https://github.com/montagovian/basedBench/issues/40).
Follow-up to #38; that issue remains open for human review.

## Problem and deliverable

The user proposes GEPA / optimize_anything and asks for deeper engagement with
actual data. The prior fixed 48-question architecture is cheap but trades repair
recall against false alarms. Before another search, establish what information is
missing, what signals are useful, and what an optimizer should be allowed to
change. Deliver an evidence-linked research note, a systematic local error audit,
and an executable proposal for a bounded optimization milestone. This phase uses
saved data and public documentation only; it makes no paid provider calls.

## Scope and constraints

Inspect the frozen 99 exact versions, with 94 matched known cases. Preserve all
images, original human labels/notes, prior requests/results, the review page,
production gates and release membership. Assistant classifications are hypotheses,
not additional ground truth. The existing labels are exposed development data.
Do not reinterpret an answer-quality label as source quality or benchmark fit.
Do not reuse the prior finite experiment's $5 authorization as an open-ended
optimization allowance. Human labels and review notes remain local in this phase.
No merge, publication, automatic admission or issue closure is in scope.

## Interfaces and ownership

All investigators read `data/backfill/jev-decomposition-v1/analysis/cases.json`,
`dataset/`, saved diagnostics, and the four `jev_decomposition_*` modules.
Write new private work only under `data/backfill/jev-optimization-groundwork/`.
Every case reference uses the exact `case_id`; counts distinguish versions and
known groups. Every observation distinguishes recorded human feedback, model
output, and assistant inference. All rows and unknowns remain accounted for.

- Primary: issue and plan, official research integration, image-backed case
  inspection, architecture/evaluation contracts, final recommendation and docs.
- Error-audit agent (Sol): `error-audit.json` and `error-audit.md` only. Inspect all
  repair cases and combined false alarms, including corrected versions; classify
  plausible failure causes with exact evidence and uncertainty. No code changes.
- Signal-audit agent (Sol): `signal-audit.json`, `signal-audit.md`, and its private
  reproducible script only. Inventory applicability, feature separability and
  matched changes; identify whether simple saved-signal controls expose issues.
  Any exploratory fitting is labeled in-sample or group-held-out correctly, never
  an optimized test result. No model requests or benchmark-label changes.
- Optimizer-research agent (Luna): `optimizer-research.md` only. Verify current
  official GEPA APIs, constraints, diagnostics and train/validation semantics;
  propose integration with typed Jev decisions. No dependency installation.

## Architecture to resolve

Prefer a constrained declarative candidate: Jev question texts, applicability
choices, evidence roles, routing and a small deterministic aggregation policy.
The evaluator and labels are fixed outside the candidate. Do not execute arbitrary
optimizer-generated code. Jev remains the fast typed decision model; a reflection
model proposes changes offline. Compare a prompt-only seed against structural
changes so search does not hide which component helped. Input observation quality
and inference from comments require separate diagnosis.

Local evaluator outputs must include per-class decisions, abstentions, errors,
version-to-group mapping, corrected-pair behavior and cost. Training diagnostics
may carry exact failure evidence only if a future paid run explicitly authorizes
its provider and payload; no validation/test note can enter reflection. An API's
validation set is part of adaptive selection, not an untouched final test.

## Work packages and acceptance

1. Read relevant roadmap, issues, results and current official sources.
2. Open a scoped successor issue before any implementation or paid optimization.
3. Independently audit all known errors, diagnostic signals, and optimizer APIs.
4. Visually inspect a complementary set of images with answer, source comments,
   exact human note and Jev decisions side by side; do not rely solely on the
   previous three showcase cases.
5. Integrate findings into a concrete candidate contract, controls, metric,
   family-separated evaluation, finite budget estimate and stopping rule.
6. Record the reproducible artifacts and recommendation; keep #38 open. A paid
   launch requires a concrete model, input payload, maximum cost and approved
   scope. Finish groundwork without waiting for that decision.

Acceptance is a useful milestone: specific evidence about the data and an
implementable search design, rather than promises that an optimizer will improve
numbers. Check every aggregate against frozen files and inspect exact versions.
Link primary sources and report API-version uncertainty. Run appropriate tests
only if production code changes; verify no frozen artifacts were altered.

## Provisional experiment hypotheses and decision rule

Hypothesis: separating applicability, evidence relevance, required joke connections
and actual answer coverage produces more useful Jev decisions than generic
presence/absence questions, and reflective optimization can find a better policy.
Controls: frozen broad image-aware check, frozen combined model, and unchanged
seed evaluated on identical inputs. Optimize repair detection subject to ready
retention and useful coverage; report all three, not raw accuracy alone. Treat
corrected answer pairs as diagnostic evidence, keeping each family together.

Freeze a finite candidate/evaluation budget and independent final evaluation
before search. Proposed starting ceiling is $5 across reflection and Jev, with no
image-helper reruns, but this is a proposal rather than authorization. Stop at the
cap, maximum search count, unresolved provider usage, or a decisive evidence
bottleneck. A promising candidate must improve repair detection without worsening
ready-answer rejection on the held-out comparison; abstaining on everything
cannot qualify. Quantify small-sample uncertainty and inspect changed decisions.
Promotion still needs independent human-reviewed evidence.

## Bounded offline calibration control

The exact frozen-score frontier reveals a possible cutoff opportunity that a
coarse grid missed. Before attributing any future gain to GEPA, run one local
calibration control with a predeclared protocol. Keep the five saved outer folds,
the original feature columns, C=0.1 logistic model, scaling and family weights.
Inside each outer training set, use three group-separated inner folds (seed 4001)
to obtain calibration scores. Choose a cutoff that maximizes caught repairs
subject to retaining at least as many training ready versions as the native broad
check; tie-break on ready retention, then proximity to 0.5. Refit on outer training
data and apply that cutoff once to its outer test fold. Assert every inner/outer
group boundary; no outer-test outcomes may choose its cutoff. If an inner split
lacks both training classes, report that fold as uncalibrated with the frozen 0.5
cutoff. Report results as exposed-development evidence, not an unseen test.

The signal agent owns separate `threshold-control.py`, `.json`, and `.md` under
the new private groundwork directory. This is one zero-provider-call baseline,
not an open-ended threshold/regularization search. Compare original outer 0.5
scores to the frozen outputs to verify the refit matches before interpreting
calibration. Do not replace the original results or select a rule post hoc from
the outer outcomes.

## Groundwork completion

The [findings](jev-optimization-findings.md) integrate the complete 34-version
error audit, all-case signal audit, seven direct image inspections, and verified
release-compatible GEPA API research. The one nested calibration control restores
three ready answers and catches one additional repair versus the frozen combined
model, reaching 64/77 and 7/17. The added repair has an ambiguous-ground-truth note;
the result still falls short of broad ready retention and separates only one of
six matched correction pairs. No further calibration variants were tried.

Both private scripts regenerate byte-identical outputs. Refit outer probabilities
match the saved scores exactly. Five frozen manifests verify 1,779 file entries,
including source records and the original/current review analyses. No provider
calls, package installations or production source edits occurred. The next
milestone is the constrained adapter/evaluator implementation and a separately
authorized finite search; #38 and #40 remain open for human review.
