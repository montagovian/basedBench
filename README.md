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
Reddit → safety gate → quality gate → consensus → human review → prediction → judge → snapshot → HF Hub
```

- **Reddit fetch** (`r/ExplainTheJoke`, `r/PeterExplainsTheJoke` by default; recent
  posts via `--time-filter`, historical date ranges via `--after-date/--before-date`
  over pullpush.io)
- **Safety gate**: text-only LLM pre-filter that drops content unfit for a public
  dataset (explicit sexual content, slurs, hate, doxx). Keeps edgy/dark/political humor.
- **Quality gate**: cheap text-only LLM pre-filter that rejects memes with no
  recoverable meaning (e.g. a known phrase scrambled into pure nonsense)
- **Consensus**: `gpt-5.4-mini` analyzes top comments, must agree on a specific
  explanation passing 10 stages of validation (confidence ≥ 0.6, len ≥ 100, no
  vague phrases, etc.)
- **Review**: Gradio UI to validate/exclude individual memes before they become ground truth
- **Predict**: any OpenAI or Anthropic vision model explains each validated meme
  (image only — no comments, no title, no web search)
- **Judge**: every prediction is scored by **each** judge model
  (`gpt-5.4-mini` + `claude-sonnet-4-6` by default) → correct/incorrect, with a
  cross-judge agreement rate as a robustness signal
- **Snapshot**: freezes the validated set as a content-addressed dataset version
- **Push**: publishes the snapshot to HF Hub (memes + per-model predictions + leaderboard)

The gates and consensus are deliberately tunable — see [Feedback loops](#feedback-loops)
for how flagged failures drive prompt/model improvements without silent regressions.

## Quick start

```bash
uv sync
cp .env.example .env  # fill in REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, OPENAI_API_KEY

uv run basedbench ingest --limit 20
uv run basedbench review              # validate in Gradio
uv run basedbench predict gpt-5.5
uv run basedbench judge
uv run basedbench status

# quick end-to-end smoke test on a bounded, unreviewed batch
uv run basedbench tracer --fetch 12 --target-consensus 5 --predict gpt-5.5
```

## Feedback loops

The pipeline's automated decisions — the gates, consensus, and the consensus
*gloss* itself — are wrong sometimes. Two feedback loops turn those mistakes into
a labelled corpus you use to improve the prompts, instead of tuning from intuition.

The golden rule for both: **retune a prompt against the real flagged cases, not
your memory of them.** Before committing a prompt change, re-run it over the
flagged set *and* a sample of known-good memes, and confirm it fixes the failures
without regressing the good ones.

### 1. Consensus gloss quality — "AI Gloss Failures"

When the consensus explanation exists but is *wrong* (misses the joke, merges
incompatible readings, ignores a linked source):

1. In the **Review Queue** tab, open the **🚩 Flag this meme's ground-truth**
   accordion. Mark it `wrong` / `partial` / `correct`, tag the failure modes, and
   optionally write the canonical explanation it *should* have produced.
2. Flagged memes collect in the **AI Gloss Failures** tab (a regression set).
   The current gloss is snapshotted at flag time, so you can tell whether a later
   change actually fixed it.
3. `basedbench regression-eval` re-runs consensus on the flagged set with the
   *current* prompt/model and shows old vs. new vs. canonical side-by-side —
   read-only, so it never mutates ground truth.

### 2. Filter decisions — "Filter Misfires"

When a meme was *excluded* (or *kept*) by the wrong call — the safety/quality
gate dropped a good meme, kept a bad one, or consensus missed a real agreement:

1. In the **Inspect** tab, browse **all** content (including excluded memes) in
   the rich review view. Each meme shows the gate/consensus model's own verdict
   and reasoning, so you can judge whether the decision was right.
2. Open the **🚩 A filter got this wrong** accordion, pick which filter erred
   (it defaults to whichever acted on the meme), and say what should have happened.
3. Flagged misfires collect in the **Filter Misfires** tab, grouped by gate —
   the evidence base for the next gate-prompt revision.

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
| `ingest` | Fetch posts, download images, run safety + quality gate + consensus |
| `predict <model>` | Run a VLM over memes that need a prediction |
| `judge` | Score predictions — each is judged by every configured judge model |
| `status` | Pipeline state + next-step hints |
| `tracer` | Bounded fetch → gates → consensus → prediction smoke test; optional `--judge` |
| `traces` | Inspect every recorded LLM call (filter by role/post/session/error) |
| `run <model>` | ingest → predict → judge → status (one shot) |
| `cleanup` | Maintenance (e.g. `--missing-images` excludes memes whose image never downloaded) |
| `regression-eval` | Replay current consensus over the flagged "AI Gloss Failures" set (read-only) |
| `snapshot create/list` | Freeze and inspect validated sets |
| `export <snapshot>` | Write JSONL + images + dataset card to disk |
| `push <snapshot>` | Publish to HuggingFace Hub as a multi-config dataset |
| `review` | Launch the Gradio UI (Review Queue · Browse · Prediction Comparison · Inspect · Stats & Leaderboard · AI Gloss Failures · Filter Misfires) |
| `view` | Launch the Gradio UI read-only |

## Status

Core pipeline complete and in active use (ingest → review → predict → judge →
leaderboard); snapshot/HF-push wired but not yet run end-to-end. Test suite:
`uv run pytest`. Implementation state, architecture, and gotchas live in
`HANDOFF.md`.

## License

MIT
