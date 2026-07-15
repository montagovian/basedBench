"""Tests for db/ module — mirrors v4 query tests."""

import pytest

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


def test_migrate_creates_batches_tables(db: Database):
    batches = db.conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='batches'"
    ).fetchone()[0]
    batch_memes = db.conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='batch_memes'"
    ).fetchone()[0]
    assert batches == 1
    assert batch_memes == 1


def test_migrate_creates_processing_state_table(db: Database):
    count = db.conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='meme_processing_state'"
    ).fetchone()[0]
    version = db.conn.execute("PRAGMA user_version").fetchone()[0]
    assert count == 1
    assert version == 11


def test_migrate_creates_consensus_eval_tables(db: Database):
    tables = db.conn.execute(
        """SELECT name FROM sqlite_master
           WHERE type='table' AND name LIKE 'consensus_eval_%'
           ORDER BY name"""
    ).fetchall()
    assert [r[0] for r in tables] == [
        "consensus_eval_items",
        "consensus_eval_results",
        "consensus_eval_runs",
    ]


def test_migrate_creates_image_fingerprints_table(db: Database):
    count = db.conn.execute(
        """SELECT COUNT(*) FROM sqlite_master
           WHERE type='table' AND name='image_fingerprints'"""
    ).fetchone()[0]
    assert count == 1


def test_migrate_creates_tag_tables(db: Database):
    tables = db.conn.execute(
        """SELECT name FROM sqlite_master
           WHERE type='table' AND name IN ('tags', 'meme_tags')
           ORDER BY name"""
    ).fetchall()
    assert [r[0] for r in tables] == ["meme_tags", "tags"]


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


def test_meme_tags_roundtrip(db: Database):
    q.insert_meme(db, sample_post("post1"))

    q.add_meme_tag(db, "post1", "Failure: Visual Reference Miss", "misses the sign")
    q.add_meme_tag(db, "post1", "failure: visual reference miss", "updated note")

    tags = q.list_tags(db)
    meme_tags = q.tags_for_meme(db, "post1")

    assert len(tags) == 1
    assert tags[0].name == "Failure: Visual Reference Miss"
    assert len(meme_tags) == 1
    assert meme_tags[0].name == "Failure: Visual Reference Miss"
    assert meme_tags[0].notes == "updated note"

    assert q.remove_meme_tag(db, "post1", "FAILURE: VISUAL REFERENCE MISS")
    assert q.tags_for_meme(db, "post1") == []


def test_tag_management_preserves_associations_and_cascades(db: Database):
    q.insert_meme(db, sample_post("post1"))
    q.insert_meme(db, sample_post("post2"))

    q.add_meme_tag(db, "post1", "Failure: Visual Reference Miss", "misses the sign")
    q.add_meme_tag(db, "post2", "Failure: Visual Reference Miss", "same issue")
    q.add_meme_tag(db, "post2", "Failure: Cultural Context")

    summaries = q.list_tag_summaries(db)
    assert [(t.name, t.meme_count) for t in summaries] == [
        ("Failure: Cultural Context", 1),
        ("Failure: Visual Reference Miss", 2),
    ]
    assert (
        q.meme_tag_note(db, "post1", "failure: visual reference miss")
        == "misses the sign"
    )

    assert q.update_tag(
        db,
        "failure: visual reference miss",
        "Visual Reference Miss",
        "Image detail was missed",
    )
    renamed = q.tag_summary_by_name(db, "visual reference miss")
    assert renamed is not None
    assert renamed.name == "Visual Reference Miss"
    assert renamed.description == "Image detail was missed"
    assert renamed.meme_count == 2
    assert [t.name for t in q.tags_for_meme(db, "post1")] == ["Visual Reference Miss"]

    with pytest.raises(ValueError, match="already exists"):
        q.update_tag(db, "Visual Reference Miss", "Failure: Cultural Context")

    assert q.delete_tag(db, "Visual Reference Miss")
    assert q.tag_summary_by_name(db, "Visual Reference Miss") is None
    assert q.tags_for_meme(db, "post1") == []
    assert [t.name for t in q.tags_for_meme(db, "post2")] == [
        "Failure: Cultural Context"
    ]


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


