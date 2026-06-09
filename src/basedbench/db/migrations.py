"""Database migrations using PRAGMA user_version.

SQL copied verbatim from v4 to ensure identical schema.
"""

from __future__ import annotations

import sqlite3

# Migration 1: Initial schema (verbatim from v4 001_initial.sql)
MIGRATION_001 = """\
CREATE TABLE IF NOT EXISTS memes (
    post_id TEXT PRIMARY KEY,
    subreddit TEXT NOT NULL,
    title TEXT NOT NULL,
    image_url TEXT,
    local_image_path TEXT,
    permalink TEXT,
    post_score INTEGER,
    created_utc TEXT,
    retrieved_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS comments (
    comment_id TEXT PRIMARY KEY,
    post_id TEXT NOT NULL REFERENCES memes(post_id),
    author TEXT,
    body TEXT NOT NULL,
    score INTEGER,
    is_moderator INTEGER NOT NULL DEFAULT 0,
    created_utc TEXT
);
CREATE INDEX IF NOT EXISTS idx_comments_post_id ON comments(post_id);

CREATE TABLE IF NOT EXISTS ground_truths (
    post_id TEXT PRIMARY KEY REFERENCES memes(post_id),
    explanation TEXT NOT NULL,
    consensus_confidence REAL,
    source_comment_ids TEXT,
    num_agreeing_comments INTEGER,
    avg_comment_score REAL,
    consensus_model TEXT,
    consensus_prompt_version TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS prompt_versions (
    prompt_id TEXT PRIMARY KEY,
    role TEXT NOT NULL CHECK(role IN ('consensus', 'prediction', 'judge')),
    system_prompt TEXT NOT NULL,
    user_prompt_template TEXT NOT NULL,
    version TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reviews (
    post_id TEXT PRIMARY KEY REFERENCES memes(post_id),
    status TEXT NOT NULL CHECK(status IN ('validated', 'excluded')),
    reason TEXT,
    reviewed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id TEXT NOT NULL REFERENCES memes(post_id),
    model_id TEXT NOT NULL,
    prediction TEXT NOT NULL,
    latency_ms INTEGER,
    token_count INTEGER,
    error TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(post_id, model_id)
);
CREATE INDEX IF NOT EXISTS idx_predictions_model ON predictions(model_id);

CREATE TABLE IF NOT EXISTS judgments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prediction_id INTEGER NOT NULL REFERENCES predictions(id),
    verdict TEXT NOT NULL CHECK(verdict IN ('correct', 'incorrect')),
    judge_reasoning TEXT,
    judge_model TEXT,
    judge_prompt_version TEXT REFERENCES prompt_versions(prompt_id),
    judged_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_judgments_prediction ON judgments(prediction_id);

CREATE TABLE IF NOT EXISTS snapshots (
    snapshot_id TEXT PRIMARY KEY,
    name TEXT UNIQUE,
    description TEXT,
    meme_count INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS snapshot_memes (
    snapshot_id TEXT NOT NULL REFERENCES snapshots(snapshot_id),
    post_id TEXT NOT NULL REFERENCES memes(post_id),
    PRIMARY KEY (snapshot_id, post_id)
);

CREATE TABLE IF NOT EXISTS config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

# Migration 2: Add dataset_version column to predictions
MIGRATION_002 = "ALTER TABLE predictions ADD COLUMN dataset_version TEXT"

# Migration 3: LLM call logging table
MIGRATION_003 = """\
CREATE TABLE IF NOT EXISTS llm_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    post_id TEXT NOT NULL,
    model TEXT NOT NULL,
    system_prompt TEXT NOT NULL,
    user_prompt TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    latency_ms INTEGER NOT NULL DEFAULT 0,
    response TEXT,
    error TEXT,
    verdict TEXT,
    reasoning TEXT,
    image_path TEXT,
    completion_tokens INTEGER,
    prompt_tokens INTEGER
);
CREATE INDEX IF NOT EXISTS idx_llm_calls_session_id ON llm_calls(session_id);
CREATE INDEX IF NOT EXISTS idx_llm_calls_role ON llm_calls(role);
CREATE INDEX IF NOT EXISTS idx_llm_calls_post_id ON llm_calls(post_id);
"""

# Migration 4: Dataset pushes table (new in v5)
MIGRATION_004 = """\
CREATE TABLE IF NOT EXISTS dataset_pushes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id TEXT NOT NULL REFERENCES snapshots(snapshot_id),
    hf_repo TEXT NOT NULL,
    pushed_at TEXT NOT NULL,
    meme_count INTEGER NOT NULL,
    model_count INTEGER NOT NULL
);
"""

# Migration 5: Consensus regression set — flagged ground-truth failures,
# used to A/B prompt or model changes against a known set of misses.
MIGRATION_005 = """\
CREATE TABLE IF NOT EXISTS consensus_regression (
    post_id TEXT PRIMARY KEY REFERENCES memes(post_id),
    status TEXT NOT NULL CHECK(status IN ('wrong', 'partial', 'correct')),
    canonical_explanation TEXT,
    failure_modes TEXT,
    reviewer_notes TEXT,
    consensus_at_annotation TEXT NOT NULL,
    annotated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_consensus_regression_status
    ON consensus_regression(status);
"""


# Migration 6: Filter-misfire feedback — human flags that a safety/quality/
# consensus decision was wrong (false exclude, false keep, missed consensus).
# Parallel to consensus_regression, but about the binary FILTER decision rather
# than the quality of a consensus gloss.
MIGRATION_006 = """\
CREATE TABLE IF NOT EXISTS gate_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id TEXT NOT NULL REFERENCES memes(post_id),
    gate TEXT NOT NULL CHECK(gate IN ('safety', 'quality', 'consensus')),
    gate_decision TEXT,
    correct_decision TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(post_id, gate)
);
CREATE INDEX IF NOT EXISTS idx_gate_feedback_gate ON gate_feedback(gate);
"""


MIGRATION_007 = """\
PRAGMA foreign_keys=OFF;

