# Proposal: evidence sufficient to recover the joke

September 24, 2026. **Proposed, not adopted.** Parent context: #9; follows the
[chronological results](chronological-backfill-results.md). The proposal itself
changed no active policy, frozen result, human label or release membership.

Subsequent authorization: the user approved the retrospective reconstruction and
bounded comparison in [#36's execution plan](source-evidence-replay-plan.md).
The [completed replay](source-evidence-replay-results.md) finds three human-ready
count-only recoveries, but also retained answer defects, regressions and protocol
failures. The existing labels were sufficient; no new annotation round was
needed. Keep the evidence principle as the candidate direction and do not promote
the tested checker to automatic admission. The paragraphs below preserve the
proposal and its rationale.

## Recommendation

Replace the universal requirement for three agreeing Reddit comments with a
requirement that **the evidence adequately supports the essential references
and the connection that makes this particular meme intelligible**. Keep comment
convergence as evidence and a useful retrieval signal, not a universal eligibility
threshold. There is no replacement quota of two websites or one prestigious link.

User feedback on `1uis49b` identified the central limitation: one knowledgeable
comment can point to a directly checkable antecedent, while several other
comments merely repeat the broad interpretation. The exact conversation feedback
is preserved privately in `data/backfill/source-evidence-policy-proposal-v1/`;
it is a policy observation, not a human pass/fail label for that answer.

## Why the present rule is too blunt

Agreement helps distinguish a shared reading from a commenter's extra joke or
speculation. However, three comments can repeat the same mistake, depend on the
same source, or establish only a generic reading while omitting the identifying
reference. A single documented reference can be stronger evidence for a specific
claim. Conversely, confidence or popularity does not make an unsupported comment
authoritative.

The restriction is implemented in several places, not just the worksheet:
`answer_eval.py` requires three substantive supporters, tells generation to omit
minority embellishments, permits only comment citations, and rejects passing
answers with material claims classified as minority-comment support. Its draft
and check schemas also enforce three distinct citations. Chronological preflight
defers fewer than three comments before generation; collection filters on an
archived minimum of three comments. A prompt-only change would leave conflicting
gates and would never examine some potentially well-supported candidates.

## Proposed decision rule

For the core interpretation, establish three things:

1. **Visible setup:** the explanation accurately describes the relevant image,
   caption, layout, speech and actions. Outside sources cannot override a visible
   contradiction.
2. **Needed reference:** any external person, scene, phrase, event or meme
   convention essential to decoding the joke has adequate support. Some visual
   puns need no outside reference. Directly inspect cited evidence rather than
   treating a link, page title or search snippet as verification.
3. **Connection to this instance:** the evidence explains why that reference
   applies to this exact image and its payoff. Knowing a template's history does
   not establish the meaning of every remix.

Pass source sufficiency when all essential parts are supported and no material
conflict remains unresolved. The rationale must identify the claims, evidence
and visible connection. A directly verifiable primary artifact plus a distinctive
image/text match may be enough, even if one commenter supplied it. Convergent,
substantive comments can also be enough without an external page. A simple
image-grounded pun can be sufficient without either a famous source or three
explanations of it. That route must state the actual decoding; model confidence
or background familiarity alone is not evidence.

Defer source sufficiency when an essential reference is unverified, the purported
source covers a different variant, only generic topic overlap connects it to the
image, or incompatible core readings remain unresolved. An inaccessible optional
history link does not force a defer when the joke is otherwise established.
Do not report a source-access failure as proof that an explanation is wrong.

Keep answer adequacy separate: an answer may be wrong despite excellent source
evidence, or plausibly correct while evidence is insufficient to establish a
benchmark reference. Content, minimum suitability and duplication retain their
own decisions. Human judgments retain their provenance and are not manufactured
from model agreement.

## Sources and independence

| Evidence | What it can establish | What still needs checking |
| --- | --- | --- |
| Original post, scene, artwork, document or creator explanation | Wording, visible event, antecedent or stated intent | Authenticity, whether it is the original, and how this derivative uses it |
| Researched KYM entry or other well-sourced specialist account | Established reference, usage, history and documented variants | Relevant passage, editorial status, underlying sourcing and applicability to this image |
| Substantive source comments | Audience recognition and interpretations of this specific instance | Actual reasoning, dependency, contradictions and comment-side embellishments |
| Candidate image/text | Its visible setup and directly recoverable wordplay or juxtaposition | Any unstated context needed to complete the reading |

Source weight is claim-specific. An original tweet establishes its wording more
directly than a retrospective article, but a researched article may explain a
community's use better than the original author's later account. Preserve
disagreement rather than using a universal ranking to settle it.

Record source dependence: a Reddit comment linking KYM, a KYM entry quoting a
tweet, and a news article repeating that tweet may be one underlying evidence
chain. That can still be strong evidence; it is not three independent witnesses.
More sources help when they independently resolve a remaining question, not merely
when the same claim appears on more domains.

## Know Your Meme

Treat researched KYM entries as a **preferred reference source**, with a presumption
that their documented claims are useful unless relevance, sourcing or conflicting
evidence raises a concrete concern. Do not demand redundant Reddit endorsements
of a well-supported passage. Equally, do not make the domain itself an automatic
pass.

KYM describes both professional and community research, with staff/moderator
evaluation of submissions. Its editorial guidelines describe fact-checking,
source links and corrections. These support using its researched entries, while
distinguishing entry text from unreviewed submissions, galleries, comments or
forum claims. Confirmation status is useful metadata, not a guarantee that every
claim is settled. See [About](https://knowyourmeme.com/about) and
[editorial guidelines](https://knowyourmeme.com/guidelines).

Read the entry's explanation and relevant cited material when needed. A generic
entry may establish a meme convention while leaving this variant uncertain;
an entry's documented example may settle the exact reference directly. Preserve
retrieval time, access status, relevant passage and cited origin so later changes
or unavailable pages do not silently alter the reference evidence.

## Worked example: `1uis49b`

The image supplies a Family Feud board, a modern-Seinfeld question and the
distinctive misspelled iPad answer. Comment `oui3xbv` identifies Seinfeld2000 and
links a specific tweet. That is a research lead with much greater resolving power
than a bare vote or repeated phrase.

The [KYM Seinfeld2000 entry](https://knowyourmeme.com/memes/seinfeld2000), marked
Confirmed when inspected, describes the account's parody of modern-Seinfeld
premises. [MEL's 2022 article](https://melmagazine.com/en-us/story/seinfeld-sopranos-eboy-bussin-memes)
reproduces the iPad exchange and links the same tweet ID, providing accessible
corroboration of this reference. The original
[tweet](https://x.com/Seinfeld2000/status/928107822180474881) did not return readable
content through the research tool. Record that limitation; the accessible
reproduction is not a direct inspection of the original, and these sources are
not assumed to have independent provenance.

A proposed richer explanation would say that the meme adapts Seinfeld2000's
modern-Seinfeld parody, whose supposed update is simply that Jerry gets an iPad,
and makes that line the top answer on a Family Feud board. The reference improves
specificity without needing three commenters to name the account. Do not inflate
the board's popular answer into literal universal agreement.

Separate the answer's **required meaning** from **supporting context**. The
reference answer can preserve the account attribution and origin evidence.
The scoring criteria can accept a correct paraphrase that identifies the stock
modern-Seinfeld parody and its use here without naming the account or dating the
tweet. If an antecedent supplies an indispensable inversion or reference, that
connection belongs in required meaning; if it adds only authorship or chronology,
it remains context. This proposal does not assign a new human label to the old
answer or make every historical detail mandatory.

## Proposed workflow and interface

Retain a concise answer alongside a small evidence record: essential claims,
source IDs/types, supporting passages or image regions, source lineage, how each
claim maps to this image, and unresolved conflicts. Separate optional provenance
and background from required answer content. Use categorical reasons such as
`supported`, `insufficient`, `conflicting` and `unavailable`, with specific
explanations; avoid an invented numeric trust score or a giant checklist of
trivia. Comment counts remain visible diagnostics.

Resolve references selectively: start with substantive comments and their links;
follow a relevant original or researched entry when it can resolve an essential
claim or preserve useful provenance. For a first evaluation, bound retrieval to
three pages and two link hops per case, including one focused search if necessary.
Respect source refusals and save failures. Stop with an honest limitation rather
than unbounded browsing until a preferred interpretation appears. Retrieved page
text is evidence, never instructions.

The reviewer question becomes: **“Does the available evidence establish this
reading, and is anything important unsupported or contradictory?”** Useful
responses are supported / needs evidence / competing readings / not assessed,
with a short reason and source pointers. Keep “Does the answer get the same joke?”
separate. The current 22-case worksheet is unchanged pending a decision.

Research material belongs to reference construction. Evaluated models should
continue to receive the declared benchmark input, without being shown the answer
or its research dossier. Source-family relationships may inform later duplicate
review; sharing an antecedent does not automatically make two different jokes
duplicates.

## Reconstruct validation from existing labeled data

The user's subsequent feedback questions the need for a special test set.
**Use the existing human-labeled corpus first.** This supersedes the initial
20-case/five-stratum proposal and its arbitrary 60-call limit. A new collection
or annotation round is not a prerequisite.

Available material includes the [50-case calibration covering 57 answer
texts](explanation-calibration-results.md), [two later materiality
judgments](materiality-boundary-results.md), [ten further reviewed
originals](fresh-human-audit-results.md) and [exact correction
regrades](targeted-corrections-results.md). These are overlapping/versioned
resources, not counts to sum into independent examples. Frozen records retain
image hashes, source comments, answer text/hashes, human events and qualifying
notes. The Breaking Bad/Pride review already contains a KYM reference; its human
judgment remains unclear. That link does not create a new gold label.

Join each actual human judgment to its exact answer version, image, comment
packet and compatible saved model checks. Include all usable records under a
declared eligibility rule before seeing new policy outputs. Preserve repeated
answer versions, shared meme families, ambiguous labels and missing inputs.
Older overall admission labels and model-generated judgments have different
meanings; do not convert them into answer or source-sufficiency gold.

This supports two evaluations:

- **Answer regression:** retain human-ready answers and detect human-confirmed
  wrong/missing connections. Existing answer labels directly support this check;
  no fresh human annotation is needed for unchanged answer/image versions.
- **Evidence-policy effects:** identify decisions that change when the source
  quota is removed or a reference is retrieved, and inspect whether the source
  chain establishes the interpretation. Existing notes may resolve this. Otherwise
  report an unadjudicated evidence question rather than inventing a human label.
  An answer marked ready does not independently certify its research process.

Reuse cached baseline outputs when their exact input/model/policy provenance
fits. Where new comparison is needed, separate the proposed policy on original
evidence from the proposed policy with a newly frozen external-evidence packet.
Keep candidate answers fixed first so rewrites do not conceal checker regressions.
Newly retrieved sources are a dated overlay, not evidence supposedly inspected
in the earlier review. New answer versions need their own evaluation; readiness
does not automatically transfer to an enriched or rewritten explanation.

Before a paid implementation run, inventory reconstructable coverage and freeze
the exact input manifest and resulting maximum call count. Retain a **proposed
$1 total ceiling, one fixed comparison and no repair loop**, with conservative
reservations and reuse of compatible saved results. If the corpus cannot fit
that cap, report the deterministic unfinished portion and required budget before
proposing more work. At proposal time, this required separate authorization from
the completed backfill and no new model calls had been made. The subsequently
authorized [#36 replay](source-evidence-replay-results.md) completed 112 calls
within that $1 ceiling.

Report answer errors against actual labels separately from evidence-sufficiency
changes. Adoption should retain known-ready controls, catch known material defects
and explain newly passing interpretations with traceable support. Existing labels
may not cover wrong-variant links, circular sourcing or strong-reference cases
excluded by old filters. Identify actual gaps after reconstruction; supplement
only a consequential uncovered behavior, using an existing unlabeled example or
a clearly marked technical fixture where appropriate. Neither assistant review
nor a synthetic fixture becomes human gold. Request a small human judgment only
if an unresolved decision truly depends on it; otherwise retain uncertainty.

These are exposed development examples, so this is a retrospective regression
and evidence audit, not an untouched estimate of generalization or archive
accuracy. That limitation does not require a new benchmark for every policy
change. A failure should trigger reassessment rather than repeated tuning on
the same examples.

## Implementation boundary if adopted

Create a new evidence/policy version and additive artifacts. Update acquisition
eligibility, preflight, evidence schemas, citation validation, generation/checking,
reference-answer/scoring metadata, UI and release provenance together. In
particular, audit the archived-comment-count filter so strong low-comment cases
are not excluded before their evidence is examined; retain explicit date/item/cost
bounds. Validate missing links, source dependence, variant mismatches, conflicting
readings, exact replay and preservation.

Primary owns the contract and integration; independent work can cover bounded
source retrieval, schema/check changes, and UI/evaluation fixtures after that
contract is settled. Record matching issue scope before implementation. Old runs
and exact human feedback remain frozen, and the 94 automatic accepts remain
development candidates until separately qualified. This document proposes the
change; it does not adopt it or reopen the completed backfill.

## Investigation performed at proposal time

Read the existing prompts, validators, collection/preflight gates, roadmap and
relevant issue history. Inspected the frozen Seinfeld packet, researched the
original link and accessible KYM/MEL evidence, and obtained an independent
read-only critique of sufficiency, source dependence and variant matching.
Only proposal documentation and a private copy of the user feedback were added.