def test_safety_candidates_skip_same_prompt_terminal_state(db: Database):
    post = sample_post("post1")
    q.insert_meme(db, post)

    assert q.memes_needing_safety_gate(db, "model-a", "safety-v1") == ["post1"]
    q.record_meme_processing_state(
        db, "post1", "safety", "model-a", "safety-v1", "passed"
    )

    assert q.memes_needing_safety_gate(db, "model-a", "safety-v1") == []
    assert q.memes_needing_safety_gate(db, "model-a", "safety-v2") == ["post1"]


def test_consensus_candidates_skip_same_prompt_no_consensus(db: Database):
    post = sample_post("post1")
    q.insert_meme(db, post)

    assert q.memes_without_ground_truth(db, "model-a", "consensus-v1") == ["post1"]
    q.record_meme_processing_state(
        db, "post1", "consensus", "model-a", "consensus-v1", "no_consensus"
    )

    assert q.memes_without_ground_truth(db, "model-a", "consensus-v1") == []
    assert q.memes_without_ground_truth(db, "model-a", "consensus-v2") == ["post1"]


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


def test_scoped_prediction_query_includes_only_requested_unreviewed(db: Database):
    _setup_validated_meme(db, "validated")
    _setup_validated_meme(db, "unreviewed")
    _setup_validated_meme(db, "excluded")
    _setup_validated_meme(db, "global_backlog")
    db.conn.execute("DELETE FROM reviews WHERE post_id = 'unreviewed'")
    q.upsert_review(db, "excluded", "excluded", "bad")

    scoped = q.memes_for_prediction_by_ids(
        db,
        "gpt-4o",
        ["unreviewed", "excluded"],
        validated_only=False,
    )
    assert [m.post_id for m in scoped] == ["unreviewed"]

    validated_only = q.memes_for_prediction_by_ids(
        db,
        "gpt-4o",
        ["validated", "unreviewed", "global_backlog"],
        validated_only=True,
    )
    assert [m.post_id for m in validated_only] == ["validated", "global_backlog"]

    pred = ModelPrediction.success("validated", "v1", "gpt-4o", "done", 100, 50)
    q.insert_prediction(db, pred)
    after_pred = q.memes_for_prediction_by_ids(
        db,
        "gpt-4o",
        ["validated", "global_backlog"],
        validated_only=True,
    )
    assert [m.post_id for m in after_pred] == ["global_backlog"]


def test_scoped_judgment_query_does_not_require_review(db: Database):
    _setup_validated_meme(db, "unreviewed")
    _setup_validated_meme(db, "global_pred")
    db.conn.execute("DELETE FROM reviews WHERE post_id = 'unreviewed'")
    q.insert_prediction(
        db, ModelPrediction.success("unreviewed", "v1", "gpt-4o", "x", 100, 50)
    )
    q.insert_prediction(
        db, ModelPrediction.success("global_pred", "v1", "gpt-4o", "y", 100, 50)
    )

    scoped = q.predictions_needing_judgment_for_post_ids(
        db,
        ["unreviewed"],
        "gpt-4o",
        "judge-a",
    )
    assert [p.post_id for p in scoped] == ["unreviewed"]

    q.register_prompt(db, "judge_prompt", "judge", "s", "u", "1.0")
    q.insert_judgment(
        db,
        scoped[0].prediction_id,
        "correct",
        "ok",
        "judge-a",
        "judge_prompt",
    )
    assert q.predictions_needing_judgment_for_post_ids(
        db, ["unreviewed"], "gpt-4o", "judge-a"
    ) == []


# ═══════════════════════════════════════════════════════
# Prompt versions / batches
# ═══════════════════════════════════════════════════════


def test_register_gate_prompt_roles(db: Database):
    q.register_prompt(db, "safety_v1", "safety_gate", "s", "u", "1.0")
    q.register_prompt(db, "quality_v1", "quality_gate", "s", "u", "1.0")
    roles = db.conn.execute(
        "SELECT role FROM prompt_versions ORDER BY role"
    ).fetchall()
    assert [r[0] for r in roles] == ["quality_gate", "safety_gate"]


