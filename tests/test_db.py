"""Tests for db/ module — mirrors v4 query tests."""

from basedbench.db import Database
from basedbench.db import queries as q
from basedbench.llm.record import LlmCallRecord
from basedbench.schemas import ModelPrediction

from .conftest import sample_post


# ═══════════════════════════════════════════════════════
# Migrations
# ═══════════════════════════════════════════════════════


def test_migrate_fresh_db(db: Database):
    """Fresh DB should have all tables and columns."""
    # Check dataset_version column exists
    row = db.conn.execute(
        "SELECT COUNT(*) FROM pragma_table_info('predictions') WHERE name = 'dataset_version'"
    ).fetchone()
    assert row[0] == 1


def test_migrate_idempotent(db: Database):
    """Running migrations twice should not fail."""
    from basedbench.db.migrations import run_migrations
    run_migrations(db.conn)
    row = db.conn.execute(
        "SELECT COUNT(*) FROM pragma_table_info('predictions') WHERE name = 'dataset_version'"
    ).fetchone()
    assert row[0] == 1


def test_migrate_creates_llm_calls_table(db: Database):
    count = db.conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='llm_calls'"
    ).fetchone()[0]
    assert count == 1


def test_migrate_creates_dataset_pushes_table(db: Database):
    count = db.conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='dataset_pushes'"
    ).fetchone()[0]
    assert count == 1


# ═══════════════════════════════════════════════════════
# Memes
# ═══════════════════════════════════════════════════════


def test_insert_and_check_meme(db: Database):
    post = sample_post("post1")
    assert q.insert_meme(db, post) is True
    assert q.meme_exists(db, "post1") is True
    assert q.meme_exists(db, "nonexistent") is False


def test_insert_meme_idempotent(db: Database):
    post = sample_post("post1")
    assert q.insert_meme(db, post) is True
    assert q.insert_meme(db, post) is False


# ═══════════════════════════════════════════════════════
# Comments
# ═══════════════════════════════════════════════════════


def test_insert_and_get_comments(db: Database):
    post = sample_post("post1")
    q.insert_meme(db, post)
    for c in post.comments:
        q.insert_comment(db, "post1", c)
    comments = q.get_comments(db, "post1")
    assert len(comments) == 2
    # Ordered by score descending
    assert comments[0].score == 50
    assert comments[1].score == 30


# ═══════════════════════════════════════════════════════
# Ground Truths
# ═══════════════════════════════════════════════════════


def test_ground_truth_operations(db: Database):
    post = sample_post("post1")
    q.insert_meme(db, post)

    # Before ground truth
    missing = q.memes_without_ground_truth(db)
    assert missing == ["post1"]

    # Upsert ground truth
    q.upsert_ground_truth(
        db, "post1", "This meme is about cats", 0.9,
        ["c1", "c2"], 5, 42.0, "gpt-4o-mini", "prompt_v1",
    )

    # After ground truth
    missing = q.memes_without_ground_truth(db)
    assert missing == []

    pairs = q.get_all_ground_truths(db)
    assert len(pairs) == 1
    assert pairs[0] == ("post1", "This meme is about cats")


def test_reconstruct_raw_post(db: Database):
    post = sample_post("post1")
    q.insert_meme(db, post)
    for c in post.comments:
        q.insert_comment(db, "post1", c)

    reconstructed = q.reconstruct_raw_post(db, "post1")
    assert reconstructed is not None
    assert reconstructed.post_id == "post1"
    assert len(reconstructed.comments) == 2

    assert q.reconstruct_raw_post(db, "nonexistent") is None


# ═══════════════════════════════════════════════════════
# Reviews
# ═══════════════════════════════════════════════════════


def test_quality_gate_query(db: Database):
    post = sample_post("post1")
    q.insert_meme(db, post)

    needing = q.memes_needing_quality_gate(db)
    assert "post1" in needing


