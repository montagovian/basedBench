# basedBench5: Python Rewrite with HuggingFace Integration

> **Historical document.** This is the original pre-implementation plan and is
> kept for design rationale only. It does **not** track current state — code
> samples here (e.g. `consensus_model = "gpt-4o-mini"`, a single `judge_model`,
> a 3-tab Gradio app) are superseded. For current truth see **README.md**
> (pipeline + feedback loops) and **HANDOFF.md** (live state, architecture,
> gotchas).

## Context

basedBench4 is a Rust CLI for benchmarking VLMs on meme understanding. It works well but creates friction for two goals: publishing a HuggingFace Dataset and deploying a HuggingFace Space. The entire HF ecosystem is Python (`datasets`, `huggingface_hub`, `gradio`). The Rust code solves no performance problem — the pipeline is I/O bound waiting on Reddit and LLM APIs. A Python rewrite eliminates the language boundary, makes HF integration native, and reduces maintenance to one codebase. The existing Gradio review UI (`space/app.py`, 398 lines) is already Python.

## Architecture: One Package, Three Interfaces

```
basedBench5/
├── pyproject.toml              # Single package: CLI + Space + pipeline
├── app.py                      # HF Space entry point (3 lines, delegates to basedbench.app)
├── README.md                   # HF Space card (sdk: gradio)
├── .env.example
│
├── src/basedbench/
│   ├── __init__.py             # VERSION = "5.0.0"
│   ├── __main__.py             # python -m basedbench support
│   ├── config.py               # Pydantic Settings (.env + HF Secrets)
│   ├── errors.py               # Exception hierarchy
│   ├── schemas.py              # Pydantic models (RawPost, ConsensusResult, etc.)
│   │
│   ├── db/
│   │   ├── connection.py       # Database class (aiosqlite for pipeline, sqlite3 for Gradio)
│   │   ├── migrations.py       # Same SQL as v4, PRAGMA user_version based
│   │   └── queries.py          # All 40+ query methods ported from v4
│   │
│   ├── llm/
│   │   ├── prompts.py          # All 4 prompt constants + prompt_id hash + VAGUE_PHRASES
│   │   ├── record.py           # LlmCallRecord dataclass
│   │   ├── provider.py         # Predictor Protocol
│   │   ├── openai.py           # OpenAI predictions (async, openai SDK)
│   │   ├── anthropic.py        # Anthropic predictions (async, anthropic SDK)
│   │   ├── consensus.py        # Consensus detection + 10-stage post-parse validation
│   │   ├── judge.py            # LLM judge (binary verdict)
│   │   └── quality_gate.py     # Text-only pre-filter
│   │
│   ├── reddit/
│   │   ├── client.py           # OAuth2 auth, pagination, rate limit handling
│   │   └── images.py           # Download, validate (Pillow), store
│   │
│   ├── pipeline/
│   │   ├── ingest.py           # fetch → quality gate → consensus
│   │   ├── predict.py          # route to provider, insert prediction
│   │   ├── judge.py            # concurrent judging (semaphore=10)
│   │   ├── snapshot.py         # freeze validated memes
│   │   └── export.py           # Push to HuggingFace Hub
│   │
│   ├── cli.py                  # Typer app (all commands)
│   └── app.py                  # Gradio Blocks (5 tabs)
│
└── tests/
    ├── conftest.py             # In-memory DB fixtures, mock LLM responses
    ├── test_schemas.py
    ├── test_db.py
    ├── test_consensus.py
    ├── test_judge.py
    └── test_pipeline.py
```

## Key Decisions

### Database: SQLite (same as v4)
- `aiosqlite` for async pipeline operations
- `sqlite3` for sync Gradio callbacks (Gradio uses threads)
  - Use `check_same_thread=False` since Gradio dispatches across threads
  - Connection-per-request pattern to avoid concurrent access issues
- Same schema as v4 with one addition: `dataset_pushes` table
- Same WAL mode, busy_timeout, foreign keys
- Same PRAGMA user_version migration strategy

### HuggingFace Dataset: Parquet with Embedded Images
```python
from datasets import Dataset, Features, Value, Image

# Main config: memes with images
ds = Dataset.from_dict({
    "post_id": post_ids,
    "subreddit": subreddits,
    "ground_truth": explanations,
    "image": [PIL.Image.open(p) for p in image_paths],
    "consensus_confidence": confidences,
    "num_agreeing_comments": counts,
})
ds.push_to_hub("user/basedbench", config_name="memes")

# Per-model predictions
for model_id in models:
    pred_ds.push_to_hub("user/basedbench", config_name=f"predictions_{model_id}")

# Leaderboard
lb_ds.push_to_hub("user/basedbench", config_name="leaderboard")
```

