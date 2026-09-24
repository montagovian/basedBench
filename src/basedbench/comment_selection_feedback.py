"""Evaluate private explicit-comment anchors against frozen arm outcomes.

This diagnostic deliberately emits separate counters for membership, initial
visibility, exclusion and order. It does not compute a combined accuracy score.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any

ARMS = ("baseline", "pointwise", "pairwise")
POSITIVE = "positive_retention"
NEGATIVE = "negative_exclusion"
ORDERING = "ordering_negative"
AMBIGUOUS = "ambiguous_exclusion"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _verify_provenance(anchors: dict) -> dict[str, str]:
    """Verify frozen source hashes and that every anchor matches its source."""
    paths = anchors.get("source_paths")
    if not isinstance(paths, dict) or set(paths) != set(anchors["sources"]):
        raise ValueError("Anchor inventory must map every source hash to a source path")
    resolved = {name: Path(path) for name, path in paths.items()}
    hashes = {}
    for name, path in resolved.items():
        actual = _sha256(path)
        if actual != anchors["sources"][name]:
            raise ValueError(f"Frozen source hash mismatch: {name}")
        hashes[name] = actual
    event_path = resolved["events.jsonl"]
    events = {row["event_id"]: row for row in
              (json.loads(line) for line in event_path.read_text(encoding="utf-8").splitlines())}
    review_cases = _load_json(resolved["review-cases.json"])
    cases = _load_json(resolved["cases.json"])
    reviewed_case = {case["review_id"]: (case["case_id"], case["family_id"])
                     for case in review_cases}
    full_case = {case["case_id"]: case for case in cases}
    for anchor in anchors["anchors"]:
        event = events.get(anchor.get("event_id"))
        if not event or event.get("kind") != "feedback":
            raise ValueError("Anchor event is missing or is not a feedback event")
        if anchor.get("quote") and anchor["quote"] not in event.get("note", ""):
            raise ValueError("Anchor quote is not an exact substring of its frozen event note")
        if anchor["kind"] == AMBIGUOUS:
            continue
        if reviewed_case.get(event.get("review_id")) != (
            anchor.get("case_id"), anchor.get("family_id")
        ):
            raise ValueError("Anchor case does not match the event's reviewed case")
        case = full_case.get(anchor["case_id"])
        if not case:
            raise ValueError("Anchor case or family does not match the frozen source case")
        if not any(comment.get("id") == anchor.get("comment_id") for comment in case.get("comments", [])):
            raise ValueError("Anchor comment ID is absent from the exact source case")
    return hashes


def _validate(anchors: dict, outcomes: list[dict]) -> None:
    if anchors.get("schema_version") != "comment-selection-feedback-anchors-v1":
        raise ValueError("Unsupported anchor schema")
    if not isinstance(anchors.get("sources"), dict) or not isinstance(anchors.get("anchors"), list):
        raise ValueError("Anchor inventory must include sources and anchors")
    seen = set()
    allowed = {POSITIVE, NEGATIVE, ORDERING, AMBIGUOUS}
    for anchor in anchors["anchors"]:
        if anchor.get("kind") not in allowed:
            raise ValueError("Unknown anchor kind")
        if anchor.get("kind") != AMBIGUOUS and not all(
            anchor.get(key) for key in ("case_id", "family_id", "comment_id", "event_id", "quote")
        ):
            raise ValueError("Actionable anchors require case, family, comment and provenance")
        if anchor.get("kind") == AMBIGUOUS and not anchor.get("event_id"):
            raise ValueError("Ambiguous anchors require source event provenance")
        key = (anchor.get("case_id"), anchor.get("comment_id"), anchor.get("kind"))
        if key in seen:
            raise ValueError("Duplicate anchor")
        seen.add(key)
    case_ids = set()
    for row in outcomes:
        if not {"case_id", "family_id", "status", "lists"}.issubset(row):
            raise ValueError("Each outcome requires case_id, family_id, status, and lists")
        if row["case_id"] in case_ids:
            raise ValueError("Duplicate outcome case")
        case_ids.add(row["case_id"])
        if row["status"] not in {"completed", "abstained"}:
            raise ValueError("Outcome status must be completed or abstained")
        if set(row["lists"]) != set(ARMS):
            raise ValueError("Every outcome must include all three arms")
        for arm in ARMS:
            lists = row["lists"][arm]
            if lists.get("status") not in {"completed", "unavailable"}:
                raise ValueError(f"{arm} list status must be completed or unavailable")
            if lists["status"] == "unavailable":
                continue
            if not {"selected_ids", "retained_ids", "excluded_ids"}.issubset(lists):
                raise ValueError(f"{arm} lists require selected_ids, retained_ids, excluded_ids")
            selected, retained, excluded = (lists[name] for name in
                                            ("selected_ids", "retained_ids", "excluded_ids"))
            if len(selected) > 3 or retained[:len(selected)] != selected:
                raise ValueError(f"{arm} selected_ids must be the first three retained IDs")
            if (len(set(selected)) != len(selected) or len(set(retained)) != len(retained)
                    or len(set(excluded)) != len(excluded)):
                raise ValueError(f"{arm} comment ID lists must not contain duplicates")
            if set(excluded) & (set(selected) | set(retained)):
                raise ValueError(f"{arm} excluded IDs must be disjoint from selected and retained IDs")
            for name in ("selected_ids", "retained_ids", "excluded_ids"):
                values = lists[name]
                if not isinstance(values, list) or any(not isinstance(v, str) for v in values):
                    raise ValueError(f"{arm}.{name} must be a list of comment IDs")


def evaluate(anchors: dict, outcomes: list[dict], *, anchors_sha256: str | None = None,
             verify_sources: bool = False) -> dict:
    """Return independent per-arm anchor counts and actionable failures.

    Positive anchors are required in the full retained list; their top-three
    presence is reported separately. Negative anchors are measured in the top
    three and against both retained and selected lists. `preferred_ids` plus
    `badfirst_id` supports future first-read comparisons; `must_not_be_first`
    handles an explicit incomplete-first constraint.
    """
    _validate(anchors, outcomes)
    verified_sources = _verify_provenance(anchors) if verify_sources else dict(anchors["sources"])
    anchors_by_case: dict[str, list[dict]] = {}
    family_by_case = {}
    for anchor in anchors["anchors"]:
        if anchor.get("case_id"):
            anchors_by_case.setdefault(anchor["case_id"], []).append(anchor)
            prior = family_by_case.setdefault(anchor["case_id"], anchor.get("family_id"))
            if prior != anchor.get("family_id"):
                raise ValueError("Anchors for a case disagree on family_id")
    rows_by_case = {row["case_id"]: row for row in outcomes}
    for case_id, row in rows_by_case.items():
        if case_id in family_by_case and row["family_id"] != family_by_case[case_id]:
            raise ValueError("Outcome family_id does not match its private anchors")
    results = {}
    for arm in ARMS:
        totals = Counter()
        totals["unavailable_cases"] = 0
        failures = []
        missing_anchor_cases = sorted(set(anchors_by_case) - set(rows_by_case))
        for case_id, row in rows_by_case.items():
            values = row["lists"][arm]
            if values["status"] != "completed":
                totals["unavailable_cases"] += 1
                continue
            selected = values["selected_ids"]
            retained = values["retained_ids"]
            excluded = values["excluded_ids"]
            first_three = selected[:3]
            for anchor in anchors_by_case.get(case_id, []):
                cid = anchor.get("comment_id")
                kind = anchor["kind"]
                detail = {"case_id": case_id, "comment_id": cid, "kind": kind,
                          "event_id": anchor.get("event_id"), "quote": anchor.get("quote")}
                if kind == POSITIVE:
                    totals["positive_retention_total"] += 1
                    kept = cid in retained
                    totals["positive_retention_met"] += int(kept)
                    if not kept:
                        failures.append({**detail, "check": "positive_retention"})
                    totals["positive_top3_total"] += 1
                    top3 = cid in first_three
                    totals["positive_top3_met"] += int(top3)
                    if not top3:
                        failures.append({**detail, "check": "positive_top3"})
                elif kind == NEGATIVE:
                    totals["negative_top3_total"] += 1
                    clean_top = cid not in first_three
                    totals["negative_top3_met"] += int(clean_top)
                    if not clean_top:
                        failures.append({**detail, "check": "negative_top3"})
                    totals["negative_exclusion_total"] += 1
                    clean_exclusion = cid in excluded and cid not in retained and cid not in selected
                    totals["negative_exclusion_met"] += int(clean_exclusion)
                    if not clean_exclusion:
                        failures.append({**detail, "check": "negative_exclusion"})
                elif kind == ORDERING:
                    totals["ordering_total"] += 1
                    must_not_first = anchor.get("constraints", {}).get("must_not_be_first", False)
                    preferred = anchor.get("constraints", {}).get("preferred_ids", [])
                    badfirst = anchor.get("constraints", {}).get("badfirst_id", cid)
                    if must_not_first:
                        met = not selected or selected[0] != cid
                    elif preferred and badfirst:
                        positions = {item: i for i, item in enumerate(selected)}
                        met = all(item in positions and badfirst in positions and
                                  positions[item] < positions[badfirst] for item in preferred)
                    else:
                        met = None
                    if met is None:
                        totals["ordering_unscorable"] += 1
                    else:
                        totals["ordering_scored"] += 1
                        totals["ordering_met"] += int(met)
                        if not met:
                            failures.append({**detail, "check": "ordering"})
        results[arm] = {**dict(totals), "missing_anchor_cases": missing_anchor_cases,
                        "failures": failures}
    ambiguous = [a for a in anchors["anchors"] if a["kind"] == AMBIGUOUS]
    return {
        "schema_version": "comment-selection-feedback-results-v1",
        "provenance": {
            "anchors_sha256": anchors_sha256,
            "source_sha256": verified_sources,
            "outcome_cases": len(outcomes),
            "anchor_count": len(anchors["anchors"]),
            "ambiguous_anchor_count": len(ambiguous),
            "ambiguous_events": [a["event_id"] for a in ambiguous],
        },
        "arms": results,
        "quote_fidelity": {
            "verified_against": "frozen source quote stored per anchor",
            "anchor_quotes_present": sum(bool(a.get("quote")) for a in anchors["anchors"]),
            "anchor_quotes_total": len(anchors["anchors"]),
            "note": "Outcome lists contain IDs only; fidelity is checked in the frozen inventory provenance, not inferred from model output.",
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--anchors", required=True, type=Path)
    parser.add_argument("--outcomes", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    anchors = _load_json(args.anchors)
    outcomes = _load_json(args.outcomes)
    result = evaluate(anchors, outcomes, anchors_sha256=_sha256(args.anchors), verify_sources=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