def test_auto_review_idempotent(db: Database):
    post = sample_post("post1")
    q.insert_meme(db, post)

    assert q.insert_auto_review(db, "post1", "no humor") is True
    assert q.insert_auto_review(db, "post1", "different reason") is False


def test_upsert_review(db: Database):
    post = sample_post("post1")
    q.insert_meme(db, post)
    q.upsert_ground_truth(
        db, "post1", "explanation", 0.9, [], 3, 10.0, "model", "v1",
    )

    q.upsert_review(db, "post1", "validated")
    status = q.get_status_counts(db)
    assert status.validated == 1


# ═══════════════════════════════════════════════════════
# Predictions
# ═══════════════════════════════════════════════════════


def _setup_validated_meme(db: Database, post_id: str = "post1"):
    """Helper: insert meme, ground truth, and validate."""
    post = sample_post(post_id)
    q.insert_meme(db, post)
    for c in post.comments:
        q.insert_comment(db, post_id, c)
    q.upsert_ground_truth(
        db, post_id, "This meme is about cats", 0.9,
        ["c1", "c2"], 5, 42.0, "gpt-4o-mini", "prompt_v1",
    )
    q.upsert_review(db, post_id, "validated")


def test_insert_prediction(db: Database):
    _setup_validated_meme(db)
    pred = ModelPrediction.success(
        "post1", "v1", "gpt-4o", "It's about cats", 1500, 200,
    )
    assert q.insert_prediction(db, pred) is True


def test_prediction_upsert_only_overwrites_failures(db: Database):
    _setup_validated_meme(db)

    # Insert failure
    fail = ModelPrediction.failure("post1", "v1", "gpt-4o", "timeout")
    q.insert_prediction(db, fail)

    # Overwrite with success
    success = ModelPrediction.success(
        "post1", "v1", "gpt-4o", "It's about cats", 1500, 200,
    )
    assert q.insert_prediction(db, success) is True

    # Verify success is stored
    pid = q.find_prediction_id(db, "post1", "gpt-4o")
    assert pid is not None


def test_success_not_overwritten_by_failure(db: Database):
    _setup_validated_meme(db)

    success = ModelPrediction.success(
        "post1", "v1", "gpt-4o", "It's about cats", 1500, 200,
    )
    q.insert_prediction(db, success)

    # Try to overwrite with failure — should not change
    fail = ModelPrediction.failure("post1", "v1", "gpt-4o", "timeout")
    assert q.insert_prediction(db, fail) is False


def test_memes_needing_prediction(db: Database):
    _setup_validated_meme(db)

    needing = q.memes_needing_prediction(db, "gpt-4o")
    assert len(needing) == 1
    assert needing[0].post_id == "post1"

    # After prediction, should be empty
    pred = ModelPrediction.success(
        "post1", "v1", "gpt-4o", "explanation", 100, 50,
    )
    q.insert_prediction(db, pred)
    needing = q.memes_needing_prediction(db, "gpt-4o")
    assert len(needing) == 0


def test_find_prediction_id(db: Database):
    _setup_validated_meme(db)

    assert q.find_prediction_id(db, "post1", "gpt-4o") is None

    pred = ModelPrediction.success(
        "post1", "v1", "gpt-4o", "explanation", 100, 50,
    )
    q.insert_prediction(db, pred)
    pid = q.find_prediction_id(db, "post1", "gpt-4o")
    assert pid is not None
    assert pid > 0


# ═══════════════════════════════════════════════════════
# Judgments
# ═══════════════════════════════════════════════════════


