"""Offline release commands stay independent of live database content."""

import hashlib
import json

from PIL import Image
from typer.testing import CliRunner

from basedbench.cli import app
from basedbench.db import queries

from .conftest import sample_post


def test_release_cli_survives_live_database_and_asset_changes(db, tmp_path, monkeypatch):
    import basedbench.cli as cli

    def forbid_live_load():
        raise AssertionError("Release commands must not open the live DB or load credentials")

    monkeypatch.setattr(cli, "_load", forbid_live_load)
    image = tmp_path / "meme.png"
    Image.new("RGB", (3, 3), "blue").save(image)
    expected_image = image.read_bytes()
    queries.insert_meme(db, sample_post("item"))
    queries.upsert_ground_truth(db, "item", "Exact original joke", 0.9, [], 3, 10.0,
                               "fixture-model", "fixture-prompt")
    queries.upsert_review(db, "item", "validated")
    db.conn.execute("UPDATE memes SET local_image_path = ? WHERE post_id = ?", (str(image), "item"))
    snapshot = queries.create_snapshot(db, "legacy-fixture")
    saved = queries.snapshot_meme_details(db, snapshot)[0]
    selection = {
        "name": "cli-fixture", "policy_version": "legacy-current-content-v1",
        "evaluation": {"model_panel": ["model-a"]},
        "items": [{
            "post_id": saved.post_id, "title": saved.title, "subreddit": saved.subreddit,
            "ground_truth": saved.ground_truth, "image_path": "meme.png", "cohort": "legacy",
            "exposure": "unknown", "admission_origin": "unknown", "policy_version": "legacy",
            "answer_readiness": "unknown", "source_support": "unknown", "content_status": "unknown",
            "suitability": "unknown", "duplicate_status": "unknown", "rights_status": "mixed_rights",
            "answer_provenance": {"private_note": "not for export"},
        }],
    }
    spec = tmp_path / "selection.json"
    spec.write_text(json.dumps(selection))
    frozen = tmp_path / "frozen"
    runner = CliRunner()
    result = runner.invoke(app, ["release", "freeze", str(spec), "--source-root", str(tmp_path), "--output", str(frozen)])
    assert result.exit_code == 0, result.output
    digest = json.loads(result.stdout)["content_sha256"]
    db.conn.execute("UPDATE ground_truths SET explanation = 'Changed answer' WHERE post_id = 'item'")
    image.unlink()
    assert queries.snapshot_meme_details(db, snapshot)[0].ground_truth == "Changed answer"
    assert runner.invoke(app, ["release", "verify", str(frozen)]).exit_code == 0
    inputs = runner.invoke(app, ["release", "inputs", str(frozen)])
    assert inputs.exit_code == 0, inputs.output
    payload = json.loads(inputs.stdout)[0]
    assert set(payload) == {"post_id", "image_path", "image_sha256"}
    assert payload["image_sha256"] == hashlib.sha256(expected_image).hexdigest()
    report = runner.invoke(app, ["release", "report", str(frozen)])
    assert report.exit_code == 0, report.output
    assert json.loads(report.stdout)["cohorts"]["legacy"]["models"]["model-a"]["scored_denominator"] == 0
    exported = tmp_path / "export"
    result = runner.invoke(app, ["release", "export", str(frozen), "--output", str(exported)])
    assert result.exit_code == 0, result.output
    row = json.loads((exported / "data/memes.jsonl").read_text())
    assert row["ground_truth"] == "Exact original joke"
    assert row["release_sha256"] == digest
    assert "answer_provenance" not in row
    assert (exported / "images/item.png").read_bytes() == expected_image
    result = runner.invoke(app, ["release", "export", str(frozen), "--output", str(exported)])
    assert result.exit_code != 0


def test_release_cli_reports_malformed_selection_without_creating_destination(tmp_path):
    selection = tmp_path / "invalid.json"
    selection.write_text("[]")
    destination = tmp_path / "release"
    result = CliRunner().invoke(app, ["release", "freeze", str(selection), "--source-root", str(tmp_path),
                                     "--output", str(destination)])
    assert result.exit_code != 0
    assert not destination.exists()