def test_batch_helpers_track_order_and_status(db: Database):
    q.create_batch(db, "batch1", "tracer", params_json='{"fetch": 2}')
    q.insert_meme(db, sample_post("post1"))
    q.insert_meme(db, sample_post("post2"))

    assert q.add_batch_meme(db, "batch1", "post2", 2) is True
    assert q.add_batch_meme(db, "batch1", "post1", 1) is True
    assert q.add_batch_meme(db, "batch1", "post1", 1) is False
    assert q.batch_meme_ids(db, "batch1") == ["post1", "post2"]

    q.update_batch_meme_status(db, "batch1", "post1", "consensus")
    q.update_batch_meme_status(db, "batch1", "post2", "no_consensus")
    assert q.batch_stage_counts(db, "batch1") == {
        "consensus": 1,
        "no_consensus": 1,
    }

    found = q.find_batch(db, "batch1")
    assert found is not None
    assert found.kind == "tracer"


# ═══════════════════════════════════════════════════════
# Consensus eval harness
# ═══════════════════════════════════════════════════════


def test_consensus_eval_item_upsert_and_list(db: Database):
    _setup_validated_meme(db, "p1")

    q.upsert_consensus_eval_item(
        db,
        "p1",
        "bad_gloss",
        True,
        expected_explanation="The better explanation.",
        source="manual",
        notes="top comments support a different gloss",
    )
    q.upsert_consensus_eval_item(
        db,
        "p1",
        "source_comment_mismatch",
        True,
        expected_explanation="Updated expectation.",
        source="manual_review",
    )

    items = q.list_consensus_eval_items(db)
    assert len(items) == 1
    assert items[0].post_id == "p1"
    assert items[0].category == "source_comment_mismatch"
    assert items[0].expected_has_consensus is True
    assert items[0].expected_explanation == "Updated expectation."
    assert items[0].source == "manual_review"
    assert q.consensus_eval_category_counts(db) == {"source_comment_mismatch": 1}


def test_consensus_eval_seeding_from_flags_and_controls(db: Database):
    _setup_validated_meme(db, "flagged_bad")
    _setup_validated_meme(db, "flagged_gate")
    _setup_validated_meme(db, "yes_control")
    no_post = sample_post("no_control")
    q.insert_meme(db, no_post)
    for comment in no_post.comments:
        q.insert_comment(db, "no_control", comment)
    q.record_meme_processing_state(
        db,
        "no_control",
        "consensus",
        "model",
        "prompt",
        "no_consensus",
    )

    q.flag_consensus_regression(
        db,
        "flagged_bad",
        "wrong",
        consensus_at_annotation="Old wrong explanation.",
        canonical_explanation="Corrected explanation.",
        failure_modes="vote_bias",
    )
    q.flag_gate_feedback(
        db,
        "flagged_gate",
        "consensus",
        gate_decision="no_consensus",
        correct_decision="consensus",
        notes="humans agreed but gate missed it",
    )

    assert q.seed_consensus_eval_from_regressions(db) == 2
    assert q.seed_consensus_eval_yes_controls(db, 10) == 1
    assert q.seed_consensus_eval_no_controls(db, 10) == 1

    counts = q.consensus_eval_category_counts(db)
    assert counts == {
        "bad_gloss": 1,
        "easy_yes_consensus": 1,
        "hard_yes_consensus": 1,
        "true_no_consensus": 1,
    }


def test_consensus_eval_run_and_result_round_trip(db: Database):
    _setup_validated_meme(db, "p1")
    q.upsert_consensus_eval_item(
        db,
        "p1",
        "easy_yes_consensus",
        True,
        expected_explanation="Expected explanation.",
        source="validated_control",
    )
    item = q.list_consensus_eval_items(db)[0]

    q.create_consensus_eval_run(
        db,
        run_id="run1",
        model="gpt-test",
        prompt_version="prompt-v1",
        prompt_label="baseline",
        system_prompt="system",
        user_prompt_template="user",
        item_count=1,
        notes="smoke",
    )
    q.insert_consensus_eval_result(
        db,
        "run1",
        item,
        actual_has_consensus=True,
        actual_explanation="Actual explanation.",
        confidence=0.91,
        agreeing_comment_ids=["p1_c1", "p1_c2"],
        reasoning="comments agree",
        passed=True,
        latency_ms=123,
        llm_call_id=None,
    )

    runs = q.list_consensus_eval_runs(db)
    assert len(runs) == 1
    assert runs[0].run_id == "run1"
    assert runs[0].prompt_label == "baseline"
    assert q.latest_consensus_eval_run_id(db) == "run1"

    results = q.list_consensus_eval_results(db, "run1")
    assert len(results) == 1
    assert results[0].post_id == "p1"
    assert results[0].passed is True
    assert results[0].actual_has_consensus is True
    assert results[0].agreeing_comment_ids == '["p1_c1", "p1_c2"]'


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


