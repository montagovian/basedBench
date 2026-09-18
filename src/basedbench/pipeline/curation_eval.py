"""Local admission baselines using only frozen, pre-review model inputs."""

from __future__ import annotations

import math
import platform
import shutil
import tempfile
import time
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from basedbench.pipeline.curation_corpus import digest, file_hash, load_corpus, write_json, write_jsonl

RESULT_VERSION = "curation-decision-v1"
FEATURE_VERSION = "historical-explanation-comments-v1"


@dataclass(frozen=True)
class Decision:
    """Common result shape for future encoder/API adapters.

    Score is model-specific, not a claim of calibrated acceptance probability.
    A failed call is defer + error, never a negative training label.
    """

    post_id: str
    input_sha256: str
    model: str
    score: float | None
    decision: str
    diagnostics: tuple[str, ...] = ()
    error: str | None = None
    latency_ms: float | None = None
    cost_usd: float | None = None
    schema_version: str = RESULT_VERSION


def decide(score: float | None, accept_threshold: float, reject_threshold: float, *, error: str | None = None) -> str:
    if not 0 <= reject_threshold < accept_threshold <= 1:
        raise ValueError("Require 0 <= reject threshold < accept threshold <= 1")
    if error or score is None:
        return "defer"
    if not math.isfinite(score) or not 0 <= score <= 1:
        raise ValueError("Score must be finite and in [0, 1]")
    return "accept" if score >= accept_threshold else "reject" if score <= reject_threshold else "defer"


def feature_text(model_input: dict) -> str:
    """Explicit allowlist: never stringify a record containing its review label."""
    return f"Explanation:\n{model_input['explanation']}\n\nComments:\n{model_input['comment_evidence']}"


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _wilson(successes: int, total: int) -> list[float] | None:
    if not total:
        return None
    z, p = 1.959963984540054, successes / total
    center = (p + z * z / (2 * total)) / (1 + z * z / total)
    radius = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / (1 + z * z / total)
    return [max(0.0, center - radius), min(1.0, center + radius)]


def metrics(rows: list[dict], decisions: list[Decision]) -> dict:
    by_id = {d.post_id: d for d in decisions}
    if len(by_id) != len(decisions) or set(by_id) != {r["post_id"] for r in rows}:
        raise ValueError("Expected exactly one result per evaluation example")
    counts: Counter = Counter()
    accepted_groups = set()
    for row in rows:
        result = by_id[row["post_id"]]
        if result.input_sha256 != row["input_sha256"]:
            raise ValueError("Result refers to different input")
        if result.decision not in {"accept", "reject", "defer"} or (result.error and result.decision != "defer"):
            raise ValueError("Invalid decision/error combination")
        counts[result.decision] += 1
        counts[f"{row['label']}_as_{result.decision}"] += 1
        counts["errors"] += bool(result.error)
        if result.decision == "accept":
            accepted_groups.add(row["group_id"])
    positives = sum(r["label"] == "accept" for r in rows)
    negatives = len(rows) - positives
    scored = [(by_id[r["post_id"]].score, int(r["label"] == "accept")) for r in rows
              if by_id[r["post_id"]].score is not None and not by_id[r["post_id"]].error]
    return {
        "n": len(rows), "historical_positives": positives, "historical_negatives": negatives,
        "accepted": counts["accept"], "rejected": counts["reject"], "deferred": counts["defer"], "errors": counts["errors"],
        "true_accepts": counts["accept_as_accept"], "false_accepts": counts["reject_as_accept"],
        "false_rejects": counts["accept_as_reject"], "accepted_groups": len(accepted_groups),
        "accept_precision": _ratio(counts["accept_as_accept"], counts["accept"]),
        "accept_precision_wilson95_independent_items": _wilson(counts["accept_as_accept"], counts["accept"]),
        "positive_retention": _ratio(counts["accept_as_accept"], positives),
        "negative_accept_rate": _ratio(counts["reject_as_accept"], negatives),
        "false_reject_rate": _ratio(counts["accept_as_reject"], positives),
        "defer_rate": _ratio(counts["defer"], len(rows)),
        "brier_score": sum((s - y) ** 2 for s, y in scored) / len(scored) if scored else None,
    }


