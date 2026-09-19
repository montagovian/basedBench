# Companion plan: classifier experiments

Prepared September 18, 2026. Status: approved; first TF-IDF, frozen MiniLM, JEV,
and paired GPT-5.5 text/image runs complete.
See the [curation evaluation workflow](curation-evaluation.md) for implementation
and preliminary results. The current split is fixed for practice comparisons;
earlier use of reserved examples is recorded in a history audit. No tested method
has established readiness for unattended admission. JEV was much cheaper, but its
first direct admission question and both GPT variants selected mostly historical
rejections. Further adaptation and diagnostic comparisons remain pending.
Parent: [automated curation and backfill](automated-backfill-plan.md).
Related: [tag vocabulary and assignment](tagging-taxonomy-plan.md).

## Cost and model preference

Use **GPT-5.6 Luna** as the inexpensive generative comparison model for the next
experiments. Do not make further GPT-5.5 curation calls without a new explicit
request. Preserve its existing results as historical baselines.

Prioritize **JEV development** if its selection quality and useful yield are
reasonably comparable with Luna. Compare both measures at similar coverage;
matching another weak model alone does not establish admission quality. Measure
the full workflow cost, including any image interpretation supplied by Luna.

Every API run requires an explicit spending limit, reserves the maximum allowed
cost before dispatch, and keeps uncertain requests charged against that limit.
The first Luna/decomposition round has a **$1 total cap**: at most $0.10 for an
eight-example development check and $0.90 for the 80-example practice comparison.
Use standard service, bounded output, saved responses, and no automatic retries.

Compare Luna's old overall-decision prompt with its three-check text version,
then compare that text version with JEV's native three-question version. Include
a Luna image variant to measure additional visual evidence. All variants use the
same development references and target examples. The structured versions return
content-policy, joint ground-truth, and benchmark-value judgments. Code rejects
on any failed check, defers on any unresolved check, and otherwise accepts.
Do not interpret the overall historical labels as labels for individual checks.

## Decision this work should produce

Determine which model approaches can reproduce historical admission decisions
well enough to support the hands-off backfill. Compare specialized classifiers,
general classifiers such as Jev, and LLMs through the same evaluation contract.
Select a backend for each demonstrated use case rather than assume one model
should own every decision. Ground-truth construction is one task with diagnostic
checks for agreement, claim support, and image/source consistency. Separate
classifiers or API calls for these checks are experimental options, not requirements.

This expands milestone 2 of the main plan. It depends on milestone 1's frozen
corpus, label provenance, and development/calibration/test partitions. Tagging
can reuse the infrastructure, but requires its own targets and evaluation.

## Working hypotheses

A pretrained encoder may already represent much of what predicts curation:
specificity, relationships between statements, and whether an explanation
recovers a meaningful implication. A small classifier can learn how those
representations relate to the historical decisions. Fine-tuning the encoder can
adapt the representation when the necessary distinctions are missing.

That is a hypothesis about transfer from pretraining. Roughly 1,900 historical
decisions justify experiments; they do not establish that every difficult
reference or visual failure is covered.

Architecture, training objective, and input evidence are separate choices:

- An encoder is not inherently a similarity model or a classifier; its training
  and output layer determine the job.
- A decoder can also produce one label or serve as a classifier. Compare efficient
  structured decisions, not a small classifier against unnecessarily long prose.
- A classifier cannot recover visual evidence absent from its input. A generated
  image description is an additional model contribution, not direct image access.
- A flexible classification API does not establish its underlying architecture.

## Experiment sequence

Use successive rounds rather than an exhaustive combination of every model,
prompt, and feature set. Pin exact checkpoints, API model versions, prompts,
training settings, and package versions when implementing each run.

### Round 1: fixed text evidence, several ways to classify it

Build one reproducible text record from the candidate explanation and selected
source comments. Define packing, ordering, and length limits before comparing
models. Record omitted evidence. Compare on a common input budget first; treat
benefits from a larger context budget as a separate experiment.

| Candidate | What changes during development | What it tests |
| --- | --- | --- |
| TF-IDF plus logistic regression | Weights over words/phrases | Whether obvious lexical or writing-style cues explain much of the label |
| Frozen text embeddings plus logistic regression | A small decision layer; encoder stays fixed | Whether existing semantic representations make the policy learnable |
| SetFit | Sentence encoder adaptation plus a classification layer | Whether modest task adaptation improves on frozen representations |
| GLiClass | Supplied criteria/examples; optional adaptation in a later round | Whether a general label-conditioned classifier fits the task |
| Jev | Supplied questions, criteria, and calibration | Whether focused general-purpose classification is competitive |
| Current and updated LLM baselines | Prompt/examples and efficient output settings | Whether broader reasoning capabilities materially improve admission |

Include accept-all and reject-all controls. Overall accuracy can reward rejecting
most items; zero useful yield cannot satisfy the project objective.

