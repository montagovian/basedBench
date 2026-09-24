# Jev decomposition experiment results

September 24, 2026. Related to [issue #38](https://github.com/montagovian/basedBench/issues/38)
and [draft PR #39](https://github.com/montagovian/basedBench/pull/39).
**The issue remains open for human review and explicit closure approval.**

The native batching premise holds for this workload: 49 typed decisions took a
median 119 ms per Jev request. The complete experiment made 706 provider calls
and 16,294 Jev judgments for an estimated **$0.107015**, within the approved $5
cap. Fine-grained features produced some useful corrections, but the combined
classifier still passed 11 of 17 human-repair answers and rejected 16 of 77
human-ready answers. Keep the experimental infrastructure; do not adopt this
classifier as an automatic answer-quality gate.

## Design and denominators

The [pre-implementation plan](jev-decomposition-plan.md) links the official
TypeSafe cookbook, community implementations and primary research. The finite
comparison included broad text and image-observation controls, 48 atomic Noul
predicates, a complete answer-span/comment support matrix, a focused second pass,
fixed learned combinations, repeats and individual-question measurements. No
questions, thresholds or model requests were changed after outcomes arrived.

All 99 exact answer/evidence versions remain accounted for: 88 posts, 86 known
groups, 78 ready, 18 repair and three unclear. The image-aware matched comparison
contains **94 known-label versions in 81 groups: 77 ready and 17 repair**. One
ready animated image was held by the frozen interface. One repair case's dense
image exhausted the helper's 2,000-token output allowance; its image-aware arms
were held without a retry. The three unclear labels remain visible and were
excluded from fitting and accuracy. All 99 text-only controls completed.

The 87 unique supported images received image-only GPT-6 Luna requests; 86
observations completed. Every image-aware arm reused the same frozen observation.
Jev received candidate answers, comments and observations, never human labels or
notes. Its model was pinned to `jev-1.13.0`. Learned models used the predeclared
five group-separated folds, training-only scaling, family-version weights and
fixed regularization. These are exposed development cases, not a new test set.

## Quality on the same 94 known cases

The counts below use native three-way Choice decisions for broad/focused checks,
the predeclared atomic rule, and 0.5 out-of-fold decisions for learned models.
An uncertain result is neither a caught repair nor a rejected ready answer.

| Method | Ready passed / 77 | Ready failed | Repair caught / 17 | Repair passed | Uncertain |
|---|---:|---:|---:|---:|---:|
| Broad text control | 75 | 2 | 0 | 17 | 0 |
| Broad with observation | 67 | 10 | 2 | 15 | 0 |
| Broad Choice inside 49-question batch | 67 | 10 | 3 | 14 | 0 |
| Frozen atomic rule | 8 | 2 | 1 | 0 | 83 |
| Focused broad Choice | 66 | 11 | 2 | 15 | 0 |
| Learned atomic features | 60 | 17 | 5 | 12 | 0 |
| Learned atomic + matrix + focused features | 61 | 16 | 6 | 11 | 0 |

The combined model's balanced accuracy was 57.3%, versus 49.4% for the broad
image-aware control; AUROC was 0.593 versus 0.553. That trades four additional
caught repairs for six additional rejected ready answers. At the fixed 0.8/0.2
abstention route, the combined model decided 53 of 94 scored cases (55.2% of all
96 known labels), made 13 errors, passed six repair cases and correctly failed
only one. The atomic rule's apparent conservatism came from deferring 83/94
cases; it has no independent calibrated probability.

The image observation changed 12 broad decisions: ready passes fell from 75 to
67 while repair detections rose from zero to two. Adding 48 parallel questions
changed the bundled broad Choice on only one known case. Focusing evidence
changed two bundled Choices, both away from the human label. The selector
reduced the evidence in 78/97 image-aware cases, from 910 to 641 comment
instances overall; it was doing substantive filtering, not simply copying the
full evidence. Relevance and apparent contradiction did not establish a
comment's truth or importance to the intended joke.

## Observed cost, latency and stability

| Stage | Calls | Jev judgments | Accounted cost | Median request latency |
|---|---:|---:|---:|---:|
| Broad text | 99 | 99 | $0.004547 | 111 ms |
| Image observation | 87 | — | $0.037615 | 5,146 ms |
| Broad with observation | 97 | 97 | $0.005353 | 179 ms |
| Atomic batch | 97 | 4,753 | $0.009517 | 119 ms |
| Evidence matrix | 109 | 5,320 | $0.034510 | 159 ms |
| Focused batch | 97 | 4,753 | $0.008976 | 129 ms |
| Atomic repeats | 24 | 1,176 | $0.002356 | 134 ms |
| Single predicates | 96 | 96 | $0.004695 | 99 ms |

The conservative ledger accounts for $0.107570 versus the $0.107015 usage-based
estimate, principally conservative helper cache accounting. No unknown usage or
pending calls remain. All 619 Jev calls validated; the one helper incomplete
response is retained. Provider latency totaled about 9.55 minutes, mostly the
image helper; timings are observed serial API timings, not model compute.

Across 12 selected groups, eight individual predicates took a median total
851 ms and cost about $0.000400 per group; the full 49-question batch took a
median 113 ms and about $0.000099. This compares eight individual requests with
a 49-question batch, so it does not isolate an eight-way batching speedup.
Across 24 repeat pairs, the broad Choice never changed; the atomic threshold
rule changed once. Consistency is not independent evidence of correctness.

## Concrete review examples

The local review page retains every image, unchanged answer, exact human note,
method decision and selected comment. Its twelve-case shortlist includes both
apparent wins and learned-model errors. The following are assistant inspections,
not new human labels:

- **`1jley2r-5021e767b2de5d4b`**, Freddie Mercury: the combined model fails the
  answer where the broad check passes it. This agrees with feedback that the
  answer misses the particular implied event and adds an irrelevant lyric.
- **`1tzz3h1-7697859daf77dafd`**, hidden face: the combined model catches the vague
  answer, while broad and focused Choices pass it. The observation itself misses
  the face in the closet, so this is also a shared visual-evidence weakness.
- **`1u9z5ho-4237a9eb2faa29be`**, RE4 inventory: broad/focused checks fail the
  answer, but the combined model passes it at 0.847. The answer discusses square
  packing while omitting the game-specific connection raised in the feedback
  and comments. Supported fragments do not prove the whole joke was recovered.
- **`1u8acxi-89c345571e8428b9`**, the human-ready revised political/celebrity answer: the combined
  model rejects it at about 0.004 while the broad check passes it at 0.94.
  Several comments support the answer; strong disagreement/alternative signals
  appear to become a false alarm. The private inspection records the exact version.
- **`1u2t76j-dbc2d375fe40bd8c`**, cabbage: focusing turns a ready answer from pass
  to fail. The selected material retains both the direct sauerkraut explanation
  and a tenuous alternative reading plus scientific detail. Treating every
  apparent conflict as equally relevant can distract from the intended joke.

The repair-label audit also found three versions with blank notes, unresolved
readings in two other notes, and a benchmark-fit concern among the repair
labels. Those records were preserved, not relabeled after seeing results. The
RE4 note asks about a reference absent from the answer; that absence is not a
provenance mismatch. Correlated versions and these note qualifications limit
how precisely the headline metrics measure answer adequacy.

## Decision and verification

This completes the authorized finite experiment, not qualification of an
admission policy. The cheap native decision substrate is useful. The current
48 generic adequacy predicates plus learned aggregation do not reliably
recover missing joke mechanisms. A future design should test concrete,
meme-specific competing interpretations and required decoding steps against
verified evidence, with absence-of-support distinct from contradiction. First
review the present wins, false alarms and shared observation failures; do not
start another tuning run or change production policy automatically.

All 630 tests pass; the final report refinements pass their focused tests.
Security and whitespace checks are clean. Completed replay preserved the exact
records-manifest hash with both provider-client constructors blocked: zero new
calls. All 39,381 protected prior files remain unchanged. Review rendering
preserves identical case outputs, fold assignments and numeric summaries.
Raw images, calls, human notes and result files remain private under
`data/backfill/jev-decomposition-v1/`. No release membership, active checker or
human judgment changed. Issue #38 stays open awaiting human review.
