# Targeted corrections ready for human review

September 23, 2026 · [#27](https://github.com/montagovian/basedBench/issues/27)
· [Frozen scope](targeted-corrections-plan.md)

**Four original/proposal pairs are ready at `http://127.0.0.1:9879/`.**
Mamdani and philosophers are correction targets; Bowsette and Pride Month are
interpretation cases. The one proposal per case is assistant-authored from the
saved evidence, not a validated repair or a measured Luna output. Preparation
used **zero paid calls / $0**, with no new source collection or model comparison.

## How to review

Judge both answers as written: **Good enough to grade**, **Material defect** or
**Cannot judge yet**. Both answers can be acceptable; preference is optional.
For competing readings, use the note to say whether a usable reference is
possible or whether ambiguity should remain unresolved. There is no required
choice of a single interpretation. Save each pair; on the last case use
**Save feedback**.

Comments are optional. Revealing them records the current draft first, then
shows the exact original comments and any clearly separated reference notes.
Those notes are not extra Reddit supporters. Prior labels, author identities
and assistant selection rationales are hidden. These are previously reviewed
development cases; shuffled A/B presentation does not erase that exposure.

Any new judgment on an original answer remains a new contextual revision.
The #26 feedback, including Bowsette's uncertainty, Pride's unclear label and
Death Note's tentative ready note, stays in its original snapshot. The six
ready cases and eight overlap holds are outside this four-case packet.

## Evidence and provenance

Mamdani's subject and setup are anchored to written image content. The possible
Peter-narrator confusion is a development hypothesis, not established causation.
The philosopher proposal attributes names to the saved comments; it does not
identify people from faces. Supplemental background about the named philosophers
comes from [the New Yorker's biographical account](https://www.newyorker.com/magazine/2022/05/16/how-queer-was-ludwig-wittgenstein)
and [Stanford's Schopenhauer entry](https://plato.stanford.edu/entries/schopenhauer/).
These references do not verify the portraits or every anecdote in the comments.

Bowsette retains evidence for competing implications and the fact that the
outcome is off-panel. Pride uses the reviewer-linked
[format account](https://knowyourmeme.com/memes/its-pride-month-you-know-what-that-means)
alongside the original image and comments. Reference checks were made September
23; no external page is treated as a replacement human verdict or proof of
three-comment consensus. No suitability rule changed.

Packet: `data/curation/targeted-corrections-v1/`, ID
`d2f4e8d9e1368844ed2c9da42aba461d3dcc723487a96318f7b0248215e1d00a`.
It freezes the four original inputs, proposed texts, prior human anchors,
supporting comment IDs, supplemental notes, evidence limitations and plan hash.
The complete original ten-case feedback and 18-case accounting remain separate.
Proposal source: `data/backfill/targeted-correction-proposals-v1.json`.

To resume the gallery:

```sh
uv run python -m basedbench.targeted_corrections serve \
  data/curation/targeted-corrections-v1 --port 9879
```

## Verification and continuation

All **508 tests pass**: 506 in the sandbox and the two localhost HTTP tests with
socket access after their sandbox bind failures. Eight new tests cover exact
human provenance, source/author blinding, pre-reveal drafts, no overwrite and
refusal of changed snapshots, plans, original answers, inputs, comments,
selection or image bytes.

A disposable browser packet verified paired uncertainty judgments, the note
checkpoint before reveal, separated reference notes, saving and reload
persistence. Those two assistant test events exist only in the disposable
packet. Its server and tab were closed. The real gallery opened with the
correct image, four pairs and **zero feedback or reveal events**; no assistant
judgment was entered there.

Of 24,315 inventoried prior files, **24,313 are byte-identical**, including the
database, frozen runs, human journals and unrelated app/helper-test edits. Two
SQLite runtime sidecars are absent at verification: the prior WAL was empty,
and the database itself has the exact prior hash. No sidecars were restored.
Exact original answers, images, comments, human anchors and new packet manifests
verify, as do earlier calibrated, focused, capacity and materiality
code/input/result hashes.
Local verification: `data/backfill/targeted-corrections-verification-v1.json`.
Raw evidence, images, proposal files and feedback remain local and uncommitted.

**#27 stays open for actual human feedback.** After review, freeze the new
journal separately and report the two correction targets separately from the
two interpretation cases. Keep both-acceptable, partial and unclear outcomes.
No proposal is adopted automatically, and #9 expansion remains pending.
