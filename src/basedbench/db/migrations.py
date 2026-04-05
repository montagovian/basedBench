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
