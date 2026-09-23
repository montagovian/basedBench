"""Release audits cover metadata privacy and exported byte integrity."""

import hashlib
import importlib.util
import json
from pathlib import Path


def _audit_module():
    script = Path(__file__).resolve().parents[1] / "scripts/release_audit.py"
    spec = importlib.util.spec_from_file_location("release_audit", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_export_audit_checks_sidecars_and_exact_bytes(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "images").mkdir()
    image = b"fixture image bytes"
    (tmp_path / "images/item.jpg").write_bytes(image)
    row = {"post_id": "item", "ground_truth": "answer", "image_filename": "item.jpg",
           "image_sha256": hashlib.sha256(image).hexdigest(),
           "answer_sha256": hashlib.sha256(b"answer").hexdigest()}
    (tmp_path / "data/memes.jsonl").write_text(json.dumps(row) + "\n")
    for name in ("predictions", "judgments", "leaderboard"):
        (tmp_path / f"data/{name}.jsonl").write_text("")
    (tmp_path / "README.md").write_text("Raw Reddit comments, Reddit authors are intentionally omitted.")
    module = _audit_module()
    clean = module.Audit()
    module.check_export(clean, tmp_path, 1)
    assert clean.failures == []
    (tmp_path / "report.json").write_text(json.dumps({"nested": {"answer_provenance": {"reviewer_notes": "private"}}}))
    (tmp_path / "images/item.jpg").write_bytes(b"changed")
    audit = module.Audit()
    module.check_export(audit, tmp_path, 1)
    assert any("forbidden keys" in failure for failure in audit.failures)
    assert any("image hash mismatch" in failure for failure in audit.failures)
