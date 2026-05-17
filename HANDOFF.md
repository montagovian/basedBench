# basedBench5 — session handoff

**Date:** 2026-05-16
**Repo:** https://github.com/montagovian/basedBench (private)
**Branch:** main, clean, all pushed
**Tests:** 84 passing (`uv run pytest`)

## What this is

A Python rewrite of basedBench4 (Rust), targeting the HuggingFace ecosystem
(Datasets + Spaces). Benchmarks Vision-Language Models on meme understanding,
with ground truth derived from Reddit comment consensus instead of synthetic
labels. See README.md for the user-facing pitch.

## Current pipeline state (live DB at `data/basedbench.db`)

```
292 memes ingested (Reddit /top/, was t=week, now t=year)
 42 with ground truth (consensus passed)
 19 validated in Gradio          ← user partway through reviewing
156 auto-excluded by quality gate
  1 prediction (gpt-5.5)         ← from the smoke run, on 1 meme
  1 judgment                     ← verdict: incorrect
```

## What the user was doing when the session ended

Mid-eval-run. The plan:

1. **Eval run ingest** — DONE. Pulled 282 memes/40 consensus from `t=week`.
2. **Pivoted to `t=year`** for temporal diversity (1-line change, committed
   as `74194c1`). User decided to first finish reviewing the existing 40
   from `t=week`, then re-ingest with the broader time window.
3. **Currently reviewing in Gradio** — at 19 validated / 156 excluded / a
   bunch left. Gradio is/was running at http://localhost:7860 (kill via
   `lsof -tiTCP:7860 -sTCP:LISTEN | xargs kill`).
