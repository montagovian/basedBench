"""Feedback provenance, append-only revisions, hidden opinions and HTTP boundaries."""

import json
import threading
from pathlib import Path

import httpx
import pytest
from PIL import Image

from basedbench import curation_review as review
from basedbench.pipeline.curation_corpus import digest, file_hash, write_json, write_jsonl


@pytest.fixture
def sources(tmp_path, monkeypatch):
    corpus, run = tmp_path / "corpus", tmp_path / "run"
    (corpus / "assets").mkdir(parents=True)
    run.mkdir()
    image = tmp_path / "image.png"
    Image.new("RGB", (30, 20), "green").save(image)
    sha = file_hash(image)
    (corpus / "assets" / sha).write_bytes(image.read_bytes())
    rows = []
    for i in range(64):
        model_input = {"image_sha256": sha, "explanation": f"Answer {i}", "comment_evidence": f"Private comments {i}"}
        rows.append({"post_id": f"p{i}", "input": model_input, "input_sha256": digest(model_input),
                     "split": "test" if i >= 55 else "calibration", "group_id": f"group{i}",
                     "label": "accept" if i % 3 else "reject", "provenance": {"reviewed_at": "2026-05-01"}})
    # Prior discussion, an API reference, and related copies must not leak into controls.
    rows[18]["group_id"] = rows[0]["group_id"]
    rows[19]["group_id"] = rows[17]["group_id"]
    monkeypatch.setattr(review, "load_corpus", lambda _: ({"corpus_id": "test-corpus"}, rows))
    plan = {"corpus_id": "test-corpus", "arms": ["luna_direct", "luna_checks", "luna_image_checks", "jev"],
            "evaluation_ids": [r["post_id"] for r in rows[1:17]], "reference_ids": ["p17"],
            "input_hashes": {r["post_id"]: r["input_sha256"] for r in rows[1:17]}}
    write_json(run / "plan.json", plan)
    decisions = [{"post_id": r["post_id"], "input_sha256": r["input_sha256"], "model": "model:" + arm,
                  "decision": "accept" if arm == "jev" else "reject"}
                 for r in rows[1:17] for arm in plan["arms"]]
    write_jsonl(run / "decisions.jsonl", decisions)
    write_jsonl(run / "components.jsonl", [])
    prior = tmp_path / "prior.jsonl"
    write_jsonl(prior, [{"corpus_id": "test-corpus", "recorded_at": "2026-09-18", "items": [
        {"post_id": "p0", "input_sha256": rows[0]["input_sha256"], "current_decision": None,
         "reason": "Tentative and unresolved", "decision_status": "unresolved"}]}])
    return corpus, run, prior, rows


@pytest.fixture
def packet(tmp_path, sources):
    corpus, run, prior, _ = sources
    output = tmp_path / "packet"
    review.prepare_packet(corpus, run, prior, output)
    return output


def request_for(store, **changes):
    case = next(c for c in store.cases.values() if c["stratum"] != "previous_discussion")
    return review.ReviewRequest(**({"request_id": "first-request", "packet_id": store.manifest["packet_id"],
        "post_id": case["post_id"], "input_sha256": case["input_sha256"],
        "fields": {"ground_truth": "repair"}, "notes": "Misses the punchline"} | changes))


def test_preparation_is_reproducible_excludes_test_and_known_exposures(packet, tmp_path, sources):
    corpus, run, prior, _ = sources
    again = tmp_path / "again"
    result = review.prepare_packet(corpus, run, prior, again)
    assert result == json.loads((packet / "manifest.json").read_text())
    cases = list(review.ReviewStore(packet).cases.values())
    fresh = [c for c in cases if c["stratum"] != "previous_discussion"]
    assert len(fresh) == len({c["group_id"] for c in fresh}) == 28
    assert not {"p0", "p17", "p18", "p19"} & {c["post_id"] for c in fresh}
    assert all(c["split"] != "test" for c in cases)
    assert sum(c["stratum"] == "random_control" for c in cases) == 16
    assert sum(c["stratum"] == "targeted" for c in cases) == 12
    with pytest.raises(FileExistsError):
        review.prepare_packet(corpus, run, prior, packet)


