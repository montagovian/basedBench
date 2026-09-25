# basedBench Agent Notes

## Benchmark Task Definition

basedBench evaluates whether a model **gets the joke** in a meme. It does not
evaluate whether a model can produce a psychological or aesthetic theory of why
something is funny.

When editing prompts, docs, evals, or review UI copy, preserve this distinction:

- Correct predictions identify the relevant people, events, memes, media,
  phrases, visual details, or cultural references.
- Correct predictions reconstruct the intended setup, implication, contrast,
  inversion, irony, wordplay, or other mechanism a viewer must notice to
  understand the meme.
- Judges should compare the model's explanation to the consensus ground truth
  and ask whether it got the same joke.
- Do not require models to explain why humor works, why humans feel amused, or
  any general theory of comedy.

The Reddit comments that create consensus are evidence that humans recovered the
intended joke. They are not expected to provide a formal account of humor.

## Development

- Use `uv` for Python package management and command execution.
- Run `uv run pytest` before release-facing changes.
- For frontend/UI changes, verify the running app in a browser whenever
  practical, especially after Gradio layout or callback changes. Do not rely
  only on import/build checks for UI work.
- Keep local working data under `data/` and generated exports under `export/`;
  neither is a public repo artifact.
- Do not commit secrets, raw SQLite databases, local images, caches, or LLM call
  logs.

## Planning, Issues, and Delegation

- For substantial work, first read the roadmap, relevant GitHub issues, results,
  and affected code. Write a detailed implementation plan under `docs/` before
  implementation or paid experiments. Define the deliverable, non-goals, evidence,
  interfaces/data contracts, dependencies, file ownership, validation, and done
  criteria. Resolve the shared design before splitting implementation work.
- When using `gh` to manage project work, reuse existing issues where they fit;
  create scoped issues for meaningful missing work before implementing it. Use
  parent issues for milestones and child issues for independently deliverable
  parts. Include the plan, dependencies, acceptance criteria, and validation.
  Keep issue status and `docs/roadmap.md` aligned with verified outcomes. Avoid
  creating an issue for every minor edit or duplicating an existing issue.
- Once the plan is concrete, actively delegate substantial independent work to
  subagents. This is an explicit standing request for parallel agent work, not
  just optional final review. Prefer Luna for well-specified implementation,
  fixtures, inventories, documentation, and bounded analysis; use Sol for harder
  implementation, integration, or review. Use available model IDs, such as
  `gpt-6-luna` and `gpt-6-sol`, and do not change benchmark model configurations
  merely because those models are used as coding agents.
- Give each subagent the relevant issue/plan, exact scope, inputs, interfaces,
  owned files, preserved artifacts, acceptance criteria, and required checks.
  Parallelize disjoint changes after agreeing on shared contracts; serialize
  overlapping edits or use isolated worktrees. The primary agent owns overall
  design, coordination, integration, and final validation, and should do useful
  complementary work while subagents run. Small or inseparable tasks can remain
  local; explain that choice briefly when substantial delegation was expected.
- Plan to reach a useful milestone, not an indefinite sequence of small tuning
  experiments. State an experiment's hypothesis, controls, scope, spending cap,
  decision rule, and stopping condition up front. Repeated negative results
  should trigger a milestone-level reassessment rather than automatic retuning.
- Preserve frozen runs, exact human feedback, and unrelated working-tree edits.
  Assistant inspection flags are development hypotheses, not human gold. Keep
  answer readiness separate from source support, content, suitability, and
  duplicate clearance; do not tighten suitability to manufacture agreement.
- Planning and delegation do not add approval gates. Proceed within the user's
  authorized scope; only surface missing decisions that materially affect that
  scope, spending, publication, or correctness. Keep making independent progress
  while a genuinely necessary decision is pending.
