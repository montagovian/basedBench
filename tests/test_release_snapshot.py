"""Exact-byte and failure tests for immutable release snapshots."""

from __future__ import annotations

import copy
import hashlib
import io
import json
import threading

import pytest
from PIL import Image

from basedbench.pipeline.release_snapshot import (
    canonical_bytes,
    evaluation_inputs,
    freeze_release,
    load_release,
)


def _png(color: str) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (3, 2), color).save(buffer, format="PNG")
    return buffer.getvalue()


def _jpeg(color: str) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), color).save(buffer, format="JPEG")
    return buffer.getvalue()


def _item(post_id: str, *, cohort: str = "development") -> dict:
    return {
        "post_id": post_id,
        "title": f"title {post_id}",
        "subreddit": "memes",
        "ground_truth": f"A reference to {post_id} — exact joke.",
        "image_path": f"assets/{post_id}.png",
        "cohort": cohort,
        "exposure": "unknown",
        "admission_origin": "human_curated" if cohort == "development" else "unknown",
        "policy_version": "release-gates-v1",
        "answer_readiness": "ready" if cohort == "development" else "unknown",
        "source_support": "pass" if cohort == "development" else "unknown",
        "content_status": "pass" if cohort == "development" else "unknown",
        "suitability": "pass" if cohort == "development" else "unknown",
        "duplicate_status": "pass" if cohort == "development" else "unknown",
        "rights_status": "mixed_rights" if cohort == "development" else "unknown",
        "answer_provenance": {"event_id": f"event-{post_id}", "private_path": "local/ledger"},
    }


@pytest.fixture
def source(tmp_path):
    root = tmp_path / "source"
    (root / "assets").mkdir(parents=True)
    (root / "assets" / "a.png").write_bytes(_png("red"))
    (root / "assets" / "b.png").write_bytes(_png("blue"))
    return root


@pytest.fixture
def selection():
    return {
        "name": "candidate-v1",
        "policy_version": "release-gates-v1",
        "description": "An exact local candidate",
        "evaluation": {"model_panel": ["model-a"], "prediction_prompt_id": "predict-v1"},
        "items": [_item("b", cohort="legacy"), _item("a")],
    }


def test_freeze_is_deterministic_and_self_contained(source, selection, tmp_path):
    first = tmp_path / "first"
    manifest = freeze_release(selection, first, source_root=source)
    reordered = copy.deepcopy(selection)
    reordered["items"].reverse()
    second = tmp_path / "second"
    same = freeze_release(reordered, second, source_root=source)

    assert manifest == same == load_release(first) == load_release(second)
    assert (first / "manifest.json").read_bytes() == (second / "manifest.json").read_bytes()
    assert [item["post_id"] for item in manifest["items"]] == ["a", "b"]
    assert manifest["membership_sha256"] == hashlib.sha256(canonical_bytes(["a", "b"])).hexdigest()
    unsigned = {key: value for key, value in manifest.items() if key != "content_sha256"}
    assert manifest["content_sha256"] == hashlib.sha256(canonical_bytes(unsigned)).hexdigest()
    assert manifest["evaluation"] == {
        "model_panel": ["model-a"], "prediction_prompt_id": "predict-v1",
        "judge_prompt_id": None, "scoring_version": "majority-v1",
    }
    assert "image_path" not in manifest["items"][0]
    assert manifest["items"][0]["answer_sha256"] == hashlib.sha256(
        selection["items"][1]["ground_truth"].encode("utf-8")
    ).hexdigest()

    inputs = evaluation_inputs(first)
    assert [set(row) for row in inputs] == [
        {"post_id", "image_path", "image_sha256"},
        {"post_id", "image_path", "image_sha256"},
    ]
    assert inputs[0]["image_path"] == str(first / "images" / "a.png")

    # The source text, image and selected data can all change after freezing.
    source.joinpath("assets", "a.png").write_bytes(_png("green"))
    selection["items"][1]["ground_truth"] = "new answer"
    selection["items"][1]["answer_provenance"]["event_id"] = "new-event"
    assert load_release(first) == manifest
    assert (first / "images" / "a.png").read_bytes() == _png("red")
    assert evaluation_inputs(first) == inputs


