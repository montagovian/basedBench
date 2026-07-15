# Release Readiness

This document records the public release policy and the current open-source
quality gate.

## Release Gate

Run these before publishing code or dataset artifacts:

```bash
uv run pytest
uv run python scripts/release_audit.py --db data/basedbench.db
uv run basedbench status
uv run basedbench cleanup --duplicate-images --dry-run
uv run basedbench export <snapshot-name> --output export/<snapshot-name>
uv run python scripts/release_audit.py --db data/basedbench.db --export-dir export/<snapshot-name>
```

The release audit is non-mutating. It fails if the Git tree is dirty, private
files are tracked, new secret findings appear, Bandit/pip-audit/pytest fail, DB
privacy checks fail, or an export includes forbidden fields.

## Artifact Policy

Do not publish:

- `data/basedbench.db`
- local image cache paths outside the generated export
- raw Reddit comments or authors
- review rows, review reasons, consensus eval notes, or gate feedback
- `llm_calls`, API request IDs, prompts, raw responses, or local paths
- `.env`, `.env.*`, caches, logs, coverage output, or scratch audit output

Public dataset exports may include:

- `post_id`
- `title`
- `subreddit`
- `ground_truth`
- copied image files
- model predictions
- individual judge verdicts and reasoning, including historical rejudgments
- derived consensus fields, judge agreement statistics, and leaderboard totals

## Dataset Rights Statement

Generated dataset cards must keep the Hugging Face metadata license as `other`
because public exports contain mixed-rights material.

The card should state that maintainer-created materials are available under the
MIT License, including the benchmark code, schema, export format, evaluation
prompts where applicable, benchmark-specific metadata, leaderboard tables, judge
verdicts and reasoning, and maintainer-authored documentation/annotations to the
extent the maintainers own or control them.

The card should separately state that meme images, Reddit titles, subreddit
names, post IDs, cultural references, logos, characters, screenshots, and other
source artifacts may be owned by third parties; BasedBench does not claim
ownership of those materials; and the MIT License for this repository does not
apply to those third-party materials.

The card should explain the publication rationale: third-party meme/source
materials are included for research, criticism, commentary, and benchmark
evaluation under a fair-use rationale. The use is transformative because the
images are test stimuli for evaluating whether models understand the intended
joke, not substitutes for the original posts or images. The export should keep
omitting raw comments, authors, internal prompts/responses, local paths, and
operational logs.

## Current Findings

- Blocker/High: none known after the current release audit work lands.
- Medium: Bandit `B608` is skipped in the release runner because this codebase
  uses fixed SQL fragments for optional filters and `IN` placeholder lists. User
  values remain bound parameters. Revisit this if future code accepts arbitrary
  SQL column names, operators, or order clauses from users.
- Medium: raw dataset images are third-party Reddit-derived media, not MIT
  licensed project code. The generated dataset card marks the dataset license as
  `other` and explains that raw comments/authors are intentionally omitted.
