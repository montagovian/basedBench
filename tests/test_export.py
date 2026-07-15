"""Tests for normalized public export artifacts."""

import json

from basedbench.config import Config
from basedbench.db import queries as q
from basedbench.llm.record import LlmCallRecord
from basedbench.pipeline.export import _build_dataset_card
from basedbench.pipeline.export import run as run_export
from basedbench.pipeline.hf_push import run as run_hf_push
from basedbench.schemas import ModelPrediction

from .conftest import sample_post


def test_dataset_card_explains_mixed_rights_status() -> None:
    card = _build_dataset_card(
        snapshot_name="v0.1",
        snapshot_id="abc123",
        created_at="2026-07-14T00:00:00Z",
        meme_count=519,
        prediction_count=1038,
        judgment_count=3114,
        leaderboard_rows="| gpt-5.5 | 416 | 519 | 80.2% |",
        dataset_repo="montagovian/basedbench",
    )
    normalized = " ".join(card.split())

    assert "license: other" in card
    assert "Materials created and controlled by the BasedBench maintainers" in card
    assert "under the MIT License" in card
    assert "do not claim ownership" in card
    assert "The MIT License for this repository does not apply" in card
    assert "fair-use rationale" in normalized
    assert "research, criticism, commentary, and benchmark evaluation" in normalized
    assert "not as a substitute for the original posts or images" in normalized
    assert "Raw Reddit comments, Reddit authors" in card
    assert "intentionally omitted" in card
    assert '`predictions` has one row per successful model prediction' in card
    assert "Historical rejudgments remain present" in card
    assert "only the latest judgment" in normalized
    assert "Successful predictions: 1038" in card
    assert "Judgment records: 3114" in card
    assert 'load_dataset("montagovian/basedbench", "judgments")' in card


def _read_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_local_export_writes_normalized_tables(db, tmp_path) -> None:
    image_path = tmp_path / "post1.jpg"
    image_path.write_bytes(b"test-image")
    post = sample_post("post1")
    q.insert_meme(db, post)
    db.conn.execute(
        "UPDATE memes SET local_image_path = ? WHERE post_id = ?",
        (str(image_path), "post1"),
    )
    q.upsert_ground_truth(
        db, "post1", "The cat understands the joke", 0.9,
        ["c1", "c2"], 5, 42.0, "consensus-model", "consensus-prompt",
    )
    q.upsert_review(db, "post1", "validated")
    q.insert_prediction(
        db,
        ModelPrediction.success(
            "post1", "dataset-v1", "target-model", "It is about a cat", 100, 30
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
            latency_ms=100,
            response="It is about a cat",
        ),
    )
    q.register_prompt(db, "judge-prompt", "judge", "system", "user", "1.0")
    prediction_id = q.find_prediction_id(db, "post1", "target-model")
    q.insert_judgment(
        db, prediction_id, "correct", "matches", "judge-a", "judge-prompt"
    )
    q.insert_judgment(
        db, prediction_id, "correct", "also matches", "judge-b", "judge-prompt"
    )
    q.insert_judgment(
        db, prediction_id, "incorrect", "historical", "judge-b", "judge-prompt"
    )
    snapshot_id = q.create_snapshot(db, "export-test")

    config = Config(
        reddit_client_id="test",
        reddit_client_secret="test",
        openai_api_key="test",
    )
    output_dir = tmp_path / "export"
    run_export(db, config, "export-test", output_dir)

    memes = _read_jsonl(output_dir / "data" / "memes.jsonl")
    predictions = _read_jsonl(output_dir / "data" / "predictions.jsonl")
    judgments = _read_jsonl(output_dir / "data" / "judgments.jsonl")
    leaderboard = _read_jsonl(output_dir / "data" / "leaderboard.jsonl")

    assert memes[0]["snapshot_id"] == snapshot_id
    assert predictions[0]["prediction_id"] == prediction_id
    assert predictions[0]["prediction_prompt_id"] == "prediction-prompt-v1"
    assert predictions[0]["consensus_verdict"] is None
    assert len(judgments) == 3
    assert [j["is_latest"] for j in judgments if j["judge_model"] == "judge-b"] == [
        False,
        True,
    ]
    assert leaderboard == []
    assert (output_dir / "images" / "post1.jpg").read_bytes() == b"test-image"


def test_hf_push_uses_four_normalized_configs(db, tmp_path, monkeypatch) -> None:
    import datasets
    import huggingface_hub

    image_path = tmp_path / "post1.jpg"
    image_path.write_bytes(b"test-image")
    q.insert_meme(db, sample_post("post1"))
    db.conn.execute(
        "UPDATE memes SET local_image_path = ? WHERE post_id = ?",
        (str(image_path), "post1"),
    )
    q.upsert_ground_truth(
        db, "post1", "The cat understands the joke", 0.9,
        ["c1", "c2"], 5, 42.0, "consensus-model", "consensus-prompt",
    )
    q.upsert_review(db, "post1", "validated")
    q.insert_prediction(
        db,
        ModelPrediction.success(
            "post1", "dataset-v1", "target-model", "It is about a cat", 100, 30
        ),
    )
    q.register_prompt(db, "judge-prompt", "judge", "system", "user", "1.0")
    prediction_id = q.find_prediction_id(db, "post1", "target-model")
    q.insert_judgment(
        db, prediction_id, "correct", "matches", "judge-a", "judge-prompt"
    )
    q.insert_judgment(
        db, prediction_id, "correct", "also matches", "judge-b", "judge-prompt"
    )
    q.create_snapshot(db, "hf-export-test")

    pushed: list[tuple[str, int]] = []
    uploaded: dict = {}
    events: list[str] = []

    def fake_push(dataset, repo_id, *, config_name, **kwargs):
        pushed.append((config_name, len(dataset)))
        events.append(config_name)

    class FakeHfApi:
        def __init__(self, token):
            assert token == "hf-test"

        def create_repo(self, **kwargs):
            assert kwargs["repo_id"] == "test/basedbench"

        def upload_file(self, **kwargs):
            uploaded.update(kwargs)
            events.append("README.md")

    monkeypatch.setattr(datasets.Dataset, "push_to_hub", fake_push)
    monkeypatch.setattr(huggingface_hub, "HfApi", FakeHfApi)

    config = Config(
        reddit_client_id="test",
        reddit_client_secret="test",
        openai_api_key="test",
        hf_token="hf-test",
        hf_dataset_repo="test/basedbench",
    )
    run_hf_push(db, config, "hf-export-test")

    assert pushed == [
        ("memes", 1),
        ("predictions", 1),
        ("judgments", 2),
        ("leaderboard", 1),
    ]
    assert uploaded["path_in_repo"] == "README.md"
    assert uploaded["repo_type"] == "dataset"
    assert events == ["README.md", "memes", "predictions", "judgments", "leaderboard"]
