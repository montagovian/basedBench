# basedBench Architecture

basedBench is a Python pipeline and review UI for building a meme-understanding
benchmark from public Reddit explanation communities.

## Pipeline

```text
Reddit -> image download -> safety gate -> consensus -> human review
       -> prediction -> judge -> snapshot -> export / Hugging Face push
```

The benchmark target is intentionally narrow: a model receives only the meme
image and must explain the joke. Ground truth is derived from Reddit comment
consensus and then validated by a human reviewer.

## Main Components

- `src/basedbench/cli.py`: Typer command line interface.
- `src/basedbench/app.py`: Gradio review and inspection UI.
- `src/basedbench/config.py`: environment-driven settings.
- `src/basedbench/db/`: SQLite migrations and query helpers.
- `src/basedbench/reddit/`: Reddit and PullPush clients plus image download.
- `src/basedbench/llm/`: OpenAI/Anthropic predictors, judges, and prompts.
- `src/basedbench/pipeline/`: ingest, predict, judge, snapshot, export, and push flows.

## Data Boundaries

Local working data lives under `data/` and is intentionally ignored by git. The
raw SQLite database contains operational tables such as Reddit comments, review
state, LLM call logs, and local image paths. It is not a public release artifact.

Public exports should contain only benchmark-facing fields:

- post ID
- title
- subreddit
- ground-truth explanation
- image file
- model predictions
- judge verdict summaries

Raw comments, authors, review reasons, LLM prompts/responses outside benchmark
predictions, local paths, and API request metadata should stay out of public
dataset artifacts.

## Important Invariants

- Predictors see the image only: no title, comments, Reddit metadata, tools, or
  web search.
- Normal prediction and judging operate on currently validated memes.
- Failed prediction rows are excluded from snapshot export and leaderboard
  helpers.
- SQLite connections run in autocommit mode; use explicit `BEGIN`/`COMMIT` for
  multi-row transactions.
- The review UI should only serve files from the active DB's `data/images`
  directory.
- `basedbench view` is read-only and should not expose review or labeling
  mutation controls.

## Release Gate

Before publishing code or dataset artifacts, run:

```bash
uv run pytest
uv run python scripts/release_audit.py --db data/basedbench.db
```

When validating a generated export, also pass:

```bash
uv run python scripts/release_audit.py \
  --db data/basedbench.db \
  --export-dir export/<snapshot-name>
```
