# Companion plan: tag vocabulary and assignment

Prepared September 18, 2026. Status: proposal; no taxonomy changes or automated
tag assignments have been applied.
Parent: [automated curation and backfill](automated-backfill-plan.md).
Related: [classifier experiments](classifier-experiments-plan.md).

## Objective and relationship to the backfill

Develop a useful, reproducible vocabulary for describing BasedBench items and
apply it automatically. Tags should help inspect coverage, understand failures,
and compare releases. They initially provide diagnostics; they do not determine
admission, difficulty, or leaderboard weighting.

Vocabulary discovery and classifier development can begin alongside historical
curation work. The first backfilled release does not depend on completing a
comprehensive taxonomy. Any later use of tags to control selection is a separate
versioned policy change with its own evaluation.

The benchmark remains about getting the joke. Mechanism tags describe what must
be understood, such as a sound-alike substitution or ironic implication. They do
not require a theory of why humans feel amused or a rating of meme quality.

## Starting material

The September 18 local inspection found 26 tag definitions, 198 assignments
across 126 memes, and no populated tag descriptions. Existing tags include
`phonological`, `music-reference`, `dot-connecting`, and `vision-reasoning`, as
well as editorial and model-performance annotations.

These are useful seeds, not a complete annotation set. Preserve their names,
assignments, notes, and provenance. Do not silently rewrite their meaning or
assume that every legacy tag belongs in the automated vocabulary.

An unassigned tag is **unknown**, not automatically false. A person may have
tagged only an interesting aspect of an item. This distinction applies both to
training and evaluation: treating every missing assignment as a negative would
manufacture incorrect supervision.

## Two separate jobs

1. **Vocabulary discovery:** identify useful distinctions, name them, define
   their boundaries, and decide which deserve stable categories.
2. **Assignment:** determine which defined categories apply to a particular
   target using specified evidence.