def test_judgment_flow(db: Database):
    _setup_validated_meme(db)
    pred = ModelPrediction.success(
        "post1", "v1", "gpt-4o", "It's about cats", 1500, 200,
    )
    q.insert_prediction(db, pred)

    # Needs judgment
    needing = q.predictions_needing_judgment(db)
    assert len(needing) == 1
    assert needing[0].post_id == "post1"

    # Register prompt version (FK on judgments.judge_prompt_version)
    q.register_prompt(db, "v1", "judge", "system", "user", "1.0")

    # Judge it
    pid = q.find_prediction_id(db, "post1", "gpt-4o")
    q.insert_judgment(db, pid, "correct", "Correct explanation", "gpt-4o-mini", "v1")

    # No longer needs judgment
    needing = q.predictions_needing_judgment(db)
    assert len(needing) == 0


def test_predictions_needing_judgment_model_filter(db: Database):
    _setup_validated_meme(db)

    pred1 = ModelPrediction.success("post1", "v1", "gpt-4o", "cats", 100, 50)
    q.insert_prediction(db, pred1)

    # Filter by model
    needing = q.predictions_needing_judgment(db, model_id="gpt-4o")
    assert len(needing) == 1

    needing = q.predictions_needing_judgment(db, model_id="claude-3")
    assert len(needing) == 0


# ═══════════════════════════════════════════════════════
# Snapshots
# ═══════════════════════════════════════════════════════


def test_snapshot_creation(db: Database):
    _setup_validated_meme(db, "post1")
    _setup_validated_meme(db, "post2")

    sid = q.create_snapshot(db, "test-snapshot", "A test snapshot")

    snaps = q.list_snapshots(db)
    assert len(snaps) == 1
    assert snaps[0].name == "test-snapshot"
    assert snaps[0].meme_count == 2

    meme_ids = q.snapshot_meme_ids(db, sid)
    assert sorted(meme_ids) == ["post1", "post2"]


def test_snapshot_no_validated_memes(db: Database):
    import pytest
    from basedbench.errors import ConfigError

    with pytest.raises(ConfigError):
        q.create_snapshot(db, "empty")


def test_find_snapshot(db: Database):
    _setup_validated_meme(db)
    sid = q.create_snapshot(db, "v1-release")

    # By name
    found = q.find_snapshot(db, "v1-release")
    assert found is not None
    assert found.snapshot_id == sid

    # By ID prefix
    found = q.find_snapshot(db, sid[:8])
    assert found is not None

    # Not found
    assert q.find_snapshot(db, "nonexistent") is None


# ═══════════════════════════════════════════════════════
# Image path
# ═══════════════════════════════════════════════════════


def test_update_image_path(db: Database):
    post = sample_post("post1")
    q.insert_meme(db, post)
    q.update_meme_image_path(db, "post1", "data/images/post1.jpg")

    raw = q.reconstruct_raw_post(db, "post1")
    # image_url is original, local_image_path is updated via separate query
    # but reconstruct doesn't expose local_image_path directly on RawPost
    # Verify via direct SQL
    row = db.conn.execute(
        "SELECT local_image_path FROM memes WHERE post_id = ?", ("post1",)
    ).fetchone()
    assert row[0] == "data/images/post1.jpg"


# ═══════════════════════════════════════════════════════
# Excluded memes
# ═══════════════════════════════════════════════════════


def test_excluded_memes_not_in_prediction_queue(db: Database):
    post = sample_post("post1")
    q.insert_meme(db, post)
    q.upsert_ground_truth(
        db, "post1", "explanation", 0.9, [], 3, 10.0, "model", "v1",
    )
    q.upsert_review(db, "post1", "excluded", "not a meme")

    needing = q.memes_needing_prediction(db, "gpt-4o")
    assert len(needing) == 0


# ═══════════════════════════════════════════════════════
# Status
# ═══════════════════════════════════════════════════════


def test_status_counts(db: Database):
    _setup_validated_meme(db, "post1")
    _setup_validated_meme(db, "post2")

    post3 = sample_post("post3")
    q.insert_meme(db, post3)
    q.upsert_ground_truth(
        db, "post3", "explanation", 0.9, [], 3, 10.0, "model", "v1",
    )
    q.upsert_review(db, "post3", "excluded", "bad")

    status = q.get_status_counts(db)
    assert status.total_memes == 3
    assert status.with_consensus == 3
    assert status.validated == 2
    assert status.excluded == 1
    assert status.unreviewed == 0