4. **Next after review** — `basedbench predict gpt-5.5` and `basedbench
   predict claude-opus-4-7`, then `basedbench judge`, then snapshot +
   leaderboard. (See remaining tasks #15-#18 in task list.)

After the current 40 are reviewed, the user wants to **re-ingest with the
new `t=year` filter** (`basedbench ingest --limit 500`) which will add
hundreds more memes spanning the whole past year.

## Active background processes to know about

- **Gradio review UI** may be running on port 7860. Check with
  `lsof -tiTCP:7860 -sTCP:LISTEN`. Kill with the pid if needed. It can be
  safely restarted with `uv run basedbench review`.

## Architecture (one-liner per module)

| File | Purpose |
|---|---|
| `src/basedbench/config.py` | Pydantic Settings; reads `.env`; HF Space-aware path resolution |
| `src/basedbench/errors.py` | Exception hierarchy + `is_fatal_llm_error` (auth/quota fast-fail) |
| `src/basedbench/schemas.py` | Pydantic models for posts, predictions, consensus, judgments |
| `src/basedbench/db/connection.py` | SQLite; **autocommit mode** (isolation_level=None) — see Gotcha 1 |
| `src/basedbench/db/migrations.py` | PRAGMA user_version-based migrations; includes `dataset_pushes` (v5-new) |
| `src/basedbench/db/queries.py` | All 40+ query helpers; pure functions taking `Database` first |
| `src/basedbench/llm/_retry.py` | Shared tenacity retry that excludes fatal errors |
| `src/basedbench/llm/provider.py` | `Predictor` Protocol |
| `src/basedbench/llm/openai.py` | OpenAI vision predictor (image+text via `gpt-5.5` etc) |
| `src/basedbench/llm/anthropic.py` | Anthropic vision predictor (`claude-opus-4-7` etc) |
| `src/basedbench/llm/consensus.py` | 10-stage post-parse validation; the hardest piece, ported faithfully from v4 |
| `src/basedbench/llm/judge.py` | Binary correct/incorrect judge |
| `src/basedbench/llm/quality_gate.py` | Cheap text-only "is this even a meme" pre-filter |
| `src/basedbench/llm/prompts.py` | All prompt constants verbatim from v4 + `load_image_base64` + `prompt_id` hash |
| `src/basedbench/reddit/client.py` | httpx-based async OAuth client; `t=year` time filter |
| `src/basedbench/reddit/images.py` | Image download + Pillow validation + idempotent storage |
| `src/basedbench/pipeline/ingest.py` | fetch → quality gate → consensus (the long one) |
| `src/basedbench/pipeline/predict.py` | Route by model_id, run VLM, store prediction |
| `src/basedbench/pipeline/judge.py` | Concurrent judging (semaphore=10), sequential DB inserts |
| `src/basedbench/pipeline/snapshot.py` | Freeze validated set as content-addressed dataset version |
| `src/basedbench/pipeline/export.py` | Write snapshot to disk (JSONL + images + dataset card) |
| `src/basedbench/pipeline/hf_push.py` | Push to HF Hub as multi-config dataset (untested end-to-end) |
| `src/basedbench/cli.py` | Typer CLI exposing all commands |
| `src/basedbench/app.py` | Gradio Blocks (3 tabs: Review Queue / Browse / Prediction Comparison) |
| `app.py` (root) | HF Space entrypoint, 3-line delegator |

## Gotchas

### 1. SQLite autocommit (CRITICAL)

`Database.open()` sets `isolation_level=None`. Python's default deferred
transaction mode silently discards writes when the connection closes
without `commit()`. We hit this in the smoke run — ingest reported
"10 memes added" while the DB ended up empty. Fixed in `a5cddcf`. **Don't
revert to default isolation level.** If you ever need a real transaction
(see `create_snapshot`), use explicit `BEGIN`/`COMMIT`. Regression tests
live in `tests/test_persistence.py`.

### 2. Fatal-vs-transient LLM errors

`openai.RateLimitError` covers both "you're going too fast" (retry) and
"your card declined" (don't retry). `errors.is_fatal_llm_error` checks
`e.code` / `e.body["error"]["code"]` for `insufficient_quota`,
`invalid_api_key`, etc., plus HTTP 401/402/403. All LLM call sites
re-raise wrapper errors with `fatal=True`; orchestrators short-circuit
at phase boundaries with a clear message. **Don't strip this** — first
smoke run wasted minutes retrying a dead key.

### 3. Consensus 10-stage validation

`src/basedbench/llm/consensus.py` has 10 reasons to reject a "yes" from
the LLM (low confidence, short explanation, vague phrases, low avg
comment score, etc.). It's verbose but every stage exists because v4
needed it. Read the v4 `consensus.rs` if you ever want to change behavior.

### 4. Two model defaults vs the one you'd benchmark

`Config.consensus_model` and `Config.judge_model` default to
`gpt-5.4-mini` (cheap; runs on every meme as inner-loop). The actual
**target** model is whatever you pass to `basedbench predict <model>` —
that's the one being benchmarked. README suggests `gpt-5.5` and the
user wants to also run `claude-opus-4-7`.

### 5. Model id strings as of May 2026

- OpenAI flagship: `gpt-5.5` (released 2026-04-23)
- OpenAI cheap: `gpt-5.4-mini`
- Anthropic flagship: `claude-opus-4-7` (released 2026-04-16)
- `gpt-4o-mini` and friends are deprecated — *do not* default to them.

### 6. Gradio doesn't reload data on tab switch

The Prediction Comparison dropdown is populated when the app starts.
After validating something new in Review Queue, the dropdown won't show
it until you restart `basedbench review`. Same with the `_subreddits()`
dropdown in Browse. Known limitation, ported from v4.

### 7. HF push is wired but not smoke-tested

Code path in `pipeline/hf_push.py` looks right but I've never actually
pushed to HF Hub from this codebase. If/when you try, the failure modes
will be (a) wrong `HF_TOKEN` permissions, (b) feature schema mismatch
between local PIL images and HF's `Image` feature.

## Open thread the user raised at handoff

> "do you get spend metrics back from the providers it would be
> interesting and useful to keep track of that"

**Status:** we collect `prompt_tokens` + `completion_tokens` per call in
the `llm_calls` table already (see `llm/record.py` and the schema). We
just don't have a `basedbench cost` command to multiply by per-model
pricing and aggregate. ~30 lines of work — needs a price table
(`gpt-5.5: $X.XX/1M input, $Y.YY/1M output` etc.) keyed by model_id,
then a SQL `SUM(prompt_tokens * input_rate + completion_tokens *
output_rate) GROUP BY model, role`. Worth doing once the eval run is
producing data.

The user knows they can also check platform.openai.com /
console.anthropic.com for authoritative totals — those just lack the
per-meme/per-role granularity our DB has.

## Quick commands cheat sheet

```bash
# pipeline
uv run basedbench status                         # current state
uv run basedbench ingest --limit 500             # fetch + gate + consensus
uv run basedbench review                         # Gradio at :7860
uv run basedbench predict gpt-5.5                # VLM run
uv run basedbench predict claude-opus-4-7
uv run basedbench judge                          # score predictions
uv run basedbench traces --role judge --limit 5  # inspect calls
uv run basedbench snapshot create --name v0.1
uv run basedbench export v0.1 --output ./export
uv run basedbench push v0.1 --repo USER/basedbench   # untested!

# dev
uv run pytest                                    # 84 tests
uv sync                                          # install deps

# data
sqlite3 data/basedbench.db                       # poke around
rm -rf data/basedbench.db*                       # nuke (irreversible)
```

## What I'd do first in the new session

1. Read this file, then `git log --oneline -10` and `basedbench status` to
   confirm DB state matches what's described above.
2. Check if user finished reviewing (look at `validated` count in status).
3. If yes → kick off `predict gpt-5.5` and `predict claude-opus-4-7`,
   then `judge`, then show leaderboard.
4. If they want the bigger run → `basedbench ingest --limit 500` (now
   uses `t=year`) → more review → then predict.

Don't re-derive any of the architecture decisions. They were chosen
deliberately (Pydantic for schemas, aiosqlite-less sync sqlite, Typer
over Click, rich for progress bars, tenacity over backon). All
ported-faithfully decisions match v4 unless explicitly noted in commit
messages.