def test_catalog_hides_comments_models_history_and_sampling_labels(packet):
    catalog = review.ReviewStore(packet).catalog()
    text = json.dumps(catalog)
    for private in ["Private comments", "historical_label", "targeted", "model:jev", "Tentative and unresolved"]:
        assert private not in text
    assert all(c["explanation"].startswith("Answer") for c in catalog["cases"])


def test_partial_feedback_revision_and_idempotency_survive_restart(packet):
    store = review.ReviewStore(packet)
    first = request_for(store)
    result = store.append(first)
    # No overall accept/reject or other dimension is inferred from an answer repair.
    assert result["event"]["fields"] == {"ground_truth": "repair"}
    assert result["event"]["rubric_sha256"] == store.manifest["rubric_sha256"]
    assert store.append(first)["event"]["event_id"] == result["event"]["event_id"]
    restarted = review.ReviewStore(packet)
    assert len(restarted.events()) == 1
    second = first.model_copy(update={"request_id": "revision", "base_revision": result["event"]["event_id"],
                                      "fields": {"content": "boundary", "admission": "undecided"}})
    revised = restarted.append(second)
    assert revised["state"]["save_count"] == 2
    assert restarted.events()[0] == result["event"]
    assert revised["event"]["base_revision"] == result["event"]["event_id"]
    with pytest.raises(review.ConflictError):
        store.append(first.model_copy(update={"request_id": "stale-window"}))
    with pytest.raises(review.ConflictError):
        store.append(first.model_copy(update={"notes": "Different contents for same id"}))


def test_reveal_preserves_before_and_after_context_without_forcing_verdict(packet):
    store = review.ReviewStore(packet)
    before = request_for(store, kind="reveal", reveal="comments", fields={"familiarity": "unclear"})
    opened = store.append(before)
    assert opened["event"]["exposed_before"] == []
    assert opened["context"]["comments"].startswith("Private comments")
    assert opened["state"]["latest"] is None
    restarted = review.ReviewStore(packet)
    after = restarted.append(request_for(store, request_id="after", fields={"value": "yes", "familiarity": "needed_context"}))
    assert after["event"]["exposed_before"] == ["comments"]
    assert after["state"]["save_count"] == 1
    assert len(restarted.events()) == 2


@pytest.mark.parametrize("changes", [
    {"input_sha256": "wrong"}, {"packet_id": "wrong"}, {"post_id": "test-case"},
    {"fields": {"content": "accept"}}, {"fields": {"invented": "yes"}},
    {"fields": {}, "notes": " "}, {"kind": "reveal", "reveal": "secrets"},
])
def test_invalid_feedback_never_appends(packet, changes):
    store = review.ReviewStore(packet)
    with pytest.raises(ValueError):
        store.append(request_for(store, **changes))
    assert store.events() == []


def test_changed_packet_is_rejected(packet):
    (packet / "cases.json").write_text("[]")
    with pytest.raises(ValueError, match="integrity"):
        review.ReviewStore(packet)


def test_http_save_and_origin_boundaries(packet):
    server = review.make_server(packet, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{server.server_port}", trust_env=False) as client:
            catalog = client.get("/api/cases").json()
            case = catalog["cases"][0]
            assert client.get(case["image_url"]).headers["content-type"] == "image/png"
            assert client.get("/").status_code == 200
            assert client.get("/cases.json").status_code == 404
            assert client.get("/api/cases", headers={"Host": "attacker.example"}).status_code == 403
            payload = {"request_id": "http-request", "packet_id": catalog["packet_id"], "post_id": case["post_id"],
                       "input_sha256": case["input_sha256"], "fields": {"value": "yes"}}
            assert client.post("/api/events", json=payload).status_code == 403
            headers = {"X-Review-Token": catalog["token"], "Origin": "https://attacker.example"}
            assert client.post("/api/events", json=payload, headers=headers).status_code == 403
            headers.pop("Origin")
            result = client.post("/api/events", json=payload, headers=headers)
            assert result.status_code == 200
            assert client.get("/api/cases").json()["cases"][0]["latest"]["fields"] == {"value": "yes"}
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
