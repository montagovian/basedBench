import base64
import hashlib
import json
from pathlib import Path
import shutil
from unittest.mock import patch

import pytest

from basedbench.pipeline import source_evidence_baselines as baselines


def _hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n")


def _request(answer, comments, image, model):
    payload = json.dumps({"candidate_answer": answer, "comment_evidence": comments})
    return {
        "model": model,
        "instructions": "A frozen prompt",
        "text": {"format": {"schema": {"type": "object"}}},
        "input": [{"role": "user", "content": [
            {"type": "input_text", "text": payload},
            {"type": "input_image", "image_url": "data:image/png;base64," + base64.b64encode(image).decode()},
        ]}],
    }


def _fixture(tmp_path):
    image = b"frozen image bytes"
    image_hash = hashlib.sha256(image).hexdigest()
    explanation = "The candidate explanation"
    comments = "Exact source comment packet"
    cases = [
        {"case_id": "exact", "post_id": "post-1", "input": {
            "explanation": explanation, "comment_evidence": comments, "image_sha256": image_hash}},
        {"case_id": "changed-answer", "post_id": "post-1", "input": {
            "explanation": explanation + " changed", "comment_evidence": comments, "image_sha256": image_hash}},
        {"case_id": "changed-comments", "post_id": "post-1", "input": {
            "explanation": explanation, "comment_evidence": comments + " changed", "image_sha256": image_hash}},
        {"case_id": "changed-image", "post_id": "post-1", "input": {
            "explanation": explanation, "comment_evidence": comments,
            "image_sha256": hashlib.sha256(b"different image").hexdigest()}},
    ]
    dataset = tmp_path / "dataset"
    _write_json(dataset / "cases.json", cases)
    cache_root = tmp_path / "data" / "backfill"
    experiment = cache_root / "calibrated-luna-dev-v1"
    legacy_case = {"case_id": "post-1", "post_id": "post-1", "input": cases[0]["input"]}
    _write_json(experiment / "cases.json", [legacy_case])

    jobs = []
    results_manifest = {}
    plan_files = {"cases.json": _hash(experiment / "cases.json")}
    for arm, repeat, model in [
        ("simple_6", 0, "gpt-6-luna"),
        ("simple_6", 1, "gpt-6-luna"),
        ("simple_56", 0, "gpt-5.6-luna"),
    ]:
        key = f"post-1.{arm}_r{repeat}"
        request = _request(explanation, comments, image, model)
        request_path = experiment / "requests" / f"{key}.json"
        _write_json(request_path, request)
        request_sha = baselines._digest(request)
        jobs.append({"key": key, "case_id": "post-1", "arm": arm, "repeat": repeat,
                     "model": model, "request_sha256": request_sha})
        plan_files[str(request_path.relative_to(experiment))] = _hash(request_path)
        call = {"status": "completed", "input_sha256": "legacy-input-hash", "output_text": "{}",
                "response": {"model": model, "id": f"resp-{key}"}, "usage": {"input_tokens": 10}}
        call_path = experiment / "calls" / f"{key}.json"
        _write_json(call_path, call)
        results_manifest[str(call_path.relative_to(experiment))] = _hash(call_path)
        results_manifest[str(request_path.relative_to(experiment))] = _hash(request_path)
    plan = {"experiment_id": "", "files": plan_files, "jobs": jobs}
    plan["experiment_id"] = baselines._digest({key: value for key, value in plan.items()
                                                if key != "experiment_id"})
    _write_json(experiment / "plan.json", plan)
    _write_json(experiment / "results-manifest.json", results_manifest)
    return tmp_path / "data", dataset, experiment


def _fake_parse(experiment, case, legacy_case, arm, call, mapping=None):
    answer_quality = "fail" if arm == "simple_56" else "pass"
    return {"parsed": {"answer_quality": answer_quality, "evidence_status": "supported",
                        "verdict": answer_quality},
            "answer_quality": answer_quality, "evidence_status": "supported",
            "joint_verdict": answer_quality, "verdict_kind": "joint_answer_and_evidence_gate"}


