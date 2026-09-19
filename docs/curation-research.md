# Curation research: what the low precision is telling us

September 18, 2026. Offline analysis of saved calls; no new paid model calls.

**We have evidence of a poorly specified target as well as real model mistakes.**
The current results do not establish that the historical curator was too strict,
or that the models can reliably identify good additions. Some historical rejects
look useful on inspection; others have concrete defects. Most importantly, an
excluded *post* is not necessarily an unsuitable *joke*: several copies of the
same meme have opposite labels.

The local image packet is at
[`data/curation/research-v1/casebook.html`](../data/curation/research-v1/casebook.html).
It contains the images, original explanations, source comments, current model
decisions and my provisional assessments. It is read-only and remains local.
This document records findings and the next experiment design, not new labels.

## Are the models agreeing?

All comparisons below use the same 80 calibration examples: 23 historical
approvals and 57 historical rejects. The current four variants are Luna direct,
Luna with three text checks, Luna with three image-and-text checks, and JEV with
three text checks. These are four configurations, not four independent models.

| Comparison | Exact decision agreement | What that agreement contains |
| --- | ---: | --- |
| Luna text checks / JEV checks | 73/80 (91.3%) | 70 joint accepts, 3 joint rejects |
| Luna image checks / JEV checks | 66/80 (82.5%) | 64 joint accepts, 2 joint rejects |
| Luna direct / saved GPT-5.5 text direct | 73/80 (91.3%) | 65 joint accepts, 8 joint rejects |
| All four current variants | 61/80 (76.3%) | 59 unanimous accepts, 2 unanimous rejects |

The high agreement mostly means **they accept nearly everything**. Luna text
checks accept 73 items and JEV accepts 74. Among the ten items rejected by either
one, they agree on rejecting only three. Their acceptance rates alone would
produce about 85.1% agreement if their decisions were independent; the observed
91.3% is more informative than that, but is not evidence of near-perfect shared
discrimination.

Unanimity is not an admission solution. Of the 59 unanimous accepts, only 18 were
historically approved: 30.5% precision against the old labels, versus 28.8% for
accepting all 80. All four accept **41 of the 57 historical rejects**. Including
the three older API variants leaves 49 unanimous accepts, of which 16 were
historically approved (32.7%). Shared criteria, evidence and reference examples
make these votes correlated.

The fitted classifiers behave differently. At a descriptive 0.5 cutoff, TF-IDF
selects 11 items (3 approvals), and frozen MiniLM selects 36 (11 approvals).
Their decisions agree with Luna text checks on 16/80 and 41/80 respectively.
The tendency to accept almost everything is primarily shared by the API prompt
variants, not every approach tested. These cutoffs are not validated deployment
thresholds.

## The largest problems we can already identify

### 1. Historical selection and intrinsic suitability are mixed together

I visually compared three pairs with opposite labels:

| Meme | What the comparison shows |
| --- | --- |
| Teapot riddle on a milk carton | Essentially the same screenshot and answer. One copy was approved May 22, another rejected June 5. Both are in the same calibration group. |
| Number-plate prank | Same joke; the rejected copy has a smaller screenshot surrounded by large black margins. The approved copy was reviewed first and is one of our prompt references. |
| Clarkson / Porsche 928 | Same meme and very similar answers. The rejected copy was reviewed first, then the approved copy five days later. The approved copy is another prompt reference. |

Duplicate removal, presentation quality, changed standards or an accidental
decision could explain these differences. The records do not tell us which.
In particular, chronology does **not** support a universal explanation that the
later copy was rejected as a duplicate.

Our classifier instructions explicitly say not to guess duplication against an
unseen collection. If some historical rejects mean “we already have this,” the
classifier can follow the instructions correctly and still be scored wrong.
It would also be wrong to automatically flip those labels: selecting only one
copy may have been the right collection decision.

The number-plate and Clarkson families also cross from development references
into calibration under different group IDs. **Two of our four approved prompt
references have rejected counterparts among the 80 targets.** The conservative
image grouping missed them. The Clarkson pair has the same difference hash, but
the aspect-ratio guard prevents a match; the number-plate versions differ in
layout and framing. Existing split checks protect recorded groups, not every
actual meme family. This adds concrete evidence to the already documented
limitations of the evaluation split. Do not reshuffle the frozen corpus or
retroactively present these results as an independent test.

