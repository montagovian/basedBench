"""Frozen Jev optimization split, leakage and scoring checks."""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path

import pytest

from basedbench.pipeline import jev_optimization_protocol as protocol


def _row(cid: str, group: str, gold: str) -> dict:
    return {"case_id": cid, "group_id": group, "gold": gold,
            "input": {"explanation": "A meme answer"},
            "comments": [{"id": "comment-1", "text": "the joke"}],
            "observation": {"visible_text": "text"},
            "baseline": {"broad": "pass", "combined": "fail", "calibrated": "pass"}}


def test_weights_balance_classes_and_families() -> None:
    rows = [_row("r1", "fam-r", "ready"), _row("r2", "fam-r", "ready"),
            _row("r3", "fam-r2", "ready"), _row("x1", "fam-x", "repair")]
    lookup = {row["case_id"]: row for row in rows}
    examples = protocol._examples(list(lookup), "train", lookup)
    weights = {e["case_id"]: e["weight"] for e in examples}
    assert sum(weights.values()) == pytest.approx(4)
    assert weights["r1"] == weights["r2"]
    assert weights["r3"] == pytest.approx(2 * weights["r1"])
    assert weights["x1"] == pytest.approx(weights["r1"] + weights["r2"] + weights["r3"])
    assert set(examples[0]) == {"case_id", "partition", "weight"}


def test_score_and_feedback_are_partition_safe() -> None:
    row = _row("r1", "family", "repair")
    row["human"] = {"notes": "secret diagnostic", "provenance": "private"}
    row["comments"][0]["human_note"] = "private comment metadata"
    row["observation"]["reviewer_name"] = "private observation metadata"
    example = {"case_id": "r1", "partition": "train", "weight": 2.5}
    result = {"prediction": "fail", "trace": {"units": [{"unit": {"id": "u0", "comment_id": "comment-1",
                                                                   "start": 0, "end": 8, "text": "the joke",
                                                                   "full_context": "duplicate"},
                                                         "role": {"choice": "core_decoding", "probabilities": {"core_decoding": 1.0}, "confidence": 1.0},
                                                         "need": {"choice": "essential", "probabilities": {"essential": 1.0}, "confidence": 1.0},
                                                         "coverage": {"choice": "missing", "probabilities": {"missing": 1.0}, "confidence": 1.0},
                                                         "essential": True}],
                                             "reason_codes": ["essential_missing"],
                                             "human_notes": "must not travel"}}
    assert protocol.score(example, row, result) == 2.5
    assert protocol.score(example, row, "uncertain") == 0
    fb = protocol.feedback(example, row, result)
    assert fb["expected"] == "fail"
    unit = dict(zip(fb["trace"]["columns"], fb["trace"]["rows"][0], strict=True))
    assert {k: unit[k] for k in ("unit_id", "comment_id", "start", "end")} == {
        "unit_id": "u0", "comment_id": "comment-1", "start": 0, "end": 8}
    assert unit["coverage"] == "missing" and unit["essential"]
    assert unit["p_essential"] == 1 and unit["p_missing"] == 1
    source_comment = next(c["text"] for c in fb["input"]["comments"] if c["id"] == unit["comment_id"])
    assert source_comment[unit["start"]:unit["end"]] == "the joke"
    assert "text" not in fb["trace"]["columns"]
    assert "case_id" not in fb and "group_id" not in fb
    assert all(s not in json.dumps(fb) for s in ("secret diagnostic", "private comment metadata",
                                                "private observation metadata", "duplicate", "must not travel"))
    for partition in ("val", "test"):
        assert protocol.feedback({**example, "partition": partition}, row, result) == {}
    with pytest.raises(ValueError, match="Invalid prediction"):
        protocol.score(example, row, "garbage")


def test_group_leakage_rejected() -> None:
    lookup = {row["case_id"]: row for row in
              [_row("r1", "same", "ready"), _row("r2", "same", "repair"),
               _row("r3", "other", "ready")]}
    with pytest.raises(ValueError, match="Family leakage"):
        protocol._assert_group_split((["r1"], ["r2"], ["r3"]), lookup)


def test_summary_preserves_controls_and_paired_families() -> None:
    rows = [_row(f"r{i}", f"family-{i}", "ready") for i in range(77)]
    rows += [_row(f"x{i}", f"family-{i}" if i < 6 else f"repair-{i}", "repair") for i in range(17)]
    records = [{"case_id": row["case_id"], "fold": 0, "method": method,
                "prediction": "pass" if row["gold"] == "ready" else "fail",
                "policy_id": "p", "result": {}}
               for row in rows for method in ("seed", "optimized")]
    summary = protocol.summarize(rows, records)
    assert summary["metrics"]["optimized"]["repair_catches"] == 17
    assert summary["metrics"]["broad"]["repair_catches"] == 0
    assert summary["paired_families"]["optimized"] == {"families": 6, "both_correct": 6}
    assert summary["development_screen"]["met"]
    assert len(summary["changed_decisions"]) == 17
    with pytest.raises(ValueError, match="Duplicate"):
        protocol.summarize(rows, records + [records[0]])


def test_screen_uses_net_repair_gain() -> None:
    rows = [_row(f"r{i}", f"ready-{i}", "ready") for i in range(77)]
    rows += [_row(f"x{i}", f"repair-{i}", "repair") for i in range(17)]
    for i in range(2):
        rows[77 + i]["baseline"]["broad"] = "fail"
    records = [{"case_id": row["case_id"], "fold": 0, "method": "optimized",
                "prediction": "pass" if row["gold"] == "ready" else
                              "fail" if row["case_id"] in {"x2", "x3", "x4"} else "pass"}
               for row in rows]
    screen = protocol.summarize(rows, records)["development_screen"]
    assert screen["new_repair_catches"] == 3
    assert screen["lost_repair_catches"] == 2
    assert screen["net_repair_catches"] == 1
    assert not screen["met"]


def test_frozen_real_source_manifest_and_folds(tmp_path: Path) -> None:
    source = Path(__file__).resolve().parents[1] / "data/backfill/jev-decomposition-v1"
    if not source.is_dir():
        pytest.skip("Private frozen source absent from this checkout")
    root = tmp_path / "frozen"
    plan = protocol.prepare(source, root)
    loaded, cases = protocol.load(root)
    assert loaded == plan
    assert len(cases) == 94 and len(plan["excluded"]) == 5
    assert Counter(r["reason"] for r in plan["excluded"]) == {"unknown_label": 3, "image_incomplete": 2}
    assert Counter(cid for f in plan["folds"] for cid in f["test_ids"]) == Counter({c: 1 for c in cases})
    for fold in range(5):
        train, val, test = protocol.example_sets(plan, cases, fold)
        for examples in (train, val, test):
            assert sum(e["weight"] for e in examples) == pytest.approx(len(examples))
            assert {cases[e["case_id"]]["gold"] for e in examples} == {"ready", "repair"}
    with pytest.raises(FileExistsError):
        protocol.prepare(source, root)
    (root / "cases.json").write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="cases file changed"):
        protocol.load(root)
