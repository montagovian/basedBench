# Immutable existing-pool candidate and offline baseline

September 23, 2026. [Draft PR #32](https://github.com/montagovian/basedBench/pull/32)
implements the [plan](release-candidate-plan.md) under
[#10](https://github.com/montagovian/basedBench/issues/10).

## Delivered scope

The existing-pool candidate is frozen with **519 legacy items and zero newly
admitted development items**. Exact answer text, decoded/validated image bytes,
membership, policy, exposure and admission provenance are content-addressed.
Export and image-only input retrieval verify the frozen payload and never join
the live database. Old snapshot APIs and historical records remain available.

The new offline CLI supports `release freeze`, `verify`, `inputs`, `report` and
`export`. Atomic creation refuses existing destinations, damaged images and
incomplete inputs; exports use a public field allowlist and preserve the
mixed-rights `license: other` statement. Reports qualify cached results only when
image, answer, prediction, prompt and scoring versions match. Unresolved items
and missing predictions never count as successful scores.

This milestone made **zero model calls and spent $0**. No checker was promoted,
no database answers were replaced, no collection ran, no PR was merged and no
dataset was published. #10 remains open for qualified additions and a fully
version-bound scored evaluation; the offline engineering milestone is complete.

## Candidate identity and local artifacts

Name: `basedbench-release-candidate-v1`.

- Release schema: `basedbench.release.v1`.
- Policy: `basedbench.release-candidate-policy.v1`.
- Content SHA256: `8dd5778a595dbba4a5c572ac74640fd984554464f2d067fb0cb437255807637c`.
- Membership SHA256: `ab530da7108a38136bec125a30d0864c45653497bfb71f7952aa9a6ef9fac1e3`.
- Normalized evidence SHA256: `6ba3dd37546c825e6b73926eee824c15c1de34fa6c585773a8871bdac27b2887`.
- Tested implementation commit: `251c1a5`.

All runtime artifacts remain local in the original workspace:

| Path | Purpose |
| --- | --- |
| `data/releases/basedbench-release-candidate-v1/` | Verified manifest and 519 exact images |
| `data/basedbench-release-candidate-v1/` | Selection, evidence, private held ledger, provenance inventory, baseline report, image-only inputs and verification |
| `export/basedbench-release-candidate-v1/` | Allowlisted immutable candidate export; no unverified scores inserted |
| `export/basedbench-legacy-history-checkpoint-v1/` | Separately labeled compatibility export preserving historical predictions and rejudgments |

The historical export retains 519 images, 2,785 successful predictions and 10,660
individual judgments across six stored target models. It includes a provenance
note explaining its mixed dataset versions and unproven historical image binding.
Raw comments, authors, operational responses and logs remain omitted.

## Membership, readiness and holds

The original legacy answer pairs still reproduce snapshot ID
`ad24bf870ce6285d`. This is evidence that its answer text has not drifted; it cannot
reconstruct old image hashes. The cohort's admission origin follows its published
human-validated status, with the unavailable individual historical actor/event
record kept unknown. It is exposed legacy evaluation material; no claim is made
about individual models' training exposure. Missing gate history stays unknown.

All **118 development identities remain outside this candidate**:

- The fixed #26/#27 cached pool has 18 identities: eight exact ready versions
  available (six originals, one tentative, and two accepted proposals), one still
  needing repair, one unresolved interpretation and eight unchanged overlap holds.
  Source, content, suitability and duplicate evidence are separate from readiness.
- The June 20–26 pilot has 100 identities, preserving its v2 outcomes of 41 accepts,
  58 deferrals and one rejection. These are development automation outcomes, not
  admissions under a newly qualified production policy. All individual findings
  remain in the private ledger.

These pools are disjoint from each other and the legacy 519. The eight ready
versions retain exact source hashes, frozen packet/journal references and human
event IDs. Their source ledgers hash canonical JSON strings; the release hashes
raw UTF-8 answer text. Both conventions are verified and recorded. Human
readiness does not establish the other gates, and absence of a human label is
not a new mandatory review requirement. Mixed-rights status applies without
inventing a requirement to prove individual ownership before this local freeze.

## Baseline and its limits

The five-model historical panel is unchanged: Claude Opus 4.8, Gemini 3.1 Pro
Preview, GPT-5.5, Muse Spark 1.1 and Grok 4.3. The figures below reproduce **stored
history on legacy member IDs across multiple dataset versions**, using the latest
vote per distinct judge and the existing at-least-two/strict-majority rule. They
are neither a fresh run nor certified scores against the frozen image bytes.

| Historical target | Correct / scored | Stored accuracy | Unanimous / multi-judge |
| --- | ---: | ---: | ---: |
| Claude Opus 4.8 | 312 / 519 | 60.1% | 457 / 519 |
| Gemini 3.1 Pro Preview | 442 / 519 | 85.2% | 464 / 519 |
| GPT-5.5 | 419 / 519 | 80.7% | 465 / 519 |
| Muse Spark 1.1 | 395 / 519 | 76.1% | 467 / 519 |
| Grok 4.3 | 254 / 519 | 48.9% | 448 / 519 |

All five member histories have 519 predictions and zero unresolved majority votes.
The separate subset whose stored `dataset_version` equals the legacy snapshot ID
contains **541 predictions**: 2 Claude, 11 Gemini, 8 GPT, 518 Muse and 2 Grok. The
report preserves that subset and the full model/version breakdown separately.
Matching a dataset version still does not prove a historical image hash or the
exact ground-truth input to each judge call.

Consequently, **zero cached predictions and zero judgments qualify for current
frozen-content scoring**. For each of the five panel models, the current legacy
and combined report has 519 missing predictions, scored denominator zero and
null accuracy/agreement. The development cohort has zero members. The report
does not turn missing results into errors or successes. Prediction/judge prompt
IDs remain unqualified rather than being fabricated from unrelated call records;
the implemented aggregation version is `majority-v1`.

A new scored evaluation needs an explicit provider panel, prompt/judge versions
and a separate spending cap. The historical baseline remains useful for reference
but cannot fill that provenance gap retroactively.

## Verification

The clean checkpoint `7af35ba` passed 507 tests, Bandit, dependency and secret
checks, database privacy/correctness and the legacy export audit. The initial
checkpoint attempt had failed; six vulnerable locked dependencies were patched,
six inspected secret-scanner false positives were recorded, assessment-label
Bandit false positives were narrowly annotated and four runtime guards made
explicit. No security rule was globally disabled by this work.

The complete implementation test run passed **554 tests**, with two upstream
Typer/Click deprecation warnings and no skipped tests. Bandit, dependency audit,
database and export checks also passed. The first full implementation audit
flagged a deliberate privacy-test sentinel as a possible secret; its exact
non-credential value was inspected and recorded in the baseline before the final
clean gate rerun.

The real candidate replays byte-for-byte: **520 frozen files, 526 exported files,
and the complete baseline report** match a second creation. Every copied image
matches its pre-freeze inventory hash, all 519 image-only input records have only
identity/path/hash fields, and the original **24,370 inventoried files remain
byte-identical**, including the database, frozen feedback, prior runs and both
dirty UI files. The final preservation inventory and verification JSON are local.

An integration test changes a disposable live database answer and deletes its
source image after freezing; export and evaluation inputs remain unchanged.
Other tests cover bad checksums/truncation, manifest/image tampering, missing
assets, overwrites, privacy, exact cache mismatches and judge denominators. A
first real freeze rejected an extra adapter metadata field without leaving a
partial release; the corrected adapter now exercises the full freezer contract.
Its rejected preparation remains locally labeled `-pre-integration`.

Legacy status and duplicate-cleanup dry-run checks used a disposable DB copy
because those commands open writable connections. The dry-run calculated 146
fingerprints and 13 possible duplicate exclusions in that copy; none were applied
to the original database. There were no frontend changes to browser-test.

## Next decision

[#9](https://github.com/montagovian/basedBench/issues/9) remains unlaunched. The
[bounded proposal](chronological-expansion-proposal.md) specifies a possible
June 27–July 27 UTC window, 1,000-candidate ceiling, source/overlap/retry accounting
and $5 total model cap. These are proposals, not user-approved parameters. It
retains the denied-source and missing-image/comment coverage gaps; model/policy
qualification is unresolved. No further prompt-tuning loop or broad human queue
was added to this milestone.
