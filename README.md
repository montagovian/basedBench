---
title: basedBench
emoji: 🃏
colorFrom: indigo
colorTo: pink
sdk: gradio
sdk_version: "5.0.0"
app_file: app.py
pinned: false
license: mit
short_description: VLM Meme Understanding Benchmark
---

# basedBench

A benchmark for evaluating how well Vision-Language Models understand internet memes.

Ground truth is derived from Reddit comment consensus (≥3 substantive comments agreeing
on the same specific explanation), not synthetic labels. Each model prediction is judged
correct/incorrect by an LLM judge against the consensus explanation.

This is the fifth iteration — a Python rewrite of the Rust basedBench4 unified around
the HuggingFace ecosystem (Datasets + Spaces).

## Pipeline

```
Reddit → quality gate → consensus → human review → prediction → judge → snapshot → HF Hub
```

- **Reddit fetch** (`r/ExplainTheJoke`, `r/PeterExplainsTheJoke` by default)
- **Quality gate**: cheap text-only LLM pre-filter that rejects non-memes
- **Consensus**: gpt-4o-mini analyzes top comments, must agree on a specific explanation
  passing 10 stages of validation (confidence ≥ 0.6, len ≥ 100, no vague phrases, etc.)
- **Review**: Gradio UI to validate/exclude individual memes before they become ground truth
- **Predict**: any OpenAI or Anthropic vision model explains each validated meme
- **Judge**: strict LLM judge compares prediction to ground truth → correct/incorrect
- **Snapshot**: freezes the validated set as a content-addressed dataset version
- **Push**: publishes the snapshot to HF Hub (memes + per-model predictions + leaderboard)

## Quick start

```bash
uv sync
cp .env.example .env  # fill in REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, OPENAI_API_KEY

uv run basedbench ingest --limit 20
uv run basedbench review              # validate in Gradio
uv run basedbench predict gpt-5.5
uv run basedbench judge
uv run basedbench status
```

## Snapshot and publish

```bash
uv run basedbench snapshot create --name v0.1 --description "initial cut"
uv run basedbench snapshot list
uv run basedbench export v0.1 --output ./export
uv run basedbench push v0.1 --repo your-username/basedbench
```

## Commands

| Command | Description |
|---|---|
| `ingest` | Fetch posts, download images, run quality gate + consensus |
| `predict <model>` | Run a VLM over validated memes |
| `judge` | Run the LLM judge on unjudged predictions |
| `status` | Pipeline state + next-step hints |
| `traces` | Inspect every recorded LLM call (filter by role/post/session/error) |
| `run <model>` | ingest → predict → judge → status (one shot) |
| `snapshot create/list` | Freeze and inspect validated sets |
| `export <snapshot>` | Write JSONL + images + dataset card to disk |
| `push <snapshot>` | Publish to HuggingFace Hub as a multi-config dataset |
| `review` | Launch Gradio UI (review queue, browse, prediction comparison) |

## Status

Active port from basedBench4. Test suite: `uv run pytest`.

## License

MIT
