"""Checks for leakage, denominators, provenance and static-review safety."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from basedbench.pipeline.jev_decomposition_analysis import prepare
from basedbench.pipeline import jev_decomposition_questions as questions
from basedbench.pipeline.curation_corpus import digest


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _save(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def _run_fixture(tmp_path: Path, *, incomplete: bool = False, cap_stop: bool = False,
                 single_class: bool = False) -> Path:
    root = tmp_path / "run"
    dataset = root / "dataset"
    dataset.mkdir(parents=True)
    (dataset / "assets").mkdir()
    (dataset / "assets" / "image.png").write_bytes(b"frozen image")
    cases, records = [], []
    for i in range(12):
        gold = "ready" if single_class or i % 2 == 0 else "repair"
        if i == 11:
            gold = "unclear"
        case_id = f"case-{i}"
        human = {"quality": gold, "events": [{"quality": gold, "notes": "<script>alert('x')</script>" if i == 0 else "Original human note"}]}
        if i == 0:
            human["events"].append({"quality": gold, "notes": "Second exact note\nwith line break"})
        case = {"case_id": case_id, "post_id": f"post-{i // 2}", "group_id": f"family-{i // 2}",
                "human": human, "input": {"explanation": "<img src=x onerror=alert(1)>" if i == 0 else f"Answer {i}",
                                           "comment_evidence": "evidence", "image_sha256": "image"},
                "comments": [{"id": "c0", "text": "<svg onload=alert(1)>" if i == 0 else "Comment"}],
                "image_path": str((dataset / "assets" / "image.png").resolve()), "image_error": None}
        feature = {key: float(i if j == 0 else i % 2) for j, key in enumerate(questions.FEATURE_IDS)}
        arms = {
            "broad_text": {"state": "completed", "answer_quality": "pass", "score": 0.7},
            "broad_observation": {"state": "completed", "answer_quality": "fail" if i % 2 else "pass", "score": 0.2 if i % 2 else 0.8},
            "atomic": {"state": "completed", "answer_quality": "pass" if i % 2 == 0 else "fail", "score": 0.8 if i % 2 == 0 else 0.2, "features": feature},
            "matrix": {"state": "completed", "answer_quality": None, "score": None,
                       "features": {key: float(i % 3) for key in questions.MATRIX_SUMMARY_IDS}},
            "focused": {"state": "completed", "answer_quality": "pass" if i % 2 == 0 else "fail", "score": 0.8 if i % 2 == 0 else 0.2, "features": feature},
        }
        if incomplete and i == 3:
            arms["focused"] = {"state": "technical_error", "answer_quality": None, "error": "timeout"}
        cases.append(case)
        records.append({"case_id": case_id, "post_id": case["post_id"], "group_id": case["group_id"], "human": human,
                        "arms": arms, "observation": {"visible_text": "<script>bad</script>",
                                                   "visible_scene": "<b>scene</b>", "uncertainties": ["uncertain text"]},
                        "selected_comment_ids": ["c0"]})
    _save(dataset / "cases.json", cases)
    _save(dataset / "manifest.json", {"files": {"cases.json": _sha(dataset / "cases.json"), "assets/image.png": _sha(dataset / "assets" / "image.png")}})
    _save(root / "records.json", records)
    plan = {"dataset_manifest_sha256": _sha(dataset / "manifest.json")}
    plan["experiment_id"] = digest(plan)
    _save(root / "plan.json", plan)
    _save(root / "runtime_report.json", {"experiment_id": plan["experiment_id"], "complete": not cap_stop,
                                          "stop_reason": "budget_cap" if cap_stop else None,
                                          "cost_usd": 0.1, "question_counts": {"atomic": 48}})
    _save(root / "records-manifest.json", {"files": {name: _sha(root / name) for name in
                                                   ("records.json", "plan.json", "runtime_report.json", "dataset/manifest.json")}})
    return root


def test_grouped_oof_and_training_only_scaler(tmp_path: Path) -> None:
    root = _run_fixture(tmp_path)
    out = tmp_path / "analysis"
    summary = prepare(root, out)
    rows = json.loads((out / "cases.json").read_text())
    folds = json.loads((out / "folds.json").read_text())
    assert len(folds) == 10
    for fold in folds:
        assert not set(fold["train_group_ids"]) & set(fold["test_group_ids"])
        assert not set(fold["train_case_ids"]) & set(fold["test_case_ids"])
        train = [r for r in rows if r["case_id"] in fold["train_case_ids"]]
        feature_id = questions.FEATURE_IDS[0]
        index = fold["feature_ids"].index(f"atomic.{feature_id}")
        assert fold["scaler_mean"][index] == pytest.approx(sum(r["arms"]["atomic"]["features"][feature_id] for r in train) / len(train))
    assert all(r["methods"]["learned_atomic"]["state"] == "completed" for r in rows if r["gold"] != "unclear")
    assert rows[-1]["methods"]["learned_atomic"]["state"] == "excluded_unclear"
    assert summary["methods"]["learned_atomic"]["known"] == 11
    assert summary["methods"]["learned_atomic"]["unclear"] == 1
    assert summary["methods"]["atomic"]["auroc_n"] == 0
    assert summary["methods"]["learned_atomic"]["route_08"]["n"] == 11
    assert summary["methods"]["learned_atomic"]["risk_coverage"]["0.8"]["by_class"]["ready"]["eligible"] == 6


def test_technical_denominators_and_escaped_review(tmp_path: Path) -> None:
    root = _run_fixture(tmp_path, incomplete=True)
    out = tmp_path / "analysis"
    summary = prepare(root, out)
    combined = summary["methods"]["learned_combined"]
    assert combined["known"] == 11
    assert combined["excluded_known"] == 1
    assert combined["state_counts"]["excluded_incomplete"] == 1
    assert summary["methods"]["focused"]["state_counts"]["technical_error"] == 1
    page = (out / "index.html").read_text()
    assert "&lt;script&gt;alert" in page
    assert "&lt;img src=x onerror=alert(1)&gt;" in page
    assert "&lt;svg onload=alert(1)&gt;" in page
    assert "Second exact note\nwith line break" in page
    assert "Full human judgment and provenance (2 events)" in page
    assert "Machine image observation" in page and "fallible; not human ground truth" in page
    assert "&lt;b&gt;scene&lt;/b&gt;" in page and "uncertain text" in page
    assert "<script>alert" not in page
    assert "<svg onload" not in page
    assert (out / "assets" / "image.png").read_bytes() == b"frozen image"


def test_tamper_refusal_and_no_overwrite(tmp_path: Path) -> None:
    root = _run_fixture(tmp_path)
    out = tmp_path / "analysis"
    prepare(root, out)
    with pytest.raises(FileExistsError):
        prepare(root, out)
    (root / "records.json").write_text("[]")
    with pytest.raises(ValueError, match="Hash mismatch"):
        prepare(root, tmp_path / "tampered")
    assert not (tmp_path / "tampered").exists()


def test_identity_drift_rejected(tmp_path: Path) -> None:
    root = _run_fixture(tmp_path)
    records = json.loads((root / "records.json").read_text())
    records[0]["human"] = {"quality": "repair"}
    _save(root / "records.json", records)
    manifest = json.loads((root / "records-manifest.json").read_text())
    manifest["files"]["records.json"] = _sha(root / "records.json")
    _save(root / "records-manifest.json", manifest)
    with pytest.raises(ValueError, match="drift"):
        prepare(root, tmp_path / "analysis")


def test_cap_stopped_single_class_retains_base_arm_report(tmp_path: Path) -> None:
    root = _run_fixture(tmp_path, cap_stop=True, single_class=True)
    out = tmp_path / "analysis"
    summary = prepare(root, out)
    assert summary["partial_due_to_cap"] is True
    assert summary["methods"]["broad_text"]["completed_known"] == 11
    assert summary["methods"]["learned_atomic"]["state_counts"]["excluded_insufficient_classes"] == 11
    assert summary["methods"]["learned_combined"]["state_counts"]["excluded_insufficient_classes"] == 11
    assert json.loads((out / "folds.json").read_text()) == []
