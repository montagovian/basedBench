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
- judge verdict summaries and leaderboard totals

## Current Findings

- Blocker/High: none known after the current release audit work lands.
- Medium: Bandit `B608` is skipped in the release runner because this codebase
  uses fixed SQL fragments for optional filters and `IN` placeholder lists. User
  values remain bound parameters. Revisit this if future code accepts arbitrary
  SQL column names, operators, or order clauses from users.
- Medium: raw dataset images are third-party Reddit-derived media, not MIT
  licensed project code. The generated dataset card marks the dataset license as
  `other` and explains that raw comments/authors are intentionally omitted.
