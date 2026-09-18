"""Freeze historical admission evidence without changing the live database.

This is a corpus of overall curation decisions, not task-specific consensus,
safety, or explanation-quality labels. Only ``input`` is available to models.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sqlite3
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageChops, ImageOps, ImageStat, __version__ as pillow_version

from basedbench.pipeline.duplicates import compute_image_fingerprint, hamming_distance

SCHEMA_VERSION = "curation-corpus-v1"
SPLITS = ("development", "calibration", "test")
LIMITATIONS = [
    "Labels describe overall historical admission, not individual gate correctness.",
    "Original generation is recovered from logs; the exact review-time display is not versioned.",
    "Images are frozen as found now; historical image bytes were not versioned.",
    "Duplicate grouping uses image similarity and identical explanations; semantic joke families remain unaudited.",
    "Calibration results are exploratory. Final-test evaluation requires resolved provenance and family grouping.",
]


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def file_hash(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(canonical_json(row) + "\n" for row in rows))


def _read_source(db_path: Path) -> tuple[list[dict], dict[str, list[dict]], set[str], dict]:
    # A read transaction gives all queries one consistent view, including WAL.
    conn = sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA query_only = ON")
        conn.execute("BEGIN")
        reviews = [dict(r) for r in conn.execute("""
            SELECT m.post_id, m.subreddit, m.title, m.local_image_path, m.permalink,
                   m.created_utc, r.status, r.reason, r.reviewed_at,
                   g.explanation AS current_explanation, g.created_at AS generated_at
            FROM memes m JOIN reviews r USING (post_id)
            LEFT JOIN ground_truths g USING (post_id)
            WHERE r.status = 'validated' OR (r.status = 'excluded' AND r.reason = 'other')
            ORDER BY m.post_id
        """)]
        calls: dict[str, list[dict]] = defaultdict(list)
        # Matching the stored generation time is safer than taking an arbitrary
        # later eval rerun. Never fall back to a post-review response.
        for row in conn.execute("""
            SELECT l.* FROM llm_calls l
            JOIN ground_truths g USING (post_id) JOIN reviews r USING (post_id)
            WHERE (r.status = 'validated' OR (r.status = 'excluded' AND r.reason = 'other'))
              AND l.role = 'consensus' AND l.error IS NULL AND l.verdict = 'consensus'
              AND abs(julianday(l.created_at) - julianday(g.created_at)) * 86400 < 2
              AND julianday(l.created_at) <= julianday(r.reviewed_at)
            ORDER BY l.post_id, l.id
        """):
            calls[row["post_id"]].append(dict(row))
        # Previously examined regression/eval cases cannot become pristine test cases.
        known = {r[0] for r in conn.execute("""
            SELECT post_id FROM consensus_eval_items
            UNION SELECT post_id FROM consensus_regression
            UNION SELECT post_id FROM gate_feedback
        """)}
        inventory = {f"{r[0]}:{r[1] or ''}": r[2] for r in conn.execute("""
            SELECT status, CASE
                WHEN reason LIKE 'auto:%' THEN 'auto:*'
                WHEN reason LIKE 'safety:%' THEN 'safety:*'
                WHEN reason LIKE 'duplicate_image:%' THEN 'duplicate_image:*'
                ELSE reason END AS reason_group, count(*)
            FROM reviews GROUP BY status, reason_group ORDER BY status, reason_group
        """)}
        return reviews, calls, known, inventory
    finally:
        conn.close()


def _historical_input(call: dict) -> dict:
    response = json.loads(call["response"])
    explanation = response.get("selected_explanation")
    if response.get("has_consensus") is not True or not isinstance(explanation, str) or not explanation.strip():
        raise ValueError("missing successful original explanation")
    # Strip author names from known prompt headers; keep the historical comment
    # scores/bodies rather than silently substituting today's DB comments.
    prompt = call["user_prompt"]
    if not re.search(r"(?m)^ID: \S+ \| Score: -?\d+ \| Author: ", prompt):
        raise ValueError("unrecognized historical comments format")
    prompt = re.sub(r"(?m)^(ID: \S+ \| Score: -?\d+) \| Author: [^\n]*", r"\1", prompt)
    return {"explanation": explanation.strip(), "comment_evidence": prompt}


def _assign_groups(rows: list[dict], assets: Path, known: set[str], seed: str, families: dict[str, str]) -> None:
    parents = {r["post_id"]: r["post_id"] for r in rows}

    def root(pid: str) -> str:
        while parents[pid] != pid:
            parents[pid] = parents[parents[pid]]
            pid = parents[pid]
        return pid

    def union(left: str, right: str) -> None:
        a, b = sorted((root(left), root(right)))
        parents[b] = a

    seen: dict[tuple[str, str], str] = {}
    for row in rows:
        pid = row["post_id"]
        keys = [("image", row["input"]["image_sha256"]),
                ("explanation", " ".join(row["input"]["explanation"].casefold().split()))]
        if pid in families:
            keys.append(("family", families[pid]))
        for key in keys:
            if key in seen:
                union(pid, seen[key])
            seen[key] = pid

    # Conservative near-image matches, including small recompression changes.
    # Template reuse alone is insufficient: also require near-identical pixels.
    thumbnails: dict[str, Image.Image] = {}

    def thumbnail(row: dict) -> Image.Image:
        sha = row["input"]["image_sha256"]
        if sha not in thumbnails:
            with Image.open(assets / sha) as image:
                thumbnails[sha] = ImageOps.exif_transpose(image).convert("RGB").resize(
                    (256, 256), Image.Resampling.LANCZOS
                )
        return thumbnails[sha]

    for i, left in enumerate(rows):
        lf = left["provenance"]["image_fingerprint"]
        for right in rows[i + 1:]:
            if root(left["post_id"]) == root(right["post_id"]):
                continue
            rf = right["provenance"]["image_fingerprint"]
            if abs(lf["width"] / lf["height"] - rf["width"] / rf["height"]) > 0.02:
                continue
            if hamming_distance(lf["dhash"], rf["dhash"]) > 4 or hamming_distance(lf["ahash"], rf["ahash"]) > 2:
                continue
            diff = ImageChops.difference(thumbnail(left), thumbnail(right)).convert("L")
            if ImageStat.Stat(diff).mean[0] <= 4:
                union(left["post_id"], right["post_id"])

    exposed_groups = {root(pid) for pid in known if pid in parents}
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[root(row["post_id"])].append(row)
    assignments = {group: "development" for group in exposed_groups}
    label_totals = Counter(r["label"] for r in rows)
    fractions = {"development": 0.7, "calibration": 0.15, "test": 0.15}
    assigned: dict[str, Counter] = {s: Counter() for s in SPLITS}
    for group in exposed_groups:
        assigned["development"].update(r["label"] for r in grouped[group])
    # Stratify by the overall decision while keeping each group indivisible.
    # Place large groups first, then hash order; do not search for a good seed
    # after seeing classifier performance. Exposed groups remain development.
    ordered = sorted(grouped, key=lambda g: (-len(grouped[g]), digest([seed, g])))
    for group in ordered:
        if group in assignments:
            continue
        labels = Counter(r["label"] for r in grouped[group])

        def allocation_cost(split: str) -> float:
            cost = 0.0
            for label, count in labels.items():
                target = label_totals[label] * fractions[split]
                deficit = assigned[split][label] - target
                cost += ((deficit + count) ** 2 - deficit**2) / max(target, 1)
            return cost

        split = min(SPLITS, key=allocation_cost)
        assignments[group] = split
        assigned[split].update(labels)
    for row in rows:
        group = root(row["post_id"])
        row.update(group_id=group, split=assignments[group])
        row["provenance"]["previously_examined_group"] = group in exposed_groups


def build_corpus(
    db_path: Path,
    output: Path,
    *,
    project_root: Path,
    seed: str = "basedbench-curation-v1",
    other_provenance: str = "inferred_manual",
    family_file: Path | None = None,
) -> dict:
    """Create a new immutable version, quarantining unreconstructable examples."""
    if other_provenance not in {"inferred_manual", "confirmed_manual"}:
        raise ValueError("other_provenance must be inferred_manual or confirmed_manual")
    if output.exists():
        raise FileExistsError(f"Refusing to replace frozen corpus: {output}")
    families = json.loads(family_file.read_text()) if family_file else {}
    if not isinstance(families, dict) or not all(isinstance(k, str) and isinstance(v, str) and v for k, v in families.items()):
        raise ValueError("Family file must map post IDs to nonempty family strings")
    reviews, calls, known, inventory = _read_source(db_path)
    unknown = families.keys() - {r["post_id"] for r in reviews}
    if unknown:
        raise ValueError(f"Family file contains unknown/noncandidate IDs: {sorted(unknown)}")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}-", dir=output.parent))
    try:
        assets = staging / "assets"
        assets.mkdir()
        rows, quarantined = [], []
        for review in reviews:
            pid = review["post_id"]
            try:
                matches = calls.get(pid, [])
                if len(matches) != 1:
                    raise ValueError(f"expected one original consensus call; found {len(matches)}")
                call = matches[0]
                model_input = _historical_input(call)
                if not review["local_image_path"]:
                    raise ValueError("missing local image path")
                image_path = Path(review["local_image_path"])
                image_path = image_path if image_path.is_absolute() else project_root / image_path
                # Freeze first, then fingerprint the frozen bytes, preventing a
                # mutable source image from desynchronizing hashes and assets.
                payload = image_path.read_bytes()
                sha = hashlib.sha256(payload).hexdigest()
                frozen_path = assets / sha
                if not frozen_path.exists():
                    frozen_path.write_bytes(payload)
                fingerprint = compute_image_fingerprint(pid, str(frozen_path.resolve()), project_root)
                if fingerprint is None:
                    raise ValueError("image fingerprint unavailable")
                model_input["image_sha256"] = sha
                original_differs = model_input["explanation"] != (review["current_explanation"] or "").strip()
                rows.append({
                    "post_id": pid,
                    "input": model_input,
                    "input_sha256": digest(model_input),
                    "label": "accept" if review["status"] == "validated" else "reject",
                    "provenance": {
                        "label_source": "validated_review" if review["status"] == "validated" else other_provenance,
                        "review_reason": review["reason"], "reviewed_at": review["reviewed_at"],
                        "source_created_at": review["created_utc"], "permalink": review["permalink"],
                        "input_reconstruction": "original_generation_not_verified_review_display",
                        "current_explanation_differs": original_differs,
                        "image_fingerprint": {"dhash": fingerprint.dhash, "ahash": fingerprint.ahash,
                                              "width": fingerprint.width, "height": fingerprint.height},
                        "original_call": {k: call[k] for k in ("id", "created_at", "model", "prompt_version",
                                                               "system_prompt", "user_prompt", "response")},
                    },
                })
            except (ValueError, TypeError, AttributeError, OSError, Image.DecompressionBombError) as exc:
                quarantined.append({"post_id": pid, "status": review["status"], "reason": str(exc)})
        if not rows:
            raise ValueError("No reconstructable curation examples")
        _assign_groups(rows, assets, known, seed, families)
        # Remove assets belonging only to quarantined records.
        used = {r["input"]["image_sha256"] for r in rows}
        for asset in assets.iterdir():
            if asset.name not in used:
                asset.unlink()
        write_jsonl(staging / "examples.jsonl", rows)
        write_jsonl(staging / "quarantine.jsonl", quarantined)
        group_labels: dict[str, set[str]] = defaultdict(set)
        for row in rows:
            group_labels[row["group_id"]].add(row["label"])
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "seed": seed, "other_provenance": other_provenance,
            "builder": {"source_sha256": file_hash(Path(__file__)), "pillow_version": pillow_version,
                        "fingerprint_source_sha256": file_hash(Path(__file__).with_name("duplicates.py"))},
            "split_policy": "stratified-group-greedy-70-15-15-v1; previously-examined groups in development",
            "grouping": {"status": "provisional", "family_overrides": families,
                         "method": "exact-image/near-image/identical-explanation/explicit-family-v1"},
            "counts": {
                "candidates": len(reviews), "included": len(rows), "quarantined": len(quarantined),
                "groups": len(group_labels), "conflicting_label_groups": sum(len(v) > 1 for v in group_labels.values()),
                "current_explanation_differs": sum(r["provenance"]["current_explanation_differs"] for r in rows),
                "previously_examined_examples": sum(r["provenance"]["previously_examined_group"] for r in rows),
                "splits": {s: dict(Counter(r["label"] for r in rows if r["split"] == s)) for s in SPLITS},
            },
            "review_inventory": inventory,
            "limitations": LIMITATIONS,
            "files": {p.relative_to(staging).as_posix(): file_hash(p) for p in sorted(staging.rglob("*")) if p.is_file()},
        }
        manifest["corpus_id"] = digest(manifest)
        manifest["created_at"] = datetime.now(timezone.utc).isoformat()
        write_json(staging / "manifest.json", manifest)
        # rename fails if an existing nonempty corpus appeared concurrently.
        staging.rename(output)
        return manifest
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def load_corpus(path: Path) -> tuple[dict, list[dict]]:
    """Verify the manifest and every frozen payload before using any labels."""
    manifest = json.loads((path / "manifest.json").read_text())
    unsigned = {k: v for k, v in manifest.items() if k not in {"corpus_id", "created_at"}}
    if manifest["schema_version"] != SCHEMA_VERSION or digest(unsigned) != manifest["corpus_id"]:
        raise ValueError("Invalid corpus manifest/version/hash")
    for relative, expected in manifest["files"].items():
        target = (path / relative).resolve()
        if not target.is_relative_to(path.resolve()) or file_hash(target) != expected:
            raise ValueError(f"Corpus payload failed integrity check: {relative}")
    rows = [json.loads(line) for line in (path / "examples.jsonl").read_text().splitlines()]
    groups: dict[str, str] = {}
    ids = set()
    for row in rows:
        if row["post_id"] in ids or row["split"] not in SPLITS or row["label"] not in {"accept", "reject"}:
            raise ValueError("Invalid/duplicate corpus example")
        ids.add(row["post_id"])
        if digest(row["input"]) != row["input_sha256"]:
            raise ValueError("Invalid model input hash")
        if groups.setdefault(row["group_id"], row["split"]) != row["split"]:
            raise ValueError("Group leaked across splits")
        sha = row["input"]["image_sha256"]
        if manifest["files"].get(f"assets/{sha}") != sha:
            raise ValueError("Missing/unmatched image asset")
    return manifest, rows
