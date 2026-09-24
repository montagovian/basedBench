"""Fixtures exercise the same packet/event identity joins as private snapshots."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from basedbench.pipeline.curation_corpus import digest, file_hash, write_json
from basedbench.pipeline import source_evidence_dataset as dataset


def _snapshot(root: Path, name: str, cases: list[dict], events: list[dict],
              image: bytes | None = b"invalid-image") -> Path:
    folder = root / "curation" / name
    folder.mkdir(parents=True)
    write_json(folder / "cases.json", cases)
    (folder / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))
    files = {"cases.json": file_hash(folder / "cases.json")}
    if image is not None:
        import hashlib
        sha = hashlib.sha256(image).hexdigest()
        image_folder = folder / "images"
        image_folder.mkdir()
        (image_folder / sha).write_bytes(image)
        files[f"images/{sha}"] = sha
    manifest = {"files": files, "packet_id": "packet", "corpus_id": "corpus",
                "rubric_sha256": "rubric"}
    write_json(folder / "manifest.json", manifest)
    return folder


def _case(post: str, explanation: str, *, answers: list[dict] | None = None,
          image: bytes = b"invalid-image") -> dict:
    import hashlib
    inp = {"explanation": explanation, "comment_evidence": "ID: c1 | Source text",
           "image_sha256": hashlib.sha256(image).hexdigest()}
    if answers is not None:
        inp["answers"] = answers
    return {"post_id": post, "group_id": post, "input": inp, "input_sha256": digest(inp)}


def _event(case: dict, event_id: str, fields: dict, *, base: str | None = None,
           notes: str = "") -> dict:
    return {"post_id": case["post_id"], "input_sha256": case["input_sha256"],
            "event_id": event_id, "base_revision": base, "kind": "feedback",
            "packet_id": "packet", "corpus_id": "corpus", "rubric_sha256": "rubric",
            "fields": fields, "notes": notes, "recorded_at": event_id}


def test_exact_versions_revisions_conflicts_and_missing_labels(tmp_path, monkeypatch):
    answers = [{"source": "original", "text": "Original answer"},
               {"source": "human-repair", "text": "Corrected answer"}]
    fresh = _case("post1", "Original answer", answers=answers)
    _snapshot(tmp_path, "fresh-human-audit-v2", [fresh],
              [_event(fresh, "f1", {"quality_a": "repair", "quality_b": "ready"},
                      notes="Specific reference missing")])
    review = _case("post1", "Original answer")
    _snapshot(tmp_path, "review-v1", [review],
              [_event(review, "r1", {"ground_truth": "repair", "admission": "accept"}),
               _event(review, "r2", {"ground_truth": "ready", "admission": "accept"},
                      base="r1", notes="Revised after looking again")])
    monkeypatch.setattr(dataset, "SNAPSHOTS", ("fresh-human-audit-v2", "review-v1"))
    output = tmp_path / "out"
    report = dataset.prepare(tmp_path, output)
    cases = json.loads((output / "cases.json").read_text())
    assert report["cases"] == 2
    assert {c["input"]["explanation"] for c in cases} == {"Original answer", "Corrected answer"}
    original = next(c for c in cases if c["input"]["explanation"] == "Original answer")
    corrected = next(c for c in cases if c["input"]["explanation"] == "Corrected answer")
    assert original["human"]["quality"] == "conflicting"
    assert corrected["human"]["quality"] == "ready"
    assert {e["event_id"] for e in original["human"]["events"]} == {"f1", "r2"}
    assert [e["event_id"] for e in original["human"]["events"][-1]["revision_history"]] == ["r1", "r2"]
    assert all(c["image_error"] == "missing_or_invalid_image" for c in cases)
    assert all(c["case_id"].startswith("post1-") for c in cases)
    assert all(c["input_sha256"] == digest(c["input"]) for c in cases)
    with pytest.raises(FileExistsError):
        dataset.prepare(tmp_path, output)


def test_admission_does_not_create_answer_label_and_missing_image_is_hold(tmp_path, monkeypatch):
    case = _case("post2", "Only answer")
    _snapshot(tmp_path, "review-v1", [case],
              [_event(case, "r1", {"admission": "accept"})], image=None)
    monkeypatch.setattr(dataset, "SNAPSHOTS", ("review-v1",))
    report = dataset.prepare(tmp_path, tmp_path / "out")
    assert report["cases"] == 0
    assert report["excluded"] == [{"snapshot": "review-v1", "post_id": "post2", "slot": 0,
                                   "reason": "no_answer_quality_field"}]


def test_manifest_and_event_identity_tampering_rejected(tmp_path, monkeypatch):
    case = _case("post3", "Answer")
    folder = _snapshot(tmp_path, "review-v1", [case],
                       [_event(case, "r1", {"ground_truth": "ready"})])
    monkeypatch.setattr(dataset, "SNAPSHOTS", ("review-v1",))
    (folder / "cases.json").write_text("[]")
    with pytest.raises(ValueError, match="Source file changed"):
        dataset.prepare(tmp_path, tmp_path / "out1")
    write_json(folder / "cases.json", [case])
    event = _event(case, "r1", {"ground_truth": "ready"})
    event["input_sha256"] = "0" * 64
    (folder / "events.jsonl").write_text(json.dumps(event) + "\n")
    with pytest.raises(ValueError, match="packet identity"):
        dataset.prepare(tmp_path, tmp_path / "out2")


def test_unlabeled_alternate_version_is_not_manufactured(tmp_path, monkeypatch):
    answers = [{"source": "original", "text": "Original"},
               {"source": "candidate", "text": "Candidate"}]
    case = _case("post4", "Original", answers=answers)
    _snapshot(tmp_path, "fresh-human-audit-v2", [case],
              [_event(case, "f1", {"quality_a": "repair"})])
    monkeypatch.setattr(dataset, "SNAPSHOTS", ("fresh-human-audit-v2",))
    report = dataset.prepare(tmp_path, tmp_path / "out")
    cases = json.loads((tmp_path / "out/cases.json").read_text())
    assert [c["input"]["explanation"] for c in cases] == ["Original"]
    assert report["excluded"] == [{"snapshot": "fresh-human-audit-v2", "post_id": "post4",
                                   "slot": 1, "reason": "no_answer_quality_field"}]


def test_attributable_reassessment_uses_exact_review_input(tmp_path, monkeypatch):
    case = _case("post5", "Stored answer")
    _snapshot(tmp_path, "review-v1", [case], [])
    feedback = tmp_path / "curation/feedback"
    feedback.mkdir()
    reassessment = {"event_id": "human-reassessment", "corpus_id": "corpus", "items": [
        {"post_id": "post5", "input_sha256": case["input_sha256"],
         "dimensions": {"ground_truth": {"certainty": "stated", "verdict": "fail"}},
         "reason": "Wrong reference"},
        {"post_id": "post5", "input_sha256": "0" * 64,
         "dimensions": {"ground_truth": {"certainty": "stated", "verdict": "fail"}},
         "reason": "Unmatched version"},
        {"post_id": "post5", "input_sha256": case["input_sha256"],
         "current_decision": "accept", "reason": "Admission only"}]}
    (feedback / "reassessments.jsonl").write_text(json.dumps(reassessment) + "\n")
    monkeypatch.setattr(dataset, "SNAPSHOTS", ("review-v1",))
    report = dataset.prepare(tmp_path, tmp_path / "out")
    cases = json.loads((tmp_path / "out/cases.json").read_text())
    assert len(cases) == 1
    assert cases[0]["human"]["quality"] == "repair"
    assert cases[0]["human"]["events"][0]["notes"] == "Wrong reference"
    assert report["excluded"][-1]["reason"] == "unmatched_or_unrecognized_ground_truth"


def test_duplicate_packet_and_manifest_path_escape_rejected(tmp_path, monkeypatch):
    case = _case("post6", "Answer")
    folder = _snapshot(tmp_path, "review-v1", [case, case],
                       [_event(case, "r1", {"ground_truth": "ready"})])
    monkeypatch.setattr(dataset, "SNAPSHOTS", ("review-v1",))
    with pytest.raises(ValueError, match="Duplicate post"):
        dataset.prepare(tmp_path, tmp_path / "out1")
    write_json(folder / "cases.json", [case])
    manifest = json.loads((folder / "manifest.json").read_text())
    manifest["files"]["cases.json"] = file_hash(folder / "cases.json")
    outsider = tmp_path / "curation/outsider.json"
    outsider.write_text("{}")
    manifest["files"]["../outsider.json"] = file_hash(outsider)
    write_json(folder / "manifest.json", manifest)
    with pytest.raises(ValueError, match="Source file changed"):
        dataset.prepare(tmp_path, tmp_path / "out2")


def test_independent_feedback_chains_keep_conflicting_judgments(tmp_path, monkeypatch):
    case = _case("post7", "Answer")
    _snapshot(tmp_path, "review-v1", [case],
              [_event(case, "independent-1", {"ground_truth": "ready"}),
               _event(case, "independent-2", {"ground_truth": "repair"})])
    monkeypatch.setattr(dataset, "SNAPSHOTS", ("review-v1",))
    report = dataset.prepare(tmp_path, tmp_path / "out")
    row = json.loads((tmp_path / "out/cases.json").read_text())[0]
    assert report["cases"] == 1
    assert row["human"]["quality"] == "conflicting"
    assert {e["event_id"] for e in row["human"]["events"]} == {"independent-1", "independent-2"}
    assert all(len(e["revision_history"]) == 1 for e in row["human"]["events"])


def test_later_feedback_family_metadata_replaces_source_packet_group(tmp_path, monkeypatch):
    packet_dir = tmp_path / "curation/explanation-calibration-v1"
    packet_dir.mkdir(parents=True)
    source_cases = []
    feedback_cases = []
    events = []
    summaries = []
    for pid in ("pA", "pB"):
        original = _case(pid, f"Answer for {pid}", answers=[{"source": "original", "text": f"Answer for {pid}"}])
        original["stratum"] = "random_cached"
        original["case_id"] = pid
        source_cases.append(original)
        triplet = {k: original["input"][k] for k in ("explanation", "comment_evidence", "image_sha256")}
        event = _event(original, f"feedback-{pid}", {"quality_a": "ready"})
        events.append(event)
        feedback_cases.append({"post_id": pid, "case_id": pid, "group_id": "pA",
                               "stratum": "random_cached", "family_weight": .5,
                               "human_event_id": event["event_id"],
                               "input": triplet, "input_sha256": digest(triplet)})
        summaries.append({"post_id": pid, "event": event,
                          "answers": [{"source": "original", "quality": "ready",
                                       "text_sha256": digest(f"Answer for {pid}")}]})
    write_json(packet_dir / "cases.json", source_cases)
    write_json(packet_dir / "manifest.json", {"files": {"cases.json": file_hash(packet_dir / "cases.json")}})
    folder = tmp_path / "curation/explanation-calibration-feedback-v1"
    folder.mkdir()
    write_json(folder / "cases.json", feedback_cases)
    (folder / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))
    write_json(folder / "human-feedback.json", summaries)
    write_json(folder / "duplicate-inspection.json", [{"left": "pA", "right": "pB",
                 "relation": "same_image_and_joke"}])
    files = {name: file_hash(folder / name) for name in
             ("cases.json", "events.jsonl", "human-feedback.json", "duplicate-inspection.json")}
    manifest = {"files": files, "packet_id": "packet",
                "packet_manifest_sha256": file_hash(packet_dir / "manifest.json")}
    manifest["snapshot_id"] = digest(manifest)
    write_json(folder / "manifest.json", manifest)
    monkeypatch.setattr(dataset, "SNAPSHOTS", ("explanation-calibration-feedback-v1",))
    report = dataset.prepare(tmp_path, tmp_path / "out")
    rows = json.loads((tmp_path / "out/cases.json").read_text())
    assert report["known_groups"] == 1
    assert {r["group_id"] for r in rows} == {"pA"}
    assert {r["family_weight"] for r in rows} == {.5}
    assert {r["stratum"] for r in rows} == {"random_cached"}
    changed = next(r for r in rows if r["post_id"] == "pB")
    assert changed["provenance"]["review_selections"][0]["source_packet_group_id"] == "pB"
    assert changed["human"]["quality"] == "ready"
    assert changed["input_sha256"] == digest(changed["input"])
    frozen_manifest = json.loads((tmp_path / "out/manifest.json").read_text())
    assert frozen_manifest["producer_code_sha256"] == file_hash(Path(dataset.__file__))
    write_json(folder / "duplicate-inspection.json", [])
    manifest["files"]["duplicate-inspection.json"] = file_hash(folder / "duplicate-inspection.json")
    manifest["snapshot_id"] = digest({k: v for k, v in manifest.items() if k != "snapshot_id"})
    write_json(folder / "manifest.json", manifest)
    with pytest.raises(ValueError, match="lacks inspected pair"):
        dataset.prepare(tmp_path, tmp_path / "out2")