def test_prediction_counts_only_include_currently_validated_memes(db: Database):
    _setup_validated_meme(db, "validated")

    post = sample_post("excluded")
    q.insert_meme(db, post)
    q.upsert_ground_truth(
        db, "excluded", "explanation", 0.9, [], 3, 10.0, "model", "v1",
    )
    q.upsert_review(db, "excluded", "excluded", "bad")

    q.insert_prediction(
        db,
        ModelPrediction.success("validated", "v1", "gpt-5.5", "ok", 1, 1),
    )
    q.insert_prediction(
        db,
        ModelPrediction.success("excluded", "v1", "gpt-5.5", "old", 1, 1),
    )

    counts = {c.model_id: c for c in q.get_prediction_counts(db)}
    assert counts["gpt-5.5"].predicted == 1
    assert counts["gpt-5.5"].total_available == 1


def test_judgment_counts_ignore_non_validated_predictions(db: Database):
    _setup_validated_meme(db, "validated")

    post = sample_post("excluded")
    q.insert_meme(db, post)
    q.upsert_ground_truth(
        db, "excluded", "explanation", 0.9, [], 3, 10.0, "model", "v1",
    )
    q.upsert_review(db, "excluded", "excluded", "bad")

    q.insert_prediction(
        db,
        ModelPrediction.success("validated", "v1", "gpt-5.5", "ok", 1, 1),
    )
    q.insert_prediction(
        db,
        ModelPrediction.success("excluded", "v1", "gpt-5.5", "old", 1, 1),
    )
    q.register_prompt(db, "judge-v1", "judge", "s", "u", "1.0")
    validated_pid = q.find_prediction_id(db, "validated", "gpt-5.5")
    excluded_pid = q.find_prediction_id(db, "excluded", "gpt-5.5")

    q.insert_judgment(db, validated_pid, "correct", "", "gpt-5.4-mini", "judge-v1")
    q.insert_judgment(db, excluded_pid, "incorrect", "", "gpt-5.4-mini", "judge-v1")

    counts = {(c.model_id, c.judge_model): c for c in q.get_judgment_counts(db)}
    row = counts[("gpt-5.5", "gpt-5.4-mini")]
    assert row.judged == 1
    assert row.correct == 1
    assert row.incorrect == 0


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


def test_flag_and_list_consensus_regression(db: Database):
    _setup_validated_meme(db, "p1")
    _setup_validated_meme(db, "p2")

    q.flag_consensus_regression(
        db,
        post_id="p1",
        status="wrong",
        consensus_at_annotation="A bad gloss.",
        canonical_explanation="The real joke is X.",
        failure_modes="vote_bias,merged_views",
        reviewer_notes="Top votes were misleading.",
    )
    q.flag_consensus_regression(
        db,
        post_id="p2",
        status="partial",
        consensus_at_annotation="Half-right.",
    )

    all_entries = q.list_consensus_regressions(db)
    assert len(all_entries) == 2
    by_id = {e.post_id: e for e in all_entries}
    assert by_id["p1"].status == "wrong"
    assert by_id["p1"].failure_modes == "vote_bias,merged_views"
    assert by_id["p1"].canonical_explanation == "The real joke is X."
    assert by_id["p2"].status == "partial"
    assert by_id["p2"].canonical_explanation is None


def test_flag_consensus_regression_invalid_status_raises(db: Database):
    _setup_validated_meme(db, "p1")
    with pytest.raises(ValueError, match="invalid status"):
        q.flag_consensus_regression(
            db, post_id="p1", status="nonsense", consensus_at_annotation="x"
        )


def test_flag_consensus_regression_is_idempotent(db: Database):
    """Re-flagging the same post overwrites the prior entry, doesn't duplicate."""
    _setup_validated_meme(db, "p1")
    q.flag_consensus_regression(db, "p1", "wrong", consensus_at_annotation="v1")
    q.flag_consensus_regression(db, "p1", "partial", consensus_at_annotation="v2")
    entries = q.list_consensus_regressions(db)
    assert len(entries) == 1
    assert entries[0].status == "partial"
    assert entries[0].consensus_at_annotation == "v2"


