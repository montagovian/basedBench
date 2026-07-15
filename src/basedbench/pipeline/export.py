"""Export a snapshot as normalized JSONL tables, images, and a dataset card."""

from __future__ import annotations

import json
import shutil
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from rich.console import Console

from basedbench.config import Config
from basedbench.db import queries
from basedbench.db.connection import Database
from basedbench.model_policy import is_active_summary_model


def _image_filename(post_id: str, local_image_path: str | None) -> str:
    if local_image_path:
        ext = Path(local_image_path).suffix.lstrip(".") or "jpg"
    else:
        ext = "jpg"
    return f"{post_id}.{ext}"


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def _build_dataset_card(
    *,
    snapshot_name: str,
    snapshot_id: str,
    created_at: str,
    meme_count: int,
    prediction_count: int,
    judgment_count: int,
    leaderboard_rows: str,
    dataset_repo: str = "your-username/basedbench",
) -> str:
    return f"""---
license: other
task_categories:
  - visual-question-answering
  - image-to-text
tags:
  - memes
  - vlm
  - benchmark
  - humor-understanding
---

# BasedBench: {snapshot_name}

BasedBench is a VLM meme-understanding benchmark. This snapshot contains
{meme_count} human-validated memes with ground-truth explanations derived from
Reddit comment consensus.

## Task Definition

The task is to determine whether a model gets the joke in a meme. A correct
prediction identifies the relevant people, events, meme formats, media, phrases,
visual details, or cultural references, then reconstructs the intended setup,
implication, contrast, inversion, irony, wordplay, or other mechanism a viewer
must notice to understand the meme.

This benchmark does not test whether a model can produce a psychological or
aesthetic theory of why something is funny.

## Leaderboard

| Model | Correct | Total | Accuracy |
|-------|---------|-------|----------|
{leaderboard_rows}

## Dataset Contents

The public artifact includes:

- Reddit post IDs, titles, and subreddit names.
- Meme images used as benchmark stimuli.
- Human-validated ground-truth explanations.
- Every successful model prediction retained by BasedBench for this snapshot.
- Every judge verdict and reasoning record for those predictions, including
  superseded rejudgments.
- Derived consensus fields and leaderboard totals.

Raw Reddit comments, Reddit authors, review metadata, reviewer notes, consensus
source comment IDs, local file paths, API request metadata, internal prompts, raw
LLM responses, and LLM call logs are intentionally omitted.

## Usage

```python
from datasets import load_dataset

memes = load_dataset("{dataset_repo}", "memes")
predictions = load_dataset("{dataset_repo}", "predictions")
judgments = load_dataset("{dataset_repo}", "judgments")
leaderboard = load_dataset("{dataset_repo}", "leaderboard")
```

## Dataset Structure

The dataset uses normalized long-form tables joined by `snapshot_id`, `post_id`,
and `prediction_id`:

- `memes` has one row per meme in the snapshot, with the image, title,
  subreddit, and human-validated ground truth.
- `predictions` has one row per successful model prediction. It includes the
  target model, prediction text, dataset and prompt versions where available,
  latency, token count, timestamp, and derived consensus vote fields.
- `judgments` has one row per judgment attempt. It includes the target and judge
  models, verdict, reasoning, judge prompt ID, timestamp, and an `is_latest`
  marker. Historical rejudgments remain present.
- `leaderboard` has one derived row per target model, including score coverage
  and judge agreement statistics.

Failed API calls and operational error messages are not benchmark predictions
and are omitted from the public tables. The current BasedBench database retains
one successful prediction per `(post_id, model_id)` pair; historical successful
prediction reruns that were never retained by the database cannot be exported.

## Methodology

Ground-truth explanations are extracted from Reddit comments via LLM consensus
detection. A candidate ground truth must reflect at least three substantive
comments agreeing on the same specific explanation, and a human reviewer must
validate the meme before it enters a release snapshot.

Predictor models receive only the meme image. They do not receive the Reddit
title, comments, subreddit, ground truth, web search, or external tools.

Each model prediction is scored by an LLM judge ensemble using strict criteria:
the judge asks whether the model recovered the same joke as the ground truth.
For derived consensus fields and leaderboard accuracy, only the latest judgment
from each `(prediction_id, judge_model)` pair is counted. A prediction receives
a consensus verdict when at least two judges cast the same verdict and that
verdict has a strict majority; otherwise it is omitted from the leaderboard
denominator. All individual and historical judgments remain available in the
`judgments` config.

## License and Rights

This dataset has mixed rights status, so the machine-readable Hugging Face
license is `other`.

Materials created and controlled by the BasedBench maintainers are released
under the MIT License. This includes the benchmark code, dataset schema, export
format, evaluation prompts where applicable, benchmark-specific metadata,
leaderboard tables, judge verdicts and reasoning, and other maintainer-authored
documentation and annotations to the extent the maintainers own or control those
materials.

Meme images, Reddit post titles, subreddit names, post IDs, cultural references,
logos, characters, screenshots, and other source artifacts may be owned by third
parties. The BasedBench maintainers do not claim ownership of those underlying
third-party materials. The MIT License for this repository does not apply to
those third-party materials; all such rights remain with their respective
owners.

The meme images and limited source metadata are included under a fair-use
rationale for research, criticism, commentary, and benchmark evaluation. The use
is transformative: the images are used as individual test stimuli for measuring
whether vision-language models understand the intended joke, not as a substitute
for the original posts or images. The dataset uses only the material needed to
support that benchmark task, omits raw comment text and authors, and does not
serve as a general-purpose meme archive or replacement market for the source
works.

Users are responsible for determining whether their downstream use of any
third-party material is permitted by law or by the relevant rights holder. If you
believe specific material should not be included, please contact the dataset
maintainers through the Hugging Face repository or the project repository.

## Intended Use

This dataset is intended for research and evaluation of multimodal model
understanding, especially whether models can connect visual details, text,
cultural references, and joke structure.

It is not intended for training models to impersonate Reddit users, reconstruct
deleted discussions, identify commenters, or build a general meme redistribution
corpus.

## Snapshot

- Snapshot name: `{snapshot_name}`
- Snapshot ID: `{snapshot_id}`
- Created: `{created_at}`
- Memes: {meme_count}
- Successful predictions: {prediction_count}
- Judgment records: {judgment_count}
"""


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
    (output_dir / "data").mkdir(parents=True, exist_ok=True)
    (output_dir / "images").mkdir(parents=True, exist_ok=True)

    memes = queries.snapshot_meme_details(db, snapshot.snapshot_id)
    _write_jsonl(
        output_dir / "data" / "memes.jsonl",
        (
            {
                "snapshot_id": snapshot.snapshot_id,
                "post_id": meme.post_id,
                "title": meme.title,
                "subreddit": meme.subreddit,
                "ground_truth": meme.ground_truth,
                "image_filename": _image_filename(meme.post_id, meme.local_image_path),
            }
            for meme in memes
        ),
    )

    predictions = queries.snapshot_predictions(db, snapshot.snapshot_id)
    _write_jsonl(
        output_dir / "data" / "predictions.jsonl",
        (
            {
                "prediction_id": p.prediction_id,
                "snapshot_id": p.snapshot_id,
                "post_id": p.post_id,
                "model_id": p.model_id,
                "prediction": p.prediction,
                "dataset_version": p.dataset_version,
                "prediction_prompt_id": p.prediction_prompt_id,
                "latency_ms": p.latency_ms,
                "token_count": p.token_count,
                "created_at": p.created_at,
                "consensus_verdict": p.consensus_verdict,
                "judge_count": p.judge_count,
                "correct_votes": p.correct_votes,
                "incorrect_votes": p.incorrect_votes,
            }
            for p in predictions
        ),
    )

    judgments = queries.snapshot_judgments(db, snapshot.snapshot_id)
    _write_jsonl(
        output_dir / "data" / "judgments.jsonl",
        (
            {
                "judgment_id": j.judgment_id,
                "snapshot_id": j.snapshot_id,
                "prediction_id": j.prediction_id,
                "post_id": j.post_id,
                "model_id": j.model_id,
                "judge_model": j.judge_model,
                "verdict": j.verdict,
                "reasoning": j.reasoning,
                "judge_prompt_id": j.judge_prompt_id,
                "judged_at": j.judged_at,
                "is_latest": j.is_latest,
            }
            for j in judgments
        ),
    )

    leaderboard = [
        e for e in queries.snapshot_leaderboard(db, snapshot.snapshot_id)
        if is_active_summary_model(e.model_id)
    ]
    agreement = [
        a for a in queries.get_judge_agreement(db, snapshot.snapshot_id)
        if is_active_summary_model(a.model_id)
    ]
    agreement_by_model = {a.model_id: a for a in agreement}
    _write_jsonl(
        output_dir / "data" / "leaderboard.jsonl",
        (
            {
                "snapshot_id": snapshot.snapshot_id,
                "model_id": e.model_id,
                "judge_model": e.judge_model,
                "correct": e.correct,
                "incorrect": e.total - e.correct,
                "total": e.total,
                "accuracy": e.accuracy,
                "judged_by_multiple": agreement_by_model[e.model_id].judged_by_multiple,
                "unanimous_agreements": agreement_by_model[e.model_id].agreements,
                "agreement_rate": agreement_by_model[e.model_id].rate,
            }
            for e in leaderboard
        ),
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

    model_ids = sorted({p.model_id for p in predictions})
    dataset_info = {
        "description": f"BasedBench VLM Meme Understanding Benchmark - {snapshot.name}",
        "license": "other",
        "snapshot_id": snapshot.snapshot_id,
        "configs": {
            "memes": {"num_rows": len(memes)},
            "predictions": {"num_rows": len(predictions)},
            "judgments": {"num_rows": len(judgments)},
            "leaderboard": {"num_rows": len(leaderboard)},
        },
    }
    (output_dir / "dataset_info.json").write_text(json.dumps(dataset_info, indent=2))

    leaderboard_rows = "\n".join(
        f"| {e.model_id} | {e.correct} | {e.total} | {e.accuracy * 100:.1f}% |"
        for e in leaderboard
    )
    readme = _build_dataset_card(
        snapshot_name=snapshot.name,
        snapshot_id=snapshot.snapshot_id,
        created_at=snapshot.created_at,
        meme_count=len(memes),
        prediction_count=len(predictions),
        judgment_count=len(judgments),
        leaderboard_rows=leaderboard_rows,
    )
    (output_dir / "README.md").write_text(readme)

    console.print(f'Exported snapshot "{snapshot.name}" to {output_dir}/')
    console.print(
        f"  {len(memes)} memes, {len(predictions)} predictions, "
        f"{len(judgments)} judgments, {len(model_ids)} models, "
        f"{images_copied} images copied"
    )
    return output_dir