The review database stores only the latest status, reason and timestamp. The
review UI defaults the exclusion reason to `other`; the frozen corpus marks
these as inferred manual decisions. This is consistent with manual review, but
does not recover the reason, reviewer identity or exact historical display.

These three pairs are diagnostic examples, not an estimate of how many labels
are ambiguous. They cannot by themselves account for dozens of false accepts.

### 2. Our worthwhile-task check has almost no discriminating power here

**All three decomposed variants pass every one of the 57 historical rejects on
benchmark value.** JEV and image Luna pass all 80; text Luna fails just one,
which was historically approved.

That is unsurprising given the question we wrote. It passes any recoverable
reference or mechanism, explicitly allows simple puns, excludes difficulty and
aesthetic funniness as criteria, and leaves duplication out of scope. The corpus
already consists of posts that received a generated consensus explanation.
We are asking whether those explanations describe something interpretable, and
they generally do.

This is a limitation of **our operational definition**, not proof that simple
puns should be excluded. We should establish which distinctions actually matter
to the curator before inventing stricter rules to improve a score. BasedBench
still measures getting the joke, not explaining the psychology of humor.

### 3. Some models recognize the reference without verifying the whole answer

The image review gives concrete reasons to retain some rejections:

- **Harry Potter's greatest achievement:** the answer explains his retort to
  Snape, but misses the meme's comparison: classmates value that comeback above
  defeating Voldemort and his other heroic accomplishments. Image Luna catches
  this; text Luna and JEV pass it.
- **Kurt Cobain:** the answer identifies him and mentions his death, but omits
  the statement being contradicted in the image: musicians supposedly never
  touch guns. Both decomposed Luna variants reject; JEV passes.
- **Triangle factory / square hole:** the answer recognizes the Square Hole
  video while leaving out the other half of the mashup. Image Luna rejects;
  JEV gives the answer a 0.97 pass score.
- **Spicy ramen:** the image contains a racial slur absent from the supplied
  explanation. Image Luna rejects under the current publication rule; the
  text-only variants pass. Better text instructions cannot establish facts
  missing from their inputs.

There are also failures among unanimous accepts. In the back-versus-neck optical
illusion, the answer incorporates a Quagmire-style sexual reaction from comments
as though it belongs to the meme. Image Luna endorses that addition. The Dr. Now
sticker answer gives his identity and other catchphrases instead of explaining
the particular line on the sticker. These are useful boundary cases for answer
completeness, even where the underlying image could be usable after repair.

### 4. Some rejects really do look worth reconsidering

I inspected a deterministic sample of 12 of the 41 historical rejects accepted
by all four current variants, then ten selected comparison/failure cases: 22
images altogether, with comments and explanations. I knew the historical labels
and model outcomes; this was **not blind adjudication**. These judgments are
provisional and cannot estimate a corpus-wide relabeling rate.

Two particularly good candidates are the Chromium-browser meme, where different
logos conceal the same underlying engine, and Mario bypassing Gojo's Infinity
through the Super Mario 64 backwards-long-jump glitch. Both connect visible
details to specific references; multiple comments support the stored answer.
The yo/gurt meme also has a recoverable reference supported by its comments.
I do not see an obvious intrinsic reason to exclude these under our current
standard. Collection duplication or a different publication rule could still
matter.

Other cases call for policy clarification: simple trick questions, optical
illusions, implied sexual humor and demeaning social commentary. A high-resolution
childhood-photo joke also illustrates the distinction between explaining the
meme's intended assumption and endorsing it as a reliable real-world fact.

Model unanimity can be wrong in the other direction too. The only historical
approval rejected by all seven API variants is the Evangelion thermal-paste
reference. The image shows paste on a hand next to a themed GPU; Luna's image
rationale says it explicitly depicts the sexual act being referenced. It does
not. We might choose to exclude the reference itself, but that requires the
correct policy judgment, not a false description of the pixels.

### 5. JEV still has a plausible improvement path

The current shared reference material is about 16,466 characters, versus roughly
2,000 characters for the median candidate record (measured with Python's default
JSON serialization). Eight unexplained overall labels plus all their comments
are substantial context for a single component question. They also cannot teach
the component-specific reason behind each exclusion.

