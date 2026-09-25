# Targeted correction feedback results

September 23, 2026 · [#27](https://github.com/montagovian/basedBench/issues/27)
· [Frozen scope](targeted-corrections-plan.md)
· [Preparation](targeted-corrections-preparation.md)

**Two proposals are human-ready: Mamdani and Bowsette.** Three of the four
selected pairs have saved regrades, comprising six answer judgments. Both
philosopher answers remain repair, although the proposal is preferred. Pride
has no new saved answer judgments; the user separately said they do not know
about that case. The bounded pass is complete with that uncertainty retained,
not with a forced fourth verdict. Preparation and analysis cost **$0 / zero
model calls**.

## Exact pair outcomes

| Case | Original | Assistant proposal | Preference | Outcome |
| --- | --- | --- | --- | --- |
| Mamdani (`1u8acxi`) | Repair, B | Ready, A | A | Human-confirmed grounding repair |
| Philosophers (`1u9czw9`) | Repair, B | Repair, A | A | Preferred proposal remains defective |
| Bowsette (`1u96sfo`) | Repair, A | Ready, B | B | Exact proposal preserving competing readings is accepted |
| Pride Month (`1u1cqvx`) | No new judgment, A | No new judgment, B | None saved | Unresolved; prior original unclear remains separate |

Keep the two purposes separate: the **two grounding targets** yield one
confirmed repair and one still-defective pair. The **two interpretation cases**
yield one accepted proposal and one unjudged pair. Across the whole selection,
there are two confirmed repairs, one neither-ready pair and one unresolved
pair. This is neither four completed comparisons nor a model success rate.

The journal contains three feedback events and **zero comment reveals in this
round**. All three preferences favor the proposal, but only two proposals are
ready. Earlier comment exposure and human/assistant familiarity remain; these
are exposed development cases. No optional reason fields were selected.
Source support, suitability and duplicates were not separately adjudicated.

## What the feedback means

**Mamdani:** the exact replacement is ready and preferred over the defective
original. It corrects the subject and states the wedding-invitation setup and
song-choice connection. This is evidence for that particular manual correction,
not a validated general safeguard against subject confusion. The proposed
Peter-narrator explanation for the original mistake remains a hypothesis.

**Philosophers:** the complete human note is:

> A is better but "discussed in the comments as Wittgenstein and Schopenhauer" is not the right framing, is that the ground truth or not? (it is)

The note explicitly confirms the named referents as ground truth and rejects
the proposal's distancing formulation. The assistant put provenance language
inside the answer where a direct explanation was needed. The next correction
should state the referents and the character-to-appearance/generalization
connection directly, while keeping comment attribution in evidence metadata.
This interpretation follows the human note; it does not turn the currently
rejected proposal into ready or approve an unwritten revision. No further
proposal was generated during this analysis.

**Bowsette:** the accepted text includes both the sexual-possession implication
and the crown-removal reading, with the result left off-panel. Accepting that
exact answer does not select one reading as the sole canonical interpretation.
The #26 repair judgment and its ground-truth uncertainty stay intact; the new
judgment establishes that this separately written version is good enough to
grade. No source-count or suitability verdict is inferred from acceptance.

**Pride:** no new event exists for either answer. The separate task message is:

> i don't really know about breaking bad pride but regraded the rest

It records conversational uncertainty about the case, not two UI "unclear"
labels. The original's earlier #26 unclear judgment remains in its own snapshot;
the proposal has no human answer-level judgment. Both new fields stay absent.
Park the case; unfamiliarity need not become a rejection or another review task.

## Available versions across the fixed pool

Eight of the ten reviewed identities now have an **exact human-ready answer
version available**: six #26 originals and two #27 proposals. Death Note's
tentative ready note remains attached. Philosophers still needs correction;
Pride remains unresolved. The original-only #26 result is still six ready,
three repair and one unclear; no earlier result is rewritten.

The full **18-identity ledger** therefore has eight with a ready version
available, one needing correction, one unresolved interpretation and eight
unchanged overlap holds. The holds remain retrieval candidates, not confirmed
duplicates. This cross-round availability accounting is human-assisted curation,
not archive accuracy, automatic admission yield, Luna generation performance or
publication clearance. The two ready proposals have not replaced database rows.

## Freeze, verification and decision

Snapshot: `data/curation/targeted-corrections-feedback-v1/`, ID
`9b9efe8f562fd87d7e01fbfe673073d9a0c865b5fec4bebf1bc41ffcd95713d3`.
It retains all four original/proposal inputs, image bytes, the exact three-event
journal, six labels, preferences and notes, plus the separate conversational
statement. Missing answer judgments are explicitly absent with no fabricated
events. The existing complete-review freezer rejects missing judgments, so this
snapshot uses a distinct partial-feedback format and does not alter that frozen
code or pretend to be a complete eight-judgment review.

The separate analysis includes an 18-case availability ledger with exact answer
hashes, source snapshots and human event IDs:
`data/backfill/targeted-corrections-feedback-analysis-v1.json`.
Verification is recorded in
`data/backfill/targeted-corrections-feedback-verification-v1.json`.
All **24,346 inventoried prior files are byte-identical**, including the live
journal with the new regrades, all earlier feedback, frozen runs, database and
unrelated app/helper-test edits. The new snapshot's journal is byte-identical to
the live journal. Packet/source/implementation hashes and earlier model
code/input/result manifests verify. No application or test code changed; the
508-test preparation baseline is retained, with direct artifact-integrity
checks for this analysis. Raw artifacts remain local and uncommitted.

**Close #27 with the three regrades and Pride abstention explicit.** Keep the
two human-ready proposal versions available, carry the philosopher wording
correction forward, and park Pride. The next useful correction is the direct
framing already specified by the user, not another broad annotation round or
capacity increase. This pass ends here: no automatic adoption, new proposal
round, model comparison, suitability change, publication or #9 expansion.
