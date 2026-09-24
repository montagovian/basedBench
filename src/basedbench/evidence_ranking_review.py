"""Local, blinded review of frozen evidence-ranking packs."""

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

STATIC = Path(__file__).with_name("evidence_ranking_static")
CHOICES = ("A", "B", "C")
CLUES = {"yes", "partly", "no", "unsure"}
MISLEADING = {"yes", "no", "unsure"}
WINNERS = {"A", "B", "C", "tie", "unsure"}
MAX_BODY = 32_768


class ConflictError(ValueError):
    """A request conflicts with already recorded feedback."""


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


class ReviewStore:
    """Validate a private packet and append review events under root/review-feedback."""

    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.manifest = json.loads((self.root / "review-manifest.json").read_text(encoding="utf-8"))
        cases_path = self.root / "review-cases.json"
        if (not _safe_id(self.manifest.get("packet_id")) or
                self.manifest["packet_id"] != _json_hash({k: v for k, v in self.manifest.items() if k != "packet_id"})):
            raise ValueError("Invalid packet ID")
        if _sha(cases_path) != self.manifest.get("cases_sha256"):
            raise ValueError("Review cases differ from manifest")
        cases = json.loads(cases_path.read_text(encoding="utf-8"))
        if not isinstance(cases, list) or len(cases) != 16:
            raise ValueError("Review packet must contain 16 cases")
        self.cases: dict[str, dict] = {}
        self.images: dict[str, tuple[Path, str]] = {}
        for case in cases:
            rid = case.get("review_id")
            if not _safe_id(rid) or rid in self.cases:
                raise ValueError("Invalid or duplicate review ID")
            if not isinstance(case.get("methods"), dict) or set(case["methods"]) != set(CHOICES) or set(case["methods"].values()) != {"order", "rank", "collate"}:
                raise ValueError("Invalid method mapping")
            if not isinstance(case.get("packs"), dict) or set(case["packs"]) != set(CHOICES):
                raise ValueError("Every case needs three packs")
            for choice in CHOICES:
                pack = case["packs"][choice]
                if not isinstance(pack, dict) or pack.get("status", "completed") not in {"completed", "unavailable"}:
                    raise ValueError("Invalid pack status")
                if pack.get("status", "completed") == "completed":
                    if not isinstance(pack.get("excerpts"), list) or not isinstance(pack.get("budget_words"), int) or not isinstance(pack.get("word_count"), int):
                        raise ValueError("Invalid completed pack")
            raw_path = case.get("image_path")
            if not isinstance(raw_path, str):
                raise ValueError("Missing image path")
            image = Path(raw_path)
            image = (image if image.is_absolute() else self.root / image).resolve()
            if not image.is_relative_to(self.root) or not image.is_file():
                raise ValueError("Image must be a file within the packet root")
            if _sha(image) != self.manifest.get("image_hashes", {}).get(rid):
                raise ValueError("Image differs from manifest")
            mime = _image_mime(image.read_bytes())
            self.cases[rid] = case
            self.images[rid] = (image, mime)
        if set(self.manifest.get("image_hashes", {})) != set(self.cases):
            raise ValueError("Image hash inventory differs from cases")
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
                raise ValueError("Feedback journal does not match this packet")
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
                "most_useful": latest["most_useful"] if latest else None,
                "note": latest["note"] if latest else "",
                "saved_at": latest["recorded_at"] if latest else None,
                "methods_revealed": any(e["kind"] == "reveal" for e in own),
                "source_opened": any(e["kind"] == "context" and e["source"] == "comments" for e in own),
                "reference_opened": any(e["kind"] == "context" and e["source"] == "reference" for e in own)}

    def catalog(self) -> dict:
        events = self.events()
        rows = []
        for case in self.cases.values():
            rid = case["review_id"]
            packs = {}
            for choice in CHOICES:
                original = case["packs"][choice]
                status = original.get("status", "completed")
                packs[choice] = ({"status": "unavailable"} if status == "unavailable" else
                                 {"status": "completed", "excerpts": [{k: excerpt.get(k) for k in ("comment_id", "text", "partial")}
                                    for excerpt in original["excerpts"]],
                                  "word_count": original["word_count"], "budget_words": original["budget_words"]})
            rows.append({"review_id": rid, "image_url": f"/image/{rid}", "packs": packs,
                         "state": self._state(rid, events)})
        return {"packet_id": self.manifest["packet_id"], "token": self.token, "cases": rows}

    def _append(self, request: dict, kind: str, extra: dict) -> dict:
        rid = request.get("review_id")
        request_id = request.get("request_id")
        if rid not in self.cases or not _safe_id(request_id) or request.get("packet_id") != self.manifest["packet_id"]:
            raise ValueError("This request does not match the review packet")
        request_hash = _json_hash(request)
        with self.lock, self.journal.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            events = self._events(handle)
            for old in events:
                if old["request_id"] == request_id:
                    if old["request_sha256"] != request_hash:
                        raise ConflictError("Request ID was already used for different feedback")
                    return {"event_id": old["event_id"], "state": self._state(rid, events)}
            state = self._state(rid, events)
            if kind == "reveal" and state["methods_revealed"]:
                first = next(e for e in events if e["review_id"] == rid and e["kind"] == "reveal")
                return {"event_id": first["event_id"], "state": state}
            if request.get("base_revision") != state["revision"]:
                raise ConflictError("Feedback changed in another window. Reload before saving.")
            if kind == "reveal" and state["revision"] is None:
                raise PermissionError("Save ratings before revealing methods")
            if kind == "feedback":
                extra = {**extra, "source_opened_before": state["source_opened"],
                         "reference_opened_before": state["reference_opened"],
                         "methods_revealed_before": state["methods_revealed"]}
            event = {"schema_version": "evidence-ranking-review-v1", "kind": kind,
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
        if not isinstance(request, dict) or set(request) != {"packet_id", "review_id", "request_id", "base_revision", "ratings", "most_useful", "note"}:
            raise ValueError("Invalid feedback fields")
        rid = request.get("review_id")
        if rid not in self.cases:
            raise ValueError("Unknown case")
        ratings = request["ratings"]
        available = {c for c in CHOICES if self.cases[rid]["packs"][c].get("status", "completed") == "completed"}
        if not isinstance(ratings, dict) or set(ratings) != available:
            raise ValueError("Rate each available pack")
        for rating in ratings.values():
            if (not isinstance(rating, dict) or set(rating) != {"clue", "misleading"}
                    or rating["clue"] not in CLUES or rating["misleading"] not in MISLEADING):
                raise ValueError("Invalid pack rating")
        if request["most_useful"] not in WINNERS or (request["most_useful"] in CHOICES and request["most_useful"] not in available):
            raise ValueError("Choose an available pack, tie, or unsure")
        if not isinstance(request["note"], str) or len(request["note"]) > 4000:
            raise ValueError("Note is too long")
        return self._append(request, "feedback", {"ratings": ratings, "most_useful": request["most_useful"],
                                                   "note": request["note"]})

    def context(self, request: dict) -> dict:
        if not isinstance(request, dict) or set(request) != {"packet_id", "review_id", "request_id", "base_revision", "source"}:
            raise ValueError("Invalid context request")
        if request["source"] not in {"comments", "reference"}:
            raise ValueError("Unknown source")
        rid = request["review_id"]
        result = self._append(request, "context", {"source": request["source"]})
        case = self.cases[rid]
        result["context"] = ({"comments": case.get("comments", [])} if request["source"] == "comments" else
                             {"reference_explanation": case.get("reference_explanation")})
        return result

    def reveal(self, request: dict) -> dict:
        if not isinstance(request, dict) or set(request) != {"packet_id", "review_id", "request_id", "base_revision"}:
            raise ValueError("Invalid reveal request")
        result = self._append(request, "reveal", {})
        case = self.cases[request["review_id"]]
        result["methods"] = case["methods"]
        result["inspection"] = {choice: {key: case["packs"][choice].get(key)
                                         for key in ("groups", "sections", "pairs", "ranking")
                                         if key in case["packs"][choice]}
                                for choice in CHOICES}
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
                    image, mime = store.images[unquote(path[7:])]
                    if _sha(image) != store.manifest["image_hashes"][unquote(path[7:])]:
                        raise ValueError("Image changed")
                    self.reply(200, image.read_bytes(), mime)
                else:
                    self.reply(404, {"error": "Not found"})
            except PermissionError as exc:
                self.reply(403, {"error": str(exc)})
            except ValueError:
                self.reply(404, {"error": "Not found"})
            except (OSError, json.JSONDecodeError):
                self.reply(500, {"error": "Could not read the local review"})

        def do_POST(self) -> None:
            if not self.allowed(write=True):
                return
            path = urlsplit(self.path).path
            if path not in {"/api/feedback", "/api/context", "/api/reveal"}:
                self.reply(404, {"error": "Not found"})
                return
            try:
                raw_size = self.headers.get("Content-Length", "")
                if not raw_size.isdecimal() or not 0 < int(raw_size) <= MAX_BODY:
                    raise ValueError("Invalid request size")
                request = json.loads(self.rfile.read(int(raw_size)))
                self.reply(200, store.save(request) if path == "/api/feedback" else
                           store.context(request) if path == "/api/context" else store.reveal(request))
            except PermissionError as exc:
                self.reply(403, {"error": str(exc)})
            except ConflictError as exc:
                self.reply(409, {"error": str(exc)})
            except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
                self.reply(400, {"error": str(exc) or "Invalid request"})
            except OSError:
                self.reply(500, {"error": "Could not confirm the save. Keep this page open and retry."})

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    return server


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = make_server(args.root, args.port)
    print(f"Evidence review: http://127.0.0.1:{server.server_port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
