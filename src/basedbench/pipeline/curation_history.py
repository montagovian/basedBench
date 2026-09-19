"""Track prior use across immutable curation corpus versions.

A per-run disjoint split does not imply that its reserved examples were never
used in a previous run. This audit reports that distinction without reshuffling.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from basedbench.pipeline.curation_corpus import digest, file_hash, load_corpus


def split_digest(rows: list[dict]) -> str:
    return digest([[r["post_id"], r["group_id"], r["split"]] for r in rows])


def audit_history(corpus: Path, history: Path, output: Path) -> dict:
    """Verify declared prior runs against their corpora and freeze an exposure audit.

    History is a JSON list of {corpus, run} paths relative to the history file.
    This can establish absence of exposure only within the declared history.
    """
    if output.exists():
        raise FileExistsError(f"Refusing to replace history audit: {output}")
    manifest, rows = load_corpus(corpus)
    entries = json.loads(history.read_text())
    if not isinstance(entries, list) or not entries:
        raise ValueError("History must contain at least one {corpus, run} entry")
    used: dict[str, set[str]] = defaultdict(set)
    verified = []
    for entry in entries:
        old_corpus = history.parent / entry["corpus"]
        run = history.parent / entry["run"]
        old_manifest, old_rows = load_corpus(old_corpus)
        report = json.loads((run / "report.json").read_text())
        if report["corpus_id"] != old_manifest["corpus_id"]:
            raise ValueError("Historical run/corpus mismatch")
        is_llm = report.get("schema_version") == "curation-llm-v1"
        allowed_splits = {"development", "calibration"} if is_llm else {"calibration"}
        if report["evaluation_split"] not in allowed_splits or report["final_test_evaluated"] is not False:
            raise ValueError("Unsupported historical run; exposure must be checked explicitly")
        development = [r["post_id"] for r in old_rows if r["split"] == "development"]
        eligible = [r["post_id"] for r in old_rows if r["split"] == report["evaluation_split"]]
        training = report["training_ids"] if is_llm else development
        evaluation = report["evaluation_ids"] if is_llm else eligible
        references = report["reference_ids"] if is_llm else []
        if not set(training + references) <= set(development) or not set(evaluation) <= set(eligible):
            raise ValueError("Historical run exposed examples outside its declared allowed split")
        if any(len(ids) != len(set(ids)) for ids in (training, evaluation, references)):
            raise ValueError("Historical run has duplicate membership IDs")
        if set(training + references) & set(evaluation):
            raise ValueError("Historical learning/reference examples overlap its evaluation")
        if is_llm and digest(references) != report["reference_ids_sha256"]:
            raise ValueError("Historical reference membership hash mismatch")
        if digest(training) != report["training_ids_sha256"] or digest(evaluation) != report["evaluation_ids_sha256"]:
            raise ValueError("Historical run membership does not match its corpus")
        if file_hash(run / "decisions.jsonl") != report["decisions_sha256"]:
            raise ValueError("Historical predictions failed integrity check")
        decisions = [json.loads(line) for line in (run / "decisions.jsonl").read_text().splitlines()]
        if {d["post_id"] for d in decisions} != set(evaluation):
            raise ValueError("Historical prediction IDs differ from reported evaluation IDs")
        inputs = {r["post_id"]: r["input_sha256"] for r in old_rows}
        if any(d["input_sha256"] != inputs[d["post_id"]] for d in decisions):
            raise ValueError("Historical predictions refer to different inputs")
        for pid in training:
            used[pid].add("training")
        for pid in evaluation:
            used[pid].add("evaluation")
        for pid in references:
            used[pid].add("reference")
        verified.append({"corpus_id": old_manifest["corpus_id"], "report_sha256": file_hash(run / "report.json"),
                         "training_ids": training, "evaluation_ids": evaluation, "reference_ids": references})

    exposed_groups = {r["group_id"] for r in rows if used[r["post_id"]]}
    reserved = [r for r in rows if r["split"] == "test"]
    details = [{"post_id": r["post_id"], "group_id": r["group_id"],
                "prior_uses": sorted(used[r["post_id"]]),
                "group_exposed": r["group_id"] in exposed_groups} for r in reserved]
    report = {
        "schema_version": "curation-history-v1", "corpus_id": manifest["corpus_id"],
        "split_sha256": split_digest(rows), "verified_runs": verified,
        "reserved_examples": details,
        "counts": {"reserved": len(reserved),
                   "previously_trained": sum("training" in d["prior_uses"] for d in details),
                   "previously_scored": sum("evaluation" in d["prior_uses"] for d in details),
                   "previously_used_as_reference": sum("reference" in d["prior_uses"] for d in details),
                   "exposed_including_group": sum(d["group_exposed"] for d in details),
                   "unexposed_in_declared_history": sum(not d["group_exposed"] for d in details)},
        "status": "exploratory_only",
        "limitations": [
            "Absence of exposure is relative to the supplied history, not proof of complete historical isolation.",
            "Semantic joke-family grouping and label provenance remain provisional.",
            "The remaining unexposed subset is not a qualified final acceptance test.",
        ],
    }
    report["audit_id"] = digest(report)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation also prevents a concurrent run from replacing this audit.
    with output.open("x") as handle:
        handle.write(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    return report


def history_status(audit_path: Path | None, manifest: dict, rows: list[dict]) -> dict:
    if audit_path is None:
        return {"status": "unaudited", "note": "No cross-run exposure audit supplied; do not call the reserved set untouched."}
    audit = json.loads(audit_path.read_text())
    if audit.get("schema_version") != "curation-history-v1" or audit.get("audit_id") != digest({k: v for k, v in audit.items() if k != "audit_id"}):
        raise ValueError("Invalid history audit hash/version")
    if audit["corpus_id"] != manifest["corpus_id"] or audit["split_sha256"] != split_digest(rows):
        raise ValueError("History audit does not match this frozen corpus/split")
    return {"status": audit["status"], "audit_id": audit["audit_id"], "counts": audit["counts"],
            "note": "Historical comparisons only; no claim of independent final-test performance."}
