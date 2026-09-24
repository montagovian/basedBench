import hashlib
import http.client
import json
import threading

import pytest

from basedbench.comment_selection_review import ConflictError, ReviewStore, _json_hash, make_server


def packet(tmp_path):
    root = tmp_path / "packet"
    root.mkdir()
    (root / "images").mkdir()
    image = root / "images" / "meme.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n" + b"test")
    texts = ["A <script> clue", "Another whole clue", "A third clue", "More context"]
    comments = [{"id": f"c{i}", "text": value} for i, value in enumerate(texts)]

    def pack(ids):
        def excerpt(i):
            return {"comment_id": f"c{i}", "text": texts[i], "start": 0, "end": len(texts[i]), "partial": False}
        first = [excerpt(i) for i in ids[:3]]
        more = [excerpt(i) for i in ids[3:]]
        return {"status": "completed", "excerpts": first, "extra_excerpts": more,
                "selected_ids": [f"c{i}" for i in ids[:3]], "retained_ids": [f"c{i}" for i in ids],
                "excluded_ids": [f"c{i}" for i in range(len(texts)) if i not in ids],
                "word_count": sum(len(e["text"].split()) for e in first),
                "total_word_count": sum(len(e["text"].split()) for e in first + more)}

    cases = []
    for i in range(8):
        cases.append({"review_id": f"r{i}", "family_id": f"f{i}", "case_id": f"case{i}",
                      "sample_kind": "development" if i < 4 else "newly_reviewed", "image_path": "images/meme.png",
                      "comments": comments, "methods": {"A": "baseline", "B": "pairwise"},
                      "packs": {"A": pack([0, 1, 2, 3]), "B": pack([0, 1, 2, 3] if i == 0 else [1, 2])}})
    cases[1]["packs"]["B"] = {"status": "unavailable"}
    source = root / "review-cases.json"
    source.write_text(json.dumps(cases), encoding="utf-8")
    manifest = {"plan_id": "plan1", "cases_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "image_hashes": {f"r{i}": hashlib.sha256(image.read_bytes()).hexdigest() for i in range(8)}}
    manifest["packet_id"] = _json_hash(manifest)
    (root / "review-manifest.json").write_text(json.dumps(manifest))
    return root


def feedback(store, request_id="save1", revision=None):
    return {"packet_id": store.manifest["packet_id"], "review_id": "r0", "request_id": request_id,
            "base_revision": revision, "ratings": {choice: {"first_helps": "yes", "irrelevant_extras": "no"} for choice in "AB"},
            "preference": "A", "note": "Possible factual concern"}


def test_blind_persistence_revision_and_reveal(tmp_path):
    root = packet(tmp_path)
    store = ReviewStore(root)
    catalog = store.catalog()
    assert len(catalog["cases"]) == 8
    assert catalog["cases"][0]["identical_initial_lists"]
    assert catalog["cases"][1]["packs"]["B"] == {"status": "unavailable"}
    assert all("methods" not in case for case in catalog["cases"])
    assert "pairwise" not in json.dumps(catalog)
    assert "<script>" in json.dumps(catalog)
    with pytest.raises(PermissionError):
        store.reveal({"packet_id": store.manifest["packet_id"], "review_id": "r0", "request_id": "early", "base_revision": None})
    saved = store.save(feedback(store))
    assert saved["state"]["revision"]
    assert store.save(feedback(store))["event_id"] == saved["event_id"]
    with pytest.raises(ConflictError, match="Request ID"):
        store.save({**feedback(store), "note": "Changed"})
    with pytest.raises(ConflictError, match="another window"):
        store.save(feedback(store, "save2"))
    reveal = {"packet_id": store.manifest["packet_id"], "review_id": "r0", "request_id": "reveal1", "base_revision": saved["state"]["revision"]}
    result = store.reveal(reveal)
    assert result["methods"] == {"A": "baseline", "B": "pairwise"}
    assert store.reveal(reveal)["event_id"] == result["event_id"]
    assert store.reveal({**reveal, "request_id": "reveal2"})["event_id"] == result["event_id"]
    assert len(store.events()) == 2
    reloaded = ReviewStore(root)
    assert reloaded.catalog()["cases"][0]["methods"] == result["methods"]
    assert reloaded.catalog()["cases"][0]["state"]["note"] == "Possible factual concern"
    reloaded.save(feedback(reloaded, "save2", saved["state"]["revision"]))
    assert reloaded.events()[-1]["methods_revealed_before"] is True


def test_provenance_manifest_and_image_guards(tmp_path):
    root = packet(tmp_path)
    source = root / "review-cases.json"
    original = source.read_text()
    cases = json.loads(original)
    cases[0]["packs"]["A"]["excerpts"][0]["text"] = "Altered"
    source.write_text(json.dumps(cases))
    manifest = json.loads((root / "review-manifest.json").read_text())
    manifest["cases_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
    manifest["packet_id"] = _json_hash({k: v for k, v in manifest.items() if k != "packet_id"})
    (root / "review-manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="source comment"):
        ReviewStore(root)
    source.write_text(original)
    with pytest.raises(ValueError, match="manifest"):
        ReviewStore(root)


def test_image_and_path_validation(tmp_path):
    root = packet(tmp_path)
    (root / "images" / "meme.png").write_bytes(b"changed")
    with pytest.raises(ValueError, match="Image differs"):
        ReviewStore(root)


def test_http_security_and_static_copy(tmp_path):
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
        headers = dict(response.getheaders())
        conn.close()
        return response.status, data, headers

    try:
        status, raw, headers = call("GET", "/api/cases")
        assert status == 200 and b'"methods":' not in raw and b"pairwise" not in raw
        assert "Content-Security-Policy" in headers
        token = json.loads(raw)["token"]
        assert call("GET", "/api/cases", headers={"Host": "evil.test"})[0] == 403
        assert call("GET", "/api/cases", headers={"Origin": "http://evil.test"})[0] == 403
        assert call("GET", "/image/../../review-cases.json")[0] == 404
        assert call("GET", "/image/r0")[0] == 200
        assert b"innerHTML" not in call("GET", "/review.js")[1]
        assert b"Which list helps you get the joke sooner?" in call("GET", "/")[1]
        request = json.dumps(feedback(ReviewStore(root))).encode()
        assert call("POST", "/api/feedback", request, {"Content-Type": "application/json"})[0] == 403
        headers = {"Content-Type": "application/json", "X-Review-Token": token}
        assert call("POST", "/api/feedback", request, headers)[0] == 200
        assert call("POST", "/api/feedback", b" " * 32769, headers)[0] == 400
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
