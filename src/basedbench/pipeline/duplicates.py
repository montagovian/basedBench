"""Image fingerprinting and duplicate cleanup helpers."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageChops, ImageOps, ImageStat

from basedbench.db import queries
from basedbench.db.connection import Database


@dataclass(frozen=True)
class ImageFingerprint:
    post_id: str
    exact_hash: str
    dhash: str
    ahash: str
    width: int
    height: int


@dataclass(frozen=True)
class DuplicateCandidate:
    post_id: str
    matched_post_id: str
    matched_status: str
    reason: str
    exact_match: bool
    dhash_distance: int
    ahash_distance: int
    pixel_difference: float | None


@dataclass(frozen=True)
class DuplicateCleanupResult:
    fingerprints_written: int
    candidates: list[DuplicateCandidate]
    excluded: int


def _resolve_image_path(project_root: Path, local_image_path: str) -> Path:
    path = Path(local_image_path)
    if path.is_absolute():
        return path
    return project_root / path


def _hex_bits(value: int, bit_count: int = 64) -> str:
    width = (bit_count + 3) // 4
    return f"{value:0{width}x}"


def _pixels(image: Image.Image) -> list[int]:
    get_flattened_data = getattr(image, "get_flattened_data", None)
    if get_flattened_data is not None:
        return list(get_flattened_data())
    return list(image.getdata())


def hamming_distance(left: str, right: str) -> int:
    """Return bit-level Hamming distance for equal-width hex hashes."""
    if len(left) != len(right):
        raise ValueError("hashes must have equal width")
    return (int(left, 16) ^ int(right, 16)).bit_count()


def _dhash(image: Image.Image, hash_size: int = 8) -> str:
    gray = image.convert("L").resize((hash_size + 1, hash_size), Image.Resampling.LANCZOS)
    pixels = _pixels(gray)
    value = 0
    for row in range(hash_size):
        offset = row * (hash_size + 1)
        for col in range(hash_size):
            value = (value << 1) | int(pixels[offset + col] > pixels[offset + col + 1])
    return _hex_bits(value, hash_size * hash_size)


def _ahash(image: Image.Image, hash_size: int = 8) -> str:
    gray = image.convert("L").resize((hash_size, hash_size), Image.Resampling.LANCZOS)
    pixels = _pixels(gray)
    mean = sum(pixels) / len(pixels)
    value = 0
    for pixel in pixels:
        value = (value << 1) | int(pixel > mean)
    return _hex_bits(value, hash_size * hash_size)


def compute_image_fingerprint(
    post_id: str,
    local_image_path: str,
    project_root: Path,
) -> ImageFingerprint | None:
    """Compute exact and perceptual hashes for a local meme image."""
    path = _resolve_image_path(project_root, local_image_path)
    if not path.exists() or not path.is_file():
        return None

    payload = path.read_bytes()
    exact_hash = hashlib.sha256(payload).hexdigest()
    with Image.open(path) as raw_image:
        image = ImageOps.exif_transpose(raw_image)
        width, height = image.size
        return ImageFingerprint(
            post_id=post_id,
            exact_hash=exact_hash,
            dhash=_dhash(image),
            ahash=_ahash(image),
            width=width,
            height=height,
        )


def backfill_image_fingerprints(
    db: Database,
    project_root: Path,
    post_ids: list[str] | None = None,
) -> int:
    """Compute missing/stale fingerprints for memes with local images."""
    if post_ids is None:
        rows = queries.list_memes_missing_image_fingerprints(db)
    else:
        rows = queries.list_memes_with_images(db, post_ids)
    written = 0
    for post_id, local_image_path in rows:
        fingerprint = compute_image_fingerprint(post_id, local_image_path, project_root)
        if fingerprint is None:
            continue
        queries.upsert_image_fingerprint(db, fingerprint)
        written += 1
    return written


def _aspect_ratio_close(left: queries.ImageFingerprintRow, right: queries.ImageFingerprintRow) -> bool:
    if left.width <= 0 or left.height <= 0 or right.width <= 0 or right.height <= 0:
        return False
    return abs((left.width / left.height) - (right.width / right.height)) <= 0.02


def _mean_abs_pixel_difference(
    project_root: Path,
    left: queries.ImageFingerprintRow,
    right: queries.ImageFingerprintRow,
) -> float | None:
    left_path = _resolve_image_path(project_root, left.local_image_path)
    right_path = _resolve_image_path(project_root, right.local_image_path)
    if not left_path.exists() or not right_path.exists():
        return None
    try:
        with Image.open(left_path) as left_raw, Image.open(right_path) as right_raw:
            left_image = ImageOps.exif_transpose(left_raw).convert("RGB").resize(
                (256, 256), Image.Resampling.LANCZOS
            )
            right_image = ImageOps.exif_transpose(right_raw).convert("RGB").resize(
                (256, 256), Image.Resampling.LANCZOS
            )
            diff = ImageChops.difference(left_image, right_image).convert("L")
            return float(ImageStat.Stat(diff).mean[0])
    except OSError:
        return None


def find_reviewed_duplicate_candidates(
    db: Database,
    project_root: Path,
    *,
    dhash_threshold: int = 4,
    ahash_threshold: int = 2,
    max_pixel_difference: float = 4.0,
) -> list[DuplicateCandidate]:
    """Find unreviewed consensus rows that duplicate an already-reviewed image."""
    pending = queries.list_unreviewed_fingerprinted_consensus_memes(db)
    reviewed = queries.list_reviewed_fingerprinted_memes(db)
    candidates: list[DuplicateCandidate] = []

    for item in pending:
        best: DuplicateCandidate | None = None
        for match in reviewed:
            if item.post_id == match.post_id:
                continue
            dhash_dist = hamming_distance(item.dhash, match.dhash)
            ahash_dist = hamming_distance(item.ahash, match.ahash)
            exact_match = item.exact_hash == match.exact_hash
            pixel_difference = None
            perceptual_hash_match = _aspect_ratio_close(item, match) and (
                dhash_dist <= dhash_threshold
                or (dhash_dist <= dhash_threshold * 2 and ahash_dist <= ahash_threshold)
            )
            if perceptual_hash_match and not exact_match:
                pixel_difference = _mean_abs_pixel_difference(project_root, item, match)
            perceptual_match = (
                perceptual_hash_match
                and pixel_difference is not None
                and pixel_difference <= max_pixel_difference
            )
            if not exact_match and not perceptual_match:
                continue

            candidate = DuplicateCandidate(
                post_id=item.post_id,
                matched_post_id=match.post_id,
                matched_status=match.review_status or "reviewed",
                reason=f"duplicate_image:{match.post_id}",
                exact_match=exact_match,
                dhash_distance=dhash_dist,
                ahash_distance=ahash_dist,
                pixel_difference=pixel_difference,
            )
            if best is None:
                best = candidate
            elif candidate.exact_match and not best.exact_match:
                best = candidate
            elif (
                candidate.exact_match == best.exact_match
                and candidate.dhash_distance + candidate.ahash_distance
                < best.dhash_distance + best.ahash_distance
            ):
                best = candidate
        if best is not None:
            candidates.append(best)

    return candidates


def auto_exclude_duplicate_images(
    db: Database,
    project_root: Path,
    *,
    dry_run: bool = False,
    dhash_threshold: int = 4,
    ahash_threshold: int = 2,
    max_pixel_difference: float = 4.0,
) -> DuplicateCleanupResult:
    """Fingerprint images and exclude unreviewed rows that duplicate reviewed rows."""
    written = backfill_image_fingerprints(db, project_root)
    candidates = find_reviewed_duplicate_candidates(
        db,
        project_root,
        dhash_threshold=dhash_threshold,
        ahash_threshold=ahash_threshold,
        max_pixel_difference=max_pixel_difference,
    )
    excluded = 0
    if not dry_run:
        for candidate in candidates:
            if queries.insert_auto_review(db, candidate.post_id, candidate.reason):
                excluded += 1
    return DuplicateCleanupResult(written, candidates, excluded)
