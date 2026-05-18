"""Export pipeline: write a snapshot to disk as JSONL + images + dataset card.

A HuggingFace Hub push uses this same on-disk layout via `datasets.load_dataset`.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from rich.console import Console

from basedbench.config import Config
from basedbench.db import queries
from basedbench.db.connection import Database


def _safe_model_name(model_id: str) -> str:
    return model_id.replace("/", "_")


def _image_filename(post_id: str, local_image_path: str | None) -> str:
    if local_image_path:
        ext = Path(local_image_path).suffix.lstrip(".") or "jpg"
    else:
        ext = "jpg"
    return f"{post_id}.{ext}"


def run(
    db: Database,
    config: Config,
    snapshot_name: str,
    output_dir: Path,
    console: Console | None = None,
) -> Path:
    """Export a snapshot to `output_dir`. Returns the output_dir."""
    console = console or Console()
    snapshot = queries.find_snapshot(db, snapshot_name)
    if snapshot is None:
        raise ValueError(f"snapshot not found: {snapshot_name}")

    output_dir = Path(output_dir)
    (output_dir / "data" / "predictions").mkdir(parents=True, exist_ok=True)
    (output_dir / "images").mkdir(parents=True, exist_ok=True)

    memes = queries.snapshot_meme_details(db, snapshot.snapshot_id)
    with (output_dir / "data" / "memes.jsonl").open("w") as f:
        for meme in memes:
            line = {
                "post_id": meme.post_id,
                "title": meme.title,
                "subreddit": meme.subreddit,
                "ground_truth": meme.ground_truth,
                "image_filename": _image_filename(meme.post_id, meme.local_image_path),
            }
            f.write(json.dumps(line) + "\n")

    model_ids = queries.snapshot_model_ids(db, snapshot.snapshot_id)
    for model_id in model_ids:
        preds = queries.snapshot_predictions_for_model(db, snapshot.snapshot_id, model_id)
        out = output_dir / "data" / "predictions" / f"{_safe_model_name(model_id)}.jsonl"
        with out.open("w") as f:
            for p in preds:
                f.write(
                    json.dumps(
                        {
                            "post_id": p.post_id,
                            "prediction": p.prediction,
                            "verdicts": p.verdicts,
                        }
                    )
                    + "\n"
                )

    leaderboard = queries.snapshot_leaderboard(db, snapshot.snapshot_id)
    agreement = queries.get_judge_agreement(db, snapshot.snapshot_id)
    with (output_dir / "data" / "leaderboard.json").open("w") as f:
        json.dump(
            {
                "entries": [
                    {
                        "model_id": e.model_id,
                        "judge_model": e.judge_model,
                        "correct": e.correct,
                        "total": e.total,
                        "accuracy": f"{e.accuracy:.4f}",
                    }
                    for e in leaderboard
                ],
                "agreement": [
                    {
                        "model_id": a.model_id,
                        "judged_by_multiple": a.judged_by_multiple,
                        "agreements": a.agreements,
                        "rate": f"{a.rate:.4f}",
                    }
                    for a in agreement
                ],
            },
            f,
            indent=2,
        )

    images_copied = 0
    for meme in memes:
        if not meme.local_image_path:
            continue
        src = Path(meme.local_image_path)
        if not src.is_absolute():
            src = config.project_root / src
        if src.exists():
            ext = src.suffix.lstrip(".") or "jpg"
            shutil.copy(src, output_dir / "images" / f"{meme.post_id}.{ext}")
            images_copied += 1

    dataset_info = {
        "description": f"BasedBench VLM Meme Understanding Benchmark - {snapshot.name}",
        "citation": "",
        "homepage": "",
        "license": "",
        "features": {
            "post_id": {"dtype": "string", "_type": "Value"},
            "title": {"dtype": "string", "_type": "Value"},
            "subreddit": {"dtype": "string", "_type": "Value"},
            "ground_truth": {"dtype": "string", "_type": "Value"},
            "image_filename": {"dtype": "string", "_type": "Value"},
        },
        "splits": {"test": {"num_examples": len(memes)}},
    }
    (output_dir / "dataset_info.json").write_text(json.dumps(dataset_info, indent=2))

    leaderboard_rows = "\n".join(
        f"| {e.model_id} | {e.correct} | {e.total} | {e.accuracy * 100:.1f}% |"
        for e in leaderboard
    )
    readme = f"""---
license: mit
task_categories:
  - visual-question-answering
  - image-to-text
tags:
  - memes
  - vlm
  - benchmark
---

# BasedBench: {snapshot.name}

VLM Meme Understanding Benchmark. {len(memes)} memes with human-validated
ground truth explanations derived from Reddit comment consensus.

## Leaderboard

| Model | Correct | Total | Accuracy |
|-------|---------|-------|----------|
{leaderboard_rows}

## Usage

```python
from datasets import load_dataset
ds = load_dataset("path/to/export")
```

## Methodology

Ground truth explanations are extracted from Reddit comments via LLM consensus
detection (>=3 comments agreeing on the same specific explanation). Each model
prediction is judged as correct/incorrect by an LLM judge using strict criteria.

Snapshot: {snapshot.snapshot_id}
Created: {snapshot.created_at}
"""
    (output_dir / "README.md").write_text(readme)

    console.print(f'Exported snapshot "{snapshot.name}" to {output_dir}/')
    console.print(
        f"  {len(memes)} memes, {len(model_ids)} models, {images_copied} images copied"
    )
    return output_dir
