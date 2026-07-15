"""Push a snapshot to the HuggingFace Hub as a multi-config dataset.

Configs published:
- `memes`:       ground truth + embedded image
- `predictions`: normalized model predictions + derived consensus
- `judgments`:   every individual and historical judge record
- `leaderboard`: per-model accuracy and agreement summary

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
from basedbench.model_policy import is_active_summary_model
from basedbench.pipeline.export import _build_dataset_card

log = logging.getLogger(__name__)


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

    api = HfApi(token=config.hf_token)
    api.create_repo(
        repo_id=repo, repo_type="dataset", exist_ok=True, private=private
    )

    # ─── memes config ───
    memes = queries.snapshot_meme_details(db, snapshot.snapshot_id)
    console.print(f"Building 'memes' config ({len(memes)} rows)...")
    rows: dict[str, list] = {
        "snapshot_id": [],
        "post_id": [],
        "title": [],
        "subreddit": [],
        "ground_truth": [],
        "image": [],
    }
    for m in memes:
        img = _resolve_image(config, m.local_image_path)
        if img is None:
            raise ValueError(f"snapshot meme {m.post_id} has no on-disk image")
        rows["snapshot_id"].append(snapshot.snapshot_id)
        rows["post_id"].append(m.post_id)
        rows["title"].append(m.title)
        rows["subreddit"].append(m.subreddit)
        rows["ground_truth"].append(m.ground_truth)
        rows["image"].append(str(img))

    if not rows["post_id"]:
        raise ValueError("no memes with on-disk images to push")

    predictions = queries.snapshot_predictions(db, snapshot.snapshot_id)
    judgments = queries.snapshot_judgments(db, snapshot.snapshot_id)
    leaderboard = [
        e for e in queries.snapshot_leaderboard(db, snapshot.snapshot_id)
        if is_active_summary_model(e.model_id)
    ]
    agreement = [
        a for a in queries.get_judge_agreement(db, snapshot.snapshot_id)
        if is_active_summary_model(a.model_id)
    ]
    agreement_by_model = {a.model_id: a for a in agreement}

    # Upload the authored card first. Dataset.push_to_hub then merges each
    # config's machine-readable schema and shard metadata into its YAML header.
    leaderboard_rows = "\n".join(
        f"| {e.model_id} | {e.correct} | {e.total} | {e.accuracy * 100:.1f}% |"
        for e in leaderboard
    )
    readme = _build_dataset_card(
        snapshot_name=snapshot.name,
        snapshot_id=snapshot.snapshot_id,
        created_at=snapshot.created_at,
        meme_count=len(rows["post_id"]),
        prediction_count=len(predictions),
        judgment_count=len(judgments),
        leaderboard_rows=leaderboard_rows,
        dataset_repo=repo,
    )
    console.print("Pushing dataset card README.md...")
    api.upload_file(
        path_or_fileobj=readme.encode("utf-8"),
        path_in_repo="README.md",
        repo_id=repo,
        repo_type="dataset",
        commit_message="Update dataset card",
    )

    memes_ds = Dataset.from_dict(
        rows,
        features=Features(
            {
                "snapshot_id": Value("string"),
                "post_id": Value("string"),
                "title": Value("string"),
                "subreddit": Value("string"),
                "ground_truth": Value("string"),
                "image": Image(),
            }
        ),
    )
    memes_ds.push_to_hub(repo, config_name="memes", token=config.hf_token, private=private)

    # ─── normalized predictions config ───
    pred_ds = Dataset.from_dict(
        {
            "prediction_id": [p.prediction_id for p in predictions],
            "snapshot_id": [p.snapshot_id for p in predictions],
            "post_id": [p.post_id for p in predictions],
            "model_id": [p.model_id for p in predictions],
            "prediction": [p.prediction for p in predictions],
            "dataset_version": [p.dataset_version for p in predictions],
            "prediction_prompt_id": [p.prediction_prompt_id for p in predictions],
            "latency_ms": [p.latency_ms for p in predictions],
            "token_count": [p.token_count for p in predictions],
            "created_at": [p.created_at for p in predictions],
            "consensus_verdict": [p.consensus_verdict for p in predictions],
            "judge_count": [p.judge_count for p in predictions],
            "correct_votes": [p.correct_votes for p in predictions],
            "incorrect_votes": [p.incorrect_votes for p in predictions],
        },
        features=Features(
            {
                "prediction_id": Value("int64"),
                "snapshot_id": Value("string"),
                "post_id": Value("string"),
                "model_id": Value("string"),
                "prediction": Value("string"),
                "dataset_version": Value("string"),
                "prediction_prompt_id": Value("string"),
                "latency_ms": Value("int64"),
                "token_count": Value("int64"),
                "created_at": Value("string"),
                "consensus_verdict": Value("string"),
                "judge_count": Value("int64"),
                "correct_votes": Value("int64"),
                "incorrect_votes": Value("int64"),
            }
        ),
    )
    console.print(f"Pushing 'predictions' ({len(predictions)} rows)...")
    pred_ds.push_to_hub(
        repo, config_name="predictions", token=config.hf_token, private=private
    )

    # ─── raw judgments config ───
    judgment_ds = Dataset.from_dict(
        {
            "judgment_id": [j.judgment_id for j in judgments],
            "snapshot_id": [j.snapshot_id for j in judgments],
            "prediction_id": [j.prediction_id for j in judgments],
            "post_id": [j.post_id for j in judgments],
            "model_id": [j.model_id for j in judgments],
            "judge_model": [j.judge_model for j in judgments],
            "verdict": [j.verdict for j in judgments],
            "reasoning": [j.reasoning for j in judgments],
            "judge_prompt_id": [j.judge_prompt_id for j in judgments],
            "judged_at": [j.judged_at for j in judgments],
            "is_latest": [j.is_latest for j in judgments],
        },
        features=Features(
            {
                "judgment_id": Value("int64"),
                "snapshot_id": Value("string"),
                "prediction_id": Value("int64"),
                "post_id": Value("string"),
                "model_id": Value("string"),
                "judge_model": Value("string"),
                "verdict": Value("string"),
                "reasoning": Value("string"),
                "judge_prompt_id": Value("string"),
                "judged_at": Value("string"),
                "is_latest": Value("bool"),
            }
        ),
    )
    console.print(f"Pushing 'judgments' ({len(judgments)} rows)...")
    judgment_ds.push_to_hub(
        repo, config_name="judgments", token=config.hf_token, private=private
    )

    # ─── leaderboard config (per-target consensus rows) ───
    lb_ds = Dataset.from_dict(
        {
            "snapshot_id": [snapshot.snapshot_id for _ in leaderboard],
            "model_id": [e.model_id for e in leaderboard],
            "judge_model": [e.judge_model for e in leaderboard],
            "correct": [e.correct for e in leaderboard],
            "incorrect": [e.total - e.correct for e in leaderboard],
            "total": [e.total for e in leaderboard],
            "accuracy": [e.accuracy for e in leaderboard],
            "judged_by_multiple": [
                agreement_by_model[e.model_id].judged_by_multiple for e in leaderboard
            ],
            "unanimous_agreements": [
                agreement_by_model[e.model_id].agreements for e in leaderboard
            ],
            "agreement_rate": [
                agreement_by_model[e.model_id].rate for e in leaderboard
            ],
        }
    )
    console.print(f"Pushing 'leaderboard' ({len(leaderboard)} rows)...")
    lb_ds.push_to_hub(repo, config_name="leaderboard", token=config.hf_token, private=private)

    queries.insert_dataset_push(
        db,
        snapshot_id=snapshot.snapshot_id,
        hf_repo=repo,
        meme_count=len(rows["post_id"]),
        model_count=len({p.model_id for p in predictions}),
    )

    console.print(
        f"\n[bold green]Pushed snapshot '{snapshot.name}' to "
        f"https://huggingface.co/datasets/{repo}[/bold green]"
    )
