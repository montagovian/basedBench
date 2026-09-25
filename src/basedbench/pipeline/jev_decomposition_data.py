"""Prepare a verified, lossless Jev decomposition dataset from the frozen #36 run."""
from __future__ import annotations

from collections import Counter
import json
import os
from pathlib import Path
import re
import shutil
import tempfile

from basedbench.pipeline.calibrated_eval import image_error
from basedbench.pipeline.curation_corpus import digest, file_hash, write_json

VERSION = "jev-decomposition-dataset-v1"
EXPECTED = {"cases": 99, "posts": 88, "groups": 86,
            "quality": {"ready": 78, "repair": 18, "unclear": 3}}


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _verify_files(root: Path, files: dict[str, str]) -> None:
    if not isinstance(files, dict):
        raise ValueError("Invalid frozen manifest files")
    resolved_root = root.resolve()
    for relative, expected in files.items():
        rel = Path(relative)
        path = root / rel
        if (rel.is_absolute() or ".." in rel.parts or path.is_symlink()
                or not path.resolve().is_relative_to(resolved_root) or not path.is_file()
                or not isinstance(expected, str) or not re.fullmatch(r"[a-f0-9]{64}", expected)
                or file_hash(path) != expected):
            raise ValueError(f"Frozen source file changed: {relative}")


def _verify_source(source_root: Path) -> tuple[list[dict], dict[str, str], dict]:
    dataset = source_root / "dataset"
    manifest = _read(dataset / "manifest.json")
    if (manifest.get("dataset_id") != digest({k: v for k, v in manifest.items()
                                                if k != "dataset_id"})):
        raise ValueError("Source dataset manifest identity changed")
    _verify_files(dataset, manifest.get("files"))
    cases = _read(dataset / "cases.json")
    audit_path = source_root / "grouping-audit.json"
    audit = _read(audit_path)
    if audit.get("audit_id") != digest({k: v for k, v in audit.items() if k != "audit_id"}):
        raise ValueError("Grouping audit identity changed")
    if audit.get("dataset_manifest_sha256") != file_hash(dataset / "manifest.json"):
        raise ValueError("Grouping audit refers to a different source dataset")
    for source_path, expected in audit.get("source_files", {}).items():
        path = Path(source_path)
        if not path.is_file() or file_hash(path) != expected:
            raise ValueError(f"Grouping audit source changed: {source_path}")
    mapping = audit.get("case_group_ids")
    case_ids = {row.get("case_id") for row in cases}
    if (not isinstance(mapping, dict) or set(mapping) != case_ids
            or any(not isinstance(v, str) or not v for v in mapping.values())):
        raise ValueError("Grouping audit does not cover the exact source cases")
    strata = audit.get("case_strata")
    if (not isinstance(strata, dict) or set(strata) != case_ids or
            any(not isinstance(value, list) or any(not isinstance(item, str) for item in value)
                for value in strata.values())):
        raise ValueError("Grouping audit strata do not cover the exact source cases")
    # The audit records reviewed corrections. Every group different from the
    # source assignment must be explicitly represented in its correction log.
    corrected = {item.get("case_id"): item for item in audit.get("corrected", [])
                 if isinstance(item, dict) and item.get("case_id")}
    for row in cases:
        raw_group = str(row.get("group_id") or row["post_id"])
        if mapping[row["case_id"]] != raw_group:
            correction = corrected.get(row["case_id"])
            if (not correction or correction.get("frozen_group_id") != raw_group
                    or correction.get("verified_group_id") != mapping[row["case_id"]]):
                raise ValueError(f"Unverified group override for {row['case_id']}")
    return cases, mapping, {"source_dataset_id": manifest["dataset_id"],
                            "source_dataset_manifest_sha256": file_hash(dataset / "manifest.json"),
                            "grouping_audit_id": audit["audit_id"],
                            "grouping_audit_sha256": file_hash(audit_path),
                            "grouping_audit_verified": True,
                            "source_manifest_hashes": manifest.get("source_manifest_hashes", {})}


def _comments(comment_evidence: str) -> list[dict[str, str]]:
    """Extract IDs and body strings from the frozen formatted evidence verbatim."""
    if not isinstance(comment_evidence, str):
        raise ValueError("Comment evidence must be text")
    marker = re.compile(r"(?m)^ID: ([^|\n]+) \| Score: [^\n]*\n")
    matches = list(marker.finditer(comment_evidence))
    comments = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(comment_evidence)
        body = comment_evidence[match.end():end]
        if body.endswith("\n---\n"):
            body = body[:-5]
        elif body.endswith("---"):
            body = body[:-3]
        comment_id = match.group(1).strip()
        if not comment_id or any(c["id"] == comment_id for c in comments):
            raise ValueError("Comment IDs must be present and unique")
        comments.append({"id": comment_id, "text": body})
    return comments


