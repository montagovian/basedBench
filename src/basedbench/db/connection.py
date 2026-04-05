"""Database connection management.

- sqlite3 for sync operations (Gradio callbacks, CLI)
- aiosqlite for async pipeline operations
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from basedbench.db.migrations import run_migrations


class Database:
    """Synchronous SQLite database wrapper."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    @classmethod
    def open(cls, path: Path) -> Database:
        """Open (or create) the database at the given path.

        Sets WAL mode, foreign keys, busy timeout. Runs migrations.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path), check_same_thread=False)
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        conn.execute("PRAGMA synchronous = NORMAL")
        run_migrations(conn)
        return cls(conn)

    @classmethod
    def open_in_memory(cls) -> Database:
        """Open an in-memory database (for testing)."""
        conn = sqlite3.connect(":memory:")
        conn.execute("PRAGMA foreign_keys = ON")
        run_migrations(conn)
        return cls(conn)

    def close(self) -> None:
        self.conn.close()