A fixed-output classifier handles an established vocabulary. Adding a category
usually requires updating and training its output layer. Label-conditioned
models such as GLiClass or Jev can receive revised descriptions at inference,
but a new description does not automatically imply reliable classification.
[GLiClass](https://github.com/Knowledgator/GLiClass),
[TypeSafe primitives](https://docs.typesafe.ai/primitives)

An encoder can discover groups and retrieve similar examples. A generative model
can propose names and definitions. Use these capabilities together rather than
expect a conventional classifier to invent its own new output classes.

## Proposed vocabulary structure

Use multiple dimensions, with multiple labels allowed where appropriate. The
following is an initial proposal, not a replacement for the existing tags:

| Dimension | Illustrative labels | Assignment target |
| --- | --- | --- |
| Reference domain | Music, television, gaming, history, current events | Meme item |
| Understanding required | Phonetic decoding, visual recognition, connecting multiple clues | Meme item |
| Joke mechanism | Wordplay, irony, literal interpretation, expectation reversal | Meme item |
| Prediction failure | Wrong reference, missed visual detail, confabulation | Specific model prediction |
| Comparative outcome | All models passed, a named model regressed | A defined evaluation run or comparison |

For example, an item might receive `music-reference`, `phonological`, and
`dot-connecting`. These labels need not compete. Define exclusive categories
explicitly when a dimension actually requires them; otherwise score each tag
individually rather than force all tag probabilities to sum to one.

Keep named entities and sources in separate fields: a show, song, character, or
event need not become a permanent top-level tag. Likewise, keep editorial
annotations such as personal favorites distinguishable from operational labels.
Depth or obscurity labels need a defined reference population before they can
support claims about difficulty.

Outcome labels must not be inferred solely from meme content. Their target
includes the relevant prediction, model, scoring version, and run. They must not
leak into an item classifier that is meant to operate before prediction.

## Milestone T1: inventory and define a seed vocabulary

Export a local inventory of current definitions, assignments, notes, and counts.
Reuse the curation corpus's family groups and partitions where possible. Use only
development material to create examples and tune definitions; keep evaluation
items out of retrieval examples and discovery.

For each candidate tag, create a versioned specification with:

- A stable identifier, display name, dimension, and assignment target.
- A precise definition and inclusion/exclusion criteria.
- Positive examples and nearby counterexamples, with their provenance.
- Required evidence: text, image, source context, or prediction/run results.
- Aliases, parent relationships if useful, and incompatible labels if applicable.
- Status: proposed, active for automated use, or retired.

For `phonological`, a proposed boundary is that getting the joke requires
recovering meaning through pronunciation or similar sounds. A straightforward
reference to a song does not qualify merely because it involves music. Keep
definitions such as this provisional until tested against examples.

Propose mappings from legacy tags to the new dimensions. Preserve unmapped or
ambiguous legacy annotations. Model-generated explanations of why a human added
a tag remain inferences, not original annotations.

**Deliverable:** a seed vocabulary and legacy mapping proposal, with an explicit
account of which assignments can support evaluation.

## Milestone T2: discover gaps without generating endless synonyms

Compare two discovery methods on development data:

| Method | Procedure | What to inspect |
| --- | --- | --- |
| Example-driven generation | Sample varied items, propose recurring distinctions, then consolidate definitions | Unsupported distinctions, synonyms, and boundaries that cannot be applied consistently |
| Embedding-assisted discovery | Cluster or retrieve related items, inspect representative examples, then extract or generate names | Groups driven by subject, template, or explanation style instead of useful evaluation distinctions |

BERTopic is a candidate for embedding-assisted discovery. It combines embeddings,
clustering, and topic representations and supports optional generative naming.
Its clusters are proposals for inspection, not an authoritative taxonomy.
[BERTopic](https://maartengr.github.io/BERTopic/index.html)

Discover dimensions separately. A cluster about SpongeBob may describe a
reference domain, while the useful capability distinctions cross that cluster:
recognizing a scene, interpreting an expression, or recovering a quoted phrase.
If generated summaries help isolate those aspects, retain the source evidence
and account for errors introduced by the summarizer.

For each proposed addition, collect representative evidence, possible aliases,
nearby counterexamples, and the reporting question it would help answer. Evaluate
recurrence, distinctness from existing tags, and stability under resampling or
paraphrasing. Frequency alone should not erase rare but meaningful phenomena.

Limit proposed additions per iteration and freeze a vocabulary version before
assignment evaluation. Low-confidence assignments are not by themselves evidence
for a new category: the cause may be poor definitions, missing evidence, or a
classifier failure.

**Deliverable:** a bounded vocabulary revision with reasons for additions,
merges, and retained distinctions. Automated proposals can remain provisional
without holding up backfill processing.

## Milestone T3: apply tags and evaluate assignment

Start with existing examples and label-conditioned classifiers. Compare an LLM,
GLiClass, and Jev on the same definitions and evidence. Use the companion
classifier harness; do not assume the winner on admission will also win on tags.

Test frozen embeddings or SetFit for established tags when trustworthy positive
and negative examples support training. A label with one positive example and
no explicit negatives does not support a credible supervised comparison.
Pseudo-labels may expand development data, but must remain separate from human
or independently established evaluation references.

Store at least the target ID/version, tag ID/version, assignment state, evidence,
model/prompt version, provenance, and a score where available. Distinguish:

- **Present:** supported by supplied evidence.
- **Absent:** explicitly assessed and found not to apply.
- **Uncertain:** assessed, but evidence or the decision is unresolved.
- **Not evaluated:** no assessment exists.

Keep technical errors separate. Missing image access must not become a confident
negative for a visual tag. Thresholds should be calibrated per tag when the
reference data permits; raw model scores and a universal 0.5 cutoff are not a
validation strategy.

Evaluate assignment quality separately from vocabulary usefulness:

| Evaluation | What it establishes |
| --- | --- |
| Per-tag precision and recall on explicitly assessed references | Assignment correctness where both presence and absence are known |
| Macro and micro summaries, with counts | Whether common tags conceal poor performance on rare ones |
| Coverage and abstention by tag and slice | What fraction receives a supported decision |
| Repeat/paraphrase consistency | Stability of a classifier's decisions, not independent correctness |
| Redundancy, distinctness, and evidence coverage | Whether the vocabulary adds useful distinctions |
| Reporting utility | Whether tags expose meaningful coverage gaps or interpretable performance differences |

On sparse legacy positives, report known-positive recovery and unknown coverage;
do not claim full precision or recall over the corpus. If no new human labels
are collected, additional automated evaluation can establish consistency and
model agreement, but cannot independently establish true tag accuracy. Keep
that distinction visible in the report and assignment provenance.

**Deliverable:** a frozen vocabulary, versioned assignments, and a report that
distinguishes validated findings from exploratory automated labels.

## Milestone T4: controlled evolution during backfill

Keep the active vocabulary fixed during a batch or release. Accumulate recurring
uncovered patterns and candidate tags locally. At a bounded revision point,
compare proposals against existing definitions and assess supported coverage,
distinctness, and stability using development data.

Automated rules can promote a candidate to the next operational vocabulary when
the specified evidence is available; otherwise leave it provisional. Promotion
means adoption of a schema definition, not proof of independently validated tag
accuracy. It does not create a mandatory human approval queue.

Keep stable IDs and aliases for renames. Meaning changes require a new definition
version and fresh assignments. Preserve retired tags and historical assignments
so old reports remain reproducible. When comparing releases across a changed
vocabulary, remap or reassess both under a common version and disclose the scope.

The current `tags` and `meme_tags` tables support names, descriptions, notes, and
item associations. Implementation will need explicit vocabulary/assignment
versions, provenance, and prediction/run targets. Design that extension before
writing automated results into the legacy annotations.

**Deliverable:** a repeatable vocabulary revision procedure and diagnostic tag
report for each backfill batch. Initial tagging failures remain outside the
critical path for admission.

## First implementation package

1. A read-only tag inventory and export under `data/`.
2. A seed specification format and a small set of well-defined candidate tags.
3. A bounded discovery report with evidence-backed proposed additions.
4. Assignment adapters using the common classifier result contract.
5. A report covering partial labels, uncertainty, provenance, and versions.

Keep raw examples, notes, assignments, and discovery outputs in local working
data. Any future public tag export should use defined dataset-facing fields and
follow the existing release artifact policy.
