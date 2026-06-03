# basedBench5 — session handoff

**Date:** 2026-06-01
**Repo:** https://github.com/montagovian/basedBench (private)
**Branch:** main (check `git status -sb` for working tree and push state)
**Tests:** 162 passing (`uv run pytest`)

## What this is

A Python rewrite of basedBench4 (Rust), targeting the HuggingFace ecosystem
(Datasets + Spaces). Benchmarks Vision-Language Models on meme understanding,
with ground truth derived from Reddit comment consensus instead of synthetic
labels. See README.md for the user-facing pitch and the **Feedback loops**
section for how flagged failures drive prompt improvements.

## Current Pipeline State

The live DB is local, changes as review/eval work continues, and exact counts
go stale quickly. Treat this file as workflow/architecture context; run this for
current operational state:

```bash
uv run basedbench status
```

Expected DB shape: `data/basedbench.db`, `PRAGMA user_version` = 7. Snapshots
may still be absent unless `basedbench snapshot create` has been run.

## Working model defaults (verify against `config.py` before trusting)

- **consensus**: `gpt-5.4-mini` (text-only inner loop, runs on every meme)
- **judge ensemble**: `["gpt-5.4-mini", "claude-sonnet-4-6"]` — every prediction
  is judged by *each* model to surface judge-family bias. Override via
  `JUDGE_MODELS='["m1","m2"]'` (JSON).
- **predict targets** (what you actually benchmark): `gpt-5.5`, `claude-opus-4-7`,
  passed to `basedbench predict <model>`.

## The strict workflow (how the user wants ingest run)

Human review gate **before** spending predict/judge tokens. `ingest` deliberately
stops at consensus: fetch → safety gate → quality gate → consensus. The user then
validates in Gradio. Only run `predict`/`judge` against the validated set.

## Two feedback loops (the recent focus)

1. **AI Gloss Failures** (`consensus_regression` table): flag a wrong consensus
   *gloss* from the Review Queue tab → collected in the AI Gloss Failures tab →
   `basedbench regression-eval` replays current consensus over the set (read-only).
2. **Filter Misfires** (`gate_feedback` table): in the Inspect tab, browse ALL
   content (incl. excluded) and flag when a safety/quality/consensus *decision*
   was wrong → collected in the Filter Misfires tab.

Golden rule (now in README): retune a gate/consensus prompt against the real
flagged cases + a known-good sample, never from intuition. This is exactly how
the scrambled-into-nonsense quality-gate fix (`6f5dcbc`) was validated.

## Architecture (one-liner per module)

| File | Purpose |
|---|---|
| `src/basedbench/config.py` | Pydantic Settings; `judge_models` is a list; requires ANTHROPIC_API_KEY when a claude-* judge is configured |
| `src/basedbench/errors.py` | Exception hierarchy + `is_fatal_llm_error` (auth/quota fast-fail) |
| `src/basedbench/schemas.py` | Pydantic models for posts, predictions, consensus, judgments |
| `src/basedbench/db/connection.py` | SQLite; **autocommit mode** (isolation_level=None) — see Gotcha 1 |
| `src/basedbench/db/migrations.py` | PRAGMA user_version migrations (currently 7): + `consensus_regression` (005), `gate_feedback` (006), tracer batches + gate prompt roles (007) |
| `src/basedbench/db/queries.py` | All query helpers (pure fns taking `Database` first); regression, gate-feedback, and batch-scoped helpers |
| `src/basedbench/llm/_retry.py` | Shared tenacity retry that excludes fatal errors |
| `src/basedbench/llm/provider.py` | `Predictor` Protocol |
| `src/basedbench/llm/openai.py` | OpenAI vision predictor; predict uses `reasoning_effort="medium"` (image only) |
| `src/basedbench/llm/anthropic.py` | Anthropic vision predictor; predict uses adaptive thinking + `effort=medium` |
| `src/basedbench/llm/consensus.py` | 10-stage post-parse validation; hardest piece, ported from v4 |
| `src/basedbench/llm/judge.py` | `Judge` Protocol + OpenAI/Anthropic judges + `make_judge()` factory (routes by model id) |
| `src/basedbench/llm/safety_gate.py` | Content-appropriateness pre-filter (drops explicit/hate/doxx; keeps edgy) |
| `src/basedbench/llm/quality_gate.py` | "Is there a recoverable meaning" pre-filter (rejects scrambled-nonsense) |
| `src/basedbench/llm/prompts.py` | All prompt constants + `VAGUE_PHRASES` + `load_image_base64` + `prompt_id` hash |
| `src/basedbench/reddit/client.py` | httpx async OAuth client; `--time-filter` windows; 404-skips removed posts |
| `src/basedbench/reddit/pullpush.py` | pullpush.io client for historical date-range ingest (lags on recent dates) |
| `src/basedbench/reddit/images.py` | Image download + Pillow validation + idempotent storage |
| `src/basedbench/pipeline/ingest.py` | fetch → safety gate → quality gate → consensus, concurrent (Semaphore 10) |
| `src/basedbench/pipeline/predict.py` | Route by model_id, run VLM, store prediction |
| `src/basedbench/pipeline/judge.py` | Multi-judge concurrent judging; per-judge stats + agreement summary |
| `src/basedbench/pipeline/tracer.py` | Bounded fetch → gates → consensus → prediction smoke test scoped to one DB-backed batch |
| `src/basedbench/pipeline/snapshot.py` | Freeze validated set as content-addressed dataset version |
| `src/basedbench/pipeline/export.py` | Write snapshot to disk (JSONL + images + dataset card) |
| `src/basedbench/pipeline/hf_push.py` | Push to HF Hub as multi-config dataset (untested end-to-end) |
| `src/basedbench/cli.py` | Typer CLI; commands incl. `regression-eval`, `cleanup`, `view` |
| `src/basedbench/app.py` | Gradio Blocks — 7 tabs (see below) |
| `app.py` (root) | HF Space entrypoint, delegator |