CREATE TABLE IF NOT EXISTS prompt_versions_new (
    prompt_id TEXT PRIMARY KEY,
    role TEXT NOT NULL CHECK(role IN (
        'consensus', 'prediction', 'judge', 'safety_gate', 'quality_gate'
    )),
    system_prompt TEXT NOT NULL,
    user_prompt_template TEXT NOT NULL,
    version TEXT NOT NULL,
    created_at TEXT NOT NULL
);

INSERT OR IGNORE INTO prompt_versions_new
    (prompt_id, role, system_prompt, user_prompt_template, version, created_at)
SELECT prompt_id, role, system_prompt, user_prompt_template, version, created_at
FROM prompt_versions;

DROP TABLE prompt_versions;
ALTER TABLE prompt_versions_new RENAME TO prompt_versions;

CREATE TABLE IF NOT EXISTS batches (
    batch_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    created_at TEXT NOT NULL,
    params_json TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS batch_memes (
    batch_id TEXT NOT NULL REFERENCES batches(batch_id) ON DELETE CASCADE,
    post_id TEXT NOT NULL REFERENCES memes(post_id),
    position INTEGER NOT NULL,
    added_at TEXT NOT NULL,
    stage_status TEXT NOT NULL,
    PRIMARY KEY (batch_id, post_id)
);
CREATE INDEX IF NOT EXISTS idx_batch_memes_post_id ON batch_memes(post_id);

PRAGMA foreign_keys=ON;
"""

MIGRATION_008 = """\
CREATE TABLE IF NOT EXISTS meme_processing_state (
    post_id TEXT NOT NULL REFERENCES memes(post_id),
    stage TEXT NOT NULL CHECK(stage IN ('safety', 'consensus')),
    model TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN (
        'passed', 'excluded', 'consensus', 'no_consensus'
    )),
    reasoning TEXT,
    llm_call_id INTEGER REFERENCES llm_calls(id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (post_id, stage, model, prompt_version)
);
CREATE INDEX IF NOT EXISTS idx_meme_processing_state_lookup
    ON meme_processing_state(stage, model, prompt_version, status);
CREATE INDEX IF NOT EXISTS idx_meme_processing_state_post
    ON meme_processing_state(post_id);

INSERT OR REPLACE INTO meme_processing_state
    (post_id, stage, model, prompt_version, status, reasoning, llm_call_id,
     created_at, updated_at)
SELECT
    post_id, stage, model, prompt_version, status, reasoning, llm_call_id,
    created_at, updated_at
FROM (
    SELECT
        lc.post_id,
        CASE lc.role
            WHEN 'safety_gate' THEN 'safety'
            WHEN 'consensus' THEN 'consensus'
        END AS stage,
        lc.model,
        lc.prompt_version,
        CASE
            WHEN lc.role = 'safety_gate' AND lc.verdict = 'keep' THEN 'passed'
            WHEN lc.role = 'safety_gate' AND lc.verdict = 'exclude' THEN 'excluded'
            WHEN lc.role = 'consensus' AND lc.verdict = 'consensus' THEN 'consensus'
            WHEN lc.role = 'consensus' AND lc.verdict = 'no_consensus' THEN 'no_consensus'
        END AS status,
        lc.reasoning,
        lc.id AS llm_call_id,
        lc.created_at,
        lc.created_at AS updated_at
    FROM llm_calls lc
    JOIN (
        SELECT post_id, role, model, prompt_version, MAX(id) AS id
        FROM llm_calls
        WHERE role IN ('safety_gate', 'consensus')
          AND verdict IN ('keep', 'exclude', 'consensus', 'no_consensus')
          AND error IS NULL
        GROUP BY post_id, role, model, prompt_version
    ) latest ON latest.id = lc.id
) backfill
WHERE status IS NOT NULL;
"""

MIGRATION_009 = """\
CREATE TABLE IF NOT EXISTS consensus_eval_items (
    post_id TEXT PRIMARY KEY REFERENCES memes(post_id),
    category TEXT NOT NULL CHECK(category IN (
        'false_positive_consensus',
        'bad_gloss',
        'true_no_consensus',
        'easy_yes_consensus',
        'hard_yes_consensus',
        'source_comment_mismatch'
    )),
    expected_has_consensus INTEGER NOT NULL CHECK(expected_has_consensus IN (0, 1)),
    expected_explanation TEXT,
    source TEXT NOT NULL,
    notes TEXT,
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_consensus_eval_items_category
    ON consensus_eval_items(category, active);

CREATE TABLE IF NOT EXISTS consensus_eval_runs (
    run_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    prompt_label TEXT NOT NULL,
    system_prompt TEXT NOT NULL,
    user_prompt_template TEXT NOT NULL,
    item_count INTEGER NOT NULL,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS consensus_eval_results (
    run_id TEXT NOT NULL REFERENCES consensus_eval_runs(run_id),
    post_id TEXT NOT NULL REFERENCES memes(post_id),
    category TEXT NOT NULL,
    expected_has_consensus INTEGER NOT NULL CHECK(expected_has_consensus IN (0, 1)),
    expected_explanation TEXT,
    actual_has_consensus INTEGER NOT NULL CHECK(actual_has_consensus IN (0, 1)),
    actual_explanation TEXT,
    confidence REAL,
    agreeing_comment_ids TEXT,
    reasoning TEXT,
    passed INTEGER NOT NULL CHECK(passed IN (0, 1)),
    error TEXT,
    latency_ms INTEGER,
    llm_call_id INTEGER REFERENCES llm_calls(id),
    created_at TEXT NOT NULL,
    PRIMARY KEY (run_id, post_id)
);
CREATE INDEX IF NOT EXISTS idx_consensus_eval_results_run
    ON consensus_eval_results(run_id, passed, category);
"""

MIGRATION_010 = """\
CREATE TABLE IF NOT EXISTS image_fingerprints (
    post_id TEXT PRIMARY KEY REFERENCES memes(post_id),
    exact_hash TEXT NOT NULL,
    dhash TEXT NOT NULL,
    ahash TEXT NOT NULL,
    width INTEGER NOT NULL,
    height INTEGER NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_image_fingerprints_exact_hash
    ON image_fingerprints(exact_hash);
"""


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    cursor = conn.execute(
        f"SELECT COUNT(*) FROM pragma_table_info('{table}') WHERE name = ?",
        (column,),
    )
    return cursor.fetchone()[0] > 0


def run_migrations(conn: sqlite3.Connection) -> None:
    """Run all pending migrations based on PRAGMA user_version."""
    version = conn.execute("PRAGMA user_version").fetchone()[0]

    if version < 1:
        conn.executescript(MIGRATION_001)
        conn.execute("PRAGMA user_version = 1")

    if version < 2:
        if not _column_exists(conn, "predictions", "dataset_version"):
            conn.execute(MIGRATION_002)
        conn.execute("PRAGMA user_version = 2")

    if version < 3:
        conn.executescript(MIGRATION_003)
        conn.execute("PRAGMA user_version = 3")

    if version < 4:
        conn.executescript(MIGRATION_004)
        conn.execute("PRAGMA user_version = 4")

    if version < 5:
        conn.executescript(MIGRATION_005)
        conn.execute("PRAGMA user_version = 5")

    if version < 6:
        conn.executescript(MIGRATION_006)
        conn.execute("PRAGMA user_version = 6")

    if version < 7:
        conn.executescript(MIGRATION_007)
        conn.execute("PRAGMA user_version = 7")

    if version < 8:
        conn.executescript(MIGRATION_008)
        conn.execute("PRAGMA user_version = 8")

    if version < 9:
        conn.executescript(MIGRATION_009)
        conn.execute("PRAGMA user_version = 9")

    if version < 10:
        conn.executescript(MIGRATION_010)
        conn.execute("PRAGMA user_version = 10")