def test_list_consensus_regressions_filters_by_status(db: Database):
    _setup_validated_meme(db, "a")
    _setup_validated_meme(db, "b")
    _setup_validated_meme(db, "c")
    q.flag_consensus_regression(db, "a", "wrong", consensus_at_annotation="x")
    q.flag_consensus_regression(db, "b", "wrong", consensus_at_annotation="y")
    q.flag_consensus_regression(db, "c", "partial", consensus_at_annotation="z")

    wrong_only = q.list_consensus_regressions(db, status="wrong")
    assert {e.post_id for e in wrong_only} == {"a", "b"}


def test_unflag_consensus_regression(db: Database):
    _setup_validated_meme(db, "p1")
    q.flag_consensus_regression(db, "p1", "wrong", consensus_at_annotation="x")
    assert q.unflag_consensus_regression(db, "p1") is True
    assert q.unflag_consensus_regression(db, "p1") is False  # already gone
    assert q.list_consensus_regressions(db) == []


# ═══════════════════════════════════════════════════════
# Gate feedback (filter misfires)
# ═══════════════════════════════════════════════════════


def test_migrate_creates_gate_feedback_table(db: Database):
    count = db.conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='gate_feedback'"
    ).fetchone()[0]
    assert count == 1


def test_flag_and_list_gate_feedback(db: Database):
    _setup_validated_meme(db, "p1")
    _setup_validated_meme(db, "p2")
    q.flag_gate_feedback(
        db, "p1", "quality", gate_decision="pass",
        correct_decision="exclude", notes="scrambled nonsense",
    )
    q.flag_gate_feedback(db, "p2", "consensus", gate_decision="no_consensus")

    entries = q.list_gate_feedback(db)
    assert {e.post_id for e in entries} == {"p1", "p2"}
    p1 = next(e for e in entries if e.post_id == "p1")
    assert p1.gate == "quality"
    assert p1.gate_decision == "pass"
    assert p1.correct_decision == "exclude"
    assert p1.notes == "scrambled nonsense"


def test_list_gate_feedback_filters_by_gate(db: Database):
    _setup_validated_meme(db, "a")
    _setup_validated_meme(db, "b")
    q.flag_gate_feedback(db, "a", "safety")
    q.flag_gate_feedback(db, "b", "quality")
    assert {e.post_id for e in q.list_gate_feedback(db, gate="safety")} == {"a"}


def test_flag_gate_feedback_idempotent_per_gate(db: Database):
    """Re-flagging the same (post, gate) overwrites; a different gate adds a row."""
    _setup_validated_meme(db, "p1")
    q.flag_gate_feedback(db, "p1", "quality", notes="first")
    q.flag_gate_feedback(db, "p1", "quality", notes="second")
    q.flag_gate_feedback(db, "p1", "safety", notes="other gate")
    entries = q.list_gate_feedback(db, gate="quality")
    assert len(entries) == 1
    assert entries[0].notes == "second"
    assert len(q.list_gate_feedback(db)) == 2  # quality + safety


def test_flag_gate_feedback_invalid_gate_raises(db: Database):
    import sqlite3
    _setup_validated_meme(db, "p1")
    with pytest.raises(sqlite3.IntegrityError):
        q.flag_gate_feedback(db, "p1", "bogus")


def test_unflag_gate_feedback(db: Database):
    _setup_validated_meme(db, "p1")
    q.flag_gate_feedback(db, "p1", "quality")
    assert q.unflag_gate_feedback(db, "p1", "quality") is True
    assert q.unflag_gate_feedback(db, "p1", "quality") is False
    assert q.list_gate_feedback(db) == []