def run_baseline(corpus: Path, output: Path, *, accept_threshold: float = 0.9, reject_threshold: float = 0.1) -> dict:
    """Fit once on development; score calibration only. Never score final test."""
    decide(None, accept_threshold, reject_threshold)
    if output.exists():
        raise FileExistsError(f"Refusing to replace baseline run: {output}")
    try:
        import joblib
        import numpy
        import scipy
        import sklearn
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import Pipeline
    except ImportError as exc:
        raise RuntimeError("Install the optional baseline dependencies with: uv sync --extra curation") from exc
    manifest, rows = load_corpus(corpus)
    train = [r for r in rows if r["split"] == "development"]
    evaluation = [r for r in rows if r["split"] == "calibration"]
    if {r["label"] for r in train} != {"accept", "reject"} or not evaluation:
        raise ValueError("Need both development labels and a nonempty calibration split")
    parameters = {"ngram_range": [1, 2], "min_df": 2, "max_features": 100000,
                  "sublinear_tf": True, "C": 1.0, "class_weight": "balanced", "max_iter": 1000, "random_state": 0}
    model = Pipeline([
        ("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=2, max_features=100000, sublinear_tf=True)),
        ("logistic", LogisticRegression(C=1.0, class_weight="balanced", max_iter=1000, random_state=0)),
    ])
    started = time.perf_counter()
    model.fit([feature_text(r["input"]) for r in train], [int(r["label"] == "accept") for r in train])
    train_ms = (time.perf_counter() - started) * 1000
    started = time.perf_counter()
    scores = model.predict_proba([feature_text(r["input"]) for r in evaluation])[:, list(model.classes_).index(1)]
    predict_ms = (time.perf_counter() - started) * 1000

    def results(name: str, values: list[float], accept: float, reject: float) -> list[Decision]:
        return [Decision(post_id=r["post_id"], input_sha256=r["input_sha256"], model=name,
                         score=float(score), decision=decide(float(score), accept, reject), cost_usd=0.0)
                for r, score in zip(evaluation, values, strict=True)]

    predictions = results("tfidf-logistic-v1", scores.tolist(), accept_threshold, reject_threshold)
    accept_all = results("accept-all-v1", [1.0] * len(evaluation), accept_threshold, reject_threshold)
    reject_all = results("reject-all-v1", [0.0] * len(evaluation), accept_threshold, reject_threshold)
    report = {
        "schema_version": "curation-baseline-v1", "corpus_id": manifest["corpus_id"],
        "created_at": datetime.now(timezone.utc).isoformat(), "feature_version": FEATURE_VERSION,
        "model": "tfidf-logistic-v1", "parameters": parameters,
        "versions": {"sklearn": sklearn.__version__, "numpy": numpy.__version__, "scipy": scipy.__version__,
                     "joblib": joblib.__version__, "python": platform.python_version(),
                     "evaluator_source_sha256": file_hash(Path(__file__))},
        "training_examples": len(train), "evaluation_split": "calibration", "final_test_evaluated": False,
        "training_ids_sha256": digest([r["post_id"] for r in train]),
        "evaluation_ids_sha256": digest([r["post_id"] for r in evaluation]),
        "thresholds": {"accept": accept_threshold, "reject": reject_threshold},
        "metrics": metrics(evaluation, predictions),
        "controls": {"accept_all": metrics(evaluation, accept_all), "reject_all": metrics(evaluation, reject_all)},
        "threshold_sweep": [
            {"accept_threshold": threshold, "reject_threshold": reject_threshold,
             **metrics(evaluation, results("tfidf-logistic-v1", scores.tolist(), threshold, reject_threshold))}
            for threshold in (0.5, 0.7, 0.8, 0.9, 0.95, 0.99) if threshold > reject_threshold
        ],
        "timing_ms": {"training": train_ms, "calibration_prediction": predict_ms},
        "api_cost_usd": 0.0,
        "limitations": manifest["limitations"] + [
            "TF-IDF sees original explanations/comments, not image pixels; scores are uncalibrated.",
            "Threshold sweep is exploratory calibration, not an independent performance estimate.",
            "Wilson intervals assume independent items; they do not account for remaining family dependence or threshold selection.",
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}-", dir=output.parent))
    try:
        joblib.dump(model, staging / "model.joblib")
        report["model_sha256"] = file_hash(staging / "model.joblib")
        write_jsonl(staging / "decisions.jsonl", [asdict(r) for r in predictions + accept_all + reject_all])
        report["decisions_sha256"] = file_hash(staging / "decisions.jsonl")
        write_json(staging / "report.json", report)
        lines = ["# Historical curation baseline", "",
                 f"Corpus: `{manifest['corpus_id']}`", "",
                 f"Trained on {len(train)} development examples; evaluated on {len(evaluation)} calibration examples. Final test was not scored.", "",
                 "| Accept threshold | Accepted | Precision | Positive retention | Deferred |", "|---|---:|---:|---:|---:|"]
        for result in report["threshold_sweep"]:
            precision = result["accept_precision"]
            retention = result["positive_retention"]
            lines.append(f"| {result['accept_threshold']:.2f} | {result['accepted']} | "
                         f"{f'{precision:.1%}' if precision is not None else 'N/A'} | "
                         f"{f'{retention:.1%}' if retention is not None else 'N/A'} | {result['deferred']} |")
        lines.extend(["", "Limitations:", "", *[f"- {s}" for s in report["limitations"]], ""])
        (staging / "report.md").write_text("\n".join(lines))
        staging.rename(output)
        return report
    finally:
        if staging.exists():
            shutil.rmtree(staging)
