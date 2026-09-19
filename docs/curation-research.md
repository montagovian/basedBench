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
The research findings retain the original labels; subsequent explicit curator
reassessments are recorded separately below.

## Curator feedback after this research pass

Alex explicitly approved **both copies of all three opposite-label pairs**:
the teapot riddle, number-plate prank and Clarkson/Porsche meme. The six items
now have accepted reassessments in the local, append-only
`data/curation/feedback/reassessments.jsonl`, tied to their frozen input hashes.
Three reassessments change a historical rejection; three reaffirm an approval.
The gallery displays current curator decisions alongside the historical ones.
All metrics below still describe the original labels and saved calls. A revised
label score would be a separate analysis, not an improvement to the models.

For Top Gear, Alex tentatively recalled thinking it was too easy. Record this as
a **curator difficulty impression**, not a measured solve rate or a certain
reconstruction of the old decision. It remains accepted. This gives us a useful
distinction: a task can be correct, scorable and desirable while also being easy.
Difficulty can inform the composition of the benchmark without making every easy
item a rejection. The same-meme grouping overlaps still need to be repaired for
future evaluation, even though the curator has resolved these label conflicts.

Future feedback should include optional perceived difficulty and its reason,
separate from answer quality and admission. Later, compare those impressions
with measured success across a specified panel of models. Familiarity with a
reference can make a meme easy for one audience and difficult for another.

### Detailed feedback on the remaining gallery cases

Alex then reviewed the remaining 16 cases. The local feedback log preserves his
wording, partial component judgments, tentative decisions and unanswered
questions. It does not turn every comment into a definitive binary label.

| Case | Recorded feedback |
| --- | --- |
| Chromium browsers | Accept. |
| Mario / Gojo | Past rejection may reflect not understanding the reference; no explicit final verdict yet. |
| Harry Potter's greatest achievement | Stored ground truth fails; repair the answer. Suitability of the underlying meme is not thereby rejected. |
| Cobain | Reject on benchmark value: insufficient meaningful punchline; the dark-photo framing also muddles the answer. |
| Spicy ramen | Content-policy fail due to the racial slur. |
| Evangelion | A content boundary case, leaning toward fail. |
| Yo / gurt | Unresolved: recognizing the word split does not yet make the joke feel meaningful; missing context remains possible. |
| Neck / back | Lean accept; content now seems fine. This does not separately endorse the answer's Quagmire embellishment. |
| Superpowered partners | Borderline content; no final admission verdict. |
| Dr. Now | Lean accept; past unfamiliarity may explain rejection. This does not separately certify the existing answer's specificity. |
| Childhood photo | Borderline content; no final admission verdict. |
| Sneed / Chuck | Lean content fail, but possibly borderline; retain the uncertainty. |
| Moron / L | Lean reject on benchmark value: too weak or nearly nonsensical. |
| Jersey Shore / grenades | Reject on benchmark value: the quote-tweet reads as an observation, while the original founding-fathers layer might be a joke. |
| Warhammer fantasy | Lean accept. |
| Triangle factory / square hole | Unresolved: unsure the references combine into a joke; missing context remains possible. |

This feedback changes the working diagnosis. Some historical negatives reflect
reference unfamiliarity, some reflect publication boundaries, and others reflect
the value of the task even after the intended meaning is understood. Those
cannot all be represented by one negative label with an inferred reason.
The four positive/lean-positive judgments and five negative/lean-negative
judgments are not nine equally certain training labels. Seven cases have no
final overall verdict, including Harry Potter, which has a clear answer defect
but no final judgment on the underlying task. Keep tentative overall decisions
out of definitive binary training targets until confirmed. Use the explicit
component feedback only for the component it addresses.

### Borderline content is a policy question, not just missing evidence

Alex floated pass/fail/borderline as an idea and explicitly did **not** instruct
us to adopt it. The current classifier and production publication policy remain
unchanged. The feedback log can still faithfully record that a particular item
feels borderline.

For a future design, distinguish:

- **Boundary case:** the content is understood, but where the policy draws the
  line is unsettled. Implied sexual references in this batch illustrate this.
- **Insufficient evidence:** we cannot establish what the content contains, for
  example because text evidence omits relevant image text.

These require different remedies: clarify the standard versus obtain better
evidence. An annotation can record both the policy assessment and evidence
certainty. A later operational rule can decide which cases pass, fail or remain
pending; an observation of borderline content must not silently authorize
publication or turn into a permanent, unexplained human-review requirement.

### Test what understanding adds, rather than a rigid meme genre

A proposed worthwhile-task diagnostic is: **what does a viewer have to recover
beyond the literal statement, and does that account explain this whole image?**
Ask for the setup, implication, wordplay or connected reference, and identify
when the supplied text already states the entire intended point. Recognition
alone may be sufficient for some accepted reference tasks; the classifier needs
contrasting examples to learn when it is sufficient here.

This is more useful to test than whether the object belongs to an internet genre
called a meme. A screenshot of text can contain an excellent joke. An observation
can also be comic. For the Jersey Shore case, Alex distinguishes the quoted
founding-fathers joke from the outer comment that mostly spells out an observation.
The classifier should inspect the complete composition and the remaining
understanding task, not automatically reject quote-tweets or observations.

Reference familiarity, task value, difficulty, publication suitability and
answer correctness remain separate observations. In particular, Cobain now
illustrates a curator value rejection even if the explanation could be repaired.
Conversely, Harry Potter illustrates an answer defect without establishing that
the meme is a bad task. None of this asks for a theory of why humans laugh.

### Context for the two unresolved reference cases

The established yo/gurt template treats the word as a greeting to an imaginary
person called Gurt, who greets the speaker back. The carton invokes that exchange
through its typography. This supplies the reference Alex may have been missing;
it does not settle whether the photo offers enough benchmark value.
[Reference context](https://knowyourmeme.com/memes/yogurt-gurt-yo)

The triangle-factory reference makes an unexpected circle a production problem;
the square-hole reference sends differently shaped blocks through one opening.
My reading of the combined image is that the problem becomes irrelevant to a
worker who puts every shape through the square hole anyway. That is a proposed
connection, not a new ground truth or evidence of curator approval. Keep the
item unresolved while discussing the connection and the value of the task.
[Triangle factory](https://knowyourmeme.com/memes/a-circle-in-the-triangle-factory-i-guess-we-doin-circles-now),
[square hole](https://knowyourmeme.com/memes/the-square-hole)

These context notes are shown separately in the gallery. They are not inserted
into the original evidence or used to rescore saved classifier calls.

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
4. **How difficult does it seem, and why?** Optional easy / medium / hard /
   unsure, with a reason such as familiar reference, subtle visual clue or
   multiple references that must be combined. Keep this impression separate from
   measured model performance; it does not override the admission decision.

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