def test_prepare_keeps_repeats_and_never_pairs_different_models(tmp_path):
    data_root, dataset, _ = _fixture(tmp_path)
    output = tmp_path / "out"
    with patch.object(baselines, "_parse_result", side_effect=_fake_parse):
        report = baselines.prepare(data_root, dataset, output)

    rows = json.loads((output / "matches.json").read_text())
    assert report["matched_trial_count"] == 3
    assert {row["repeat"] for row in rows if row["model"]["actual_returned"] == "gpt-6-luna"} == {0, 1}
    assert {row["model"]["actual_returned"] for row in rows} == {"gpt-6-luna", "gpt-5.6-luna"}
    assert all(row["answer_quality"] == row["parsed"]["answer_quality"] for row in rows)
    assert all(row["evidence_status"] == "supported" for row in rows)
    assert all(row["joint_verdict"] == row["parsed"]["verdict"] for row in rows)
    assert report["unmatched_case_count"] == 3
    unmatched = {row["case_id"]: row["reasons"] for row in report["unmatched"]}
    assert any("explanation_differs" in item for item in unmatched["changed-answer"])
    assert any("comment_packet_differs" in item for item in unmatched["changed-comments"])
    assert any("image_bytes_differ" in item for item in unmatched["changed-image"])
    with pytest.raises(FileExistsError):
        baselines.prepare(data_root, dataset, output)


def test_fresh_calibrated_cache_is_included_without_verdict_filtering(tmp_path):
    data_root, dataset, development = _fixture(tmp_path)
    fresh = development.parent / "calibrated-luna-fresh-v1"
    shutil.copytree(development, fresh)
    previous = tmp_path / "baselines"
    for name in ("matches.json", "report.json", "manifest.json"):
        (previous / name).parent.mkdir(parents=True, exist_ok=True)
        (previous / name).write_text(name)

    output = tmp_path / "baselines-complete"
    with patch.object(baselines, "_parse_result", side_effect=_fake_parse):
        report = baselines.prepare(data_root, dataset, output)

    rows = json.loads((output / "matches.json").read_text())
    fresh_rows = [row for row in rows if row["experiment"] == "calibrated-luna-fresh-v1"]
    assert report["experiments"]["calibrated-luna-fresh-v1"]["verified"] is True
    assert len(fresh_rows) == 3
    assert {row["condition"] for row in fresh_rows} == {"simple_6", "simple_56"}
    assert {row["repeat"] for row in fresh_rows if row["condition"] == "simple_6"} == {0, 1}
    assert {row["answer_quality"] for row in fresh_rows} == {"pass", "fail"}
    correction = report["completeness_correction"]
    assert correction["included_cache"] == "calibrated-luna-fresh-v1"
    assert "regardless of its verdict" in correction["rationale"]
    assert set(correction["superseded_snapshot"]["sha256"]) == {"matches.json", "report.json", "manifest.json"}


def test_fresh_cache_uses_the_original_calibrated_parser():
    from basedbench.pipeline import calibrated_eval

    legacy_case = {"case_id": "post-1"}
    call = {"response": {"model": "gpt-6-luna"}, "status": "completed", "output_text": "{}"}
    with patch.object(calibrated_eval, "parse", return_value={"answer_quality": "fail",
                                                                 "evidence_status": "supported",
                                                                 "verdict": "fail"}) as parser:
        parsed = baselines._parse_result("calibrated-luna-fresh-v1", {}, legacy_case,
                                         "simple_6", call)
    parser.assert_called_once_with(legacy_case, "simple_6", call)
    assert parsed["answer_quality"] == "fail"
    assert parsed["evidence_status"] == "supported"
    assert parsed["joint_verdict"] == "fail"


@pytest.mark.parametrize("damage", ["tamper", "missing"])
def test_invalid_frozen_cache_is_not_reused(tmp_path, damage):
    data_root, dataset, experiment = _fixture(tmp_path)
    call = next((experiment / "calls").glob("*.json"))
    if damage == "tamper":
        call.write_text(call.read_text() + " ")
    else:
        call.unlink()
    output = tmp_path / "out"
    with patch.object(baselines, "_parse_result", side_effect=_fake_parse):
        report = baselines.prepare(data_root, dataset, output)
    assert report["matched_trial_count"] == 0
    status = report["experiments"]["calibrated-luna-dev-v1"]
    assert status["verified"] is False
    assert any("hash_mismatch" in item or "missing_source_file" in item for item in status["errors"])
