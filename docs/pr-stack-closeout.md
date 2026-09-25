# PR stack closeout

The user approved the proposed closeout of PRs #32, #35, #37, #39 and #42 after
reviewing the key choices. This records the execution contract. GitHub is the
source of truth for the resulting merge/issue state.

## Accepted decisions

Retain the engineering and reproducible research code. The source-evidence and
Jev results do not promote an automatic admission or comment-filtering policy.
The GEPA investigation is complete, but its stopped optimization attempt remains
inconclusive. Preserve all frozen runs and exact human feedback.

Close #38 and #41 as completed experiments and #40 as completed investigation,
explicitly retaining the stopped paid run's limits. Keep #9 and #10 open for
coverage/qualification and release work. Keep proposed VLM experiment #43 open;
this approval does not start it. No dataset membership, database, publication,
model calls or user UI edits are part of the closeout.

## Integration and ownership

- Primary: refresh remote heads; confirm the linear ancestry and current main;
  run the existing full release audit from the clean stack tip; preserve local
  data and unrelated edits; integrate any concrete findings; merge in order;
  verify remote main content and update issue/PR status.
- Independent review agent (Sol): read-only review of shared runtime changes in
  CLI, database queries, archive adapter, release commands, release snapshot and
  release report. Check legacy compatibility, unintended default adoption,
  privacy boundaries and content binding. Return actionable findings with lines.
- Independent review agent (Sol): read-only review of the experimental provider
  boundaries and review servers, especially key handling, cost stops, default
  activation and exports. Distinguish blockers from historical experiment limits.

Review agents own no edits. Keep new work on the existing stack branch; do not
modify frozen inference code merely to tidy it. Fix a real blocker if found and
record any effect on reproducibility before continuing. No new issue is needed
for this administrative closeout of existing tracked work.

## Checks and execution

Use uv. Run the existing release audit including full pytest, tracked-file
privacy/hygiene, secret scan, Bandit and dependency audit; verify the original DB
read-only and existing immutable candidate export. No new export or model run is
needed. Source hashes and the unrelated main-worktree changes must remain intact.
Record logs under private `data/backfill/pr-stack-closeout-v1/`.

Merge with merge commits, retaining source branches, in this order:
#32 -> #35 -> #37 -> #39 -> #42. After each parent merge, explicitly retarget the
next PR to main, verify its exact head and current mergeability, mark ready and
merge without bypassing repository requirements. Preserve ancestry rather than
squashing away the stack's shared commits. Stop on unexpected remote changes,
conflicts or failed checks and resolve them before continuing.

Done criteria: five PRs report merged; remote main's final tree matches the tested
stack tip; #38/#40/#41 have the correct closing explanations; #9/#10/#43 remain
open; no raw data is committed and the original local edits remain untouched.

## Final integration gate

The full release audit passed on code commit `5bc8383`: 742 tests passed, one
existing private-data skip; tracked-file hygiene, exact secret baseline, Bandit,
dependency audit, read-only database correctness/privacy and the existing
519-item immutable export checks passed. Both independent scoped reviews found
no merge-blocking runtime, provider or review-server issue.

The first audit exposed a Bandit false positive for a user-facing verdict label
and an isolated-checkout image lookup mismatch. The corrective commit annotates
only that B105 line; no model request or policy changes. A local ignored image
symlink points the read-only database check to the original image directory.
No data or audit rule was weakened or rewritten. The second audit passed in full.
All 4,389 protected local files, including the database, prior runs, feedback,
exports and unrelated UI edits, remain byte-identical. Only this closeout record
and the roadmap are updated after the passing code audit.