def test_auto_exclude_missing_images(db: Database):
    """Memes with consensus but no local_image_path get auto-excluded."""
    # Two consensus-passed memes: one with image, one without.
    _setup_validated_meme(db, "with_image")  # don't actually validate; revert below
    _setup_validated_meme(db, "no_image")
    # Remove the review rows from setup so they're in "needs review" state.
    db.conn.execute("DELETE FROM reviews")
    # Set image path explicitly.
    q.update_meme_image_path(db, "with_image", "data/images/with_image.jpg")
    # Leave 'no_image' with NULL local_image_path.

    n = q.auto_exclude_missing_images(db)
    assert n == 1

    review = db.conn.execute(
        "SELECT status, reason FROM reviews WHERE post_id='no_image'"
    ).fetchone()
    assert review == ("excluded", "image_missing")
    no_review = db.conn.execute(
        "SELECT 1 FROM reviews WHERE post_id='with_image'"
    ).fetchone()
    assert no_review is None


def test_auto_exclude_missing_images_idempotent(db: Database):
    """Re-running doesn't double-exclude; uses INSERT OR IGNORE."""
    _setup_validated_meme(db, "broken")
    db.conn.execute("DELETE FROM reviews")  # back to needs-review state

    first = q.auto_exclude_missing_images(db)
    second = q.auto_exclude_missing_images(db)
    assert first == 1
    assert second == 0  # already excluded


def test_auto_exclude_missing_images_scoped(db: Database):
    """Scoped cleanup leaves unrelated missing-image backlog alone."""
    _setup_validated_meme(db, "in_scope")
    _setup_validated_meme(db, "out_of_scope")
    db.conn.execute("DELETE FROM reviews")

    n = q.auto_exclude_missing_images(db, ["in_scope"])
    assert n == 1

    reviews = db.conn.execute(
        "SELECT post_id, status, reason FROM reviews ORDER BY post_id"
    ).fetchall()
    assert reviews == [("in_scope", "excluded", "image_missing")]


def test_consensus_quality_stats_empty(db: Database):
    stats = q.consensus_quality_stats(db)
    assert stats.n_grounded == 0
    assert stats.mean_confidence == 0.0
    assert stats.confidence_histogram == [0] * 10


def test_consensus_quality_stats_aggregates(db: Database):
    """Insert 3 ground truths with varied confidences; check the rollup."""
    for pid in ("p1", "p2", "p3"):
        _setup_validated_meme(db, pid)
    # confidence 0.95 (bin 9), 0.85 (bin 8), 0.75 (bin 7)
    q.upsert_ground_truth(db, "p1", "x", 0.95, ["c1", "c2"], 5, 42.0, "m", "v1")
    q.upsert_ground_truth(db, "p2", "y", 0.85, ["c1"], 3, 20.0, "m", "v1")
    q.upsert_ground_truth(db, "p3", "z", 0.75, ["c1", "c2", "c3"], 7, 30.0, "m", "v1")

    stats = q.consensus_quality_stats(db)
    assert stats.n_grounded == 3
    assert abs(stats.mean_confidence - 0.85) < 1e-9
    assert stats.median_agreeing_comments == 5  # middle of {3, 5, 7}
    assert stats.confidence_histogram[7] == 1
    assert stats.confidence_histogram[8] == 1
    assert stats.confidence_histogram[9] == 1
    assert sum(stats.confidence_histogram) == 3


def test_consensus_quality_stats_handles_confidence_one(db: Database):
    """Confidence exactly 1.0 should land in bin 9 (not crash via index 10)."""
    _setup_validated_meme(db, "p1")
    q.upsert_ground_truth(db, "p1", "x", 1.0, ["c1"], 3, 10.0, "m", "v1")
    stats = q.consensus_quality_stats(db)
    assert stats.confidence_histogram[9] == 1


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
    q.insert_judgment(db, pid1, "correct", "good", "claude-sonnet-4-6", "v1")
    q.insert_judgment(db, pid2, "incorrect", "bad", "gpt-4o-mini", "v1")
    q.insert_judgment(db, pid2, "incorrect", "bad", "claude-sonnet-4-6", "v1")

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

    # Leaderboard — one consensus row per target model
    lb = q.snapshot_leaderboard(db, sid)
    assert len(lb) == 1
    assert lb[0].model_id == "gpt-4o"
    assert lb[0].judge_model == "consensus"
    assert lb[0].correct == 1
    assert lb[0].total == 2
    assert lb[0].accuracy == 0.5


