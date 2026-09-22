# Direct claim comparison results

September 22, 2026 · [Issue #18](https://github.com/montagovian/basedBench/issues/18)

**Do not promote this variant or proceed to unseen admission validation.** It
detects a concrete quiz-name omission and correctly holds the dog-pun support
shortfall, but misses other intent/support problems, challenges human-ready
answers, and loses nine cases to its quotation contract. This is a completed
negative experiment, not a reason to tighten suitability or discard the pilot.

The [predeclared comparison](claim-comparison.md) used 20 previously exposed
development cases, a fresh baseline check and one direct-check variant, with at
most one variant repair and fresh verification. All **48 GPT-5.6 Luna calls**
completed for **$0.12066741** (12.1¢; conservative accounting $0.12067461), below
the $0.25 total cap. No retries, resampling, prompt changes, fallback, provider
failures, pending calls, unknown usage or allowance violations occurred.

## Paired results

| Measure | Existing checker | Direct variant |
| --- | ---: | ---: |
| Original-answer pass | 15 | 9 |
| Original-answer fail | 5 | 4 |
| Evidence uncertainty | 0 | 1 |
| Initial technical error | 0 | 6 |
| Pilot retention originals passed | 7/7 | 6/7, one technical error |
| Historical human-ready originals passed | 1/3 | 1/3 |
| Historical human-defect originals failed | 3/3 | 1/3, two technical errors |

The variant attempts four repairs. One passes fresh verification; three encounter
quote-validation errors. Final states are ten model-supported answers (nine
unchanged and one rewrite), nine technical errors and one unresolved evidence
hold. These are workflow outcomes, not an accuracy estimate. In particular, the
one verified rewrite starts from a **human-ready** answer, so it must not be
counted as successfully repairing a known human defect.

## Concrete findings

- **Quiz names:** baseline passes the generic account. The direct check fails it
  for missing name decodings. The repair adds two references but still leaves
  essential wordplay unexplained. Raw verification notices the Norfolk & Chance
  omission, then fails exact excerpt validation. Detection improves; the answer
  does not become a verified complete repair.
- **Dog-supplement pun:** baseline passes. The variant keeps the plausible cocaine
  reading but counts only two substantive comments, excluding the reaction,
  amplifier aside and extra joke. This is a correct application of the frozen
  evidence rule, not an intrinsic joke or answer rejection.
- **Intent:** the Israel/fashion answer still passes an unqualified mockery
  attribution despite competing interpretations. The raw sub-5 audit recognizes
  that parody is disputed and the visible mechanism can be stated neutrally,
  but fails source-span validation. That useful diagnosis is not a valid result.
- **Algae:** both checkers still count a different whole-USA-prison reading as a
  third supporter of the algae/Alligator-Alcatraz pun. Literal quotation does not
  establish that comments support the same explanation.
- **State puns and two cows:** raw findings notice missing parts, but remain
  fallible. The state audit retains the contested Mary ownership wording. The
  cow audit invents an Irish poverty explanation and misattributes a quotation;
  other panel decodings are also too vague or inaccurate. Technical errors must
  not be scored as successful semantic detection.
- **Historical defects:** the Freddie draft usefully restores the crowded-bed
  implication and pictured night-it-happened reply, with HIV/AIDS and fiction
  qualification. It is inspected as a useful draft, but verification is invalid.
  Harry Potter's raw audit notices the missing greatest-achievement comparison.
  R.E.M.'s raw audit rejects the commenter-only altered title but again misses
  the actual person inserted in the corner. Neither invalid audit produces a repair.

## Quotation reliability and retention

The new contract requires literal evidence excerpts for every comment, including
irrelevant link-only comments. That design is too brittle. Of nine errored cases:

- Three fail on copied URLs in context-only comments (Gumball, Freddie verification
  and Sonic verification), including HTML entity decoding and altered parameters.
- Three fail on comment punctuation, Markdown/quotation removal or ellipses
  (state puns, sub-5 and quiz verification).
- Two use nonliteral answer spans (Harry's abbreviated name and R.E.M. punctuation).
- One assigns an absent statement to a comment (two cows), a material attribution error.

The stricter parser prevents accepting invented evidence, but many failures above
are formatting/annotation errors rather than demonstrated wrong answers. Simply
counting all holds as quality improvements would be misleading. No parser or
prompt was loosened after seeing these results, and no invalid output was rescued
into an approved answer. All raw output remains inspectable.

Six pilot positives retain clean passes: Luke/stormtrooper, the XM8 comparison,
Coke/Mentos, the four-part rebus, literature stereotypes and BC time travel.
Gumball has no inspected material explanation defect and is lost only to a URL
excerpt error. The pilot retention target is narrowly met at 6/7.

Human-ready retention fails: golf passes, while **both arms** challenge the
Sonic/Minecraft analogy and domino chain. The direct checker demands extra
replacement-character detail in Sonic; its rewrite also blurs a proposed casting
change into two redesigns. The domino rewrite is plausible and passes verification,
but the original human-ready judgment remains unchanged. This is an unnecessary
rewrite relative to that judgment, not evidence that the human label was wrong.

## Decision and verification

The decoding, intent, support, human-ready retention and technical-reliability
targets are not met. Stop this variant. **No unseen model run or chronological
expansion follows from this result.** The existing checker remains the baseline,
with its known limitations; neither source-first maps nor the quote-heavy contract
is promoted. If another improvement is pursued, first simplify annotation demands
and separate harmless source formatting from substantive support, while preserving
human-ready tolerance. That would require a separately declared comparison.

Suitability and the three-comment rule are unchanged. Assistant findings remain
development hypotheses, not new human gold. This result does not establish that
ordinary simple examples are unsuitable or require a broad human-review queue.

Local run: `data/backfill/claim-eval-v1`. Separate analysis:
`data/backfill/claim-analysis-v1`, containing 20 inspections, paired summaries and
a read-only casebook with both arms, repairs, verification and original labels.
Browser verification loaded all 20 images. Offline replay made zero provider
calls and preserved all 121 run files byte-for-byte, excluding the lock.

The shared follow-up preservation check retained **11,085 prior files** unchanged,
including #16/#17 runs, corpus/feedback records and the user's app/test edits.
**455 tests passed** across 454 sandbox-compatible tests and the separately run
localhost test. The latter needs permission to bind its test server.
