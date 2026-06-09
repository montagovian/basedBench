from __future__ import annotations

import base64

from PIL import Image

from basedbench.llm.prompts import load_image_base64, load_image_base64_under_limit


def test_load_image_base64_under_limit_preserves_small_file(tmp_path):
    path = tmp_path / "small.png"
    Image.new("RGB", (16, 16), "red").save(path)

    regular_b64, regular_mime = load_image_base64(path)
    capped_b64, capped_mime = load_image_base64_under_limit(path, max_bytes=10_000)

    assert capped_b64 == regular_b64
    assert capped_mime == regular_mime


def test_load_image_base64_under_limit_compresses_large_file(tmp_path):
    path = tmp_path / "large.png"
    image = Image.effect_noise((512, 512), 100).convert("RGB")
    image.save(path)
    assert path.stat().st_size > 20_000

    capped_b64, capped_mime = load_image_base64_under_limit(
        path,
        max_bytes=20_000,
        max_dimension=512,
    )

    assert capped_mime == "image/jpeg"
    assert len(base64.standard_b64decode(capped_b64)) <= 20_000
