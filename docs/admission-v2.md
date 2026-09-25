# Duplicate evidence integration into admission v2

Issue [#19](https://github.com/montagovian/basedBench/issues/19).
Predeclared September 22, 2026. Local integration following
[#17](duplicate-comparison-results.md), with **zero paid calls**. The experimental
claim checker is not promoted by this work.

Completed: [offline replay results](admission-v2-results.md).

Build an explicit versioned admission wrapper around the frozen v1 evaluator.
Merge the original full-audit evidence with the additional image-window retrieval
and the union of both semantic views from the completed local comparison. Keep
retrieval scores separate from adjudication, published membership and human
judgments. New crop/semantic links remain candidates; they never select keepers
or establish redundancy by themselves. Preserve original exact identity evidence.

This integration uses the measured retrieval artifacts: expanded image coverage
is the 56-post packet, while semantic queries cover 52 packet records against the
2,634-record text pool. It does not claim a new full-corpus crop audit. Record
coverage explicitly for every candidate. No old evidence is removed, including
TF-IDF links or the possible family link lost by text replacement.

Replay the frozen 100-candidate pilot through the new duplicate routes and
unchanged content/answer/suitability evaluator, using only its original raw calls.
Verify each reused request/input and record source hashes. A missing required
historical call must defer without network access. Report route/outcome changes,
inherited answer-check limitations and zero new spending. These are counterfactual
development outcomes, not a fresh quality evaluation or newly human-validated set.

Acceptance checks: the bordered pair now has a candidate link and cannot pass as
unchecked unique; prior evidence and recorded families survive; template/topic
scores cannot become confirmed copies; published exact copies remain distinct
from unpublished counterparts; human disagreements and missing/animated assets
retain their guards; replay is identical and makes zero provider calls.

Keep v1 runs, database, feedback and unrelated app/test edits byte-identical.
Write only a new local run, supporting code/tests and an integration report.
No representative selection, split mutation, release publication or automatic
chronological expansion is part of this integration.
