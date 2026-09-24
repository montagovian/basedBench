# Proposal: evidence sufficient to recover the joke

September 24, 2026. **Proposed, not adopted.** Parent context: #9; follows the
[chronological results](chronological-backfill-results.md). No code, active policy,
paid experiment, frozen result, human label or release membership changes.

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

## One bounded validation before adoption

Propose a fixed 20-case development calibration, chosen before new judgments:
four thin-comment/strong-reference examples (including Seinfeld), four existing
well-supported controls, four image/comment-only jokes, four misleading-link or
wrong-variant examples, and four disagreements/minority embellishments. Use real
available cases and record selection limits; if an appropriate KYM-linked example
cannot be located, leave that slot unresolved rather than invent the user's case.
Preserve known human labels and distinguish them from new assistant hypotheses.

Freeze images, comments, candidate answers and external evidence separately.
Compare (A) the current policy on original evidence, (B) the proposed policy on
that same evidence, and (C) the proposed policy with verified external evidence.
This separates the effects of the threshold change and additional information.
Keep candidate answers fixed for the first comparison so better rewrites do not
conceal evidence-check failures. Unsupported historical embellishments should
remain failures under all conditions unless the new evidence actually supports
them.

The proposed paid comparison ceiling is **$1 total, at most 60 new check calls,
no repairs, one fixed round**, with conservative reservations. This is a future
proposal, not remaining authorization from the completed $10 backfill. Stop at
the limit or a source/provider failure; preserve missing results and do not
replace difficult cases. No paid calls were made for this proposal.

For adoption, require recovery of genuinely supported reference cases, retention
of the known-ready controls, and no newly accepted unsupported interpretation in
the reviewed trap/control set. Material disagreements must be explained, with a
small targeted human calibration where no existing judgment resolves them; no
whole-archive human queue is proposed. Report false passes, false deferrals,
reference omissions, access failures and cost separately. This small diagnostic
exercise cannot establish a population error rate. A failure triggers a policy
reassessment, not repeated tuning on the same sample.

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

## Investigation performed

Read the existing prompts, validators, collection/preflight gates, roadmap and
relevant issue history. Inspected the frozen Seinfeld packet, researched the
original link and accessible KYM/MEL evidence, and obtained an independent
read-only critique of sufficiency, source dependence and variant matching.
Only proposal documentation and a private copy of the user feedback were added.
