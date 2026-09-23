"""Prepare a private, read-only-derived release candidate selection.

The adapter never opens the source database through the application Database
class. It uses SQLite read-only mode, validates local artifact hashes, and only
writes a new output directory after all inputs have been read successfully.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import shutil
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


POLICY_VERSION = "basedbench.release-candidate-policy.v1"
LEGACY_SNAPSHOT_NAME = "basedBench-519-2026-07"
MODEL_PANEL = [
    "claude-opus-4-8",
    "google/gemini-3.1-pro-preview",
    "gpt-5.5",
    "muse-spark-1.1",
    "x-ai/grok-4.3",
]
TARGETED_ANALYSIS = "data/backfill/targeted-corrections-feedback-analysis-v1.json"
FRESH_ANALYSIS = "data/backfill/fresh-human-audit-feedback-analysis-v1.json"
PILOT_REPORT = "data/backfill/admission-june20-26-v2/report.json"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def source_text_digest(text: str) -> str:
    """Match curation_corpus.digest(text), used by the human-feedback ledgers."""
    canonical = json.dumps(text, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256_bytes(canonical.encode("utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _feedback_archive(source_root: Path, relative: str) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    directory = source_root / relative
    manifest = _read_json(directory / "manifest.json")
    for filename in ("cases.json", "events.jsonl", "human-feedback.json"):
        path = directory / filename
        expected = manifest.get("files", {}).get(filename)
        if not expected or sha256_file(path) != expected:
            raise ValueError(f"feedback archive manifest hash mismatch: {relative}/{filename}")
    cases = _read_json(directory / "cases.json")
    feedback = _read_json(directory / "human-feedback.json")
    events = [json.loads(line) for line in (directory / "events.jsonl").read_text(encoding="utf-8").splitlines() if line]
    return manifest, cases, feedback, events


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )


def _connect_readonly(db_path: Path) -> sqlite3.Connection:
    # mode=ro and query_only prevent writes; a transaction gives the complete
    # inventory one consistent SQLite snapshot, including any active WAL.
    uri = f"file:{db_path.resolve()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    connection.execute("BEGIN")
    return connection


def _table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {str(row["name"]) for row in connection.execute(f"PRAGMA table_info({table})")}


def _required_tables(connection: sqlite3.Connection) -> None:
    existing = {
        str(row[0])
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    required = {"snapshots", "snapshot_memes", "memes", "ground_truths", "reviews", "predictions", "judgments", "llm_calls"}
    missing = sorted(required - existing)
    if missing:
        raise ValueError(f"source database is missing required tables: {', '.join(missing)}")


def _resolve_image(source_root: Path, image_path: str | None) -> Path:
    if not image_path:
        raise ValueError("legacy candidate is missing its current image path")
    relative = Path(image_path)
    candidate = relative if relative.is_absolute() else source_root / relative
    # Do not accept symlink components or a path outside the source tree.
    cursor = candidate
    chain: list[Path] = []
    while cursor != source_root and cursor != cursor.parent:
        chain.append(cursor)
        cursor = cursor.parent
    if cursor != source_root:
        raise ValueError(f"image path escapes source root: {image_path}")
    for component in chain:
        if component.is_symlink():
            raise ValueError(f"image path contains a symlink: {image_path}")
    resolved_root = source_root.resolve(strict=True)
    resolved = candidate.resolve(strict=True)
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"image path escapes source root: {image_path}") from exc
    if not resolved.is_file():
        raise ValueError(f"image path is not a file: {image_path}")
    return resolved


def _answer_record(
    text: str,
    *,
    source: str,
    readiness: str,
    event_id: str | None,
    snapshot_id: str,
    note: str = "",
    source_ledger_hash: str | None = None,
) -> dict[str, Any]:
    exact_hash = sha256_bytes(text.encode("utf-8"))
    return {
        "text": text,
        "text_sha256": exact_hash,
        "source_text_digest_sha256": source_text_digest(text),
        "source_ledger_text_sha256": source_ledger_hash,
        "source": source,
        "readiness": readiness,
        "human_event_id": event_id,
        "snapshot_id": snapshot_id,
        "note_verbatim": note,
    }


def _ready_versions(source_root: Path, fresh: dict[str, Any], targeted: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    versions: dict[str, list[dict[str, Any]]] = defaultdict(list)
    fresh_manifest, fresh_case_rows, fresh_feedback, fresh_event_rows = _feedback_archive(
        source_root, "data/curation/fresh-human-audit-feedback-v1"
    )
    targeted_manifest, targeted_case_rows, targeted_feedback, targeted_event_rows = _feedback_archive(
        source_root, "data/curation/targeted-corrections-feedback-v1"
    )
    fresh_cases = {
        str(case.get("post_id") or case.get("case_id")): case
        for case in fresh_case_rows
    }
    targeted_cases = {str(case.get("group_id") or case.get("post_id") or ""): case for case in targeted_case_rows}
    fresh_event_pairs = {
        (str(event.get("post_id")), str(event.get("event_id"))) for event in fresh_event_rows
    }
    targeted_event_pairs = {
        (str(event.get("post_id")), str(event.get("event_id"))) for event in targeted_event_rows
    }
    target_versions = {
        str(entry["post_id"]): entry
        for entry in targeted["full_18_identity_availability_ledger"]
        if entry.get("available_human_ready_version")
    }
    for post_id, ledger_entry in target_versions.items():
        ref = ledger_entry["available_human_ready_version"]
        source = str(ref["source"])
        if source != "original":
            continue
        case = fresh_cases.get(post_id)
        if not case:
            raise ValueError(f"#26 exact ready answer case is missing for {post_id}")
        if str(ref.get("snapshot_id")) != str(fresh_manifest.get("snapshot_id")):
            raise ValueError(f"#26 source snapshot does not match the verified packet manifest for {post_id}")
        if (post_id, str(ref.get("human_event_id"))) not in fresh_event_pairs:
            raise ValueError(f"#26 human event is absent from the verified journal for {post_id}")
        text = str(case.get("input", {}).get("explanation", ""))
        if source_text_digest(text) != ref["text_sha256"]:
            raise ValueError(f"#26 exact ready answer hash mismatch for {post_id}")
        versions[post_id].append(
            _answer_record(
                text,
                source="original",
                readiness="ready_tentative" if ref.get("note_verbatim") else "ready",
                event_id=str(ref["human_event_id"]),
                snapshot_id=str(ref["snapshot_id"]),
                note=str(ref.get("note_verbatim", "")),
                source_ledger_hash=str(ref["text_sha256"]),
            )
        )
    for post_id, ledger_entry in target_versions.items():
        case = targeted_cases.get(post_id)
        ref = ledger_entry["available_human_ready_version"]
        if str(ref["source"]) == "original":
            continue
        if not case:
            raise ValueError(f"ready correction case is absent from frozen packet: {post_id}")
        if str(ref.get("snapshot_id")) != str(targeted_manifest.get("snapshot_id")):
            raise ValueError(f"#27 source snapshot does not match the verified packet manifest for {post_id}")
        if (post_id, str(ref.get("human_event_id"))) not in targeted_event_pairs:
            raise ValueError(f"#27 human event is absent from the verified journal for {post_id}")
        answers = case.get("input", {}).get("answers", [])
        matches = [
            answer for answer in answers
            if answer.get("source") == ref["source"]
            and source_text_digest(str(answer.get("text", ""))) == ref["text_sha256"]
        ]
        if len(matches) != 1:
            raise ValueError(f"could not resolve exact accepted answer for {post_id}")
        versions[post_id].append(
            _answer_record(
                str(matches[0]["text"]),
                source=str(ref["source"]),
                readiness="ready",
                event_id=str(ref["human_event_id"]),
                snapshot_id=str(ref["snapshot_id"]),
                note=str(ref.get("note_verbatim", "")),
                source_ledger_hash=str(ref["text_sha256"]),
            )
        )
    # Reject ledger/text drift and duplicates rather than silently selecting.
    for post_id, entries in versions.items():
        if len(entries) != 1:
            raise ValueError(f"expected exactly one current human-ready version for {post_id}")
    source_counts = Counter(entries[0]["source"] for entries in versions.values())
    tentative_count = sum(entries[0]["readiness"] == "ready_tentative" for entries in versions.values())
    if len(versions) != 8 or source_counts["original"] != 6 or sum(
        count for source, count in source_counts.items() if source != "original"
    ) != 2 or tentative_count != 1:
        raise ValueError("frozen #26/#27 inputs must resolve to six original ready answers, two accepted proposals, and one tentative note")
    return dict(versions)


def _legacy_rows(connection: sqlite3.Connection, snapshot_id: str) -> list[sqlite3.Row]:
    return connection.execute(
        """SELECT m.post_id, m.title, m.subreddit, m.local_image_path,
                  gt.explanation, r.status AS review_status
           FROM snapshot_memes AS sm
           JOIN memes AS m ON m.post_id = sm.post_id
           LEFT JOIN ground_truths AS gt ON gt.post_id = sm.post_id
           LEFT JOIN reviews AS r ON r.post_id = sm.post_id
           WHERE sm.snapshot_id = ? ORDER BY m.post_id""",
        (snapshot_id,),
    ).fetchall()


def _score_history(
    connection: sqlite3.Connection, snapshot_id: str, *, dataset_version: str | None
) -> dict[str, Any]:
    version_filter = "AND p.dataset_version = ?" if dataset_version is not None else ""
    params: tuple[Any, ...] = (snapshot_id, dataset_version) if dataset_version is not None else (snapshot_id,)
    predictions = connection.execute(
        f"""SELECT p.id, p.post_id, p.model_id, p.dataset_version
            FROM predictions p JOIN snapshot_memes sm ON sm.post_id=p.post_id
            WHERE sm.snapshot_id=? AND p.error IS NULL {version_filter}
            ORDER BY p.model_id, p.post_id, p.id""",
        params,
    ).fetchall()
    by_model: dict[str, list[sqlite3.Row]] = defaultdict(list)
    ids = []
    for row in predictions:
        if row["model_id"] in MODEL_PANEL:
            by_model[str(row["model_id"])].append(row)
            ids.append(int(row["id"]))
    latest_votes: dict[int, dict[str, str]] = defaultdict(dict)
    if ids:
        # Query all votes in the selected history; choose the highest judgment
        # ID for each (prediction, judge), matching db.queries' legacy semantics.
        for row in connection.execute(
            f"""SELECT j.id, j.prediction_id, j.judge_model, j.verdict
                FROM judgments j WHERE j.prediction_id IN ({','.join('?' for _ in ids)})
                ORDER BY j.id""",
            ids,
        ):
            latest_votes[int(row["prediction_id"])][str(row["judge_model"])] = str(row["verdict"])
    counts: dict[str, Any] = {}
    for model in MODEL_PANEL:
        model_predictions = by_model.get(model, [])
        total = len(model_predictions)
        post_ids = {str(row["post_id"]) for row in model_predictions}
        correct = incorrect = unresolved = multi = agreement = 0
        judges_seen: set[str] = set()
        latest_vote_rows = 0
        for prediction in model_predictions:
            votes = latest_votes.get(int(prediction["id"]), {})
            judges_seen.update(votes)
            latest_vote_rows += len(votes)
            if len(votes) > 1:
                multi += 1
                if len(set(votes.values())) == 1:
                    agreement += 1
            n_correct = sum(vote == "correct" for vote in votes.values())
            n_incorrect = sum(vote == "incorrect" for vote in votes.values())
            if len(votes) >= 2 and n_correct >= 2 and n_correct > n_incorrect:
                correct += 1
            elif len(votes) >= 2 and n_incorrect >= 2 and n_incorrect > n_correct:
                incorrect += 1
            else:
                unresolved += 1
        raw = connection.execute(
            f"""SELECT COUNT(*) AS n, j.verdict
                FROM judgments j JOIN predictions p ON p.id=j.prediction_id
                JOIN snapshot_memes sm ON sm.post_id=p.post_id
                WHERE sm.snapshot_id=? AND p.error IS NULL {version_filter}
                  AND p.model_id=? GROUP BY j.verdict""",
            ((snapshot_id, dataset_version, model) if dataset_version is not None else (snapshot_id, model)),
        ).fetchall()
        raw_verdict_rows = {str(row["verdict"]): int(row["n"]) for row in raw}
        raw_judgment_rows = sum(raw_verdict_rows.values())
        counts[model] = {
            "prediction_rows": total,
            "predicted_items": len(post_ids),
            "scored_denominator": correct + incorrect,
            "correct": correct,
            "incorrect": incorrect,
            "unresolved_predictions": unresolved,
            "multi_judge_predictions": multi,
            "judge_agreement_count": agreement,
            "judge_agreement_rate": agreement / multi if multi else None,
            "distinct_judges": len(judges_seen),
            "latest_distinct_judge_votes": latest_vote_rows,
            "raw_judgment_rows": raw_judgment_rows,
            "raw_verdict_rows": raw_verdict_rows,
        }
    versions = connection.execute(
        f"""SELECT p.model_id, p.dataset_version, COUNT(*) AS prediction_rows,
                  COUNT(DISTINCT p.post_id) AS predicted_items
            FROM predictions p JOIN snapshot_memes sm ON sm.post_id=p.post_id
            WHERE sm.snapshot_id=? AND p.error IS NULL {version_filter}
            GROUP BY p.model_id, p.dataset_version
            ORDER BY p.model_id, p.dataset_version""",
        params,
    ).fetchall()
    return {
        "models": counts,
        "dataset_version_breakdown": [dict(row) for row in versions if row["model_id"] in MODEL_PANEL],
    }


def _historical_summary(connection: sqlite3.Connection, snapshot_id: str) -> dict[str, Any]:
    item_count = int(connection.execute(
        "SELECT COUNT(*) FROM snapshot_memes WHERE snapshot_id = ?", (snapshot_id,)
    ).fetchone()[0])
    snapshot_history = _score_history(connection, snapshot_id, dataset_version=snapshot_id)
    member_history = _score_history(connection, snapshot_id, dataset_version=None)
    return {
        "status": "unverified_historical_aggregate",
        "cohort": "legacy",
        "item_count": item_count,
        "snapshot_id": snapshot_id,
        "binding_status": {
            "prediction_to_image_hash": "unavailable_in_historical_records",
            "prediction_to_frozen_answer_hash": "bound_to_answer_pair_digest_only_for_matching_dataset_version",
            "judgment_to_answer_hash": "unavailable_in_historical_records",
            "scoring_version": "unavailable_in_historical_records",
            "current_compatible_prediction_rows": 0,
            "current_compatible_judgment_rows": 0,
        },
        "snapshot_dataset_version_history": {
            "status": "legacy_dataset_version_bound_but_not_image_or_answer_bound",
            "dataset_version": snapshot_id,
            "answer_pair_digest": "verified_against_legacy_snapshot_id",
            "model_counts": snapshot_history["models"],
        },
        "cross_version_member_history": {
            "status": "unverified_history_for_items_in_legacy_membership",
            "model_counts": member_history["models"],
            "dataset_version_breakdown": member_history["dataset_version_breakdown"],
        },
    }


def _legacy_items(source_root: Path, rows: list[sqlite3.Row], snapshot_id: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    pair_digest = hashlib.sha256()
    for row in sorted(rows, key=lambda item: str(item["post_id"])):
        answer = row["explanation"]
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError(f"legacy item has no ground-truth explanation: {row['post_id']}")
        pair_digest.update(str(row["post_id"]).encode("utf-8"))
        pair_digest.update(answer.encode("utf-8"))
    computed_snapshot_id = pair_digest.hexdigest()[:16]
    if computed_snapshot_id != snapshot_id:
        raise ValueError(
            "current legacy answers no longer match the historical snapshot membership hash "
            f"(expected {snapshot_id}, computed {computed_snapshot_id})"
        )
    items: list[dict[str, Any]] = []
    images: dict[str, Any] = {}
    for row in rows:
        post_id = str(row["post_id"])
        answer = row["explanation"]
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError(f"legacy item has no ground-truth explanation: {post_id}")
        raw_path = str(row["local_image_path"] or "")
        image = _resolve_image(source_root, raw_path)
        if row["review_status"] not in (None, "validated"):
            raise ValueError(f"legacy snapshot member is no longer validated: {post_id}")
        items.append({
            "post_id": post_id,
            "title": str(row["title"] or ""),
            "subreddit": str(row["subreddit"] or ""),
            "ground_truth": answer,
            "image_path": raw_path,
            "cohort": "legacy",
            "exposure": "exposed",
            "admission_origin": "legacy_human_validated",
            "policy_version": POLICY_VERSION,
            "answer_readiness": "unknown",
            "source_support": "unknown",
            "content_status": "unknown",
            "suitability": "unknown",
            "duplicate_status": "unknown",
            "rights_status": "mixed_rights",
            "answer_provenance": {
                "exposure_basis": "published legacy benchmark and known evaluation history; no inference about model training exposure",
                "legacy_snapshot_id": snapshot_id,
                "legacy_answer_hash_sha256": sha256_bytes(answer.encode("utf-8")),
                "historical_actor": "unknown",
                "admission_origin_basis": "published legacy human-validated cohort; not inferred from current reviews.status alone",
                "legacy_image_hash_sha256": None,
                "current_image_sha256_unverified_historical": sha256_file(image),
                "historical_answer_event": "unavailable",
                "historical_image_binding": "unavailable",
                "note": "The image hash is for current source bytes only and does not establish historical prediction input.",
            },
        })
        images[post_id] = {
            "source_image_path": raw_path,
            "current_image_sha256": sha256_file(image),
            "historical_image_sha256": None,
            "source_bytes_exist": True,
        }
    return items, images


def _development_holds(source_root: Path, connection: sqlite3.Connection, ready: dict[str, list[dict[str, Any]]], targeted: dict[str, Any], fresh: dict[str, Any], pilot: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    entries = targeted["full_18_identity_availability_ledger"]
    ids = [str(entry["post_id"]) for entry in entries]
    if len(ids) != 18 or len(set(ids)) != len(ids):
        raise ValueError("the frozen #26/#27 inventory must have 18 unique identities")
    rows = connection.execute(
        f"""SELECT m.post_id, m.title, m.subreddit, m.local_image_path, gt.explanation
            FROM memes m LEFT JOIN ground_truths gt ON gt.post_id=m.post_id
            WHERE m.post_id IN ({','.join('?' for _ in ids)})""",
        ids,
    ).fetchall()
    db_rows = {str(row["post_id"]): row for row in rows}
    if set(db_rows) != set(ids):
        raise ValueError("one or more #26/#27 identities are absent from source database")
    audit_by_id = {
        str(case.get("post_id") or case.get("case_id")): case
        for case in _read_json(source_root / "data/curation/fresh-human-audit-feedback-v1/cases.json")
    }
    holds: list[dict[str, Any]] = []
    for entry in entries:
        post_id = str(entry["post_id"])
        row = db_rows[post_id]
        status = str(entry.get("answer_availability_status", "unresolved"))
        blockers: list[dict[str, str]] = []
        overlap = status == "unresolved_overlap_hold"
        if overlap:
            blockers.append({"gate": "duplicate_status", "status": "hold", "basis": "unchanged family/exposure retrieval hold; not a confirmed duplicate"})
        elif status == "repair_still_needed":
            blockers.append({"gate": "answer_readiness", "status": "repair", "basis": "saved human answer judgment requires repair"})
        elif status == "unresolved":
            blockers.append({"gate": "answer_readiness", "status": "unclear", "basis": "no accepted human-ready answer version is recorded"})
        if not ready.get(post_id) and status not in {"unresolved_overlap_hold", "repair_still_needed", "unresolved"}:
            blockers.append({"gate": "answer_readiness", "status": "unknown", "basis": "no exact ready answer version is established"})
        for gate in ("source_support", "content_status", "suitability"):
            blockers.append({"gate": gate, "status": "unknown", "basis": "not independently adjudicated for this release"})
        if not overlap:
            blockers.append({"gate": "duplicate_status", "status": "unknown", "basis": "screened non-overlap identities have no independent duplicate clearance for this release"})
        current_path = str(row["local_image_path"] or "")
        current_hash = None
        if current_path:
            image = _resolve_image(source_root, current_path)
            current_hash = sha256_file(image)
        versions = list(ready.get(post_id, []))
        if not versions and row["explanation"]:
            # Keep an exact private copy of the existing answer for audit, while
            # clearly separating its historical human label from an approved version.
            versions.append({
                "text": str(row["explanation"]),
                "text_sha256": sha256_bytes(str(row["explanation"]).encode("utf-8")),
                "source": "current_database_original",
                "readiness": entry.get("prior_original_judgment", status),
                "human_event_id": None,
                "snapshot_id": None,
            })
        human_case = audit_by_id.get(post_id, {})
        holds.append({
            "post_id": post_id,
            "candidate_kind": "fresh_human_audit_pool",
            "status": "held",
            "answer_availability_status": status,
            "original_screening": entry.get("original_screening"),
            "prior_original_judgment": entry.get("prior_original_judgment"),
            "current_image_sha256": current_hash,
            "blockers": blockers,
            "answer_versions": versions,
            "source_feedback_event_ids": [
                str(value) for value in [human_case.get("human_event_id")] if value
            ],
        })

    pilot_outcomes = pilot.get("outcomes", [])
    if len(pilot_outcomes) != 100 or len({str(row.get("post_id")) for row in pilot_outcomes}) != 100:
        raise ValueError("frozen June 20-26 pilot must contain 100 unique outcomes")
    pilot_holds: list[dict[str, Any]] = []
    for outcome in sorted(pilot_outcomes, key=lambda item: str(item["post_id"])):
        components = outcome.get("components", {})
        blockers: list[dict[str, str]] = []
        for gate in ("answer", "content", "suitability", "duplicates"):
            component = components.get(gate, {})
            decision = str(component.get("decision", "unknown"))
            if decision != "pass":
                blockers.append({"gate": gate, "status": decision, "basis": ",".join(component.get("reason_codes", [])) or "component did not establish pass"})
        blockers.append({"gate": "admission_origin", "status": "hold", "basis": "historical pilot automation is preserved as development evidence; no qualified release admission is asserted"})
        pilot_holds.append({
            "post_id": str(outcome["post_id"]),
            "candidate_kind": "june_20_26_automatic_pilot",
            "status": "held",
            "historical_decision": str(outcome.get("decision", "unknown")),
            "human_validated": bool(outcome.get("human_validated", False)),
            "components": components,
            "reason_codes": outcome.get("reason_codes", []),
            "input_sha256": outcome.get("input_sha256"),
            "source_admission_experiment_id": outcome.get("provenance", {}).get("source_admission_experiment_id"),
            "blockers": blockers,
        })
    return holds + pilot_holds, {
        "fresh_human_audit_pool": {"items": len(holds), "ready_private_versions": sum(bool(ready.get(str(row["post_id"]))) for row in holds)},
        "june_20_26_automatic_pilot": {
            "items": len(pilot_holds),
            "outcome_counts": dict(Counter(str(o.get("decision", "unknown")) for o in pilot_outcomes)),
            "human_validated_items": sum(bool(o.get("human_validated")) for o in pilot_outcomes),
            "version": pilot.get("component_versions"),
            "report_version": pilot.get("version"),
        },
    }


def prepare(source_root: Path, output: Path, name: str | None = None) -> dict[str, Any]:
    """Write selection/evidence/held-ledger/provenance files into a new directory."""
    source_root = source_root.expanduser().resolve(strict=True)
    output = output.expanduser().absolute()
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"output already exists: {output}")
    if output == source_root or source_root in output.parents:
        # Output under source root is allowed only under a new data/export child,
        # preventing accidental writes into the private source root's other files.
        allowed = output.parent == source_root / "data" or output.parent == source_root / "export"
        if not allowed:
            raise ValueError("output under source root must be a direct child of data/ or export/")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", name or "basedbench-release-candidate-v1"):
        raise ValueError("name must contain 1-80 safe ASCII letters, digits, dot, underscore, or dash")
    db_path = source_root / "data/basedbench.db"
    if not db_path.is_file() or db_path.is_symlink():
        raise FileNotFoundError(f"read-only source database not found: {db_path}")
    fresh_path = source_root / FRESH_ANALYSIS
    target_path = source_root / TARGETED_ANALYSIS
    pilot_path = source_root / PILOT_REPORT
    for path in (fresh_path, target_path, pilot_path):
        if not path.is_file() or path.is_symlink():
            raise FileNotFoundError(f"required private source artifact is missing or symlinked: {path}")
    fresh = _read_json(fresh_path)
    targeted = _read_json(target_path)
    pilot = _read_json(pilot_path)
    if len(targeted.get("full_18_identity_availability_ledger", [])) != 18:
        raise ValueError("#26/#27 availability analysis must describe the fixed 18-item pool")
    ready = _ready_versions(source_root, fresh, targeted)

    connection = _connect_readonly(db_path)
    try:
        _required_tables(connection)
        snapshot = connection.execute(
            "SELECT snapshot_id, meme_count FROM snapshots WHERE name = ? ORDER BY created_at DESC LIMIT 1",
            (LEGACY_SNAPSHOT_NAME,),
        ).fetchone()
        if snapshot is None:
            raise ValueError(f"legacy snapshot not found: {LEGACY_SNAPSHOT_NAME}")
        snapshot_id = str(snapshot["snapshot_id"])
        rows = _legacy_rows(connection, snapshot_id)
        if len(rows) != int(snapshot["meme_count"]) or len(rows) != 519:
            raise ValueError(f"legacy snapshot must contain 519 resolvable rows; found {len(rows)}")
        legacy_items, image_inventory = _legacy_items(source_root, rows, snapshot_id)
        holds, development_inventory = _development_holds(source_root, connection, ready, targeted, fresh, pilot)
        historical = _historical_summary(connection, snapshot_id)
        reviews = connection.execute(
            """SELECT status, COUNT(*) n FROM reviews
               WHERE post_id IN (SELECT post_id FROM snapshot_memes WHERE snapshot_id = ?)
               GROUP BY status ORDER BY status""",
            (snapshot_id,),
        ).fetchall()
        review_counts = {str(row["status"]): int(row["n"]) for row in reviews}
        prompt_rows = connection.execute(
            """SELECT model, prompt_version, role, COUNT(*) AS calls
               FROM llm_calls
               WHERE post_id IN (SELECT post_id FROM snapshot_memes WHERE snapshot_id = ?)
                 AND role IN ('prediction', 'judge')
               GROUP BY model, prompt_version, role
               ORDER BY role, model, prompt_version""",
            (snapshot_id,),
        ).fetchall()
        prompt_inventory = [dict(row) for row in prompt_rows]
        image_binding_rows = connection.execute(
            """SELECT lc.role, COUNT(*) AS calls,
                      SUM(CASE WHEN lc.image_path IS NOT NULL AND lc.image_path <> '' THEN 1 ELSE 0 END) AS calls_with_image_path,
                      SUM(CASE WHEN lc.image_path = m.local_image_path THEN 1 ELSE 0 END) AS paths_matching_current
               FROM llm_calls lc JOIN snapshot_memes sm ON sm.post_id=lc.post_id AND sm.snapshot_id=?
               JOIN memes m ON m.post_id=lc.post_id
               WHERE lc.role IN ('prediction', 'judge')
               GROUP BY lc.role ORDER BY lc.role""",
            (snapshot_id,),
        ).fetchall()
        binding_schema = {
            "predictions_columns": sorted(_table_columns(connection, "predictions")),
            "judgments_columns": sorted(_table_columns(connection, "judgments")),
            "llm_calls_columns": sorted(_table_columns(connection, "llm_calls")),
            "missing_prediction_image_sha256": "image_sha256" not in _table_columns(connection, "predictions"),
            "missing_judgment_answer_hash": "answer_sha256" not in _table_columns(connection, "judgments"),
            "missing_judgment_prediction_hash": "prediction_sha256" not in _table_columns(connection, "judgments"),
            "missing_scoring_version": "scoring_version" not in _table_columns(connection, "judgments"),
            "llm_path_match_counts": [dict(row) for row in image_binding_rows],
        }
    finally:
        connection.close()

    evidence = {
        "schema_version": "basedbench.release-evidence.v1",
        "predictions": [],
        "judgments": [],
        "historical_summary": historical,
    }
    selection = {
        "name": name or "basedbench-release-candidate-v1",
        "description": "Historical legacy cohort with explicitly unknown gates; all newer candidates remain in the private held ledger pending independent clearance.",
        "policy_version": POLICY_VERSION,
        "evaluation": {
            "model_panel": list(MODEL_PANEL),
            "prediction_prompt_id": None,
            "judge_prompt_id": None,
            "scoring_version": "majority-v1",
        },
        "items": legacy_items,
    }
    held_ledger = {
        "schema_version": "basedbench.release-held.v1",
        "policy_version": POLICY_VERSION,
        "rights_policy_status": "mixed_rights",
        "candidate_item_counts": development_inventory,
        "held_items": sorted(holds, key=lambda item: (item["candidate_kind"], item["post_id"])),
    }
    provenance = {
        "schema_version": "basedbench.release-provenance-inventory.v1",
        "legacy_snapshot": {
            "snapshot_name": LEGACY_SNAPSHOT_NAME,
            "snapshot_id": snapshot_id,
            "expected_items": 519,
            "selected_items": len(legacy_items),
            "review_status_counts": review_counts,
            "current_images": {
                "present": len(image_inventory),
                "sha256_by_post_id": {post_id: row["current_image_sha256"] for post_id, row in sorted(image_inventory.items())},
                "historical_image_hashes_available": 0,
            },
        },
        "development_inventory": development_inventory,
        "historical_panel": {
            "models": list(MODEL_PANEL),
            "current_compatible_predictions": 0,
            "current_compatible_judgments": 0,
            "unverified_summary_in_evidence": True,
            "prompt_version_call_counts": prompt_inventory,
        },
        "inputs": {
            str(path.relative_to(source_root)): {"sha256": sha256_file(path), "bytes": path.stat().st_size}
            for path in (
                db_path, fresh_path, target_path, pilot_path,
                source_root / "data/curation/fresh-human-audit-feedback-v1/manifest.json",
                source_root / "data/curation/fresh-human-audit-feedback-v1/cases.json",
                source_root / "data/curation/fresh-human-audit-feedback-v1/human-feedback.json",
                source_root / "data/curation/fresh-human-audit-feedback-v1/events.jsonl",
                source_root / "data/curation/targeted-corrections-feedback-v1/manifest.json",
                source_root / "data/curation/targeted-corrections-feedback-v1/cases.json",
                source_root / "data/curation/targeted-corrections-feedback-v1/human-feedback.json",
                source_root / "data/curation/targeted-corrections-feedback-v1/events.jsonl",
            )
        },
        "sqlite_files": {
            "database_sha256": sha256_file(db_path),
            "wal_present": db_path.with_name(db_path.name + "-wal").is_file(),
            "wal_sha256": sha256_file(db_path.with_name(db_path.name + "-wal")) if db_path.with_name(db_path.name + "-wal").is_file() else None,
            "consistent_read_transaction": True,
        },
        "stored_binding_audit": binding_schema,
        "read_only_database": True,
        "selection_policy": {
            "legacy_unknown_gates_are_grandfathered": True,
            "newer_items_require_all_independent_clearances": True,
            "no_model_calls_or_automatic_promotion": True,
            "rights_policy_status": "mixed_rights",
            "source_answer_hash_algorithm": "SHA256(canonical_json(answer_text))",
            "frozen_release_answer_hash_algorithm": "SHA256(exact UTF-8 answer bytes)",
        },
    }

    # Stage in memory first, then create the new directory once inputs and schemas
    # have validated. A failed write removes its partial directory.
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{output.name}.staging-", dir=output.parent))
    try:
        _write_json(stage / "selection.json", selection)
        _write_json(stage / "evidence.json", evidence)
        _write_json(stage / "held-ledger.json", held_ledger)
        _write_json(stage / "provenance-inventory.json", provenance)
        if output.exists() or output.is_symlink():
            raise FileExistsError(f"output already exists: {output}")
        os.rename(stage, output)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return {
        "output": str(output),
        "selected_legacy_items": len(legacy_items),
        "held_development_items": len(holds),
        "ready_private_versions": sum(bool(entries) for entries in ready.values()),
        "current_compatible_predictions": 0,
        "model_panel": MODEL_PANEL,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="new local directory; existing paths are refused")
    parser.add_argument("--name", help="safe candidate name; defaults to basedbench-release-candidate-v1")
    args = parser.parse_args()
    print(json.dumps(prepare(args.source_root, args.output, args.name), sort_keys=True))


if __name__ == "__main__":
    main()
