"""Offline reporting and privacy-allowlisted export of an immutable release."""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from basedbench.pipeline.release_snapshot import canonical_bytes, load_release


EVIDENCE_SCHEMA = "basedbench.release-evidence.v1"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _evidence_sha256(predictions: list[dict], judgments: list[dict],
                     historical: dict | None) -> str:
    """Digest only versioned evidence fields, independent of row order.

    The historical summary participates in the digest for local reproducibility,
    but its values are never copied to the public report.
    """
    prediction_fields = (
        "prediction_id", "post_id", "model_id", "prediction", "prediction_prompt_id",
        "image_sha256", "input_mode",
    )
    judgment_fields = (
        "judgment_id", "prediction_id", "judge_model", "verdict", "reasoning",
        "judge_prompt_id", "answer_sha256", "prediction_sha256", "scoring_version",
    )
    normalized = {
        "schema_version": EVIDENCE_SCHEMA,
        "predictions": sorted(
            ({key: row[key] for key in prediction_fields if key in row} for row in predictions),
            key=lambda row: row["prediction_id"],
        ),
        "judgments": sorted(
            ({key: row[key] for key in judgment_fields if key in row} for row in judgments),
            key=lambda row: row["judgment_id"],
        ),
    }
    if historical is not None:
        normalized["historical_summary"] = historical
    try:
        return hashlib.sha256(canonical_bytes(normalized)).hexdigest()
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("evidence contains invalid JSON values") from exc


