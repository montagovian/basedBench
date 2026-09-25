"""Evidence binding and public privacy for immutable release reports."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from PIL import Image

from basedbench.pipeline import release_report, release_snapshot
from basedbench.pipeline.release_report import build_report, export_release
from basedbench.pipeline.release_snapshot import freeze_release


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _fixture(tmp_path: Path, *, scoring_version: str = "majority-v1") -> tuple[Path, dict]:
    for name in ("a", "b"):
        Image.new("RGB", (2, 2), "red" if name == "a" else "blue").save(tmp_path / f"{name}.png")
    items = []
    for post_id, cohort in (("a", "legacy"), ("b", "development")):
        items.append({
            "post_id": post_id,
            "title": f"Title {post_id}",
            "subreddit": "memes",
            "ground_truth": f"Answer {post_id}",
            "image_path": f"{post_id}.png",
            "cohort": cohort,
            "exposure": "unknown" if cohort == "legacy" else "exposed",
            "admission_origin": "legacy_human_validated" if cohort == "legacy" else "qualified_automation",
            "policy_version": "policy-v1",
            "answer_readiness": "unknown" if cohort == "legacy" else "ready_tentative",
            "source_support": "unknown" if cohort == "legacy" else "pass",
            "content_status": "unknown" if cohort == "legacy" else "pass",
            "suitability": "unknown" if cohort == "legacy" else "pass",
            "duplicate_status": "unknown" if cohort == "legacy" else "pass",
            "rights_status": "unknown" if cohort == "legacy" else "mixed_rights",
            "answer_provenance": {"reviewer_note": "PRIVATE-REVIEW-NOTE", "local_path": "/secret"},
        })
    release_dir = tmp_path / "release"
    manifest = freeze_release({
        "name": "test", "policy_version": "policy-v1", "items": items,
        "evaluation": {"model_panel": ["model-a", "model-b"],
                       "prediction_prompt_id": "predict-v1", "judge_prompt_id": "judge-v1",
                       "scoring_version": scoring_version},
    }, release_dir, source_root=tmp_path)
    return release_dir, manifest


def _evidence(manifest: dict) -> dict:
    a, b = manifest["items"]
    predictions = [
        {"prediction_id": "p-a", "post_id": "a", "model_id": "model-a",
         "prediction": "The same joke", "prediction_prompt_id": "predict-v1",
         "image_sha256": a["image_sha256"], "input_mode": "image_only",
         "provider_response": "PRIVATE-PROVIDER-RESPONSE"},
        {"prediction_id": "p-b", "post_id": "b", "model_id": "model-a",
         "prediction": "The other joke", "prediction_prompt_id": "predict-v1",
         "image_sha256": b["image_sha256"], "input_mode": "image_only"},
    ]
    judgments = [
        {"judgment_id": f"j-a-{n}", "prediction_id": "p-a", "judge_model": f"judge-{n}",
         "verdict": verdict, "reasoning": f"Reason {n}", "judge_prompt_id": "judge-v1",
         "answer_sha256": a["answer_sha256"], "prediction_sha256": _hash("The same joke"),
         "scoring_version": "majority-v1", "request_id": "PRIVATE-REQUEST-ID"}
        for n, verdict in ((1, "correct"), (2, "correct"), (3, "incorrect"))
    ]
    return {"schema_version": "basedbench.release-evidence.v1", "predictions": predictions,
            "judgments": judgments,
            "historical_summary": {"total": 519, "secret": "PRIVATE-HISTORICAL"}}


def test_cohorts_denominators_and_agreement(tmp_path: Path) -> None:
    release_dir, manifest = _fixture(tmp_path)
    report = build_report(release_dir, _evidence(manifest))
    legacy = report["cohorts"]["legacy"]["models"]["model-a"]
    development = report["cohorts"]["development"]["models"]["model-a"]
    combined = report["cohorts"]["combined"]["models"]["model-a"]
    assert (legacy["correct"], legacy["scored_denominator"], legacy["accuracy"]) == (1, 1, 1)
    assert legacy["multi_judge_agreement"] == {
        "judged_by_multiple": 1, "unanimous_agreements": 0, "rate": 0,
    }
    assert (development["predictions"], development["unresolved_items"],
            development["scored_denominator"], development["accuracy"]) == (1, 1, 0, None)
    assert (combined["predictions"], combined["missing_predictions"],
            combined["judged_items"], combined["scored_denominator"]) == (2, 0, 1, 1)
    assert report["cohorts"]["combined"]["models"]["model-b"]["missing_predictions"] == 2
    assert report["cohorts"]["development"]["exposure"] == {"exposed": 1}
    assert report["unverified_legacy"]["historical_summary"]["total"] == 519


def test_exact_binding_rejects_stale_evidence_without_scoring(tmp_path: Path) -> None:
    release_dir, manifest = _fixture(tmp_path)
    evidence = _evidence(manifest)
    evidence["predictions"][0]["image_sha256"] = "0" * 64
    evidence["judgments"][0]["answer_sha256"] = "0" * 64
    evidence["judgments"][1]["prediction_sha256"] = "0" * 64
    evidence["judgments"][2]["scoring_version"] = "old-v0"
    report = build_report(release_dir, evidence)
    assert report["evidence_coverage"]["predictions_unmatched"] == {"image_sha256_mismatch": 1}
    assert report["evidence_coverage"]["judgments_unmatched"] == {"prediction_unmatched": 3}
    assert report["cohorts"]["combined"]["models"]["model-a"]["scored_denominator"] == 0


def test_judgment_version_mismatches_are_counted(tmp_path: Path) -> None:
    release_dir, manifest = _fixture(tmp_path)
    evidence = _evidence(manifest)
    evidence["judgments"][0]["answer_sha256"] = "0" * 64
    evidence["judgments"][1]["prediction_sha256"] = "0" * 64
    evidence["judgments"][2]["judge_prompt_id"] = "old-prompt"
    report = build_report(release_dir, evidence)
    assert report["evidence_coverage"]["judgments_unmatched"] == {
        "answer_sha256_mismatch": 1, "prediction_sha256_mismatch": 1,
        "judge_prompt_id_mismatch_or_missing": 1,
    }
    assert report["cohorts"]["legacy"]["models"]["model-a"]["unresolved_items"] == 1


def test_scoring_version_and_orphan_judgment_are_unmatched(tmp_path: Path) -> None:
    release_dir, manifest = _fixture(tmp_path)
    evidence = _evidence(manifest)
    evidence["judgments"][0]["scoring_version"] = "old-v0"
    evidence["judgments"][1]["prediction_id"] = "never-supplied"
    report = build_report(release_dir, evidence)
    assert report["evidence_coverage"]["judgments_unmatched"] == {
        "scoring_version_mismatch_or_missing": 1,
        "unknown_prediction": 1,
    }
    assert report["cohorts"]["legacy"]["models"]["model-a"]["scored_denominator"] == 0


def test_unsupported_scoring_version_fails(tmp_path: Path) -> None:
    release_dir, manifest = _fixture(tmp_path, scoring_version="unknown-v2")
    with pytest.raises(ValueError, match="unsupported scoring_version"):
        build_report(release_dir, _evidence(manifest))


def test_evidence_digest_is_order_independent_and_covers_historical_summary(tmp_path: Path) -> None:
    release_dir, manifest = _fixture(tmp_path)
    evidence = _evidence(manifest)
    original = build_report(release_dir, evidence)["evidence_sha256"]
    reordered = {**evidence,
                 "predictions": list(reversed(evidence["predictions"])),
                 "judgments": list(reversed(evidence["judgments"]))}
    assert build_report(release_dir, reordered)["evidence_sha256"] == original
    changed = {**evidence, "historical_summary": {"total": 520}}
    assert build_report(release_dir, changed)["evidence_sha256"] != original
    public = export_release(release_dir, tmp_path / "public", evidence)
    public_report = json.loads((public / "report.json").read_text())
    assert public_report["evidence_sha256"] == original
    assert "unverified_legacy" not in public_report
    assert "PRIVATE-HISTORICAL" not in (public / "report.json").read_text()


def test_malformed_evidence_fails(tmp_path: Path) -> None:
    release_dir, manifest = _fixture(tmp_path)
    evidence = _evidence(manifest)
    evidence["judgments"][0]["verdict"] = "maybe"
    with pytest.raises(ValueError, match="verdict"):
        build_report(release_dir, evidence)
    evidence["judgments"][0]["verdict"] = "correct"
    del evidence["predictions"][0]["model_id"]
    with pytest.raises(ValueError, match="model_id"):
        build_report(release_dir, evidence)


@pytest.mark.parametrize("mutation", [
    lambda e: e["predictions"].append({**e["predictions"][0], "prediction_id": "other"}),
    lambda e: e["judgments"].append({**e["judgments"][0], "judgment_id": "other"}),
    lambda e: e["judgments"].append(dict(e["judgments"][0])),
])
def test_ambiguous_attempts_fail(tmp_path: Path, mutation) -> None:
    release_dir, manifest = _fixture(tmp_path)
    evidence = _evidence(manifest)
    mutation(evidence)
    with pytest.raises(ValueError, match="duplicate"):
        build_report(release_dir, evidence)


def test_missing_versions_cannot_reuse_evidence(tmp_path: Path) -> None:
    release_dir, manifest = _fixture(tmp_path)
    evidence = _evidence(manifest)
    del evidence["predictions"][0]["prediction_prompt_id"]
    del evidence["judgments"][0]["judge_prompt_id"]
    report = build_report(release_dir, evidence)
    assert report["evidence_coverage"]["predictions_unmatched"] == {
        "prediction_prompt_id_mismatch_or_missing": 1,
    }
    assert report["cohorts"]["legacy"]["models"]["model-a"]["scored_denominator"] == 0


def test_export_allowlist_deterministic_and_atomic(tmp_path: Path) -> None:
    release_dir, manifest = _fixture(tmp_path)
    evidence = _evidence(manifest)
    first = export_release(release_dir, tmp_path / "export-a", evidence)
    second = export_release(release_dir, tmp_path / "export-b", {
        **evidence, "predictions": list(reversed(evidence["predictions"])),
        "judgments": list(reversed(evidence["judgments"])),
    })
    files_a = {p.relative_to(first): p.read_bytes() for p in first.rglob("*") if p.is_file()}
    files_b = {p.relative_to(second): p.read_bytes() for p in second.rglob("*") if p.is_file()}
    assert files_a == files_b
    assert len(json.loads((first / "data" / "predictions.jsonl").read_text().splitlines()[0])) > 0
    assert b"The same joke" in files_a[Path("data/predictions.jsonl")]
    assert b"Reason 1" in files_a[Path("data/judgments.jsonl")]
    all_public_bytes = b"\n".join(files_a.values())
    for marker in (b"PRIVATE-REVIEW-NOTE", b"PRIVATE-PROVIDER-RESPONSE",
                   b"PRIVATE-REQUEST-ID", b"PRIVATE-HISTORICAL", b"answer_provenance"):
        assert marker not in all_public_bytes
    assert b"license: other" in files_a[Path("README.md")]
    assert b"qualified_automation" in files_a[Path("data/memes.jsonl")]
    with pytest.raises(FileExistsError):
        export_release(release_dir, first, evidence)
    assert files_a == {p.relative_to(first): p.read_bytes() for p in first.rglob("*") if p.is_file()}


def test_tampered_release_cannot_export(tmp_path: Path) -> None:
    release_dir, manifest = _fixture(tmp_path)
    (release_dir / "images" / manifest["items"][0]["image_filename"]).write_bytes(b"changed")
    with pytest.raises(ValueError):
        export_release(release_dir, tmp_path / "public")
    assert not (tmp_path / "public").exists()


def test_export_failure_removes_staging(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    release_dir, manifest = _fixture(tmp_path)

    def fail_write(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(release_report, "_write_json", fail_write)
    with pytest.raises(OSError, match="disk full"):
        export_release(release_dir, tmp_path / "public", _evidence(manifest))
    assert not (tmp_path / "public").exists()
    assert not list(tmp_path.glob(".public.*"))


def test_image_changed_between_validation_and_copy_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    release_dir, manifest = _fixture(tmp_path)

    def mutate_after_load(path: Path) -> dict:
        verified = release_snapshot.load_release(path)
        (release_dir / "images" / manifest["items"][0]["image_filename"]).write_bytes(b"changed")
        return verified

    monkeypatch.setattr(release_report, "load_release", mutate_after_load)
    with pytest.raises(ValueError, match="image changed during export"):
        export_release(release_dir, tmp_path / "public", _evidence(manifest))
    assert not (tmp_path / "public").exists()
    assert not list(tmp_path.glob(".public.*"))


def test_symlinked_output_parent_is_rejected(tmp_path: Path) -> None:
    release_dir, manifest = _fixture(tmp_path)
    (tmp_path / "linked").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink output parent"):
        export_release(release_dir, tmp_path / "linked" / "public", _evidence(manifest))
    assert not (tmp_path / "public").exists()