@pytest.mark.parametrize("change", [
    {"post_id": "../escape"},
    {"post_id": "a/b"},
    {"ground_truth": ""},
    {"answer_readiness": "repair"},
    {"source_support": "unknown"},
    {"rights_status": "unknown"},
    {"admission_origin": "unknown"},
    {"admission_origin": "legacy_human_validated"},
    {"exposure": "unseen"},
    {"cohort": "other"},
    {"answer_provenance": {"bad": float("nan")}},
    {"image_path": "../outside.png"},
    {"image_path": "assets/missing.png"},
])
def test_invalid_selection_fails_atomically(source, selection, tmp_path, change):
    selection["items"][1].update(change)
    output = tmp_path / "candidate"
    with pytest.raises(ValueError):
        freeze_release(selection, output, source_root=source)
    assert not output.exists()
    assert not list(tmp_path.glob(".candidate.tmp-*"))


def test_invalid_image_and_symlink_are_rejected(source, selection, tmp_path):
    (source / "assets" / "a.png").write_bytes(b"not an image")
    with pytest.raises(ValueError, match="invalid image"):
        freeze_release(selection, tmp_path / "bad", source_root=source)
    (source / "assets" / "a.png").unlink()
    (source / "assets" / "a.png").symlink_to(source / "assets" / "b.png")
    with pytest.raises(ValueError, match="symlink"):
        freeze_release(selection, tmp_path / "linked", source_root=source)


def test_truncated_jpeg_fails_full_decode(source, selection, tmp_path):
    (source / "assets" / "a.png").write_bytes(_jpeg("red")[:-20])
    with pytest.raises(ValueError, match="invalid image"):
        freeze_release(selection, tmp_path / "truncated", source_root=source)
    assert not (tmp_path / "truncated").exists()


def test_frozen_extension_uses_decoded_image_format(source, selection, tmp_path):
    (source / "assets" / "a.png").write_bytes(_jpeg("red"))
    output = tmp_path / "canonical-extension"
    manifest = freeze_release(selection, output, source_root=source)
    assert manifest["items"][0]["image_filename"] == "a.jpg"
    assert (output / "images" / "a.jpg").read_bytes() == _jpeg("red")
    assert load_release(output) == manifest
    (output / "images" / "a.jpg").rename(output / "images" / "a.png")
    manifest["items"][0]["image_filename"] = "a.png"
    unsigned = {key: value for key, value in manifest.items() if key != "content_sha256"}
    manifest["content_sha256"] = hashlib.sha256(canonical_bytes(unsigned)).hexdigest()
    (output / "manifest.json").write_bytes(canonical_bytes(manifest))
    with pytest.raises(ValueError, match="format/extension mismatch"):
        load_release(output)


def test_cooperative_lock_refuses_simultaneous_freeze(source, selection, tmp_path, monkeypatch):
    from basedbench.pipeline import release_snapshot

    entered = threading.Event()
    resume = threading.Event()
    original = release_snapshot._image_bytes

    def slow_image(path):
        if not entered.is_set():
            entered.set()
            assert resume.wait(timeout=3)
        return original(path)

    monkeypatch.setattr(release_snapshot, "_image_bytes", slow_image)
    output = tmp_path / "concurrent"
    errors = []

    def first_freeze():
        try:
            freeze_release(selection, output, source_root=source)
        except Exception as exc:
            errors.append(exc)

    thread = threading.Thread(target=first_freeze)
    thread.start()
    assert entered.wait(timeout=3)
    try:
        with pytest.raises(ValueError, match="already being frozen"):
            freeze_release(selection, output, source_root=source)
    finally:
        resume.set()
        thread.join(timeout=3)
    assert not errors
    assert not thread.is_alive()
    assert load_release(output)["name"] == "candidate-v1"
    assert not (tmp_path / ".concurrent.lock").exists()


