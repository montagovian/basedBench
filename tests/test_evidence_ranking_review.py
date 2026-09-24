import hashlib
import http.client
import json
import threading

import pytest

from basedbench.evidence_ranking_review import ConflictError, ReviewStore, make_server, _json_hash


def packet(tmp_path):
    root = tmp_path / "packet"
    root.mkdir()
    (root / "images").mkdir()
    image = root / "images" / hashlib.sha256(b"image").hexdigest()
    image.write_bytes(b"\x89PNG\r\n\x1a\n" + b"test")
    cases = []
    for index in range(16):
        cases.append({"review_id": f"r{index}", "family_id": f"f{index}", "case_id": f"c{index}",
                      "sample_kind": "sampled", "image_path": f"images/{image.name}",
                      "comments": [{"id": "c0", "text": "A <script> clue"}],
                      "reference_explanation": "Reference <script> explanation",
                      "methods": {"A": "rank", "B": "collate", "C": "order"},
                      "packs": {choice: {"status": "completed", "excerpts": [{"comment_id": "c0", "text": "A <script> clue", "partial": False}],
                                         "word_count": 3, "budget_words": 6} for choice in "ABC"}})
    cases[0]["packs"]["B"] = {"status": "unavailable"}
    cases[0]["packs"]["A"]["ranking"] = [{"comment_id": "c0", "utility": .8}]
    cases[0]["packs"]["C"]["groups"] = [{"representative_id": "c0", "member_ids": ["c0", "c1"], "duplicate_ids": ["c1"]}]
    cases[0]["packs"]["C"]["sections"] = {"source_pointers": ["c0"], "alternative_readings": ["c1"]}
    cases[0]["packs"]["C"]["pairs"] = [{"first_id": "c0", "second_id": "c1", "same_claim": .9, "conflicting": .1}]
    source = root / "review-cases.json"
    source.write_text(json.dumps(cases), encoding="utf-8")
    manifest = {"cases_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "image_hashes": {f"r{i}": hashlib.sha256(image.read_bytes()).hexdigest() for i in range(16)}}
    manifest["packet_id"] = _json_hash(manifest)
    (root / "review-manifest.json").write_text(json.dumps(manifest))
    return root


def feedback(store, request_id="save1", revision=None):
    return {"packet_id": store.manifest["packet_id"], "review_id": "r0", "request_id": request_id,
            "base_revision": revision, "ratings": {choice: {"clue": "yes", "misleading": "no"} for choice in "AC"},
            "most_useful": "A", "note": "Useful"}


def test_blind_save_reveal_reload_and_append_only_events(tmp_path):
    root = packet(tmp_path)
    store = ReviewStore(root)
    catalog = store.catalog()
    assert len(catalog["cases"]) == 16
    assert '"methods":' not in json.dumps(catalog)
    assert "reference_explanation" not in json.dumps(catalog)
    with pytest.raises(PermissionError):
        store.reveal({"packet_id": store.manifest["packet_id"], "review_id": "r0", "request_id": "early", "base_revision": None})
    context = store.context({"packet_id": store.manifest["packet_id"], "review_id": "r0", "request_id": "ctx1", "base_revision": None, "source": "comments"})
    assert "<script>" in context["context"]["comments"][0]["text"]
    saved = store.save(feedback(store))
    assert saved["state"]["revision"]
    assert saved["state"]["source_opened"]
    assert store.events()[-1]["methods_revealed_before"] is False
    reveal_request = {"packet_id": store.manifest["packet_id"], "review_id": "r0", "request_id": "reveal1", "base_revision": saved["state"]["revision"]}
    revealed = store.reveal(reveal_request)
    assert revealed["methods"] == {"A": "rank", "B": "collate", "C": "order"}
    assert revealed["inspection"]["C"]["groups"][0]["duplicate_ids"] == ["c1"]
    assert len(store.events()) == 3
    assert store.reveal(reveal_request)["event_id"] == revealed["event_id"]
    assert store.reveal({**reveal_request, "request_id": "reveal2"})["event_id"] == revealed["event_id"]
    assert store.save(feedback(store))["event_id"] == saved["event_id"]
    assert len(store.events()) == 3
    reloaded = ReviewStore(root)
    assert reloaded.catalog()["cases"][0]["state"]["ratings"]["A"]["clue"] == "yes"
    assert reloaded.catalog()["cases"][0]["state"]["methods_revealed"]
    revision = saved["state"]["revision"]
    reloaded.save(feedback(reloaded, "save2", revision))
    assert reloaded.events()[-1]["methods_revealed_before"] is True


def test_conflict_schema_and_manifest_guard(tmp_path):
    root = packet(tmp_path)
    store = ReviewStore(root)
    with pytest.raises(ValueError, match="available"):
        bad = feedback(store)
        bad["ratings"]["B"] = {"clue": "yes", "misleading": "no"}
        store.save(bad)
    with pytest.raises(ValueError, match="available"):
        bad = feedback(store)
        bad["most_useful"] = "B"
        store.save(bad)
    saved = store.save(feedback(store))
    with pytest.raises(ConflictError, match="Request ID"):
        store.save({**feedback(store), "note": "changed"})
    with pytest.raises(ConflictError, match="another window"):
        store.save(feedback(store, "save2", None))
    assert store.save(feedback(store, "save2", saved["state"]["revision"]))["state"]["note"] == "Useful"
    (root / "review-manifest.json").write_text(json.dumps({**store.manifest, "plan_id": "tampered"}))
    with pytest.raises(ValueError, match="packet ID"):
        ReviewStore(root)
    (root / "review-manifest.json").write_text(json.dumps(store.manifest))
    (root / "review-cases.json").write_text("[]")
    with pytest.raises(ValueError, match="manifest"):
        ReviewStore(root)


def test_http_origin_token_blinding_and_safe_images(tmp_path):
    root = packet(tmp_path)
    server = make_server(root, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host = f"127.0.0.1:{server.server_port}"

    def call(method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", server.server_port)
        conn.request(method, path, body=body, headers={"Host": host, **(headers or {})})
        response = conn.getresponse()
        data = response.read()
        conn.close()
        return response.status, data

    try:
        code, raw = call("GET", "/api/cases")
        assert code == 200 and b'"methods":' not in raw and b"reference_explanation" not in raw
        token = json.loads(raw)["token"]
        assert call("GET", "/api/reveal/r0")[0] == 404
        assert call("GET", "/image/../../review-cases.json")[0] == 404
        assert call("GET", "/api/cases", headers={"Origin": "http://evil.test"})[0] == 403
        local_store = ReviewStore(root)
        request = json.dumps(feedback(local_store)).encode()
        assert call("POST", "/api/feedback", request, {"Content-Type": "application/json"})[0] == 403
        headers = {"Content-Type": "application/json", "X-Review-Token": token}
        early = json.dumps({"packet_id": local_store.manifest["packet_id"], "review_id": "r0", "request_id": "early", "base_revision": None}).encode()
        assert call("POST", "/api/reveal", early, headers)[0] == 403
        assert call("POST", "/api/feedback", request, headers)[0] == 200
        saved_revision = json.loads(call("GET", "/api/cases")[1])["cases"][0]["state"]["revision"]
        reveal = json.dumps({"packet_id": local_store.manifest["packet_id"], "review_id": "r0", "request_id": "reveal1", "base_revision": saved_revision}).encode()
        code, raw = call("POST", "/api/reveal", reveal, headers)
        assert code == 200 and json.loads(raw)["methods"]["A"] == "rank"
        assert json.loads(raw)["inspection"]["C"]["sections"]["source_pointers"] == ["c0"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
