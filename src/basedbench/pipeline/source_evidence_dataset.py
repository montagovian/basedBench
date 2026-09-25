"""Reconstruct exact, human-judged answer versions from frozen curation packets.

Admission, model findings and assistant inspection are deliberately outside this
dataset. The packet input hash and the model-facing answer input hash have
different scopes; both are verified and retained in provenance.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re

from basedbench.pipeline.calibrated_eval import image_error
from basedbench.pipeline.curation_corpus import digest, file_hash, write_json

VERSION = "source-evidence-dataset-v1"
SNAPSHOTS = (
    "explanation-calibration-feedback-v1",
    "materiality-boundary-feedback-v1",
    "fresh-human-audit-v2",
    "targeted-corrections-feedback-v1",
    "review-v1",
)
PACKETS = {
    "explanation-calibration-feedback-v1": "explanation-calibration-v1",
    "materiality-boundary-feedback-v1": "materiality-boundary-v1",
}
QUALITIES = {"ready", "repair", "unclear"}


def _json(path: Path):
    return json.loads(path.read_text())


def _verify_manifest(directory: Path, *, identity: str | None = None) -> dict:
    manifest_path = directory / "manifest.json"
    manifest = _json(manifest_path)
    if identity and digest({k: v for k, v in manifest.items() if k != identity}) != manifest[identity]:
        raise ValueError(f"Manifest identity changed: {manifest_path}")
    for name, expected in manifest["files"].items():
        relative = Path(name)
        path = directory / relative
        if (relative.is_absolute() or ".." in relative.parts or path.is_symlink()
                or not path.resolve().is_relative_to(directory.resolve())
                or not isinstance(expected, str) or not re.fullmatch("[a-f0-9]{64}", expected)
                or not path.is_file() or file_hash(path) != expected):
            raise ValueError(f"Source file changed: {path}")
    return manifest


def _events(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _triplet(explanation: str, packet: dict) -> dict:
    if not isinstance(explanation, str) or not explanation.strip():
        raise ValueError("Labeled answer text is missing")
    inp = packet["input"]
    return {"explanation": explanation, "comment_evidence": inp["comment_evidence"],
            "image_sha256": inp["image_sha256"]}


def _answer_slots(packet: dict) -> list[dict]:
    inp = packet["input"]
    answers = inp.get("answers")
    if answers is None:
        return [{"source": "original", "text": inp["explanation"]}]
    if not isinstance(answers, list) or not answers:
        raise ValueError("Empty answer slots")
    return answers


def _quality_for(event: dict, slot: int, snapshot: str) -> str | None:
    fields = event.get("fields", {})
    if snapshot == "review-v1":
        if slot != 0:
            return None
        verdict = fields.get("ground_truth")
        if verdict is None:
            return None
        if verdict not in {"ready", "repair", "uncertain"}:
            raise ValueError(f"Unknown ground-truth quality {verdict!r}")
        return "unclear" if verdict == "uncertain" else verdict
    return fields.get(("quality_a", "quality_b")[slot]) if slot < 2 else None


def _asset(snapshot: Path, packet: dict) -> Path | None:
    sha = packet["input"]["image_sha256"]
    for folder in ("assets", "images"):
        path = snapshot / folder / sha
        if path.is_file():
            if file_hash(path) != sha:
                raise ValueError(f"Image identity changed: {path}")
            return path.resolve()
    return None


def _append_case(rows: dict, packet: dict, answer: dict, event: dict, source: dict,
                 asset: Path | None, quality: str):
    if quality not in QUALITIES:
        raise ValueError(f"Unknown human quality {quality!r}")
    if digest(answer["text"]) != source["answer_text_sha256"]:
        raise ValueError("Answer text hash changed")
    inp = _triplet(answer["text"], packet)
    sha = digest(inp)
    pid = packet["post_id"]
    key = (pid, sha)
    source = {**source, "quality": quality, "fields": event.get("fields", {}),
              "notes": event.get("notes", ""), "recorded_at": event.get("recorded_at"),
              "base_revision": event.get("base_revision")}
    if key not in rows:
        rows[key] = {"case_id": f"{pid}-{sha[:16]}", "post_id": pid, "input": inp,
                     "input_sha256": sha, "image_path": None, "image_error": None,
                     "group_id": packet.get("group_id", pid),
                     "family_weight": packet.get("family_weight", 1.0),
                     "stratum": packet.get("stratum"),
                     "human": {"quality": "unclear", "events": []},
                     "provenance": {"sources": [], "answer_versions": [], "review_selections": []}}
    row = rows[key]
    if row["input"] != inp:
        raise ValueError("Input digest collision")
    if row["group_id"] != packet.get("group_id", pid):
        raise ValueError("Conflicting family assignment")
    if asset:
        if row["image_path"] and row["image_path"] != str(asset):
            # Identical verified bytes across source packets; preserve first path.
            pass
        else:
            row["image_path"] = str(asset)
    row["human"]["events"].append(source)
    row["provenance"]["sources"].append({k: source[k] for k in
        ("snapshot", "manifest_sha256", "cases_sha256", "events_sha256", "event_id", "packet_input_sha256")})
    row["provenance"]["answer_versions"].append({"source": answer["source"],
        "text_sha256": source["answer_text_sha256"], "slot": source["slot"]})
    row["provenance"]["review_selections"].append(source.get("group_metadata") or {
        "snapshot": source["snapshot"], "group_id": packet.get("group_id", pid),
        "family_weight": packet.get("family_weight", 1.0), "stratum": packet.get("stratum"),
        "cases_sha256": source["cases_sha256"]})


def _verify_feedback_groups(source_packets: dict, feedback_packets: dict, directory: Path) -> None:
    """Require later family corrections to have an explicit inspected duplicate pair."""
    inspections = _json(directory / "duplicate-inspection.json")
    inspected_pairs = {frozenset((item["left"], item["right"])) for item in inspections
                       if item.get("relation") == "same_image_and_joke"}
    members: dict[str, set[str]] = defaultdict(set)
    for pid, row in feedback_packets.items():
        members[row["group_id"]].add(pid)
    for pid, row in feedback_packets.items():
        group = row["group_id"]
        if (row.get("case_id") != pid or row.get("stratum") != source_packets[pid].get("stratum")
                or row.get("family_weight") != 1 / len(members[group])):
            raise ValueError("Feedback family metadata changed")
        if group != source_packets[pid].get("group_id", pid):
            if group not in members[group] or frozenset((pid, group)) not in inspected_pairs:
                raise ValueError("Feedback family correction lacks inspected pair")


def _load_snapshot(root: Path, name: str, rows: dict, exclusions: list[dict],
                   source_hashes: dict[str, str]) -> None:
    directory = root / "curation" / name
    manifest = _verify_manifest(directory, identity="snapshot_id" if "feedback-v1" in name else None)
    source_hashes[str(directory / "manifest.json")] = file_hash(directory / "manifest.json")
    if name in PACKETS:
        packet_dir = root / "curation" / PACKETS[name]
        _verify_manifest(packet_dir)
        if file_hash(packet_dir / "manifest.json") != manifest["packet_manifest_sha256"]:
            raise ValueError("Source packet manifest changed")
        source_hashes[str(packet_dir / "manifest.json")] = file_hash(packet_dir / "manifest.json")
        source_list = _json(packet_dir / "cases.json")
        feedback_list = _json(directory / "cases.json")
    else:
        source_list = _json(directory / "cases.json")
        feedback_list = source_list
    source_packets = {p["post_id"]: p for p in source_list}
    feedback_packets = {p["post_id"]: p for p in feedback_list}
    if len(source_packets) != len(source_list) or len(feedback_packets) != len(feedback_list):
        raise ValueError("Duplicate post in source packet")
    if set(source_packets) != set(feedback_packets):
        raise ValueError("Source and feedback post sets differ")
    if name in PACKETS:
        _verify_feedback_groups(source_packets, feedback_packets, directory)
    if name == "targeted-corrections-feedback-v1":
        source_manifest = directory / "source-packet-manifest.json"
        if file_hash(source_manifest) != manifest["source_packet_manifest_sha256"]:
            raise ValueError("Targeted source packet manifest changed")
    events = _events(directory / "events.jsonl")
    by_id = {}
    feedbacks = defaultdict(list)
    superseded = set()
    for event in events:
        pid = event["post_id"]
        if pid not in source_packets or event["input_sha256"] != source_packets[pid]["input_sha256"]:
            raise ValueError(f"Feedback event packet identity changed: {name}/{pid}")
        if event["event_id"] in by_id:
            raise ValueError("Repeated event ID")
        if event["packet_id"] != manifest["packet_id"]:
            raise ValueError("Feedback event packet ID changed")
        if manifest.get("corpus_id") and event["corpus_id"] != manifest["corpus_id"]:
            raise ValueError("Feedback event corpus ID changed")
        if manifest.get("rubric_sha256") and event["rubric_sha256"] != manifest["rubric_sha256"]:
            raise ValueError("Feedback event rubric changed")
        if event.get("base_revision"):
            prior = by_id.get(event["base_revision"])
            if prior is None or prior["post_id"] != pid:
                raise ValueError("Broken event revision chain")
            if prior["kind"] == "feedback":
                superseded.add(prior["event_id"])
        by_id[event["event_id"]] = event
        if event["kind"] == "feedback":
            feedbacks[pid].append(event)
    human_feedback = {}
    feedback_path = directory / "human-feedback.json"
    if feedback_path.exists():
        human_feedback = {h["post_id"]: h for h in _json(feedback_path)}
        if len(human_feedback) != len(_json(feedback_path)):
            raise ValueError("Duplicate feedback summary")
    for pid, packet in source_packets.items():
        if digest(packet["input"]) != packet["input_sha256"]:
            raise ValueError(f"Source packet input changed: {name}/{pid}")
        feedback_packet = feedback_packets.get(pid)
        if feedback_packet is None:
            raise ValueError("Feedback packet missing post")
        case_packet = packet
        if name in PACKETS:
            if digest(feedback_packet["input"]) != feedback_packet["input_sha256"]:
                raise ValueError("Feedback triplet changed")
            if _triplet(packet["input"]["explanation"], packet) != feedback_packet["input"]:
                raise ValueError("Feedback original differs from source packet")
            case_packet = {**packet, "group_id": feedback_packet["group_id"],
                           "family_weight": feedback_packet["family_weight"],
                           "stratum": feedback_packet["stratum"]}
        terminal_events = [e for e in feedbacks[pid] if e["event_id"] not in superseded]
        if not terminal_events:
            exclusions.append({"snapshot": name, "post_id": pid, "reason": "no_feedback_event"})
            continue
        slots = _answer_slots(packet)
        summary = human_feedback.get(pid)
        if feedback_path.exists():
            if summary is None or len(terminal_events) != 1 or summary["event"] != terminal_events[0]:
                raise ValueError("Human feedback summary differs from latest event")
            if len(summary["answers"]) != len(slots):
                raise ValueError("Human feedback slots differ from packet")
        asset = _asset(directory, packet)
        for event in terminal_events:
            history = []
            ancestor = event
            while ancestor["kind"] == "feedback":
                history.append(ancestor)
                ancestor = by_id.get(ancestor.get("base_revision"))
                if ancestor is None:
                    break
            history.reverse()
            for slot, answer in enumerate(slots):
                quality = _quality_for(event, slot, name)
                if summary is not None:
                    h = summary["answers"][slot]
                    if h["source"] != answer["source"] or h["text_sha256"] != digest(answer["text"]):
                        raise ValueError("Human answer identity differs from packet")
                    if h.get("text") is not None and h["text"] != answer["text"]:
                        raise ValueError("Human answer text differs from packet")
                    if h.get("quality") != quality or h.get("judgment_present", quality is not None) != (quality is not None):
                        raise ValueError("Human quality differs from event")
                if quality is None:
                    exclusions.append({"snapshot": name, "post_id": pid, "slot": slot,
                                       "reason": "no_answer_quality_field"})
                    continue
                source = {"snapshot": name, "manifest_sha256": source_hashes[str(directory / "manifest.json")],
                    "cases_sha256": file_hash(directory / "cases.json"),
                    "events_sha256": file_hash(directory / "events.jsonl"),
                    "event_id": event["event_id"], "packet_input_sha256": packet["input_sha256"],
                    "answer_text_sha256": digest(answer["text"]), "slot": slot, "answer_source": answer["source"],
                    "event": event, "revision_history": history,
                }
                if name in PACKETS:
                    source["group_metadata"] = {
                        "snapshot": name, "group_id": feedback_packet["group_id"],
                        "family_weight": feedback_packet["family_weight"],
                        "stratum": feedback_packet["stratum"],
                        "source_packet_group_id": packet.get("group_id", pid),
                        "cases_sha256": file_hash(directory / "cases.json"),
                        "duplicate_inspection_sha256": file_hash(directory / "duplicate-inspection.json")}
                _append_case(rows, case_packet, answer, event, source, asset, quality)


def _reassessments(root: Path, rows: dict, exclusions: list[dict], source_hashes: dict[str, str]):
    path = root / "curation/feedback/reassessments.jsonl"
    if not path.is_file():
        return
    source_hashes[str(path)] = file_hash(path)
    reviewed = {p["post_id"]: p for p in _json(root / "curation/review-v1/cases.json")}
    review_corpus_id = _json(root / "curation/review-v1/manifest.json")["corpus_id"]
    for reassessment in _events(path):
        if reassessment["corpus_id"] != review_corpus_id:
            raise ValueError("Reassessment corpus identity changed")
        for item in reassessment.get("items", []):
            dimension = item.get("dimensions", {}).get("ground_truth")
            if not dimension:
                continue
            verdict = dimension.get("verdict")
            quality = {"fail": "repair", "ready": "ready", "pass": "ready",  # nosec B105: human verdict labels, not credentials
                       "unresolved": "unclear", "unclear": "unclear"}.get(verdict)
            pid = item["post_id"]
            packet = reviewed.get(pid)
            if quality is None or packet is None or item["input_sha256"] != packet["input_sha256"]:
                exclusions.append({"snapshot": "reassessments", "post_id": pid,
                                   "reason": "unmatched_or_unrecognized_ground_truth"})
                continue
            answer = _answer_slots(packet)[0]
            event = {"fields": {"ground_truth": verdict}, "notes": item.get("reason", ""),
                     "recorded_at": reassessment.get("recorded_at"), "base_revision": None}
            source = {"snapshot": "reassessments", "manifest_sha256": source_hashes[str(path)],
                "cases_sha256": file_hash(root / "curation/review-v1/cases.json"),
                "events_sha256": source_hashes[str(path)], "event_id": reassessment["event_id"],
                "packet_input_sha256": packet["input_sha256"], "answer_text_sha256": digest(answer["text"]),
                "slot": 0, "answer_source": answer["source"],
                "event": {"event_id": reassessment["event_id"],
                          "corpus_id": reassessment["corpus_id"], "item": item},
                "revision_history": [], "certainty": dimension.get("certainty"),
                "dimension_note": dimension.get("note")}
            _append_case(rows, packet, answer, event, source,
                         _asset(root / "curation/review-v1", packet), quality)


def prepare(data_root: Path, output: Path) -> dict:
    """Write one immutable reconstruction; source images stay at verified paths."""
    data_root, output = Path(data_root).resolve(), Path(output)
    if output.exists():
        raise FileExistsError("Never overwrite a frozen source-evidence dataset")
    rows: dict = {}
    exclusions: list[dict] = []
    source_hashes: dict[str, str] = {}
    for name in SNAPSHOTS:
        _load_snapshot(data_root, name, rows, exclusions, source_hashes)
    _reassessments(data_root, rows, exclusions, source_hashes)
    cases = []
    for row in rows.values():
        events = row["human"]["events"]
        qualities = {e["quality"] for e in events}
        row["human"]["quality"] = next(iter(qualities)) if len(qualities) == 1 else "conflicting"
        image_path = Path(row["image_path"]) if row["image_path"] else None
        row["image_error"] = image_error(image_path) if image_path else "missing_image"
        row["human"]["events"].sort(key=lambda e: (e["snapshot"], e["event_id"], e["slot"]))
        row["provenance"]["sources"].sort(key=lambda s: (s["snapshot"], s["event_id"]))
        row["provenance"]["answer_versions"].sort(key=lambda s: (s["source"], s["slot"]))
        row["provenance"]["review_selections"].sort(key=lambda s: (s["snapshot"], s["group_id"]))
        cases.append(row)
    cases.sort(key=lambda c: (c["post_id"], c["input_sha256"]))
    report = {"version": VERSION, "cases": len(cases), "posts": len({c["post_id"] for c in cases}),
              "known_groups": len({c["group_id"] for c in cases}),
              "quality": dict(sorted(Counter(c["human"]["quality"] for c in cases).items())),
              "image_holds": dict(sorted(Counter(c["image_error"] for c in cases if c["image_error"]).items())),
              "human_judgments": sum(len(c["human"]["events"]) for c in cases),
              "excluded": exclusions, "source_manifest_hashes": source_hashes}
    output.mkdir(parents=True)
    write_json(output / "cases.json", cases)
    write_json(output / "report.json", report)
    manifest = {"version": VERSION, "files": {name: file_hash(output / name)
                 for name in ("cases.json", "report.json")}, "source_manifest_hashes": source_hashes,
                 "producer_code_sha256": file_hash(Path(__file__))}
    manifest["dataset_id"] = digest(manifest)
    write_json(output / "manifest.json", manifest)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_root", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare(args.data_root, args.output), indent=2))


if __name__ == "__main__":
    main()