def _string(row: dict, key: str, kind: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{kind}.{key} must be a nonempty string")
    return value


def _evidence(evidence: dict | None) -> tuple[list[dict], list[dict], dict | None]:
    if evidence is None:
        evidence = {"schema_version": EVIDENCE_SCHEMA, "predictions": [], "judgments": []}
    if not isinstance(evidence, dict) or evidence.get("schema_version") != EVIDENCE_SCHEMA:
        raise ValueError(f"evidence must use {EVIDENCE_SCHEMA}")
    predictions = evidence.get("predictions")
    judgments = evidence.get("judgments")
    if not isinstance(predictions, list) or not isinstance(judgments, list):
        raise ValueError("evidence predictions and judgments must be lists")
    historical = evidence.get("historical_summary")
    if historical is not None and not isinstance(historical, dict):
        raise ValueError("historical_summary must be an object")
    seen_predictions: set[str] = set()
    seen_pairs: set[tuple[str, str]] = set()
    for prediction in predictions:
        if not isinstance(prediction, dict):
            raise ValueError("prediction evidence must be an object")
        prediction_id = _string(prediction, "prediction_id", "prediction")
        pair = (_string(prediction, "post_id", "prediction"),
                _string(prediction, "model_id", "prediction"))
        _string(prediction, "prediction", "prediction")
        if prediction_id in seen_predictions or pair in seen_pairs:
            raise ValueError("duplicate prediction ID or post/model attempt")
        seen_predictions.add(prediction_id)
        seen_pairs.add(pair)
    seen_judgments: set[str] = set()
    seen_votes: set[tuple[str, str]] = set()
    for judgment in judgments:
        if not isinstance(judgment, dict):
            raise ValueError("judgment evidence must be an object")
        judgment_id = _string(judgment, "judgment_id", "judgment")
        pair = (_string(judgment, "prediction_id", "judgment"),
                _string(judgment, "judge_model", "judgment"))
        if judgment.get("verdict") not in ("correct", "incorrect"):
            raise ValueError("judgment verdict must be correct or incorrect")
        if not isinstance(judgment.get("reasoning"), str):
            raise ValueError("judgment reasoning must be a string")
        if judgment_id in seen_judgments or pair in seen_votes:
            raise ValueError("duplicate judgment ID or repeated judge vote")
        seen_judgments.add(judgment_id)
        seen_votes.add(pair)
    return predictions, judgments, historical


def _reason_for_prediction(
    row: dict, item: dict | None, panel: list[str], prompt_id: str | None,
) -> str | None:
    if item is None:
        return "post_not_in_release"
    if row["model_id"] not in panel:
        return "model_not_in_panel"
    if row.get("input_mode") != "image_only":
        return "input_mode_mismatch"
    if row.get("image_sha256") != item["image_sha256"]:
        return "image_sha256_mismatch"
    if not prompt_id or row.get("prediction_prompt_id") != prompt_id:
        return "prediction_prompt_id_mismatch_or_missing"
    return None


def _reason_for_judgment(
    row: dict, prediction: dict | None, item: dict | None,
    prompt_id: str | None, scoring_version: str | None,
    supplied_prediction_ids: set[str],
) -> str | None:
    if prediction is None:
        return ("prediction_unmatched" if row["prediction_id"] in supplied_prediction_ids
                else "unknown_prediction")
    if item is None:
        return "prediction_unmatched"
    if row.get("answer_sha256") != item["answer_sha256"]:
        return "answer_sha256_mismatch"
    if row.get("prediction_sha256") != _sha256(prediction["prediction"]):
        return "prediction_sha256_mismatch"
    if not prompt_id or row.get("judge_prompt_id") != prompt_id:
        return "judge_prompt_id_mismatch_or_missing"
    if not scoring_version or row.get("scoring_version") != scoring_version:
        return "scoring_version_mismatch_or_missing"
    return None


def _metrics(items: list[dict], panel: list[str], predictions: list[dict],
             judgments: list[dict]) -> dict:
    item_ids = {item["post_id"] for item in items}
    by_prediction: dict[str, list[dict]] = defaultdict(list)
    for judgment in judgments:
        by_prediction[judgment["prediction_id"]].append(judgment)
    result: dict[str, dict] = {}
    for model in panel:
        selected = [p for p in predictions if p["post_id"] in item_ids and p["model_id"] == model]
        correct = incorrect = judged = multi = unanimous = 0
        for prediction in selected:
            votes = by_prediction[prediction["prediction_id"]]
            if votes:
                judged += 1
            if len(votes) >= 2:
                multi += 1
                if len({vote["verdict"] for vote in votes}) == 1:
                    unanimous += 1
            counts = Counter(vote["verdict"] for vote in votes)
            if counts["correct"] >= 2 and counts["correct"] > len(votes) / 2:
                correct += 1
            elif counts["incorrect"] >= 2 and counts["incorrect"] > len(votes) / 2:
                incorrect += 1
        denominator = correct + incorrect
        result[model] = {
            "total_items": len(items),
            "predictions": len(selected),
            "missing_predictions": len(items) - len(selected),
            "judged_items": judged,
            "unresolved_items": len(selected) - denominator,
            "correct": correct,
            "incorrect": incorrect,
            "scored_denominator": denominator,
            "accuracy": correct / denominator if denominator else None,
            "multi_judge_agreement": {
                "judged_by_multiple": multi,
                "unanimous_agreements": unanimous,
                "rate": unanimous / multi if multi else None,
            },
        }
    return result


def _process(release_dir: Path, evidence: dict | None) -> tuple[dict, dict, list[dict], list[dict]]:
    manifest = load_release(Path(release_dir))
    predictions, judgments, historical = _evidence(evidence)
    evidence_sha256 = _evidence_sha256(predictions, judgments, historical)
    items = manifest["items"]
    item_by_id = {item["post_id"]: item for item in items}
    evaluation = manifest.get("evaluation") or {}
    configured_panel = evaluation.get("model_panel") or []
    panel = sorted(set(configured_panel or [p["model_id"] for p in predictions]))
    prediction_prompt = evaluation.get("prediction_prompt_id")
    judge_prompt = evaluation.get("judge_prompt_id")
    scoring_version = evaluation.get("scoring_version", "majority-v1")
    if scoring_version != "majority-v1":
        raise ValueError(f"unsupported scoring_version: {scoring_version}")

    valid_predictions: list[dict] = []
    prediction_by_id: dict[str, dict] = {}
    rejected_predictions: Counter[str] = Counter()
    for row in predictions:
        item = item_by_id.get(row["post_id"])
        reason = _reason_for_prediction(row, item, panel, prediction_prompt)
        if reason:
            rejected_predictions[reason] += 1
            continue
        public = {key: row[key] for key in (
            "prediction_id", "post_id", "model_id", "prediction", "prediction_prompt_id",
            "image_sha256", "input_mode",
        )}
        public["release_sha256"] = manifest["content_sha256"]
        valid_predictions.append(public)
        prediction_by_id[row["prediction_id"]] = public
    valid_predictions.sort(key=lambda row: (row["post_id"], row["model_id"], row["prediction_id"]))

    valid_judgments: list[dict] = []
    rejected_judgments: Counter[str] = Counter()
    supplied_prediction_ids = {p["prediction_id"] for p in predictions}
    for row in judgments:
        prediction = prediction_by_id.get(row["prediction_id"])
        item = item_by_id.get(prediction["post_id"]) if prediction else None
        reason = _reason_for_judgment(row, prediction, item, judge_prompt,
                                      scoring_version, supplied_prediction_ids)
        if reason:
            rejected_judgments[reason] += 1
            continue
        public = {key: row[key] for key in (
            "judgment_id", "prediction_id", "judge_model", "verdict", "reasoning",
            "judge_prompt_id", "answer_sha256", "prediction_sha256", "scoring_version",
        )}
        public["post_id"] = prediction["post_id"]
        public["model_id"] = prediction["model_id"]
        public["release_sha256"] = manifest["content_sha256"]
        valid_judgments.append(public)
    valid_judgments.sort(key=lambda row: (row["post_id"], row["model_id"],
                                          row["prediction_id"], row["judge_model"]))

    cohorts: dict[str, dict] = {}
    for cohort in ("legacy", "development", "combined"):
        cohort_items = items if cohort == "combined" else [i for i in items if i["cohort"] == cohort]
        cohorts[cohort] = {
            "total_items": len(cohort_items),
            "exposure": dict(sorted(Counter(i["exposure"] for i in cohort_items).items())),
            "admission_origin": dict(sorted(Counter(i["admission_origin"] for i in cohort_items).items())),
            "answer_readiness": dict(sorted(Counter(i["answer_readiness"] for i in cohort_items).items())),
            "source_support": dict(sorted(Counter(i["source_support"] for i in cohort_items).items())),
            "content_status": dict(sorted(Counter(i["content_status"] for i in cohort_items).items())),
            "suitability": dict(sorted(Counter(i["suitability"] for i in cohort_items).items())),
            "duplicate_status": dict(sorted(Counter(i["duplicate_status"] for i in cohort_items).items())),
            "rights_status": dict(sorted(Counter(i["rights_status"] for i in cohort_items).items())),
            "models": _metrics(cohort_items, panel, valid_predictions, valid_judgments),
        }
    report = {
        "schema_version": "basedbench.release-report.v1",
        "evidence_sha256": evidence_sha256,
        "release": {
            "name": manifest["name"],
            "policy_version": manifest["policy_version"],
            "schema_version": manifest["schema_version"],
            "membership_sha256": manifest["membership_sha256"],
            "content_sha256": manifest["content_sha256"],
        },
        "evaluated_versions": {
            "model_panel": panel,
            "prediction_prompt_id": prediction_prompt,
            "judge_prompt_id": judge_prompt,
            "scoring_version": scoring_version,
            "judge_models": sorted({j["judge_model"] for j in valid_judgments}),
        },
        "cohorts": cohorts,
        "evidence_coverage": {
            "predictions_received": len(predictions),
            "predictions_matched": len(valid_predictions),
            "predictions_unmatched": dict(sorted(rejected_predictions.items())),
            "judgments_received": len(judgments),
            "judgments_matched": len(valid_judgments),
            "judgments_unmatched": dict(sorted(rejected_judgments.items())),
        },
        "limitations": [
            "Scores describe only exactly bound image-only predictions and judgments for this frozen content.",
            "Unresolved or missing predictions do not enter the scored denominator.",
            "Exposed or unknown exposure is not an unseen holdout.",
            "Historical results for mutable legacy snapshots cannot establish scores for these frozen image bytes.",
            "Answer readiness alone does not establish source support, content suitability, duplicate clearance, or rights.",
        ],
    }
    if historical is not None:
        report["unverified_legacy"] = {
            "status": "unverified_historical_summary",
            "note": "Supplied historical figures are not current frozen-content scores.",
            "historical_summary": historical,
        }
    return manifest, report, valid_predictions, valid_judgments


def build_report(release_dir: Path, evidence: dict | None = None) -> dict:
    """Report reproducible scores and coverage from a verified frozen release."""
    _, report, _, _ = _process(release_dir, evidence)
    return report


def _write_json(path: Path, value: Any) -> None:
    path.write_bytes(canonical_bytes(value))


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_bytes(b"".join(canonical_bytes(row) for row in rows))


def _card(manifest: dict, report: dict, predictions: list[dict], judgments: list[dict]) -> str:
    cohorts = report["cohorts"]
    legacy = cohorts["legacy"]
    development = cohorts["development"]
    combined = cohorts["combined"]
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

# BasedBench release {manifest['content_sha256']}

BasedBench tests whether a vision-language model gets the joke in a meme: it must
identify the relevant references and reconstruct the intended implication,
contrast, inversion, irony, or wordplay. It need not explain a theory of humor.

## Composition and exposure

This frozen release has {combined['total_items']} items: {legacy['total_items']} legacy
items and {development['total_items']} development items. Admission origins are
recorded per item in `data/memes.jsonl`. Their counts are
{combined['admission_origin']}.
The legacy cohort's historical membership does not prove that the currently
frozen image bytes reconstruct the images used by earlier runs. Development
items with exposed status are development evidence rather than an unseen holdout;
unknown exposure remains unknown. The exposure counts are {combined['exposure']}.

## Evaluation

Predictors receive image bytes only. The public tables contain {len(predictions)}
exactly bound successful predictions and {len(judgments)} exactly bound individual
judge verdicts with reasoning. A score requires two agreeing votes and a strict
majority of distinct judges. Missing or unresolved items are excluded from the
scored denominator. See `report.json` for coverage, cohorts, exposure, version
bindings, and limitations. Unverified historical figures are not current scores.

## Files and privacy

`data/memes.jsonl`, `data/predictions.jsonl`, `data/judgments.jsonl`, and
`data/leaderboard.jsonl` are normalized by post and prediction ID. Images are
copied under `images/`. Raw Reddit comments, Reddit authors, reviewer notes,
private answer provenance, internal prompts, provider responses, local paths,
request metadata, and logs are intentionally omitted.

## License and rights

This is a mixed-rights dataset; its machine-readable license is `other`.
Maintainer-owned code, schema, export format, evaluation prompts where applicable,
benchmark metadata, leaderboard tables, judge verdicts and reasoning, and
maintainer-authored documentation and annotations are under the MIT License to
the extent maintainers own or control them. Meme images, Reddit post titles,
subreddit names, post IDs, cultural references, logos, characters, screenshots,
and other source artifacts may belong to third parties. BasedBench does not
claim ownership of them, and the repository's MIT License does not cover them.
These limited third-party materials are included under a fair-use rationale for
research, criticism, commentary, and benchmark evaluation. Images serve as test
stimuli, not substitutes for original posts or a general meme archive. Users must
assess whether downstream uses are permitted by law or rights holders.
"""


def export_release(release_dir: Path, output_dir: Path, evidence: dict | None = None) -> Path:
    """Atomically export allowlisted public data; refuse an existing destination."""
    release_dir = Path(release_dir)
    output_dir = Path(output_dir)
    manifest, report, predictions, judgments = _process(release_dir, evidence)
    if output_dir.exists() or output_dir.is_symlink():
        raise FileExistsError(output_dir)
    cursor = output_dir.parent
    while cursor != cursor.parent:
        if cursor.is_symlink():
            raise ValueError(f"symlink output parent forbidden: {cursor}")
        cursor = cursor.parent
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    try:
        (staging / "data").mkdir()
        (staging / "images").mkdir()
        memes = [{key: item[key] for key in (
            "post_id", "title", "subreddit", "ground_truth", "image_filename",
            "image_sha256", "answer_sha256", "cohort", "exposure", "admission_origin",
            "policy_version", "answer_readiness", "source_support", "content_status",
            "suitability", "duplicate_status", "rights_status",
        )} for item in manifest["items"]]
        for meme in memes:
            meme["release_sha256"] = manifest["content_sha256"]
        _write_jsonl(staging / "data" / "memes.jsonl", memes)
        _write_jsonl(staging / "data" / "predictions.jsonl", predictions)
        _write_jsonl(staging / "data" / "judgments.jsonl", judgments)
        leaderboard = [
            {"cohort": cohort, "model_id": model, "release_sha256": manifest["content_sha256"],
             **metrics}
            for cohort, entry in report["cohorts"].items()
            for model, metrics in entry["models"].items()
        ]
        _write_jsonl(staging / "data" / "leaderboard.jsonl", leaderboard)
        # Never copy arbitrary historical_summary or private provenance into public JSON.
        public_report = {key: value for key, value in report.items() if key != "unverified_legacy"}
        _write_json(staging / "report.json", public_report)
        _write_json(staging / "dataset_info.json", {
            "description": "BasedBench immutable meme understanding release",
            "license": "other",
            "schema_version": manifest["schema_version"],
            "release_sha256": manifest["content_sha256"],
            "membership_sha256": manifest["membership_sha256"],
            "configs": {"memes": {"num_rows": len(memes)},
                        "predictions": {"num_rows": len(predictions)},
                        "judgments": {"num_rows": len(judgments)},
                        "leaderboard": {"num_rows": len(leaderboard)}},
        })
        (staging / "README.md").write_text(_card(manifest, public_report, predictions, judgments),
                                           encoding="utf-8")
        for item in manifest["items"]:
            payload = (release_dir / "images" / item["image_filename"]).read_bytes()
            if hashlib.sha256(payload).hexdigest() != item["image_sha256"]:
                raise ValueError(f"image changed during export: {item['post_id']}")
            (staging / "images" / item["image_filename"]).write_bytes(payload)
        if output_dir.exists() or output_dir.is_symlink():
            raise FileExistsError(output_dir)
        os.rename(staging, output_dir)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return output_dir
