"""File-based, content-addressed release snapshots.

The release directory is self-contained: subsequent reads never consult the
database or the source image paths used while freezing it.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import os
import re
import shutil
import tempfile
import warnings
from copy import deepcopy
from pathlib import Path
from typing import Any

from PIL import Image, ImageSequence, UnidentifiedImageError

SCHEMA_VERSION = "basedbench.release.v1"
_ITEM_FIELDS = {
    "post_id", "title", "subreddit", "ground_truth", "image_path", "cohort",
    "exposure", "admission_origin", "policy_version", "answer_readiness",
    "source_support", "content_status", "suitability", "duplicate_status",
    "rights_status", "answer_provenance",
}
_SELECT_FIELDS = {"name", "policy_version", "items", "evaluation", "description"}
_MANIFEST_FIELDS = {
    "schema_version", "name", "description", "policy_version", "evaluation",
    "membership_sha256", "content_sha256", "items",
}
_FROZEN_ITEM_FIELDS = (_ITEM_FIELDS - {"image_path"}) | {
    "image_filename", "image_sha256", "answer_sha256",
}
_GATE_FIELDS = ("source_support", "content_status", "suitability", "duplicate_status")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_POST_ID = re.compile(r"[A-Za-z0-9_-]+\Z")
_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
_FORMAT_EXTENSIONS = {"JPEG": ".jpg", "PNG": ".png", "GIF": ".gif", "WEBP": ".webp"}
_MATCHING_EXTENSIONS = {".jpg": {".jpg", ".jpeg"}, ".png": {".png"},
                        ".gif": {".gif"}, ".webp": {".webp"}}


def canonical_bytes(value: Any) -> bytes:
    """Encode JSON deterministically, rejecting values outside strict JSON."""
    _strict_json(value)
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"),
                   ensure_ascii=False, allow_nan=False).encode("utf-8") + b"\n"
    )


def _strict_json(value: Any) -> None:
    """Reject JSON encodings that silently change Python types or object keys."""
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if math.isfinite(value):
            return
        raise ValueError("non-finite JSON number")
    if isinstance(value, list):
        for entry in value:
            _strict_json(entry)
        return
    if isinstance(value, dict):
        for key, entry in value.items():
            if not isinstance(key, str):
                raise ValueError("JSON object keys must be strings")
            _strict_json(entry)
        return
    raise ValueError(f"unsupported JSON value: {type(value).__name__}")


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _object(value: Any, fields: set[str], required: set[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) - fields or required - set(value):
        raise ValueError(f"invalid {label} fields")
    return value


def _string(value: Any, label: str, *, empty: bool = False) -> str:
    if not isinstance(value, str) or (not empty and not value.strip()):
        raise ValueError(f"invalid {label}")
    return value


def _hash(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"invalid {label}")
    return value


def _choice(value: Any, options: set[str], label: str) -> str:
    if not isinstance(value, str) or value not in options:
        raise ValueError(f"invalid {label}: {value!r}")
    return value


def _evaluation(value: Any) -> dict:
    if value is None:
        value = {}
    value = _object(value, {"model_panel", "prediction_prompt_id", "judge_prompt_id",
                            "scoring_version"}, set(), "evaluation")
    panel = value.get("model_panel", [])
    if not isinstance(panel, list) or any(
        not isinstance(model, str) or not model.strip() for model in panel
    ) or len(panel) != len(set(panel)):
        raise ValueError("invalid evaluation model_panel")
    for key in ("prediction_prompt_id", "judge_prompt_id"):
        prompt = value.get(key)
        if prompt is not None:
            _string(prompt, key)
    scoring = _string(value.get("scoring_version", "majority-v1"), "scoring_version")
    return {
        "model_panel": panel,
        "prediction_prompt_id": value.get("prediction_prompt_id"),
        "judge_prompt_id": value.get("judge_prompt_id"),
        "scoring_version": scoring,
    }


def _item(value: Any, *, frozen: bool) -> dict:
    fields = _FROZEN_ITEM_FIELDS if frozen else _ITEM_FIELDS
    item = _object(value, fields, fields, "item")
    post_id = _string(item["post_id"], "post_id")
    if not _POST_ID.fullmatch(post_id):
        raise ValueError(f"unsafe post_id: {post_id!r}")
    for key in ("title", "subreddit", "ground_truth", "policy_version"):
        _string(item[key], key, empty=key == "title")
    _choice(item["cohort"], {"legacy", "development"}, "cohort")
    _choice(item["exposure"], {"exposed", "unknown"}, "exposure")
    _choice(item["admission_origin"], {
        "legacy_human_validated", "human_curated", "qualified_automation", "unknown",
    }, "admission_origin")
    _choice(item["answer_readiness"], {
        "ready", "ready_tentative", "repair", "unclear", "unknown",
    }, "answer_readiness")
    for key in _GATE_FIELDS:
        _choice(item[key], {"pass", "hold", "unknown"}, key)
    _choice(item["rights_status"], {"mixed_rights", "unknown"}, "rights_status")
    if not isinstance(item["answer_provenance"], dict):
        raise ValueError("answer_provenance must be a JSON object")
    try:
        canonical_bytes(item["answer_provenance"])
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("invalid answer_provenance JSON") from exc
    if item["cohort"] == "development":
        if (item["answer_readiness"] not in {"ready", "ready_tentative"}
                or any(item[key] != "pass" for key in _GATE_FIELDS)
                or item["rights_status"] != "mixed_rights"
                or item["admission_origin"] not in {"human_curated", "qualified_automation"}):
            raise ValueError(f"development item {post_id} has uncleared release gates")
    if frozen:
        filename = _string(item["image_filename"], "image_filename")
        if (Path(filename).suffix not in _EXTENSIONS
                or filename != f"{post_id}{Path(filename).suffix}"):
            raise ValueError("unsafe image_filename")
        _hash(item["image_sha256"], "image_sha256")
        _hash(item["answer_sha256"], "answer_sha256")
        if item["answer_sha256"] != _digest(item["ground_truth"].encode("utf-8")):
            raise ValueError("answer digest mismatch")
    else:
        _string(item["image_path"], "image_path")
    return item


def _no_symlinks(path: Path, stop: Path | None = None) -> None:
    cursor = path
    while True:
        if cursor.is_symlink():
            raise ValueError(f"symlink path forbidden: {cursor}")
        if cursor == stop or cursor == cursor.parent:
            return
        cursor = cursor.parent


def _source_image(raw_path: str, source_root: Path) -> Path:
    path = Path(raw_path)
    if ".." in path.parts:
        raise ValueError("image path traversal forbidden")
    try:
        root = source_root.resolve(strict=True)
    except OSError as exc:
        raise ValueError("source_root is unavailable") from exc
    if not source_root.is_dir():
        raise ValueError("source_root is not a directory")
    _no_symlinks(source_root)
    image = path if path.is_absolute() else source_root / path
    _no_symlinks(image, source_root if not path.is_absolute() else None)
    try:
        resolved = image.resolve(strict=True)
    except OSError as exc:
        raise ValueError(f"image missing: {raw_path}") from exc
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise ValueError("image must be a file within source_root")
    return resolved


def _image_bytes(path: Path) -> tuple[bytes, str]:
    try:
        payload = path.read_bytes()
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(payload)) as image:
                image_format = image.format
                image.verify()
            with Image.open(io.BytesIO(payload)) as image:
                for frame in ImageSequence.Iterator(image):
                    frame.load()
        extension = _FORMAT_EXTENSIONS.get(image_format)
        if extension is None:
            raise ValueError(f"unsupported image format: {image_format}")
    except (OSError, UnidentifiedImageError, ValueError, EOFError,
            Image.DecompressionBombWarning, Image.DecompressionBombError) as exc:
        raise ValueError(f"invalid image: {path}") from exc
    return payload, extension


def _manifest(selection: dict, source_root: Path, images_dir: Path) -> dict:
    selection = _object(selection, _SELECT_FIELDS,
                        {"name", "policy_version", "items"}, "selection")
    name = _string(selection["name"], "name")
    policy = _string(selection["policy_version"], "policy_version")
    description = selection.get("description")
    if description is not None:
        _string(description, "description", empty=True)
    rows = selection["items"]
    if not isinstance(rows, list) or not rows:
        raise ValueError("items must be a nonempty list")
    by_id: dict[str, dict] = {}
    images_dir.mkdir()
    for raw_item in rows:
        item = _item(raw_item, frozen=False)
        post_id = item["post_id"]
        if post_id in by_id:
            raise ValueError(f"duplicate post_id: {post_id}")
        path = _source_image(item["image_path"], source_root)
        ext = path.suffix.lower()
        if ext not in _EXTENSIONS:
            raise ValueError(f"unsupported image extension: {ext}")
        payload, ext = _image_bytes(path)
        filename = f"{post_id}{ext}"
        (images_dir / filename).write_bytes(payload)
        frozen = deepcopy({key: value for key, value in item.items() if key != "image_path"})
        frozen.update(image_filename=filename, image_sha256=_digest(payload),
                      answer_sha256=_digest(item["ground_truth"].encode("utf-8")))
        by_id[post_id] = frozen
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "name": name,
        "description": description,
        "policy_version": policy,
        "evaluation": _evaluation(selection.get("evaluation")),
        "membership_sha256": _digest(canonical_bytes(sorted(by_id))),
        "items": [by_id[post_id] for post_id in sorted(by_id)],
    }
    manifest["content_sha256"] = _digest(canonical_bytes(manifest))
    return manifest


def freeze_release(selection: dict, output_dir: Path, *, source_root: Path) -> dict:
    """Freeze text, image bytes and private provenance into one atomic directory."""
    output_dir = Path(output_dir)
    source_root = Path(source_root)
    if output_dir.exists() or output_dir.is_symlink():
        raise ValueError(f"release destination exists: {output_dir}")
    if not output_dir.parent.is_dir():
        raise ValueError("release parent directory does not exist")
    _no_symlinks(output_dir.parent)
    lock = output_dir.parent / f".{output_dir.name}.lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise ValueError(f"release destination is already being frozen: {output_dir}") from exc
    staging: Path | None = None
    try:
        os.close(fd)
        if output_dir.exists() or output_dir.is_symlink():
            raise ValueError(f"release destination exists: {output_dir}")
        staging = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.tmp-", dir=output_dir.parent))
        manifest = _manifest(selection, source_root, staging / "images")
        (staging / "manifest.json").write_bytes(canonical_bytes(manifest))
        if output_dir.exists() or output_dir.is_symlink():
            raise ValueError(f"release destination exists: {output_dir}")
        os.rename(staging, output_dir)
        return manifest
    finally:
        if staging is not None and staging.exists():
            shutil.rmtree(staging)
        lock.unlink()


def _unique_object(pairs: list[tuple[str, Any]]) -> dict:
    value: dict = {}
    for key, entry in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key: {key}")
        value[key] = entry
    return value


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON value: {value}")


def load_release(path: Path) -> dict:
    """Load and verify every byte and structural constraint in a release."""
    path = Path(path)
    _no_symlinks(path)
    if not path.is_dir():
        raise ValueError("release directory missing")
    expected_top = {"manifest.json", "images"}
    if {entry.name for entry in path.iterdir()} != expected_top:
        raise ValueError("release directory has missing or unexpected entries")
    manifest_path = path / "manifest.json"
    image_dir = path / "images"
    if manifest_path.is_symlink() or not manifest_path.is_file() or image_dir.is_symlink() or not image_dir.is_dir():
        raise ValueError("invalid release structure")
    try:
        payload = manifest_path.read_bytes()
        manifest = json.loads(payload, object_pairs_hook=_unique_object,
                              parse_constant=_reject_constant)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError("invalid release manifest") from exc
    manifest = _object(manifest, _MANIFEST_FIELDS, _MANIFEST_FIELDS, "manifest")
    if manifest["schema_version"] != SCHEMA_VERSION:
        raise ValueError("unsupported release schema")
    _string(manifest["name"], "name")
    _string(manifest["policy_version"], "policy_version")
    if manifest["description"] is not None:
        _string(manifest["description"], "description", empty=True)
    if manifest["evaluation"] != _evaluation(manifest["evaluation"]):
        raise ValueError("noncanonical evaluation configuration")
    rows = manifest["items"]
    if not isinstance(rows, list) or not rows:
        raise ValueError("empty release items")
    ids: list[str] = []
    filenames: set[str] = set()
    for row in rows:
        item = _item(row, frozen=True)
        ids.append(item["post_id"])
        filename = item["image_filename"]
        if filename in filenames:
            raise ValueError("duplicate image filename")
        filenames.add(filename)
        image_path = image_dir / filename
        if image_path.is_symlink() or not image_path.is_file():
            raise ValueError(f"missing or linked release image: {filename}")
        image_bytes, extension = _image_bytes(image_path)
        if Path(filename).suffix not in _MATCHING_EXTENSIONS[extension]:
            raise ValueError(f"image format/extension mismatch: {filename}")
        if _digest(image_bytes) != item["image_sha256"]:
            raise ValueError(f"image digest mismatch: {filename}")
    if ids != sorted(set(ids)):
        raise ValueError("release items must have unique sorted post IDs")
    if {entry.name for entry in image_dir.iterdir()} != filenames:
        raise ValueError("release images do not match manifest")
    _hash(manifest["membership_sha256"], "membership_sha256")
    _hash(manifest["content_sha256"], "content_sha256")
    if manifest["membership_sha256"] != _digest(canonical_bytes(ids)):
        raise ValueError("membership digest mismatch")
    unsigned = {key: value for key, value in manifest.items() if key != "content_sha256"}
    if manifest["content_sha256"] != _digest(canonical_bytes(unsigned)):
        raise ValueError("content digest mismatch")
    if payload != canonical_bytes(manifest):
        raise ValueError("manifest bytes are not canonical")
    return manifest


def evaluation_inputs(path: Path) -> list[dict]:
    """Return verified predictor inputs containing only image identity and path."""
    manifest = load_release(path)
    release_dir = Path(path).resolve(strict=True)
    return [
        {
            "post_id": item["post_id"],
            "image_path": str(release_dir / "images" / item["image_filename"]),
            "image_sha256": item["image_sha256"],
        }
        for item in manifest["items"]
    ]
