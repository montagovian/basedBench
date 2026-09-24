from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from basedbench.pipeline import jev_decomposition_data as data
from basedbench.pipeline.curation_corpus import digest, file_hash, write_json


def _source(tmp_path: Path) -> Path:
    root = tmp_path / "source"
    dataset = root / "dataset"
    dataset.mkdir(parents=True)
    assets = root / "source-assets"
    assets.mkdir()
    img = assets / "image.png"
    Image.new("RGB", (3, 2), "red").save(img)
    sha = file_hash(img)
    human = {"quality": "ready", "events": [{"notes": "Keep  exact\nformat", "fields": {"ground_truth": "ready"}}]}
    comments = "Subreddit: r/test\n\nComments (2 total):\nID: c1 | Score: 3\nFirst line\n\nSecond line\n---\nID: c2 | Score: 1\nAnother comment\n---"
    cases = [
        {"case_id": "p1-v1", "post_id": "p1", "group_id": "p1", "human": human,
         "image_path": str(img), "image_error": None,
         "input": {"explanation": "One.  Two; three!", "comment_evidence": comments,
                   "image_sha256": sha}, "input_sha256": "v1"},
        {"case_id": "p1-v2", "post_id": "p1", "group_id": "p1", "human": human,
         "image_path": str(img), "image_error": None,
         "input": {"explanation": "Version two.", "comment_evidence": comments,
                   "image_sha256": sha}, "input_sha256": "v2"},
        {"case_id": "p2-v1", "post_id": "p2", "group_id": "p2", "human": human,
         "image_path": None, "image_error": "missing_image",
         "input": {"explanation": "Held case.", "comment_evidence": comments,
                   "image_sha256": "f" * 64}, "input_sha256": "v3"},
    ]
    write_json(dataset / "cases.json", cases)
    manifest = {"files": {"cases.json": file_hash(dataset / "cases.json")},
                "source_manifest_hashes": {}}
    manifest["dataset_id"] = digest(manifest)
    write_json(dataset / "manifest.json", manifest)
    audit = {"version": "grouping-audit-v1", "dataset_manifest_sha256": file_hash(dataset / "manifest.json"),
             "source_files": {str(dataset / "cases.json"): file_hash(dataset / "cases.json"),
                              str(dataset / "manifest.json"): file_hash(dataset / "manifest.json")},
             "case_group_ids": {"p1-v1": "p1", "p1-v2": "p1", "p2-v1": "p2"},
             "case_strata": {"p1-v1": [], "p1-v2": [], "p2-v1": []}, "corrected": []}
    audit["audit_id"] = digest(audit)
    write_json(root / "grouping-audit.json", audit)
    return root


@pytest.fixture(autouse=True)
def _small_expected(monkeypatch):
    monkeypatch.setattr(data, "EXPECTED", {"cases": 3, "posts": 2, "groups": 2,
                                           "quality": {"ready": 3}})


def test_prepare_preserves_exact_versions_comments_spans_and_holds(tmp_path):
    root = _source(tmp_path)
    out = tmp_path / "prepared"
    report = data.prepare(root, out)
    cases = json.loads((out / "cases.json").read_text())
    first = next(row for row in cases if row["case_id"] == "p1-v1")

    assert report["cases"] == 3 and report["posts"] == 2 and report["groups"] == 2
    assert first["human"]["events"][0]["notes"] == "Keep  exact\nformat"
    assert first["input"]["explanation"] == "One.  Two; three!"
    assert "".join(span["text"] for span in first["spans"]) == first["input"]["explanation"]
    assert [span["text"] for span in first["spans"]] == ["One.  ", "Two; ", "three!"]
    assert [comment["id"] for comment in first["comments"]] == ["c1", "c2"]
    assert first["comments"][0]["text"] == "First line\n\nSecond line"
    assert Path(first["image_path"]).read_bytes() == (root / "source-assets/image.png").read_bytes()
    held = next(row for row in cases if row["case_id"] == "p2-v1")
    assert held["image_path"] is None and held["image_error"] == "missing_image"
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["files"]["assets/" + first["input"]["image_sha256"]] == first["input"]["image_sha256"]
    assert manifest["dataset_id"] == digest({k: v for k, v in manifest.items() if k != "dataset_id"})
    with pytest.raises(FileExistsError):
        data.prepare(root, out)


def test_prepare_rejects_tampered_dataset_before_creating_output(tmp_path):
    root = _source(tmp_path)
    with (root / "dataset/cases.json").open("a") as f:
        f.write(" ")
    out = tmp_path / "should-not-exist"
    with pytest.raises(ValueError, match="Frozen source file changed"):
        data.prepare(root, out)
    assert not out.exists()


def test_prepare_rejects_unverified_group_override(tmp_path):
    root = _source(tmp_path)
    audit_path = root / "grouping-audit.json"
    audit = json.loads(audit_path.read_text())
    audit["case_group_ids"]["p1-v2"] = "p2"
    audit["audit_id"] = digest({k: v for k, v in audit.items() if k != "audit_id"})
    write_json(audit_path, audit)
    with pytest.raises(ValueError, match="Unverified group override"):
        data.prepare(root, tmp_path / "output")


def test_spans_cap_at_eight_without_dropping_text():
    text = " ".join(f"part {i};" for i in range(20))
    spans = data._spans(text)
    assert len(spans) == 8
    assert "".join(item["text"] for item in spans) == text
    assert spans[0]["start"] == 0 and spans[-1]["end"] == len(text)
    assert all(left["end"] == right["start"] for left, right in zip(spans, spans[1:]))
