"""Tests for the normalized data indexes used by the Hugging Face Space."""

from space.data import BenchmarkData


def _data() -> BenchmarkData:
    memes = [
        {
            "snapshot_id": "snapshot-1",
            "post_id": "p1",
            "title": "Cat reference",
            "subreddit": "memes",
            "ground_truth": "The cat recognizes the song.",
            "image": "cat-image",
        },
        {
            "snapshot_id": "snapshot-1",
            "post_id": "p2",
            "title": "Dog reference",
            "subreddit": "dankmemes",
            "ground_truth": "The dog misunderstands the sign.",
            "image": "dog-image",
        },
    ]
    predictions = [
        {
            "prediction_id": 1,
            "post_id": "p1",
            "model_id": "model-a",
            "prediction": "cat answer",
            "consensus_verdict": "correct",
        },
        {
            "prediction_id": 2,
            "post_id": "p1",
            "model_id": "model-b",
            "prediction": "other answer",
            "consensus_verdict": "incorrect",
        },
        {
            "prediction_id": 3,
            "post_id": "p2",
            "model_id": "model-a",
            "prediction": "dog answer",
            "consensus_verdict": "incorrect",
        },
    ]
    judgments = [
        {
            "prediction_id": 1,
            "judge_model": "judge-a",
            "verdict": "incorrect",
            "is_latest": False,
        },
        {
            "prediction_id": 1,
            "judge_model": "judge-a",
            "verdict": "correct",
            "is_latest": True,
        },
        {
            "prediction_id": 1,
            "judge_model": "judge-b",
            "verdict": "correct",
            "is_latest": True,
        },
        {
            "prediction_id": 2,
            "judge_model": "judge-a",
            "verdict": "correct",
            "is_latest": True,
        },
        {
            "prediction_id": 2,
            "judge_model": "judge-b",
            "verdict": "incorrect",
            "is_latest": True,
        },
    ]
    leaderboard = [
        {
            "model_id": "model-a",
            "correct": 1,
            "incorrect": 1,
            "total": 2,
            "accuracy": 0.5,
            "unanimous_agreements": 1,
            "judged_by_multiple": 2,
            "agreement_rate": 0.5,
        },
        {
            "model_id": "model-b",
            "correct": 0,
            "incorrect": 1,
            "total": 1,
            "accuracy": 0.0,
            "unanimous_agreements": 0,
            "judged_by_multiple": 1,
            "agreement_rate": 0.0,
        },
    ]
    return BenchmarkData(memes, predictions, judgments, leaderboard)


def test_indexes_only_latest_judgments() -> None:
    data = _data()

    assert [row["verdict"] for row in data.judgments(1)] == ["correct", "correct"]
    assert data.historical_judgment_counts[1] == 1
    assert data.image("p1") == "cat-image"
    assert data.snapshot_id == "snapshot-1"


def test_filters_search_model_result_and_disagreement() -> None:
    data = _data()

    assert data.filtered_ids(search="song") == ["p1"]
    assert data.filtered_ids(model_id="model-b") == ["p1"]
    assert data.filtered_ids(model_id="model-a", result="correct") == ["p1"]
    assert data.filtered_ids(result="incorrect") == ["p1", "p2"]
    assert data.filtered_ids(result="disagreement") == ["p1"]


def test_leaderboard_rows_are_ranked_and_formatted() -> None:
    rows = _data().leaderboard_rows()

    assert rows[0] == ["model-a", 1, 1, 2, "50.0%", "1/2 (50.0%)"]
    assert rows[1] == ["model-b", 0, 1, 1, "0.0%", "0/1 (0.0%)"]
