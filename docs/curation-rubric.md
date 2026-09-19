# Curation feedback rubric · version 1

This is the working rubric for the next human feedback round. It clarifies what
we want the classifiers to learn; it does not change the production content gate,
rewrite historical reviews, or certify a new unattended admission threshold.

The question is whether a model **gets the joke**: does it recover the relevant
reference, setup, visual detail, implication, contrast or wordplay? We do not ask
for a theory of why people find something funny.

## What to judge

| Question | Choices | What the answer means |
| --- | --- | --- |
| Is the content suitable? | Pass / fail / policy boundary / need more context | Judge what is shown and what the joke refers to. A policy boundary means you understand the content but the publication rule needs a decision; needing context means you cannot yet tell what it means. Neither becomes an automatic pass or fail. |
| Is the stored answer good enough to grade against? | Ready / repair needed / insufficient evidence | One ground-truth judgment covers agreement in the evidence, support, completeness and consistency with the image. An answer must capture the actual joke, not merely name a related reference. |
| Would this be a useful understanding task with a correct answer? | Yes / no / unsure | Identify what a viewer must recover beyond a literal description. Does that interpretation account for the whole item? Judge this separately from the quality of its current answer. |
| Would you include this copy? | Accept / reject / repair answer first / undecided | Your overall judgment, including collection-specific issues such as a duplicate or an unreadable image. This is an explicit choice, never calculated from the other fields. |
| Did you know the reference? | Yes / needed context / still unclear | Unfamiliarity is useful diagnostic feedback, not a rejection criterion. |
| How difficult does it seem? | Easy / medium / hard / unsure | Optional human impression. Keep it separate from measured model success rates and from validity. An easy item can still be useful. |

Every field is optional. A partial judgment stays partial. Free text can explain
the reason, missing clue, disputed interpretation or desired answer repair.
Accepting a meme does not silently certify every sentence in its stored answer.

The current content rule excludes explicit sexual acts, exposed sexual anatomy,
hate or slurs, doxxing and graphic gore. Mild innuendo, dark humor and politics are not blanket
exclusions. The feedback option **policy boundary** records where this rule needs
clarification; it does not adopt a new three-way production classifier. Record
whether a concern is visible in the image, part of the intended reference, or
only a model's possibly mistaken description.

“Useful understanding task” is a working target, not a requirement for a certain
format or sophisticated humor. A text screenshot, observation, simple pun or
reference can qualify. Naming a recognizable meme is not sufficient by itself.
Use the note to explain what makes a particular case too empty, incoherent or
dependent on an unsupported reading. We will test whether these judgments are
consistent before turning them into a classifier rule.

## Examples from the feedback

- **Harry Potter's greatest achievement:** the stored answer misses the point.
  Route it toward answer repair; we do not yet have a separate rejection of the
  underlying meme's value.
- **Chromium, the opposite-label pairs and Top Gear:** accepted. Top Gear may be
  easy; that is a separate impression, not a reason to undo the acceptance.
- **Mario/Gojo:** unfamiliarity explains a possible historical rejection. The
  latest feedback did not supply a final acceptance decision.
- **Spicy ramen:** the visible slur supports a content failure even when a text
  classifier has never seen it.
- **Cobain:** the curator identified a weak/conflicted punchline as well as an
  answer concern. Fixing the answer alone need not make it worthwhile.
- **Grenades:** the curator rejected this particular quote-tweet composition as
  an observation. That does not exclude all observations or quote tweets.
- **Superpowered, childhood photo and Sneed/Chuck:** preserve the unresolved
  policy boundary. Do not silently turn a tentative lean into a hard label.
- **Yo/gurt and square hole:** additional reference context can clarify what is
  intended; it does not settle whether the resulting task is worthwhile.

## Review order and interpretation

Start with the image and stored answer. Give any initial judgments you can, then
reveal source comments when helpful. Historical decisions, previous discussion
and model opinions have a separate reveal button. The gallery records the draft
at each reveal, so later feedback can be distinguished from the first impression.
It records these exposures even if you close the page before saving a verdict.
Revisiting a case cannot make it blind again.

Save partial feedback whenever useful. Revisions append a new record; they never
overwrite the original review, image, answer or earlier feedback. “Repair answer
first” saves a proposed route and optional repair note; it does not edit the
answer or certify that a replacement is correct.

The first new batch has **28 cases: 16 random controls and 12 targeted cases**
with disagreements or non-acceptances in the saved Luna/JEV run. Previously
discussed cases and their known corpus groups are excluded from the new batch.
The original 22 cases remain available for revisiting. Random controls come from
calibration groups outside that API run and its reference set; their earlier
historical/model exposure is not erased. Selection reasons are hidden until
opinions are revealed.

These are fresh examples for this feedback round, **not a new held-out test**.
All judgments collected here are development feedback. Known image grouping is
not a complete semantic-family audit. The reserved test split stays out of the
gallery. Before claiming unattended precision we still need fresh, independently
reviewed, family-separated evaluation data.

Next, compare compact JEV and Luna criteria using only explicitly labeled
dimensions, preserve an answer-repair route, and report both bad items admitted
and good items retained. Agree a new spending cap before another paid experiment.

## Running the local gallery

Prepare a new immutable packet (the output directory must not already exist):

```sh
uv run basedbench curation review-prepare data/curation/historical-v2 \
  --run data/curation/runs/luna-jev-checks-cal-v1-normalized \
  --prior-feedback data/curation/feedback/reassessments.jsonl \
  --output data/curation/review-v1
uv run basedbench curation review-serve data/curation/review-v1 --port 8766
```

Open `http://127.0.0.1:8766/`. Images, evidence, the frozen rubric and selection
manifest live in the packet. New feedback and reveal checkpoints are appended to
`events.jsonl` there, with the packet, corpus, input and rubric identities. Copy
the entire directory to back up the packet and its feedback. No API key or live
database is needed. The server binds only to the local computer.