def _spans(text: str) -> list[dict]:
    if not isinstance(text, str) or not text:
        raise ValueError("Explanation text is missing")
    ends = [m.end() for m in re.finditer(r"[.!?;](?:[\"'’”)]*)(?:\s+|$)", text)]
    boundaries = sorted(set([0] + [end for end in ends if 0 < end < len(text)] + [len(text)]))
    intervals = list(zip(boundaries, boundaries[1:]))
    # Merge neighboring natural spans evenly until at most eight remain.
    while len(intervals) > 8:
        merged = []
        i = 0
        remaining = len(intervals)
        groups_left = 8
        while groups_left:
            size = (remaining + groups_left - 1) // groups_left
            merged.append((intervals[i][0], intervals[i + size - 1][1]))
            i += size
            remaining -= size
            groups_left -= 1
        intervals = merged
    spans = [{"id": f"span-{i + 1:02d}", "text": text[start:end],
              "start": start, "end": end}
             for i, (start, end) in enumerate(intervals)]
    if "".join(span["text"] for span in spans) != text:
        raise ValueError("Explanation span partition lost text")
    return spans


def prepare(source_root: Path, output: Path) -> dict:
    """Build a verified Jev dataset and copied supported assets atomically."""
    source_root = Path(source_root).resolve()
    output = Path(output).absolute()
    if output.exists():
        raise FileExistsError("Never overwrite a prepared Jev dataset")
    if output.resolve().is_relative_to(source_root):
        raise ValueError("Dataset output must be outside the immutable source tree")
    source_cases, group_ids, verification = _verify_source(source_root)
    out_parent = output.parent
    out_parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=out_parent))
    try:
        assets_dir = stage / "assets"
        assets_dir.mkdir()
        cases = []
        image_holds = Counter()
        copied: dict[str, str] = {}
        for original in source_cases:
            row = {key: original[key] for key in
                   ("case_id", "post_id", "human", "input")}
            row["group_id"] = group_ids[original["case_id"]]
            row["comments"] = _comments(original["input"]["comment_evidence"])
            row["spans"] = _spans(original["input"]["explanation"])
            image_path = Path(original["image_path"]) if original.get("image_path") else None
            error = original.get("image_error")
            sha = original["input"].get("image_sha256")
            if image_path is not None and (not image_path.is_file() or file_hash(image_path) != sha):
                raise ValueError(f"Image source changed for {original['case_id']}")
            if error is None and image_path is not None:
                error = image_error(image_path)
            if not error and image_path is not None:
                asset_path = assets_dir / sha
                if sha not in copied:
                    shutil.copyfile(image_path, asset_path)
                    if file_hash(asset_path) != sha:
                        raise ValueError(f"Copied image verification failed for {original['case_id']}")
                    copied[sha] = f"assets/{sha}"
                row["image_path"] = str((output / copied[sha]).resolve())
            else:
                row["image_path"] = None
                image_holds[error or "missing_image"] += 1
            row["image_error"] = error or ("missing_image" if image_path is None else None)
            cases.append(row)
        cases.sort(key=lambda case: (case["post_id"], case["case_id"]))
        quality = dict(sorted(Counter(case["human"].get("quality") for case in cases).items()))
        counts = {"cases": len(cases), "posts": len({case["post_id"] for case in cases}),
                  "groups": len({case["group_id"] for case in cases}), "quality": quality}
        if counts != EXPECTED:
            raise ValueError(f"Unexpected frozen corpus composition: {counts}")
        report = {"version": VERSION, **counts,
                  "image_holds": dict(sorted(image_holds.items())),
                  "copied_assets": len(copied), **verification}
        write_json(stage / "cases.json", cases)
        write_json(stage / "report.json", report)
        files = {str(path.relative_to(stage)): file_hash(path)
                 for path in sorted(stage.rglob("*")) if path.is_file()}
        manifest = {"version": VERSION, "files": files, **verification}
        manifest["dataset_id"] = digest(manifest)
        write_json(stage / "manifest.json", manifest)
        # Directory rename publishes the complete, hashed dataset in one step.
        os.replace(stage, output)
        return report
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
