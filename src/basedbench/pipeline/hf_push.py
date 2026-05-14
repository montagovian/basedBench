"""Push a snapshot to the HuggingFace Hub as a multi-config dataset.

Configs published:
- `memes`:                 ground truth + embedded image
- `predictions_<model>`:   per-model predictions + verdict
- `leaderboard`:           per-model accuracy summary

Anyone can then `datasets.load_dataset("user/basedbench", "memes")`.
"""

from __future__ import annotations

import logging
from pathlib import Path

from rich.console import Console

from basedbench.config import Config
from basedbench.db import queries
from basedbench.db.connection import Database
from basedbench.errors import ConfigError

log = logging.getLogger(__name__)


def _safe_config_name(model_id: str) -> str:
    """HF config names must be filesystem-safe."""
    return "predictions_" + model_id.replace("/", "_").replace(":", "_")


def _resolve_image(config: Config, local_image_path: str | None) -> Path | None:
    if not local_image_path:
        return None
    p = Path(local_image_path)
    if not p.is_absolute():
        p = config.project_root / p
    return p if p.exists() else None


def run(
    db: Database,
    config: Config,
    snapshot_name: str,
    repo_id: str | None = None,
    private: bool = False,
    console: Console | None = None,
) -> None:
    """Push a snapshot to the HF Hub.

    Requires `config.hf_token` and either `repo_id` argument or `config.hf_dataset_repo`.
    """
    console = console or Console()

    if not config.hf_token:
        raise ConfigError("HF_TOKEN required to push to HuggingFace Hub")
    repo = repo_id or config.hf_dataset_repo
    if not repo:
        raise ConfigError(
            "HF dataset repo required (set HF_DATASET_REPO or pass --repo)"
        )

    snapshot = queries.find_snapshot(db, snapshot_name)
    if snapshot is None:
        raise ValueError(f"snapshot not found: {snapshot_name}")

    # Lazy imports — these are big and only needed when pushing.
    from datasets import Dataset, Features, Image, Value
    from huggingface_hub import HfApi

    HfApi(token=config.hf_token).create_repo(
        repo_id=repo, repo_type="dataset", exist_ok=True, private=private
    )

    # ─── memes config ───
    memes = queries.snapshot_meme_details(db, snapshot.snapshot_id)
    console.print(f"Building 'memes' config ({len(memes)} rows)...")
    image_paths: list[str | None] = []
    skipped_missing = 0
    rows: dict[str, list] = {
        "post_id": [],
        "title": [],
        "subreddit": [],
        "ground_truth": [],
        "image": [],
    }
    for m in memes:
        img = _resolve_image(config, m.local_image_path)
        if img is None:
            skipped_missing += 1
            continue
        rows["post_id"].append(m.post_id)
        rows["title"].append(m.title)
        rows["subreddit"].append(m.subreddit)
        rows["ground_truth"].append(m.ground_truth)
        rows["image"].append(str(img))
        image_paths.append(str(img))

    if not rows["post_id"]:
        raise ValueError("no memes with on-disk images to push")
    if skipped_missing:
        console.print(f"  [yellow]skipped {skipped_missing} memes with missing images[/yellow]")

    memes_ds = Dataset.from_dict(
        rows,
        features=Features(
            {
                "post_id": Value("string"),
                "title": Value("string"),
                "subreddit": Value("string"),
                "ground_truth": Value("string"),
                "image": Image(),
            }
        ),
    )
    memes_ds.push_to_hub(repo, config_name="memes", token=config.hf_token, private=private)

    # ─── per-model prediction configs ───
    model_ids = queries.snapshot_model_ids(db, snapshot.snapshot_id)
    for model_id in model_ids:
        preds = queries.snapshot_predictions_for_model(db, snapshot.snapshot_id, model_id)
        pred_ds = Dataset.from_dict(
            {
                "post_id": [p.post_id for p in preds],
                "prediction": [p.prediction for p in preds],
                "verdict": [p.verdict or "" for p in preds],
                "reasoning": [p.reasoning or "" for p in preds],
            }
        )
        cfg = _safe_config_name(model_id)
        console.print(f"Pushing '{cfg}' ({len(preds)} predictions)...")
        pred_ds.push_to_hub(repo, config_name=cfg, token=config.hf_token, private=private)

    # ─── leaderboard config ───
    leaderboard = queries.snapshot_leaderboard(db, snapshot.snapshot_id)
    lb_ds = Dataset.from_dict(
        {
            "model_id": [e.model_id for e in leaderboard],
            "correct": [e.correct for e in leaderboard],
            "total": [e.total for e in leaderboard],
            "accuracy": [e.accuracy for e in leaderboard],
        }
    )
    console.print(f"Pushing 'leaderboard' ({len(leaderboard)} models)...")
    lb_ds.push_to_hub(repo, config_name="leaderboard", token=config.hf_token, private=private)

    queries.insert_dataset_push(
        db,
        snapshot_id=snapshot.snapshot_id,
        hf_repo=repo,
        meme_count=len(rows["post_id"]),
        model_count=len(model_ids),
    )

    console.print(
        f"\n[bold green]Pushed snapshot '{snapshot.name}' to "
        f"https://huggingface.co/datasets/{repo}[/bold green]"
    )