def test_normalized_snapshot_export_preserves_judgment_history(db: Database):
    _setup_validated_meme(db, "post1")
    q.insert_prediction(
        db,
        ModelPrediction.success(
            "post1", "dataset-v1", "target-model", "cats", 120, 40
        ),
    )
    q.insert_llm_call(
        db,
        LlmCallRecord(
            role="prediction",
            post_id="post1",
            model="target-model",
            system_prompt="system",
            user_prompt="user",
            prompt_version="prediction-prompt-v1",
            session_id="session-1",
            latency_ms=120,
            response="cats",
        ),
    )
    q.register_prompt(db, "judge-prompt-v1", "judge", "system", "user", "1.0")
    q.register_prompt(db, "judge-prompt-v2", "judge", "system", "user", "2.0")

    prediction_id = q.find_prediction_id(db, "post1", "target-model")
    assert prediction_id is not None
    q.insert_judgment(
        db, prediction_id, "incorrect", "old vote", "judge-a", "judge-prompt-v1"
    )
    q.insert_judgment(
        db, prediction_id, "correct", "new vote", "judge-a", "judge-prompt-v2"
    )
    q.insert_judgment(
        db, prediction_id, "correct", "agrees", "judge-b", "judge-prompt-v2"
    )
    snapshot_id = q.create_snapshot(db, "normalized-export")

    predictions = q.snapshot_predictions(db, snapshot_id)
    assert len(predictions) == 1
    prediction = predictions[0]
    assert prediction.prediction_id == prediction_id
    assert prediction.prediction_prompt_id == "prediction-prompt-v1"
    assert prediction.consensus_verdict == "correct"
    assert prediction.judge_count == 2
    assert prediction.correct_votes == 2
    assert prediction.incorrect_votes == 0

    judgments = q.snapshot_judgments(db, snapshot_id)
    assert len(judgments) == 3
    judge_a = [j for j in judgments if j.judge_model == "judge-a"]
    assert [j.reasoning for j in judge_a] == ["old vote", "new vote"]
    assert [j.is_latest for j in judge_a] == [False, True]
    assert all(j.prediction_id == prediction_id for j in judgments)


def test_snapshot_export_helpers_exclude_failed_predictions(db: Database):
    _setup_validated_meme(db, "post1")
    _setup_validated_meme(db, "post2")

    q.insert_prediction(
        db, ModelPrediction.success("post1", "v1", "gpt-5.5", "ok", 100, 50)
    )
    q.insert_prediction(
        db, ModelPrediction.failure("post2", "v1", "gpt-5.5", "rate limit")
    )
    q.insert_prediction(
        db, ModelPrediction.failure("post1", "v1", "failed-only", "rate limit")
    )

    q.register_prompt(db, "judge-v1", "judge", "system", "user", "1.0")
    good_pid = q.find_prediction_id(db, "post1", "gpt-5.5")
    failed_pid = q.find_prediction_id(db, "post2", "gpt-5.5")
    q.insert_judgment(db, good_pid, "correct", "good", "gpt-5.4-mini", "judge-v1")
    q.insert_judgment(db, good_pid, "correct", "good", "claude-sonnet-4-6", "judge-v1")
    q.insert_judgment(db, failed_pid, "incorrect", "bad", "gpt-5.4-mini", "judge-v1")
    q.insert_judgment(
        db, failed_pid, "incorrect", "bad", "claude-sonnet-4-6", "judge-v1"
    )

    sid = q.create_snapshot(db, "export-failures")

    assert q.snapshot_model_ids(db, sid) == ["gpt-5.5"]
    preds = q.snapshot_predictions_for_model(db, sid, "gpt-5.5")
    assert [p.post_id for p in preds] == ["post1"]
    assert preds[0].prediction == "ok"

    leaderboard = q.snapshot_leaderboard(db, sid)
    assert len(leaderboard) == 1
    assert leaderboard[0].model_id == "gpt-5.5"
    assert leaderboard[0].correct == 1
    assert leaderboard[0].total == 1


def test_config_allows_openai_only_commands_without_anthropic_key(monkeypatch):
    from basedbench.config import Config

    monkeypatch.setenv("REDDIT_CLIENT_ID", "id")
    monkeypatch.setenv("REDDIT_CLIENT_SECRET", "secret")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    config = Config(_env_file=None)  # type: ignore[call-arg]

    assert config.openai_api_key == "sk-test"
    assert config.anthropic_api_key is None