**Gradio tabs:** Review Queue · Browse · Prediction Comparison · Inspect ·
Stats & Leaderboard · AI Gloss Failures · Filter Misfires.

## Gotchas

### 1. SQLite autocommit (CRITICAL)
`Database.open()` sets `isolation_level=None`. Python's default deferred mode
silently discards writes when the connection closes without `commit()`. **Don't
revert.** For real transactions use explicit `BEGIN`/`COMMIT`. Regression tests
in `tests/test_persistence.py`.

### 2. Fatal-vs-transient LLM errors
`errors.is_fatal_llm_error` distinguishes quota/auth (don't retry) from rate
limits (retry). All call sites re-raise with `fatal=True`; orchestrators
short-circuit at phase boundaries. **Don't strip this.**

### 3. Consensus 10-stage validation
`llm/consensus.py` rejects a "yes" for 10 reasons (low confidence, short/vague
explanation, low avg comment score, etc.). Verbose but each stage earned its
place in v4. The consensus step — not the gates — is the dominant filter.

### 4. Reasoning parity for a fair eval (CRITICAL)
`gpt-5.5` **defaults to medium reasoning**; `claude-opus-4-7` **defaults to NO
thinking**. Benchmarking them at defaults is unfair. Both predictors are pinned
to explicit **medium**. opus-4-7 only supports adaptive thinking — a manual
`budget_tokens` returns HTTP 400, so we use `thinking={"type":"adaptive"}` +
`output_config={"effort":"medium"}`.

### 5. Predictor isolation (CRITICAL to the benchmark's validity)
Predictors see the **image only** — no comments, no title, no web search, and
**no tools passed to the API**. Regression test: `tests/test_predictor_isolation.py`.

### 6. pullpush.io can't fetch recent content
For historical date ranges (`--after-date/--before-date`) pullpush works, but it
**lags and returns nothing for the last few weeks**. For recent memes use the
native Reddit path (`--time-filter week`/`month`).

### 7. Any ingest processes the whole pending backlog
Phases 1.4/1.5/2 gate/consensus *all* pending memes, not just newly-fetched
ones. A small fetch can trigger a large backlog run if memes are ungated.

### 8. Tracer rows are smoke-test rows, not leaderboard rows
`basedbench tracer --fetch 12 --target-consensus 5 --predict gpt-5.5` creates a
`batches` row, scopes gates/consensus/prediction to that batch, and predicts
unreviewed consensus rows so the full system can be checked quickly. It does
**not** validate memes, so normal leaderboard/snapshot commands still ignore
those rows unless a human later validates them.

### 9. Model id strings as of mid-2026
- OpenAI flagship `gpt-5.5`, cheap `gpt-5.4-mini`
- Anthropic flagship `claude-opus-4-7`, judge `claude-sonnet-4-6`
- `gpt-4o*` / `claude-3-*` are deprecated — do not default to them. (Test
  fixtures still use `gpt-4o` as an arbitrary id string; that's harmless.)

### (Fixed) Gradio tab-switch refresh
Previously the Browse/Comparison dropdowns were frozen at app-startup state.
Now Browse, Prediction Comparison, Inspect, Stats, AI Gloss Failures, and Filter
Misfires all refresh via `tab.select(...)`.

## Open Issues From Deep Review (2026-06-03)

These were found in a repo-wide review and have **not** been fixed yet.

1. **Quick start blocks OpenAI-only users.** README tells users to fill only
   Reddit + `OPENAI_API_KEY`, but default `judge_models` includes
   `claude-sonnet-4-6`, and `Config()` rejects missing `ANTHROPIC_API_KEY`.
   Because every CLI command constructs `Config()`, even `status`/`ingest` can
   fail before judging. Options: make Anthropic required in quick start, default
   to OpenAI-only judges, or defer Claude-key validation to `judge`.
2. **Snapshot export/HF push can publish failed predictions.**
   `snapshot_model_ids()` and `snapshot_predictions_for_model()` do not filter
   `p.error IS NULL`; `export` and `hf_push` use those helpers directly. A
   transient/API failure row has `prediction=""`, so a snapshot can contain
   empty model answers.
3. **Prediction status counts are not scoped to validated rows.**
   `get_prediction_counts()` counts all successful predictions by model but uses
   the validated set as the denominator. If `--include-unreviewed` was used, or
   a meme was later excluded, status can show misleading completion counts.
4. **No-consensus rows are reprocessed indefinitely.**
   `memes_without_ground_truth()` selects every non-excluded meme without ground
   truth, and ingest does not persist a terminal "no consensus" decision. Every
   ingest reruns consensus on known rejects unless they are manually excluded.
5. **`basedbench view` is not actually read-only.** The command delegates to
   `review()`, which exposes validate/exclude/flag mutation controls. Either
   remove the read-only claim or add a real read-only mode.
6. **Token/cost logging misses high-volume calls.** Safety, predictions, and
   judges record usage, but quality gate and consensus do not store successful
   `prompt_tokens`/`completion_tokens`, which weakens the future `basedbench
   cost` command.
7. **Prediction prompt versions are not first-class on prediction rows.**
   Prompt IDs are content hashes (`prompt_id(role, system, user_template)`) and
   `llm_calls.prompt_version` records them, while ground truths and judgments
   have dedicated prompt-version columns. `predictions` does not: the prediction
   prompt is only recoverable indirectly through `llm_calls`. Before changing
   `EXPLAIN_MEME_PROMPT` or A/B testing a stronger prompt, add something like
   `predictions.prediction_prompt_version`, store `predictor.prompt_id` on
   insert, and consider human-readable labels such as `prediction_baseline_v1`
   / `prediction_structured_v2` alongside the immutable hash.

## Open thread the user raised earlier

> "do you get spend metrics back from the providers… keep track of that"

**Status: still open.** We store `prompt_tokens` + `completion_tokens` per call
in `llm_calls`, but there's **no `basedbench cost` command** yet. ~30 lines:
a per-model price table keyed by model_id, then
`SUM(prompt_tokens*in_rate + completion_tokens*out_rate) GROUP BY model, role`.
platform.openai.com / console.anthropic.com have authoritative totals but lack
our per-meme/per-role granularity.

## Quick commands cheat sheet

```bash
# pipeline
uv run basedbench status                              # current state
uv run basedbench ingest --limit 50                  # recent: fetch + gates + consensus
uv run basedbench ingest -t week                     # recent top-of-week
uv run basedbench ingest --after-date 2024-01-01 --before-date 2024-04-01  # historical (pullpush)
uv run basedbench tracer --fetch 12 --target-consensus 5 --predict gpt-5.5  # bounded smoke test
uv run basedbench review                             # Gradio at :7860
uv run basedbench predict gpt-5.5
uv run basedbench predict claude-opus-4-7
uv run basedbench judge                             # scored by every judge model
uv run basedbench regression-eval                   # replay flagged AI Gloss Failures (read-only)
uv run basedbench cleanup --missing-images          # exclude memes whose image never downloaded
uv run basedbench traces --role judge --limit 5
uv run basedbench snapshot create --name v0.1
uv run basedbench export v0.1 --output ./export
uv run basedbench push v0.1 --repo USER/basedbench   # untested!

# dev
uv run pytest                                        # 162 tests
uv sync

# data
sqlite3 data/basedbench.db
rm -rf data/basedbench.db*                           # nuke (irreversible)
```

## What I'd do first in a new session

1. Read this file, then `git log --oneline -10` and `uv run basedbench status`
   to get the current DB state.
2. Finish the review queue if the user wants a cleaner validated set.
3. Top up predictions for all validated memes (`gpt-5.5` and
   `claude-opus-4-7`), then `judge`, then check the Stats & Leaderboard tab.
4. As the user flags Filter Misfires / AI Gloss Failures, use them to retune the
   gate/consensus prompts (validate against the flagged set + a known-good sample).

Architecture decisions were made deliberately (Pydantic, sync sqlite in
autocommit, Typer, rich, tenacity) and match v4 unless a commit says otherwise.
Don't re-derive them.
