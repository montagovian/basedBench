"""Regression tests for cross-connection persistence.

The in-memory `db` fixture used elsewhere always shares one connection, so it
can't catch the autocommit footgun where a process writes successfully but the
next process opening the same file sees an empty database. These tests open the
file twice on purpose.
"""

from __future__ import annotations

from pathlib import Path

from basedbench.db import queries
from basedbench.db.connection import Database
from basedbench.schemas import RawPost, RedditComment


def _post(post_id: str = "p1") -> RawPost:
    return RawPost(
        post_id=post_id,
        subreddit="memes",
        title="t",
        permalink=f"/r/memes/comments/{post_id}/t",
        score=10,
        retrieved_at="2025-01-02T00:00:00Z",
        comments=[
            RedditComment(comment_id="c1", author="u", body="hi", score=5),
        ],
    )


def test_insert_meme_visible_to_second_connection(tmp_path: Path):
    """Writes must persist across process / connection boundaries."""
    db_path = tmp_path / "test.db"

    writer = Database.open(db_path)
    assert queries.insert_meme(writer, _post()) is True
    assert queries.insert_comment(writer, "p1", _post().comments[0]) is True
    writer.close()

    reader = Database.open(db_path)
    assert reader.conn.execute("SELECT COUNT(*) FROM memes").fetchone()[0] == 1
    assert reader.conn.execute("SELECT COUNT(*) FROM comments").fetchone()[0] == 1
    reader.close()


def test_ground_truth_persists_across_connections(tmp_path: Path):
    db_path = tmp_path / "test.db"

    w = Database.open(db_path)
    queries.insert_meme(w, _post())
    queries.upsert_ground_truth(
        w,
        post_id="p1",
        explanation="because reasons",
        confidence=0.9,
        source_comment_ids=["c1"],
        num_agreeing=3,
        avg_score=42.0,
        model="gpt-4o-mini",
        prompt_version="abc",
    )
    w.close()

    r = Database.open(db_path)
    row = r.conn.execute(
        "SELECT explanation, consensus_confidence FROM ground_truths WHERE post_id = ?",
        ("p1",),
    ).fetchone()
    assert row is not None
    assert row[0] == "because reasons"
    assert row[1] == 0.9
    r.close()


def test_status_counts_never_negative(tmp_path: Path):
    """Repro of the bug: 8 auto-excluded + 2 ground-truthed used to give unreviewed=-6."""
    db_path = tmp_path / "test.db"
    db = Database.open(db_path)

    # 10 memes, 2 with consensus, 8 auto-excluded by quality gate
    for i in range(10):
        queries.insert_meme(db, _post(f"p{i}"))
    for i in range(2):
        queries.upsert_ground_truth(
            db,
            post_id=f"p{i}",
            explanation="x" * 200,
            confidence=0.8,
            source_comment_ids=[],
            num_agreeing=3,
            avg_score=20.0,
            model="gpt-4o-mini",
            prompt_version="abc",
        )
    for i in range(2, 10):
        queries.insert_auto_review(db, f"p{i}", "auto: not a meme")

    counts = queries.get_status_counts(db)
    db.close()

    assert counts.total_memes == 10
    assert counts.with_consensus == 2
    assert counts.excluded == 8
    assert counts.unreviewed == 2  # the two ground-truthed memes still need review
    assert counts.unreviewed >= 0