TypeSafe's guidance specifically recommends literal conditions, smaller relevant
inputs, fewer reasoning steps and code for deterministic aggregation. It also
warns that text generation is not JEV's task. These support testing concise,
component-specific questions and evidence packages; they do not establish that
this will improve our results. [JEV 1.13 guidance](https://docs.typesafe.ai/model-jaggedness/jev-1.13)

We can preserve consensus, support and explanation completeness as one conceptual
ground-truth gate while probing narrower facts inside it. Decomposing the work
does not require inventing independent gold labels from an overall rejection.

## Can GEPA optimize JEV?

**Yes, as an integration approach; we have not tested that integration here.**
GEPA can optimize text candidates through a user-supplied evaluator. Its general
interface accepts a string or multiple named text components, examples for
development/validation, and scores plus diagnostic feedback.
[GEPA interface](https://gepa-ai.github.io/gepa/api/optimize_anything/optimize_anything/),
[evaluator contract](https://gepa-ai.github.io/gepa/api/optimize_anything/Evaluator/)

For this project, my proposed application is: an inexpensive generative model
such as Luna proposes changes to JEV's question wording and criteria; JEV scores
the labeled cases; code measures performance and returns errors and human notes
to the optimizer. JEV remains the classifier. This optimizes its instructions,
not its weights, and does not require JEV to write its own critiques.

Start with a few controlled, manual variants first: reduced reference context,
specific missing-setup checks, and clearer publication boundaries. Then GEPA can
search among useful formulations under a total dollar cap covering both JEV
evaluation and generative proposals. Keep model versions, evidence and the human
policy fixed for the first optimization experiment.

Do not optimize raw historical accuracy or precision alone. Rejecting everything
has zero useful yield and undefined precision. Prefer recovering as many good
items as possible subject to an agreed minimum precision, plus separate limits
on serious publication errors. For search, use an explicit error-cost objective
and report the precision/yield tradeoff; validate the actual admission rule on
unseen meme families. An optimizer must not silently change the publication
policy, relabel examples or include item-specific shortcuts.

## Recommended next step: a short, informative feedback round

Build a website-style review view around the frozen evidence and images. The
research packet is a read-only preview of the cases; a feedback workflow remains
to be implemented. The important change is what the feedback records:

1. **Would this be a useful task if its answer were correct?** Yes / no / unsure.
2. **Is the stored answer good enough to grade against?** Yes / repair needed /
   insufficient evidence. Record what is missing when repair is needed.
3. **Would this particular copy enter this collection?** Yes / no / unsure,
   with reasons such as duplicate, poor image, publication boundary or low value.

Keep the original decision and add a dated, versioned reassessment, with optional
free text. Show the image and stored answer before revealing historical/model
judgments to reduce anchoring. Make the original comments and related copies easy
to inspect; capture whether the reviewer changed their judgment after seeing
them. Human component feedback can stay partial rather than filling every field
from the final accept/reject decision.

A first batch of roughly 30–40 cases should mix unanimous disagreements, model
disagreements, approved controls and duplicate pairs. Include some randomly
sampled controls; do not build all future evaluation data from disputed cases.
The present 80 cases are already development feedback in practice. Keep their
history, resolve discovered family overlaps, and establish genuinely fresh,
family-separated validation before estimating unattended admission quality.

The immediate order is **clarify the target with examples, fix family accounting,
try a few cheap JEV/Luna variants, then use optimization if the target is stable**.
There is enough evidence to justify this work without another GPT-5.5 run.

## Reproduction and limitations

The ignored local folder `data/curation/research-v1/` contains `analyze.py`,
`agreement.json`, `notes.json`, `build_packet.py`, `manifest.json` and the HTML
packet. The analysis verifies that each compared API decision matches the same
80 IDs and input hashes. Baseline controls are excluded when extracting TF-IDF
and MiniLM scores. The sample uses the fixed hash seed `research-review-v1`.

Sources are `historical-v2`, `luna-jev-checks-cal-v1-normalized`, the saved
`llm-jev-cal-v1`, and the two saved fitted-classifier runs. No original calls,
labels, corpus files or split assignments were changed. Reserved-test image/text
content was not inspected. Existing exposure and grouping limitations in
[curation evaluation](curation-evaluation.md) still apply.