def test_existing_destination_is_preserved(source, selection, tmp_path):
    output = tmp_path / "candidate"
    output.mkdir()
    marker = output / "marker"
    marker.write_text("preserve me")
    with pytest.raises(ValueError, match="exists"):
        freeze_release(selection, output, source_root=source)
    assert marker.read_text() == "preserve me"


def test_paths_cannot_escape_source_root(source, selection, tmp_path):
    outside = tmp_path / "outside.png"
    outside.write_bytes(_png("black"))
    selection["items"][1]["image_path"] = str(outside)
    with pytest.raises(ValueError, match="within source_root"):
        freeze_release(selection, tmp_path / "outside-release", source_root=source)

    (source / "assets" / "linked").symlink_to(tmp_path, target_is_directory=True)
    selection["items"][1]["image_path"] = "assets/linked/outside.png"
    with pytest.raises(ValueError, match="symlink"):
        freeze_release(selection, tmp_path / "symlink-release", source_root=source)


def test_tampering_and_partial_release_fail_on_every_read(source, selection, tmp_path):
    cases = ["image", "answer", "membership", "extra", "missing", "symlink", "schema"]
    for case in cases:
        output = tmp_path / case
        freeze_release(selection, output, source_root=source)
        manifest_path = output / "manifest.json"
        if case == "image":
            (output / "images" / "a.png").write_bytes(_png("green"))
        elif case in {"answer", "membership", "schema"}:
            payload = json.loads(manifest_path.read_text())
            if case == "answer":
                payload["items"][0]["ground_truth"] = "tampered"
            elif case == "membership":
                payload["membership_sha256"] = "0" * 64
            else:
                payload["schema_version"] = "unsupported"
            manifest_path.write_bytes(canonical_bytes(payload))
        elif case == "extra":
            (output / "images" / "unexpected.png").write_bytes(_png("green"))
        elif case == "missing":
            (output / "images" / "a.png").unlink()
        elif case == "symlink":
            (output / "images" / "a.png").unlink()
            (output / "images" / "a.png").symlink_to(source / "assets" / "a.png")
        with pytest.raises(ValueError):
            load_release(output)
        with pytest.raises(ValueError):
            evaluation_inputs(output)


def test_canonical_json_is_utf8_sorted_strict_and_newline_terminated():
    assert canonical_bytes({"z": 1, "a": "é"}) == b'{"a":"\xc3\xa9","z":1}\n'
    with pytest.raises(ValueError):
        canonical_bytes({"nonfinite": float("inf")})
    with pytest.raises(ValueError):
        canonical_bytes({1: "numeric key"})


def test_noncanonical_or_unsafe_forged_manifest_is_rejected(source, selection, tmp_path):
    output = tmp_path / "candidate"
    freeze_release(selection, output, source_root=source)
    manifest_path = output / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest_path.write_text(json.dumps(manifest, indent=2))
    with pytest.raises(ValueError, match="canonical"):
        load_release(output)

    manifest["items"][0]["image_filename"] = "a.png/../../outside.png"
    unsigned = {key: value for key, value in manifest.items() if key != "content_sha256"}
    manifest["content_sha256"] = hashlib.sha256(canonical_bytes(unsigned)).hexdigest()
    manifest_path.write_bytes(canonical_bytes(manifest))
    with pytest.raises(ValueError, match="image_filename"):
        load_release(output)


def test_legacy_unknown_gates_are_explicitly_grandfathered(source, selection, tmp_path):
    selection["items"] = [_item("b", cohort="legacy")]
    output = tmp_path / "legacy"
    manifest = freeze_release(selection, output, source_root=source)
    assert manifest["items"][0]["source_support"] == "unknown"
    assert load_release(output) == manifest
