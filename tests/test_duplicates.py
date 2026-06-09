from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from basedbench.db import Database
from basedbench.db import queries as q
from basedbench.pipeline.duplicates import (
    auto_exclude_duplicate_images,
    backfill_image_fingerprints,
    hamming_distance,
)

from .conftest import sample_post


def _write_test_image(
    path: Path,
    *,
    accent: str = "red",
    text: str = "dupe",
    image_format: str = "PNG",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (80, 60), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((10, 8, 70, 52), outline="black", width=3)
    draw.line((12, 48, 68, 12), fill=accent, width=4)
    draw.text((16, 20), text, fill="black")
    image.save(path, image_format)


def _insert_grounded_meme(db: Database, post_id: str, local_path: str) -> None:
    q.insert_meme(db, sample_post(post_id))
    q.update_meme_image_path(db, post_id, local_path)
    q.upsert_ground_truth(
        db,
        post_id,
        "The joke is duplicated.",
        0.95,
        [f"{post_id}_c1", f"{post_id}_c2"],
        3,
        20.0,
        "model",
        "prompt",
    )


def test_hamming_distance_hex_hashes() -> None:
    assert hamming_distance("0000", "0000") == 0
    assert hamming_distance("0000", "000f") == 4


def test_backfill_image_fingerprints(db: Database, tmp_path: Path) -> None:
    _write_test_image(tmp_path / "data/images/p1.png")
    _insert_grounded_meme(db, "p1", "data/images/p1.png")

    assert backfill_image_fingerprints(db, tmp_path) == 1
    row = db.conn.execute(
        "SELECT post_id, exact_hash, width, height FROM image_fingerprints"
    ).fetchone()
    assert row[0] == "p1"
    assert len(row[1]) == 64
    assert row[2:] == (80, 60)


def test_auto_exclude_duplicate_images_matches_reviewed_image(
    db: Database, tmp_path: Path
) -> None:
    _write_test_image(tmp_path / "data/images/reviewed.png", image_format="PNG")
    _write_test_image(tmp_path / "data/images/pending.jpg", image_format="JPEG")
    _insert_grounded_meme(db, "reviewed", "data/images/reviewed.png")
    _insert_grounded_meme(db, "pending", "data/images/pending.jpg")
    q.upsert_review(db, "reviewed", "excluded", "human said duplicate source")

    result = auto_exclude_duplicate_images(db, tmp_path)

    assert result.excluded == 1
    assert [c.post_id for c in result.candidates] == ["pending"]
    review = db.conn.execute(
        "SELECT status, reason FROM reviews WHERE post_id = 'pending'"
    ).fetchone()
    assert review == ("excluded", "duplicate_image:reviewed")


def test_duplicate_cleanup_ignores_same_template_with_different_text(
    db: Database, tmp_path: Path
) -> None:
    _write_test_image(
        tmp_path / "data/images/template_a.png",
        text="alpha alpha alpha",
        image_format="PNG",
    )
    _write_test_image(
        tmp_path / "data/images/template_b.jpg",
        text="omega omega omega",
        image_format="JPEG",
    )
    _insert_grounded_meme(db, "template_a", "data/images/template_a.png")
    _insert_grounded_meme(db, "template_b", "data/images/template_b.jpg")
    q.upsert_review(db, "template_a", "excluded", "not good enough")

    result = auto_exclude_duplicate_images(db, tmp_path, max_pixel_difference=1.0)

    assert result.candidates == []
    review = db.conn.execute(
        "SELECT status, reason FROM reviews WHERE post_id = 'template_b'"
    ).fetchone()
    assert review is None


def test_duplicate_cleanup_does_not_choose_between_unreviewed_duplicates(
    db: Database, tmp_path: Path
) -> None:
    _write_test_image(tmp_path / "data/images/pending_a.png")
    _write_test_image(tmp_path / "data/images/pending_b.jpg", image_format="JPEG")
    _insert_grounded_meme(db, "pending_a", "data/images/pending_a.png")
    _insert_grounded_meme(db, "pending_b", "data/images/pending_b.jpg")

    result = auto_exclude_duplicate_images(db, tmp_path)

    assert result.candidates == []
    reviews = db.conn.execute("SELECT post_id FROM reviews").fetchall()
    assert reviews == []
