"""Local, blinded review of frozen Jev comment-selection lists."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import secrets
import threading
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

STATIC = Path(__file__).with_name("comment_selection_static")
CHOICES = ("A", "B")
FIRST = {"yes", "partly", "no", "unsure"}
EXTRAS = {"yes", "no", "unsure"}
PREFERENCES = {"A", "B", "tie", "neither", "unsure"}
MAX_BODY = 32_768


class ConflictError(ValueError):
    """The journal already contains incompatible feedback."""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json_hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _safe_id(value: object) -> bool:
    return isinstance(value, str) and 1 <= len(value) <= 100 and all(
        ch.isascii() and (ch.isalnum() or ch in "_-") for ch in value)


def _image_mime(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    raise ValueError("Unsupported image type")


def _words(text: str) -> int:
    return len(text.split())


def _validate_pack(pack: object, comments: dict[str, str]) -> None:
    if not isinstance(pack, dict) or pack.get("status") not in {"completed", "unavailable"}:
        raise ValueError("Invalid list status")
    if pack["status"] == "unavailable":
        return
    excerpts = pack.get("excerpts")
    extras = pack.get("extra_excerpts")
    if not isinstance(excerpts, list) or not isinstance(extras, list) or len(excerpts) > 3:
        raise ValueError("Invalid list excerpts")
    ids = []
    for excerpt in excerpts + extras:
        if not isinstance(excerpt, dict):
            raise ValueError("Invalid excerpt")
        cid = excerpt.get("comment_id")
        if (cid not in comments or excerpt.get("text") != comments[cid] or
                excerpt.get("start") != 0 or excerpt.get("end") != len(comments[cid]) or
                excerpt.get("partial") is not False or cid in ids):
            raise ValueError("Excerpt differs from source comment")
        ids.append(cid)
    if pack.get("selected_ids") != [e["comment_id"] for e in excerpts] or pack.get("retained_ids") != ids:
        raise ValueError("List IDs differ from excerpts")
    excluded = pack.get("excluded_ids")
    if (not isinstance(excluded, list) or len(set(excluded)) != len(excluded) or
            set(excluded) != set(comments) - set(ids)):
        raise ValueError("Excluded IDs differ from comments")
    if (type(pack.get("word_count")) is not int or pack["word_count"] != sum(_words(e["text"]) for e in excerpts) or
            type(pack.get("total_word_count")) is not int or pack["total_word_count"] != sum(_words(e["text"]) for e in excerpts + extras)):
        raise ValueError("List word counts differ from comments")


class ReviewStore:
    """Validate a private packet and append feedback under root/review-feedback."""

    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.manifest = json.loads((self.root / "review-manifest.json").read_text(encoding="utf-8"))
        cases_path = self.root / "review-cases.json"
        if (not _safe_id(self.manifest.get("packet_id")) or
                not _safe_id(self.manifest.get("plan_id")) or
                self.manifest["packet_id"] != _json_hash({k: v for k, v in self.manifest.items() if k != "packet_id"})):
            raise ValueError("Invalid packet ID or plan ID")
        if _sha(cases_path) != self.manifest.get("cases_sha256"):
            raise ValueError("Review cases differ from manifest")
        cases = json.loads(cases_path.read_text(encoding="utf-8"))
        if not isinstance(cases, list) or len(cases) != 8:
            raise ValueError("Review packet must contain eight cases")
        self.cases: dict[str, dict] = {}
        self.images: dict[str, tuple[Path, str]] = {}
        for case in cases:
            if not isinstance(case, dict):
                raise ValueError("Invalid case")
            rid = case.get("review_id")
            if (not _safe_id(rid) or rid in self.cases or
                    not all(isinstance(case.get(key), str) and 1 <= len(case[key]) <= 200
                            for key in ("family_id", "case_id"))):
                raise ValueError("Invalid case identity")
            if case.get("sample_kind") not in {"development", "newly_reviewed"}:
                raise ValueError("Invalid sample kind")
            if (not isinstance(case.get("methods"), dict) or set(case["methods"]) != set(CHOICES) or
                    set(case["methods"].values()) != {"baseline", "pairwise"}):
                raise ValueError("Invalid method mapping")
            if not isinstance(case.get("packs"), dict) or set(case["packs"]) != set(CHOICES):
                raise ValueError("Both lists are required")
            comments = case.get("comments")
            if (not isinstance(comments, list) or not all(isinstance(c, dict) and _safe_id(c.get("id")) and
                    isinstance(c.get("text"), str) for c in comments)):
                raise ValueError("Invalid source comments")
            by_id = {c["id"]: c["text"] for c in comments}
            if len(by_id) != len(comments):
                raise ValueError("Duplicate source comment ID")
            for choice in CHOICES:
                _validate_pack(case["packs"][choice], by_id)
            raw_path = case.get("image_path")
            if not isinstance(raw_path, str):
                raise ValueError("Missing image path")
            image = Path(raw_path)
            image = (image if image.is_absolute() else self.root / image).resolve()
            if not image.is_relative_to(self.root) or not image.is_file():
                raise ValueError("Image must be inside the packet root")
            if _sha(image) != self.manifest.get("image_hashes", {}).get(rid):
                raise ValueError("Image differs from manifest")
            self.cases[rid] = case
            self.images[rid] = (image, _image_mime(image.read_bytes()))
        if set(self.manifest.get("image_hashes", {})) != set(self.cases):
            raise ValueError("Image inventory differs from cases")
        self.feedback_dir = self.root / "review-feedback"
        self.feedback_dir.mkdir(exist_ok=True)
        self.journal = self.feedback_dir / "events.jsonl"
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.Lock()

    def _events(self, handle) -> list[dict]:
        handle.seek(0)
        events = [json.loads(line) for line in handle if line.strip()]
        for event in events:
            if event.get("packet_id") != self.manifest["packet_id"] or event.get("review_id") not in self.cases:
                raise ValueError("Feedback journal does not match packet")
        return events

    def events(self) -> list[dict]:
        with self.lock, self.journal.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle, fcntl.LOCK_SH)
            return self._events(handle)

    @staticmethod
    def _state(rid: str, events: list[dict]) -> dict:
        own = [e for e in events if e["review_id"] == rid]
        saves = [e for e in own if e["kind"] == "feedback"]
        latest = saves[-1] if saves else None
        return {"revision": latest["event_id"] if latest else None,
                "ratings": latest["ratings"] if latest else None,
                "preference": latest["preference"] if latest else None,
                "note": latest["note"] if latest else "",
                "saved_at": latest["recorded_at"] if latest else None,
                "methods_revealed": any(e["kind"] == "reveal" for e in own)}

    def catalog(self) -> dict:
        events = self.events()
        rows = []
        for case in self.cases.values():
            rid = case["review_id"]
            packs = {}
            for choice in CHOICES:
                original = case["packs"][choice]
                if original["status"] == "unavailable":
                    packs[choice] = {"status": "unavailable"}
                else:
                    packs[choice] = {"status": "completed", "excerpts": original["excerpts"],
                                     "extra_excerpts": original["extra_excerpts"],
                                     "word_count": original["word_count"],
                                     "total_word_count": original["total_word_count"]}
            state = self._state(rid, events)
            initial = [case["packs"][c].get("excerpts") for c in CHOICES]
            row = {"review_id": rid, "sample_kind": case["sample_kind"],
                   "image_url": f"/image/{rid}", "packs": packs,
                   "identical_initial_lists": initial[0] == initial[1] and all(p["status"] == "completed" for p in packs.values()),
                   "state": state}
            if state["methods_revealed"]:
                row["methods"] = case["methods"]
            rows.append(row)
        return {"packet_id": self.manifest["packet_id"], "token": self.token, "cases": rows}

    def _append(self, request: dict, kind: str, extra: dict) -> dict:
        rid = request.get("review_id")
        request_id = request.get("request_id")
        if rid not in self.cases or not _safe_id(request_id) or request.get("packet_id") != self.manifest["packet_id"]:
            raise ValueError("Request does not match packet")
        request_hash = _json_hash(request)
        with self.lock, self.journal.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            events = self._events(handle)
            for old in events:
                if old["request_id"] == request_id:
                    if old["request_sha256"] != request_hash:
                        raise ConflictError("Request ID already used for different feedback")
                    return {"event_id": old["event_id"], "state": self._state(rid, events)}
            state = self._state(rid, events)
            if kind == "reveal" and state["methods_revealed"]:
                first = next(e for e in events if e["review_id"] == rid and e["kind"] == "reveal")
                return {"event_id": first["event_id"], "state": state}
            if request.get("base_revision") != state["revision"]:
                raise ConflictError("Feedback changed in another window. Reload before saving.")
            if kind == "reveal" and state["revision"] is None:
                raise PermissionError("Save feedback before revealing methods")
            if kind == "feedback":
                extra = {**extra, "methods_revealed_before": state["methods_revealed"]}
            event = {"schema_version": "comment-selection-review-v1", "kind": kind,
                     "event_id": str(uuid.uuid4()), "request_id": request_id,
                     "request_sha256": request_hash, "packet_id": self.manifest["packet_id"],
                     "review_id": rid, "base_revision": state["revision"],
                     "recorded_at": datetime.now(timezone.utc).isoformat(), **extra}
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
            events.append(event)
            return {"event_id": event["event_id"], "state": self._state(rid, events)}

    def save(self, request: dict) -> dict:
        if not isinstance(request, dict) or set(request) != {"packet_id", "review_id", "request_id", "base_revision", "ratings", "preference", "note"}:
            raise ValueError("Invalid feedback fields")
        rid = request.get("review_id")
        if rid not in self.cases:
            raise ValueError("Unknown case")
        available = {c for c in CHOICES if self.cases[rid]["packs"][c]["status"] == "completed"}
        ratings = request["ratings"]
        if not isinstance(ratings, dict) or set(ratings) != available:
            raise ValueError("Rate each available list")
        for rating in ratings.values():
            if (not isinstance(rating, dict) or set(rating) != {"first_helps", "irrelevant_extras"} or
                    rating["first_helps"] not in FIRST or rating["irrelevant_extras"] not in EXTRAS):
                raise ValueError("Invalid list rating")
        if request["preference"] not in PREFERENCES or (request["preference"] in CHOICES and request["preference"] not in available):
            raise ValueError("Choose an available list, tie, neither, or unsure")
        if not isinstance(request["note"], str) or len(request["note"]) > 4000:
            raise ValueError("Note is too long")
        return self._append(request, "feedback", {"ratings": ratings, "preference": request["preference"], "note": request["note"]})

    def reveal(self, request: dict) -> dict:
        if not isinstance(request, dict) or set(request) != {"packet_id", "review_id", "request_id", "base_revision"}:
            raise ValueError("Invalid reveal request")
        result = self._append(request, "reveal", {})
        result["methods"] = self.cases[request["review_id"]]["methods"]
        return result


def make_server(root: Path, port: int, *, store: ReviewStore | None = None) -> ThreadingHTTPServer:
    store = store or ReviewStore(root)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def reply(self, status: int, body: object, mime: str = "application/json") -> None:
            data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(data)

        def allowed(self, write: bool = False) -> bool:
            hosts = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
            if self.headers.get("Host") not in hosts:
                self.reply(403, {"error": "Use the local review URL"})
                return False
            origin = self.headers.get("Origin")
            if origin and origin not in {"http://" + host for host in hosts}:
                self.reply(403, {"error": "Cross-origin access is not allowed"})
                return False
            if write and (self.headers.get("Content-Type") != "application/json" or
                          not secrets.compare_digest(self.headers.get("X-Review-Token", ""), store.token)):
                self.reply(403, {"error": "Reload the review before saving"})
                return False
            return True

        def do_GET(self) -> None:
            if not self.allowed():
                return
            path = urlsplit(self.path).path
            static = {"/": ("index.html", "text/html; charset=utf-8"),
                      "/review.js": ("review.js", "text/javascript; charset=utf-8"),
                      "/review.css": ("review.css", "text/css; charset=utf-8")}
            try:
                if path in static:
                    name, mime = static[path]
                    self.reply(200, (STATIC / name).read_bytes(), mime)
                elif path == "/api/cases":
                    self.reply(200, store.catalog())
                elif path.startswith("/image/") and unquote(path[7:]) in store.images:
                    rid = unquote(path[7:])
                    image, mime = store.images[rid]
                    if _sha(image) != store.manifest["image_hashes"][rid]:
                        raise ValueError("Image changed")
                    self.reply(200, image.read_bytes(), mime)
                else:
                    self.reply(404, {"error": "Not found"})
            except ValueError:
                self.reply(404, {"error": "Not found"})
            except (OSError, json.JSONDecodeError):
                self.reply(500, {"error": "Could not read local review"})

        def do_POST(self) -> None:
            if not self.allowed(write=True):
                return
            path = urlsplit(self.path).path
            if path not in {"/api/feedback", "/api/reveal"}:
                self.reply(404, {"error": "Not found"})
                return
            try:
                size = self.headers.get("Content-Length", "")
                if not size.isdecimal() or not 0 < int(size) <= MAX_BODY:
                    raise ValueError("Invalid request size")
                request = json.loads(self.rfile.read(int(size)))
                self.reply(200, store.save(request) if path == "/api/feedback" else store.reveal(request))
            except PermissionError as exc:
                self.reply(403, {"error": str(exc)})
            except ConflictError as exc:
                self.reply(409, {"error": str(exc)})
            except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
                self.reply(400, {"error": str(exc) or "Invalid request"})
            except OSError:
                self.reply(500, {"error": "Could not confirm save. Keep this page open and retry."})

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    return server


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()
    server = make_server(args.root, args.port)
    print(f"Comment selection review: http://127.0.0.1:{server.server_port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