SetFit adapts sentence representations using labeled examples before fitting a
classification head. GLiClass supports supplied labels, task descriptions, and
examples; Jev provides request-defined typed questions. These are different
adaptation routes, not interchangeable architectures. [SetFit](https://huggingface.co/docs/setfit/index),
[GLiClass](https://github.com/Knowledgator/GLiClass),
[Jev primitives](https://docs.typesafe.ai/primitives)

The target here is the historical overall inclusion decision. Keep existing
automated gate behavior as a separate operational baseline; it did not perform
the full human curation task. Legacy reject reasons are not gold labels for
every proposed component check.

**Deliverable:** a common-input report identifying useful candidates, error
patterns, and whether more specialized training is warranted.

### Round 2: address a demonstrated limitation

Choose follow-up experiments based on round 1 failures:

The first API run exposed a concrete problem: the image model could understand a
joke better than the supplied explanation, then approve the pair without requiring
the explanation to be fixed. The next diagnostic comparison should explicitly
distinguish a valid current explanation from an item requiring repair, while
keeping consensus, support, and image consistency within the joint ground-truth
task. Apply the change to multiple backends. A repair proposal is not acceptance
until the repaired explanation has been checked.

Overall historical admission agreement also remains weak. Testing adaptation to
the full development corpus remains useful, alongside confirmation of rejection
provenance. The eight references used for the API comparison do not exhaust the
historical curation standard. None of these follow-ups should use reserved items.

| Observed limitation | Follow-up |
| --- | --- |
| Frozen representations miss task-specific distinctions | Fine-tune one ModernBERT or DeBERTa classifier and compare with SetFit |
| Similar wording conceals disagreement | Test a cross-encoder jointly reading a comment and proposed interpretation |
| Important visual facts are absent | Compare text-only with direct image/text features and a joint image-aware model |
| Several useful signals need combining | Fit a small classifier or boosted-tree model over those signals |
| Strong model is accurate but operationally expensive | Test bounded escalation; consider distillation only after establishing a reliable reference |

ModernBERT supports downstream classification fine-tuning. Cross-encoders score
input pairs jointly, while separate embeddings allow caching and cheap repeated
comparison. A relevance scorer is not automatically a support/contradiction
classifier: it needs the right target labels and evaluation. [ModernBERT](https://huggingface.co/blog/modernbert),
[cross-encoder documentation](https://sbert.net/docs/cross_encoder/usage/usage.html)

For a multimodal baseline, combine frozen image features from a model such as
SigLIP 2 with text features and train a small output layer. Compare that with
joint image/text processing when failures depend on interactions such as a small
visual cue contradicting the gloss. Neither matching an image caption nor high
image/text similarity establishes that the explanation gets the joke.
[SigLIP 2](https://arxiv.org/abs/2502.14786)

For a final admission model, structured inputs could include validated support
counts, evidence-check outcomes, duplication scores, and semantic features.
CatBoost is one option for combining heterogeneous features. Use out-of-fold
upstream predictions when training on features produced by models that learned
from the same labels; otherwise the combined model can inherit training leakage.
[CatBoost](https://catboost.ai/docs/en/features/categorical-features)

Pairwise support labels, image-consistency labels, and tag labels are distinct
from the overall curation label. The first two can be diagnostics within a joint
ground-truth task. Reconcile contradictory historical regression references before
using them as gold labels. Where only weak or model-generated labels exist,
report that provenance. Distillation transfers a teacher's behavior and errors;
teacher agreement is not independent validation.

**Deliverable:** targeted evidence for which additional model capabilities help,
including preparation and inference costs.

### Round 3: test the complete admission policy

Freeze a candidate workflow and thresholds using development and calibration
data. First establish a qualified final evaluation set: the existing reserved
partition is not entirely untouched across the experiment history. Evaluate the
full accept/reject/defer behavior on that qualified set.
Test the actual escalated population, including fallback errors and costs.

An uncertain item can receive a bounded automated second assessment or remain
deferred. The pipeline does not wait for a human to resolve it. Deferral is an
operational outcome, not a third historical class manufactured from missing
labels.

Keep model replacement separate from decomposition: compare a direct decision
and component checks with more than one backend. Otherwise clearer inputs or a
better evidence generator could be mistakenly credited to a classifier.

**Deliverable:** a versioned policy recommended for the backfill, or a precise
account of which target remains unestablished.

## Evaluation contract

Historical inputs and labels must be frozen before experimentation. Split by
duplicate/joke family, reserve calibration separately, and keep retrieval
examples inside the development split. Reuse the main plan's manifest rather
than create incompatible splits in each experiment.

Never expose the target item's review outcome, rejection reason, later model
performance, or unavailable future corrections as inference features. Inspect
whether successful models rely on writing style, subreddit, or old prompt
artifacts instead of useful content. Feature-removal experiments should answer
specific shortcut concerns rather than expand into unlimited tuning.

Report these measures on the same eligible labeled population:

- **Acceptance precision:** human-accepted items divided by all automatically
  accepted items. Undefined when nothing is accepted.
- **Positive retention:** automatically accepted human positives divided by all
  human positives, with deferred positives still in the denominator.
- **Outcome coverage:** accepted, rejected, deferred, and technical failures as
  separate counts; failures must not silently disappear from the report.
- **Error and coverage by slice:** source period, reference family, visual
  dependence, and other established categories. State label coverage per slice.
- **End-to-end defects:** known consensus, explanation, and image failures,
  evaluated only where corresponding reference evidence exists.
- **Operational cost:** training, evidence generation, inference, retries,
  escalation, latency, and throughput at the expected backfill volume.

Compare methods at matched useful coverage or matched acceptance precision.
Report uncertainty clustered by meme/joke family and inspect confident errors.
Evaluate probability calibration instead of treating raw scores from different
backends as interchangeable.

Define quality and useful-yield targets after the development pilot and before
the final test. A candidate earns adoption through measured quality and operating
benefits, not its architecture or agreement with another model. Historical
agreement remains a measure of past curation; it does not certify correctness on
newer memes.

## First implementation package

1. A shared manifest loader and normalized decision-result record.
2. TF-IDF and frozen-embedding baselines plus API adapters for the first round.
3. SetFit and GLiClass adapters once the basic replay is reproducible.
4. A report of precision/retention curves, errors, deferrals, and total cost.
5. A bounded follow-up experiment selected from observed failures.

Keep corpus records, trained weights, embeddings, and raw outputs under `data/`.
Commit reusable code, configuration templates, and summarized methodology.
Benchmark classifiers may learn from the legacy corpus; benchmark predictors
must still receive only the image at evaluation time.
