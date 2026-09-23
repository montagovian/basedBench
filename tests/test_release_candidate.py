from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from scripts.prepare_release_candidate import MODEL_PANEL, prepare


PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000b49444154789c636000020000050001a5f645400000000049454e44ae426082"
)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _source_digest(text: str) -> str:
    return _sha(json.dumps(text, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def _dataset_version(pairs: list[tuple[str, str]]) -> str:
    digest = hashlib.sha256()
    for post_id, answer in sorted(pairs):
        digest.update(post_id.encode())
        digest.update(answer.encode())
    return digest.hexdigest()[:16]


def _json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def _source(tmp_path: Path) -> Path:
    root = tmp_path / "source"
    images = root / "data/images"
    images.mkdir(parents=True)
    db = sqlite3.connect(root / "data/basedbench.db")
    db.executescript("""
        CREATE TABLE snapshots(snapshot_id TEXT, name TEXT, meme_count INTEGER, created_at TEXT);
        CREATE TABLE snapshot_memes(snapshot_id TEXT, post_id TEXT);
        CREATE TABLE memes(post_id TEXT, title TEXT, subreddit TEXT, local_image_path TEXT);
        CREATE TABLE ground_truths(post_id TEXT, explanation TEXT);
        CREATE TABLE reviews(post_id TEXT, status TEXT);
        CREATE TABLE predictions(id INTEGER, post_id TEXT, model_id TEXT, prediction TEXT, error TEXT, dataset_version TEXT);
        CREATE TABLE judgments(id INTEGER, prediction_id INTEGER, verdict TEXT, judge_model TEXT);
        CREATE TABLE llm_calls(id INTEGER, post_id TEXT, model TEXT, prompt_version TEXT, role TEXT, image_path TEXT);
    """)
    legacy_pairs = [(f"legacy{index:04d}", f"answer {index}") for index in range(519)]
    legacy_id = _dataset_version(legacy_pairs)
    db.execute("INSERT INTO snapshots VALUES (?, 'basedBench-519-2026-07', 519, '2026-07-15')", (legacy_id,))
    for index in range(519):
        post_id = f"legacy{index:04d}"
        image_path = f"data/images/{post_id}.png"
        (root / image_path).write_bytes(PNG)
        db.execute("INSERT INTO memes VALUES (?, ?, ?, ?)", (post_id, f"title {index}", "ExplainTheJoke", image_path))
        db.execute("INSERT INTO ground_truths VALUES (?, ?)", (post_id, f"answer {index}"))
        db.execute("INSERT INTO reviews VALUES (?, 'validated')", (post_id,))
        db.execute("INSERT INTO snapshot_memes VALUES (?, ?)", (legacy_id, post_id))
    db.execute("INSERT INTO predictions VALUES (1, 'legacy0000', ?, 'old answer', NULL, ?)", (MODEL_PANEL[0], legacy_id))
    db.execute("INSERT INTO predictions VALUES (2, 'legacy0000', ?, 'other-run answer', NULL, 'other-version')", (MODEL_PANEL[0],))
    db.executemany("INSERT INTO judgments VALUES (?, ?, ?, ?)", [
        (1, 1, "incorrect", "judge-a"), (2, 1, "correct", "judge-a"),
        (3, 1, "correct", "judge-b"), (4, 1, "incorrect", "judge-c"),
        (5, 2, "correct", "judge-a"), (6, 2, "correct", "judge-b"),
    ])
    db.execute("INSERT INTO llm_calls VALUES (1, 'legacy0000', 'model', 'old-prompt', 'prediction', 'data/images/legacy0000.png')")

    identities = [f"dev{i:02d}" for i in range(18)]
    target_ledger = []
    fresh_cases = []
    targeted_cases = []
    expected_ready = {}
    for index, post_id in enumerate(identities):
        text = f"ready answer {index}" if index < 8 else f"old answer {index}"
        db.execute("INSERT INTO memes VALUES (?, ?, ?, ?)", (post_id, f"dev title {index}", "ExplainTheJoke", "data/images/legacy0000.png"))
        db.execute("INSERT INTO ground_truths VALUES (?, ?)", (post_id, text))
        status = "human_ready_version_available" if index < 8 else (
            "unresolved_overlap_hold" if index < 16 else "unresolved" if index == 16 else "repair_still_needed"
        )
        source = "original" if index < 6 else "proposal"
        ready = {
            "text_sha256": _source_digest(text),
            "source": source,
            "snapshot_id": "fresh-snapshot" if source == "original" else "targeted-snapshot",
            "human_event_id": f"event-{index}",
            "note_verbatim": "i don't quite grok this" if index == 5 else "",
        } if index < 8 else None
        target_ledger.append({
            "post_id": post_id,
            "answer_availability_status": status,
            "available_human_ready_version": ready,
            "original_screening": {"status": "family_or_exposure_hold" if 8 <= index < 16 else "eligible"},
            "prior_original_judgment": "repair" if index == 17 else None,
        })
        if index < 6:
            fresh_cases.append({"case_id": post_id, "human_event_id": f"event-{index}", "input": {"explanation": text}})
        elif index < 8:
            targeted_cases.append({"group_id": post_id, "input": {"answers": [{"source": "proposal", "text": text}]}})
        if index < 8:
            expected_ready[post_id] = text
    db.commit()
    db.close()

    fresh_analysis = {"selection": {"selected_ids": identities}}
    target_analysis = {"full_18_identity_availability_ledger": target_ledger}
    _json(root / "data/backfill/fresh-human-audit-feedback-analysis-v1.json", fresh_analysis)
    _json(root / "data/backfill/targeted-corrections-feedback-analysis-v1.json", target_analysis)
    fresh_dir = root / "data/curation/fresh-human-audit-feedback-v1"
    target_dir = root / "data/curation/targeted-corrections-feedback-v1"
    _json(fresh_dir / "cases.json", fresh_cases)
    _json(fresh_dir / "human-feedback.json", [])
    (fresh_dir / "events.jsonl").write_text("\n".join(json.dumps({"post_id": f"dev{i:02d}", "event_id": f"event-{i}"}) for i in range(6)), encoding="utf-8")
    _json(target_dir / "cases.json", targeted_cases)
    _json(target_dir / "human-feedback.json", [])
    (target_dir / "events.jsonl").write_text("\n".join(json.dumps({"post_id": f"dev{i:02d}", "event_id": f"event-{i}"}) for i in range(6, 8)), encoding="utf-8")
    for archive, snapshot_id in ((fresh_dir, "fresh-snapshot"), (target_dir, "targeted-snapshot")):
        files = {name: _sha((archive / name).read_text(encoding="utf-8")) for name in ("cases.json", "events.jsonl", "human-feedback.json")}
        _json(archive / "manifest.json", {"snapshot_id": snapshot_id, "files": files})
    outcomes = []
    for index in range(100):
        decision = "accept" if index < 41 else "defer" if index < 99 else "reject"
        component_decision = "pass" if decision == "accept" else "defer" if decision == "defer" else "fail"
        outcomes.append({
            "post_id": f"pilot{index:03d}",
            "decision": decision,
            "human_validated": False,
            "components": {
                gate: {"decision": component_decision, "reason_codes": []}
                for gate in ("answer", "content", "suitability", "duplicates")
            },
            "reason_codes": [],
            "input_sha256": f"input-{index}",
            "provenance": {"source_admission_experiment_id": "pilot-source"},
        })
    _json(root / "data/backfill/admission-june20-26-v2/report.json", {
        "version": "v2", "component_versions": {"answer": "eval-v3"}, "outcomes": outcomes,
    })
    return root


def test_prepare_keeps_legacy_and_holds_newer_with_exact_private_versions(tmp_path: Path) -> None:
    source = _source(tmp_path)
    before = hashlib.sha256((source / "data/basedbench.db").read_bytes()).hexdigest()
    output = tmp_path / "candidate"

    result = prepare(source, output)

    selection = json.loads((output / "selection.json").read_text())
    evidence = json.loads((output / "evidence.json").read_text())
    held = json.loads((output / "held-ledger.json").read_text())
    provenance = json.loads((output / "provenance-inventory.json").read_text())
    assert len(selection["items"]) == 519
    assert {item["cohort"] for item in selection["items"]} == {"legacy"}
    assert all(item["exposure"] == "exposed" for item in selection["items"])
    assert all(item["answer_readiness"] == "unknown" for item in selection["items"])
    assert all(item["rights_status"] == "mixed_rights" for item in selection["items"])
    assert selection["evaluation"]["model_panel"] == MODEL_PANEL
    assert evidence["predictions"] == [] and evidence["judgments"] == []
    assert evidence["historical_summary"]["binding_status"]["current_compatible_prediction_rows"] == 0
    historical = evidence["historical_summary"]
    assert historical["snapshot_dataset_version_history"]["model_counts"][MODEL_PANEL[0]]["prediction_rows"] == 1
    assert historical["snapshot_dataset_version_history"]["model_counts"][MODEL_PANEL[0]]["scored_denominator"] == 1
    assert historical["snapshot_dataset_version_history"]["model_counts"][MODEL_PANEL[0]]["correct"] == 1
    assert historical["cross_version_member_history"]["model_counts"][MODEL_PANEL[0]]["prediction_rows"] == 2
    assert len(held["held_items"]) == 118
    dev = {row["post_id"]: row for row in held["held_items"] if row["candidate_kind"] == "fresh_human_audit_pool"}
    assert len(dev) == 18
    assert set(row["text"] for row in dev["dev06"]["answer_versions"]) == {"ready answer 6"}
    assert dev["dev05"]["answer_versions"][0]["readiness"] == "ready_tentative"
    assert dev["dev00"]["answer_versions"][0]["human_event_id"] == "event-0"
    assert dev["dev00"]["answer_versions"][0]["source_ledger_text_sha256"] == _source_digest("ready answer 0")
    assert any(blocker["gate"] == "duplicate_status" for blocker in dev["dev08"]["blockers"])
    assert any(blocker["gate"] == "duplicate_status" and blocker["status"] == "unknown" for blocker in dev["dev00"]["blockers"])
    assert all(blocker["gate"] != "rights_status" for blocker in dev["dev00"]["blockers"])
    pilot = [row for row in held["held_items"] if row["candidate_kind"] == "june_20_26_automatic_pilot"]
    assert len(pilot) == 100
    assert sum(row["historical_decision"] == "accept" for row in pilot) == 41
    assert all(any(blocker["gate"] == "admission_origin" for blocker in row["blockers"]) for row in pilot)
    assert all(not any(blocker["gate"] == "answer_readiness" for blocker in row["blockers"]) for row in pilot)
    assert provenance["legacy_snapshot"]["current_images"]["present"] == 519
    assert provenance["legacy_snapshot"]["current_images"]["historical_image_hashes_available"] == 0
    assert result["ready_private_versions"] == 8
    after = hashlib.sha256((source / "data/basedbench.db").read_bytes()).hexdigest()
    assert before == after


def test_prepare_refuses_existing_output_and_unsafe_source_images(tmp_path: Path) -> None:
    source = _source(tmp_path)
    existing = tmp_path / "exists"
    existing.mkdir()
    with pytest.raises(FileExistsError):
        prepare(source, existing)

    db = sqlite3.connect(source / "data/basedbench.db")
    db.execute("UPDATE memes SET local_image_path = ? WHERE post_id = 'legacy0000'", ("/etc/passwd",))
    db.commit()
    db.close()
    with pytest.raises(ValueError, match="escapes source root"):
        prepare(source, tmp_path / "must-not-exist")
    assert not (tmp_path / "must-not-exist").exists()


def test_prepare_write_failure_leaves_no_partial_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = _source(tmp_path)
    output = tmp_path / "candidate"
    import scripts.prepare_release_candidate as adapter

    original = adapter._write_json
    calls = 0

    def fail_second(path: Path, payload: object) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("fixture write failure")
        original(path, payload)

    monkeypatch.setattr(adapter, "_write_json", fail_second)
    with pytest.raises(OSError, match="fixture write failure"):
        prepare(source, output)
    assert not output.exists()
    assert not list(tmp_path.glob(".candidate.staging-*"))