478 images at ~30KB avg = ~14MB in Parquet. Well within free tier. HF Dataset Viewer renders images automatically. Anyone can `load_dataset("user/basedbench")`.

### LLM Providers: Official SDKs Directly
- `openai` (AsyncOpenAI) for predictions, consensus, judge, quality gate
- `anthropic` (AsyncAnthropic) for Claude predictions
- `tenacity` for retry logic (replaces Rust's `backon`)
- `httpx` for Reddit API calls (OAuth2, pagination, rate limits)
- No LangChain, no LiteLLM — unnecessary abstraction

### Async Design
- Pipeline is fully async (`asyncio`)
- CLI wraps with `asyncio.run()`
- Judging uses `asyncio.Semaphore(10)` for concurrent API calls
- DB writes remain sequential (same pattern as v4)
- Gradio callbacks stay synchronous (Gradio handles threading)

### Gradio Space: 5 Tabs
1. **Leaderboard** (hero tab) — sortable table, accuracy bar chart, dataset download link
2. **Meme Explorer** — image gallery, click to see ground truth + all predictions
3. **Model Deep Dive** — select model, see all predictions sorted by verdict (failures first)
4. **Review Queue** — same workflow as v4, hidden behind HF OAuth on Space
5. **About** — methodology, model submission instructions, citation

### Space Deployment
- `app.py` at repo root: `from basedbench.app import create_app; create_app().launch()`
- `README.md` with `sdk: gradio` YAML frontmatter
- Detects `SPACE_ID` env var → uses `/data` persistent storage, reads HF Secrets
- Same repo is both GitHub source and HF Space

### SESSION_ID: Lazy, Per-Process
- `SESSION_ID` is a module-level string generated once per process via `uuid4()`
- Imported from `basedbench` where needed (same as v4's `LazyLock`)
- Each test, Gradio worker, or CLI invocation gets its own session ID — this is intentional

### Drop OTEL/Phoenix
- SQLite `llm_calls` table already captures everything
- `traces` CLI command continues to work
- Phoenix was complex for marginal benefit in v4
- Can add back later with `opentelemetry-sdk` if needed

## Config (Pydantic Settings)

```python
class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    # Reddit
    reddit_client_id: str
    reddit_client_secret: str
    reddit_user_agent: str = "basedbench/5.0.0"

    # LLM
    openai_api_key: str
    anthropic_api_key: str | None = None
    consensus_model: str = "gpt-4o-mini"
    judge_model: str = "gpt-4o-mini"

    # Quality thresholds (same defaults as v4)
    min_agreeing_comments: int = 3
    min_avg_comment_score: float = 10.0
    min_comment_score: int = 5
    max_comments_for_consensus: int = 10

    # HuggingFace
    hf_token: str | None = None
    hf_dataset_repo: str = ""  # Must be set explicitly before push

    # Paths
    data_dir: Path = Path("data")
```

## CLI Commands

```
basedbench ingest [--limit 50] [--subreddit NAME]
basedbench predict MODEL [--include-unreviewed] [--snapshot NAME]
basedbench judge [MODEL] [--rejudge-prompt HASH]
basedbench review                          # Gradio review UI locally
basedbench status                          # Pipeline state
basedbench snapshot create NAME [--desc]
basedbench snapshot list
basedbench push [--snapshot NAME]          # Push to HuggingFace Hub (replaces export)
basedbench traces [--id] [--role] [--errors] [--limit 20]
basedbench run MODEL                       # ingest → predict → judge → push
basedbench migrate --from-v4 PATH          # Import v4 data
basedbench serve [--port 7860]             # Full Space locally
```

## Dependencies

```toml
[project]
name = "basedbench"
version = "5.0.0"
requires-python = ">=3.11"
dependencies = [
    "typer>=0.12",
    "rich>=13.0",
    "pydantic>=2.0",
    "pydantic-settings>=2.0",
    "aiosqlite>=0.20",
    "httpx>=0.27",
    "openai>=1.0",
    "anthropic>=0.39",
    "tenacity>=9.0",
    "gradio>=5.0",
    "datasets>=3.0",
    "huggingface-hub>=0.25",
    "Pillow>=10.0",
    "tqdm>=4.0",            # Progress bars for ingest/predict/judge pipeline steps
]

[project.scripts]
basedbench = "basedbench.cli:app"
```

## Migration from v4

The `migrate --from-v4` command:
1. Opens v4 SQLite DB read-only
2. Creates v5 DB at a temp path (`.migrating`) with identical schema + `dataset_pushes` table
3. Copies all rows in a single transaction: memes, comments, ground_truths, reviews, predictions, judgments, llm_calls, prompt_versions, snapshots, snapshot_memes
4. Copies `data/images/` directory
5. Verifies row counts match
6. Renames temp DB to final path (atomic on failure: temp DB is deleted)
7. Optionally runs `push` to create initial HF Dataset

Schema is identical (v5 is a superset), so this is a straightforward table-by-table copy.

## Implementation Phases

### Phase 1: Foundation (scaffold + data layer)
- `uv init`, pyproject.toml, directory structure
- `schemas.py` — port all Pydantic models from Rust structs
- `config.py` — Pydantic Settings
- `errors.py` — exception hierarchy
- `db/` — connection, migrations (copy SQL verbatim from v4), queries
- `llm/prompts.py` — copy prompt constants verbatim, port prompt_id hash
- Tests for schemas, config, DB, prompts

### Phase 2: LLM Layer
- `llm/record.py` — LlmCallRecord
- `llm/provider.py` — Predictor Protocol
- `llm/openai.py` — async OpenAI predictions
- `llm/anthropic.py` — async Anthropic predictions
- `llm/consensus.py` — consensus detection with ALL 10 post-parse validation stages
- `llm/judge.py` — binary verdict parser
- `llm/quality_gate.py` — text-only pre-filter
- Tests with mocked API responses

### Phase 3: Reddit + Pipeline
- `reddit/client.py` — OAuth2, pagination, comment fetching
- `reddit/images.py` — download, validate (Pillow), store
- `pipeline/ingest.py` — fetch → quality gate → consensus (3 phases)
- `pipeline/predict.py` — provider routing
- `pipeline/judge.py` — concurrent judging with semaphore
- `pipeline/snapshot.py` — freeze validated memes
- `pipeline/export.py` — HuggingFace Dataset push

### Phase 4: CLI
- `cli.py` — all Typer commands wrapping pipeline functions
- Test with `typer.testing.CliRunner`

### Phase 5: Gradio Space
- `app.py` — 5 tabs (Leaderboard, Explorer, Deep Dive, Review, About)
- HF Space detection and adaptation
- CSS styling (constrained images, dark mode)

### Phase 6: Migration + Deploy
- `migrate --from-v4` command
- Run migration on real v4 database
- Push initial HF Dataset
- Deploy to HuggingFace Space
- End-to-end test: ingest 5 → predict → judge → push → verify on Hub

## Verification

1. `basedbench migrate --from-v4 ../basedBench4` — all 478 memes transfer correctly
2. `basedbench status` — matches v4's status output
3. `basedbench ingest --limit 5` — fetches new memes, quality gate + consensus work
4. `basedbench predict gpt-4o-mini --include-unreviewed` — predictions succeed
5. `basedbench judge` — verdicts match expectations
6. `basedbench push` — dataset appears on HuggingFace Hub with images
7. `load_dataset("user/basedbench")` — works from a clean Python environment
8. `basedbench serve` — all 5 Gradio tabs render correctly
9. Deploy to HF Space — leaderboard visible, explorer works, review tab auth-gated

## Critical Files to Port (v4 → v5)

| v4 Source | Lines | v5 Target | Complexity |
|-----------|-------|-----------|------------|
| `src/db/queries.rs` | ~900 | `db/queries.py` | High (40+ methods) |
| `src/llm/consensus.rs` | ~450 | `llm/consensus.py` | High (10 validation stages) |
| `src/cli/ingest.rs` | ~450 | `pipeline/ingest.py` | High (3 phases) |
| `src/llm/prompts.rs` | ~180 | `llm/prompts.py` | Low (copy constants) |
| `src/llm/judge.rs` | ~200 | `llm/judge.py` | Medium |
| `src/llm/openai.rs` | ~150 | `llm/openai.py` | Medium |
| `src/llm/anthropic.rs` | ~130 | `llm/anthropic.py` | Medium |
| `src/reddit/client.rs` | ~200 | `reddit/client.py` | Medium |
| `src/reddit/images.rs` | ~100 | `reddit/images.py` | Low |
| `src/cli/export.rs` | ~200 | `pipeline/export.py` | Medium (different: HF push) |
| `space/app.py` | ~400 | `app.py` | Medium (expand to 5 tabs) |
| `migrations/001_initial.sql` | ~100 | `db/migrations.py` | Low (copy verbatim) |

## Source Reference

The v4 codebase lives at `../basedBench4/`. The new session should reference it heavily during porting — every Rust file has a direct Python equivalent in the plan above.