# ═══════════════════════════════════════════════════════
# LLM Call Logging
# ═══════════════════════════════════════════════════════


def test_llm_call_logging(db: Database):
    post = sample_post("post1")
    q.insert_meme(db, post)

    record = LlmCallRecord(
        role="consensus",
        post_id="post1",
        model="gpt-4o-mini",
        system_prompt="system",
        user_prompt="user",
        prompt_version="v1",
        session_id="test-session",
        latency_ms=500,
        response='{"has_consensus": true}',
    )
    q.insert_llm_call(db, record)

    calls = q.list_llm_calls(db, role="consensus")
    assert len(calls) == 1
    assert calls[0].model == "gpt-4o-mini"

    detail = q.get_llm_call(db, calls[0].id)
    assert detail is not None
    assert detail.session_id == "test-session"
    assert detail.response == '{"has_consensus": true}'


def test_llm_call_filters(db: Database):
    post = sample_post("post1")
    q.insert_meme(db, post)

    for role in ["consensus", "judge", "judge"]:
        q.insert_llm_call(db, LlmCallRecord(
            role=role, post_id="post1", model="gpt-4o-mini",
            system_prompt="s", user_prompt="u", prompt_version="v1",
            session_id="sess1", latency_ms=100,
        ))

    assert len(q.list_llm_calls(db, role="judge")) == 2
    assert len(q.list_llm_calls(db, role="consensus")) == 1
    assert len(q.list_llm_calls(db)) == 3


# ═══════════════════════════════════════════════════════
# Export / Leaderboard
# ═══════════════════════════════════════════════════════


def test_snapshot_export_helpers(db: Database):
    _setup_validated_meme(db, "post1")
    _setup_validated_meme(db, "post2")

    pred1 = ModelPrediction.success("post1", "v1", "gpt-4o", "cats", 100, 50)
    pred2 = ModelPrediction.success("post2", "v1", "gpt-4o", "dogs", 100, 50)
    q.insert_prediction(db, pred1)
    q.insert_prediction(db, pred2)

    q.register_prompt(db, "v1", "judge", "system", "user", "1.0")

    pid1 = q.find_prediction_id(db, "post1", "gpt-4o")
    pid2 = q.find_prediction_id(db, "post2", "gpt-4o")
    q.insert_judgment(db, pid1, "correct", "good", "gpt-4o-mini", "v1")
    q.insert_judgment(db, pid2, "incorrect", "bad", "gpt-4o-mini", "v1")

    sid = q.create_snapshot(db, "export-test")

    # Meme details
    memes = q.snapshot_meme_details(db, sid)
    assert len(memes) == 2

    # Model IDs
    models = q.snapshot_model_ids(db, sid)
    assert models == ["gpt-4o"]

    # Predictions for model — verdicts dict keyed by judge_model
    preds = q.snapshot_predictions_for_model(db, sid, "gpt-4o")
    assert len(preds) == 2
    assert all("gpt-4o-mini" in p.verdicts for p in preds)
    p_by_post = {p.post_id: p for p in preds}
    assert p_by_post["post1"].verdicts["gpt-4o-mini"]["verdict"] == "correct"
    assert p_by_post["post2"].verdicts["gpt-4o-mini"]["verdict"] == "incorrect"

    # Leaderboard — one row per (target, judge)
    lb = q.snapshot_leaderboard(db, sid)
    assert len(lb) == 1
    assert lb[0].model_id == "gpt-4o"
    assert lb[0].judge_model == "gpt-4o-mini"
    assert lb[0].correct == 1
    assert lb[0].total == 2
    assert lb[0].accuracy == 0.5
