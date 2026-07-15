"""Normalized dataset loading and indexing for the read-only Space."""

from __future__ import annotations

import os
from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any


DEFAULT_DATASET_REPO = "montagovian/basedBench"


def _column(table: Any, name: str) -> list[Any]:
    try:
        return list(table[name])
    except (KeyError, TypeError):
        return [row[name] for row in table]


class BenchmarkData:
    """In-memory indexes over the four normalized dataset configs."""

    def __init__(
        self,
        memes: Any,
        predictions: Iterable[Mapping[str, Any]],
        judgments: Iterable[Mapping[str, Any]],
        leaderboard: Iterable[Mapping[str, Any]],
    ) -> None:
        self._memes = memes
        post_ids = [str(value) for value in _column(memes, "post_id")]
        titles = [str(value) for value in _column(memes, "title")]
        subreddits = [str(value) for value in _column(memes, "subreddit")]
        ground_truths = [str(value) for value in _column(memes, "ground_truth")]
        snapshot_ids = [str(value) for value in _column(memes, "snapshot_id")]

        self.post_ids = post_ids
        self._row_index = {post_id: idx for idx, post_id in enumerate(post_ids)}
        self._meta = {
            post_id: {
                "post_id": post_id,
                "title": titles[idx],
                "subreddit": subreddits[idx],
                "ground_truth": ground_truths[idx],
                "snapshot_id": snapshot_ids[idx],
            }
            for idx, post_id in enumerate(post_ids)
        }

        self.predictions_by_post: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.predictions_by_id: dict[int, dict[str, Any]] = {}
        for source in predictions:
            row = dict(source)
            prediction_id = int(row["prediction_id"])
            post_id = str(row["post_id"])
            self.predictions_by_id[prediction_id] = row
            self.predictions_by_post[post_id].append(row)
        for rows in self.predictions_by_post.values():
            rows.sort(key=lambda row: str(row["model_id"]))

        self.latest_judgments: dict[int, list[dict[str, Any]]] = defaultdict(list)
        self.historical_judgment_counts: dict[int, int] = defaultdict(int)
        for source in judgments:
            row = dict(source)
            prediction_id = int(row["prediction_id"])
            if bool(row.get("is_latest")):
                self.latest_judgments[prediction_id].append(row)
            else:
                self.historical_judgment_counts[prediction_id] += 1
        for rows in self.latest_judgments.values():
            rows.sort(key=lambda row: str(row["judge_model"]))

        self.leaderboard = [dict(row) for row in leaderboard]
        self.leaderboard.sort(
            key=lambda row: (-float(row["accuracy"]), str(row["model_id"]))
        )
        self.models = sorted(
            {
                str(row["model_id"])
                for rows in self.predictions_by_post.values()
                for row in rows
            }
        )

    @property
    def snapshot_id(self) -> str:
        if not self.post_ids:
            return ""
        return str(self._meta[self.post_ids[0]]["snapshot_id"])

    def meme(self, post_id: str) -> dict[str, Any]:
        return self._meta[post_id]

    def image(self, post_id: str) -> Any:
        return self._memes[self._row_index[post_id]]["image"]

    def predictions(self, post_id: str, model_id: str = "all") -> list[dict[str, Any]]:
        rows = self.predictions_by_post.get(post_id, [])
        if model_id == "all":
            return rows
        return [row for row in rows if str(row["model_id"]) == model_id]

    def judgments(self, prediction_id: int) -> list[dict[str, Any]]:
        return self.latest_judgments.get(prediction_id, [])

    def filtered_ids(
        self,
        search: str = "",
        model_id: str = "all",
        outcome: str = "all",
    ) -> list[str]:
        needle = search.strip().casefold()
        matches: list[str] = []
        for post_id in self.post_ids:
            meta = self._meta[post_id]
            if needle and needle not in " ".join(
                (
                    post_id,
                    str(meta["title"]),
                    str(meta["subreddit"]),
                    str(meta["ground_truth"]),
                )
            ).casefold():
                continue

            predictions = self.predictions(post_id, model_id)
            if model_id != "all" and not predictions:
                continue
            verdicts = {
                row.get("consensus_verdict")
                for row in predictions
                if row.get("consensus_verdict") in {"correct", "incorrect"}
            }
            if outcome == "all_correct" and verdicts != {"correct"}:
                continue
            if outcome == "all_incorrect" and verdicts != {"incorrect"}:
                continue
            if outcome == "mixed" and verdicts != {"correct", "incorrect"}:
                continue
            matches.append(post_id)
        return matches

    def leaderboard_rows(self) -> list[list[Any]]:
        return [
            [
                row["model_id"],
                int(row["correct"]),
                int(row["incorrect"]),
                int(row["total"]),
                f"{float(row['accuracy']) * 100:.1f}%",
                (
                    f"{int(row['unanimous_agreements'])}/"
                    f"{int(row['judged_by_multiple'])} "
                    f"({float(row['agreement_rate']) * 100:.1f}%)"
                ),
            ]
            for row in self.leaderboard
        ]


def load_from_hub(repo_id: str | None = None) -> BenchmarkData:
    """Load the published snapshot directly from the Hub, not dataset-server."""
    from datasets import load_dataset

    repo = repo_id or os.getenv("HF_DATASET_REPO", DEFAULT_DATASET_REPO)
    token = os.getenv("HF_TOKEN") or os.getenv("HF_API_KEY")
    kwargs = {"token": token} if token else {}
    try:
        memes = load_dataset(repo, "memes", split="train", **kwargs)
        predictions = load_dataset(repo, "predictions", split="train", **kwargs)
        judgments = load_dataset(repo, "judgments", split="train", **kwargs)
        leaderboard = load_dataset(repo, "leaderboard", split="train", **kwargs)
    except Exception as exc:
        raise RuntimeError(
            f"Unable to load {repo}. For a private dataset, add an HF_TOKEN "
            "with read access to the Space secrets."
        ) from exc
    return BenchmarkData(memes, predictions, judgments, leaderboard)
