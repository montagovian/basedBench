"""Local, append-only curation feedback. No model calls or live database writes."""

from __future__ import annotations

import fcntl
import json
import os
import secrets
import shutil
import tempfile
import threading
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from basedbench.pipeline.curation_corpus import canonical_json, digest, file_hash, load_corpus, write_json

STATIC = Path(__file__).with_name("review_static")
RUBRIC_VERSION = "curation-feedback-rubric-v1"
PRINCIPLES = [
    "Judge whether a model gets the joke: the reference, setup, visual detail, implication, contrast or wordplay. Do not require a theory of why humor works.",
    "The current content rule excludes explicit sexual acts, exposed sexual anatomy, hate/slurs, doxxing and graphic gore. Mentioning sex, mild innuendo, dark humor, politics or a historical reference alone do not fail. Judge the candidate, not an unrelated comment or a model's possibly mistaken description.",
    "Policy boundary means you understand the content but the publication rule needs a decision. Need more context means you cannot yet tell what it means. These feedback choices do not change production policy.",
    "Ground truth is one judgment about agreement, support, completeness and image consistency. The answer as written must capture the same core joke, not merely name a related reference. Do not mentally repair an answer and then mark it ready.",
    "Task value asks what a viewer must recover beyond a literal description, and whether that interpretation accounts for the whole item. Simple puns, text screenshots, observations and cultural references can qualify. Recognizing a meme format alone does not establish value; explain an empty or incoherent case in the note.",
    "Unfamiliarity is not an automatic rejection. Difficulty is an optional impression, separate from measured model performance and validity. Overall admission is your explicit choice; it never fills in other judgments automatically.",
    "Leave unresolved fields blank or use an unsure option. Repair answer first records a route and optional repair note; it does not change the answer. Revisions preserve previous feedback. All feedback in this gallery is development material, not held-out evaluation.",
]
FIELDS = {
    "content": {"label": "Is the content suitable?", "hint": "A policy boundary means the rule needs a decision. Need context means you cannot yet tell what the content means.", "options": {"pass": "Pass", "fail": "Fail", "boundary": "Policy boundary", "uncertain": "Need more context"}},
    "ground_truth": {"label": "Is the stored answer good enough to grade against?", "hint": "Does the evidence support this answer, and does it capture the whole joke in the image?", "options": {"ready": "Ready", "repair": "Repair needed", "uncertain": "Insufficient evidence"}},
    "value": {"label": "Would this be useful with a correct answer?", "hint": "What must a viewer understand beyond the literal description? A simple joke can still qualify.", "options": {"yes": "Yes", "no": "No", "unsure": "Unsure"}},
    "admission": {"label": "Would you include this copy?", "hint": "Your overall decision. A good meme can need an answer repair; duplicates and image quality can matter too.", "options": {"accept": "Accept", "reject": "Reject", "repair": "Repair answer first", "undecided": "Undecided"}},
    "familiarity": {"label": "Did you know the reference?", "hint": "Unfamiliarity is not a rejection criterion.", "options": {"familiar": "Yes", "needed_context": "Needed context", "unclear": "Still unclear"}},
    "difficulty": {"label": "How difficult does it seem?", "hint": "Optional impression. Easy does not automatically mean bad.", "options": {"easy": "Easy", "medium": "Medium", "hard": "Hard", "unsure": "Unsure"}},
}


def read_lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def prepare_packet(corpus: Path, run: Path, prior_feedback: Path, output: Path,
                   *, seed: str = "curation-review-v1") -> dict:
    """Freeze 16 random controls, 12 targeted cases and prior discussion cases."""
    if output.exists():
        raise FileExistsError(f"Refusing to replace review packet: {output}")
    manifest, rows = load_corpus(corpus)
    by_id = {r["post_id"]: r for r in rows}
    plan = json.loads((run / "plan.json").read_text())
    if plan["corpus_id"] != manifest["corpus_id"]:
        raise ValueError("Run and corpus do not match")
    prior = defaultdict(list)
    for event in read_lines(prior_feedback):
        if event["corpus_id"] != manifest["corpus_id"]:
            raise ValueError("Feedback and corpus do not match")
        for item in event["items"]:
            row = by_id[item["post_id"]]
            if item["input_sha256"] != row["input_sha256"] or row["split"] == "test":
                raise ValueError("Invalid or reserved prior feedback")
            prior[item["post_id"]].append({"recorded_at": event["recorded_at"], "item": item,
                "difficulty": event.get("difficulty_feedback") if item["post_id"] in event.get("difficulty_feedback", {}).get("post_ids", []) else None})
    decisions = defaultdict(list)
    components = defaultdict(list)
    for decision in read_lines(run / "decisions.jsonl"):
        pid = decision["post_id"]
        row = by_id[pid]
        if (row["split"] == "test" or decision["input_sha256"] != row["input_sha256"]
                or plan["input_hashes"].get(pid) != row["input_sha256"]):
            raise ValueError("Invalid or reserved model evidence")
        decisions[pid].append(decision)
    expected_arms = set(plan["arms"])
    if set(decisions) != set(plan["evaluation_ids"]):
        raise ValueError("Incomplete saved model run")
    for values in decisions.values():
        if len(values) != len(expected_arms) or {d["model"].rsplit(":", 1)[-1] for d in values} != expected_arms:
            raise ValueError("Incomplete or duplicate model decisions")
    for component in read_lines(run / "components.jsonl"):
        if component["post_id"] not in decisions:
            raise ValueError("Unmatched model component")
        components[component["post_id"]].append(component)

    excluded_groups = {by_id[p]["group_id"] for p in prior}
    api_groups = {by_id[p]["group_id"] for p in set(decisions) | set(plan["reference_ids"])}
    random_pool = [r for r in rows if r["split"] == "calibration"
                   and r["group_id"] not in excluded_groups | api_groups]
    target_pool = [by_id[p] for p, ds in decisions.items() if by_id[p]["group_id"] not in excluded_groups
                   and any(d["decision"] != "accept" for d in ds)]

    def sample(pool, count, stratum, used):
        picked = []
        for row in sorted(pool, key=lambda r: digest([seed, stratum, r["post_id"]])):
            if row["group_id"] not in used:
                picked.append((row, stratum))
                used.add(row["group_id"])
            if len(picked) == count:
                return picked
        raise ValueError(f"Not enough distinct groups for {stratum}: need {count}")

    used = set(excluded_groups)
    chosen = sample(random_pool, 16, "random_control", used) + sample(target_pool, 12, "targeted", used)
    chosen.sort(key=lambda pair: digest([seed, "display", pair[0]["post_id"]]))
    chosen += [(by_id[p], "previous_discussion") for p in prior]
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".curation-review-", dir=output.parent))
    try:
        (staging / "images").mkdir()
        cases = []
        for row, stratum in chosen:
            pid = row["post_id"]
            sha = row["input"]["image_sha256"]
            with Image.open(corpus / "assets" / sha) as img:
                mime = Image.MIME[img.format]
            shutil.copyfile(corpus / "assets" / sha, staging / "images" / sha)
            cases.append({"post_id": pid, "input_sha256": row["input_sha256"], "group_id": row["group_id"],
                "split": row["split"], "stratum": stratum, "input": row["input"], "image_mime": mime,
                "historical_label": row["label"], "reviewed_at": row["provenance"]["reviewed_at"],
                "previous_feedback": prior.get(pid, []), "decisions": decisions.get(pid, []),
                "components": components.get(pid, [])})
        write_json(staging / "cases.json", cases)
        rubric = {"version": RUBRIC_VERSION, "fields": FIELDS, "principles": PRINCIPLES}
        write_json(staging / "rubric.json", rubric)
        packet = {"schema_version": "curation-review-packet-v1", "corpus_id": manifest["corpus_id"],
            "seed": seed, "rubric_version": RUBRIC_VERSION, "rubric_sha256": digest(rubric),
            "new_api_calls": 0, "counts": {"random_control": 16, "targeted": 12, "previous_discussion": len(prior)},
            "source_hashes": {"prior_feedback": file_hash(prior_feedback),
                **{name: file_hash(run / name) for name in ("plan.json", "decisions.jsonl", "components.jsonl")}},
            "selection": "Hash-sampled distinct known groups. Random controls exclude prior discussion, API targets and references. Targeted cases have a non-acceptance in the saved run. Display order is hash-shuffled.",
            "limitations": ["Development feedback, not a new holdout.", "Historical and earlier model exposure persists.",
                "Known image groups are not a complete semantic-family audit.", "No reserved test cases selected."],
            "files": {p.relative_to(staging).as_posix(): file_hash(p) for p in sorted(staging.rglob("*")) if p.is_file()}}
        packet["packet_id"] = digest(packet)
        write_json(staging / "manifest.json", packet)
        staging.rename(output)
        return packet
    finally:
        if staging.exists():
            shutil.rmtree(staging)


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    request_id: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9-]+$")
    post_id: str
    input_sha256: str
    packet_id: str
    base_revision: str | None = None
    fields: dict[str, str] = Field(default_factory=dict)
    notes: str = Field(default="", max_length=12000)
    kind: str = "feedback"
    reveal: str | None = None
    question_copy_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class ConflictError(ValueError):
    pass


class ReviewStore:
    def __init__(self, packet: Path):
        self.packet = packet
        self.manifest = json.loads((packet / "manifest.json").read_text())
        if (self.manifest.get("schema_version") != "curation-review-packet-v1"
                or digest({k: v for k, v in self.manifest.items() if k != "packet_id"}) != self.manifest["packet_id"]):
            raise ValueError("Invalid review manifest")
        for relative, expected in self.manifest["files"].items():
            path = (packet / relative).resolve()
            if not path.is_relative_to(packet.resolve()) or file_hash(path) != expected:
                raise ValueError("Review packet integrity check failed")
        self.rubric = json.loads((packet / "rubric.json").read_text())
        if digest(self.rubric) != self.manifest["rubric_sha256"]:
            raise ValueError("Rubric identity mismatch")
        cases = json.loads((packet / "cases.json").read_text())
        self.cases = {c["post_id"]: c for c in cases}
        if len(self.cases) != len(cases):
            raise ValueError("Duplicate review case")
        for case in cases:
            if case["split"] == "test" or digest(case["input"]) != case["input_sha256"]:
                raise ValueError("Invalid or reserved review case")
        self.lock = threading.Lock()
        self.token = secrets.token_urlsafe(32)

    def _read_events(self, handle) -> list[dict]:
        handle.seek(0)
        events = [json.loads(line) for line in handle if line.strip()]
        for event in events:
            case = self.cases.get(event["post_id"])
            if (event["packet_id"] != self.manifest["packet_id"] or not case
                    or event["input_sha256"] != case["input_sha256"]):
                raise ValueError("Feedback journal does not match packet")
        return events

    def events(self) -> list[dict]:
        with self.lock, (self.packet / "events.jsonl").open("a+") as handle:
            fcntl.flock(handle, fcntl.LOCK_SH)
            return self._read_events(handle)

    def state(self, pid: str, events: list[dict]) -> dict:
        own = [e for e in events if e["post_id"] == pid]
        saved = [e for e in own if e["kind"] == "feedback"]
        return {"latest": saved[-1] if saved else None,
                "revealed": sorted({e["reveal"] for e in own if e["kind"] == "reveal"}),
                "save_count": len(saved), "previously_discussed": bool(self.cases[pid]["previous_feedback"])}

    def catalog(self) -> dict:
        events = self.events()
        return {"packet_id": self.manifest["packet_id"], "rubric": self.rubric, "token": self.token,
            "question_copy": self.question_copy(),
            "cases": [{"post_id": c["post_id"], "input_sha256": c["input_sha256"],
                "image_url": f"/image/{c['post_id']}", "explanation": c["input"]["explanation"],
                "collection": "previous" if c["previous_feedback"] else "fresh",
                **self.state(c["post_id"], events)} for c in self.cases.values()]}

    def question_copy(self) -> dict | None:
        """Clarify display wording without rewriting the frozen rubric or prior events."""
        copy = json.loads((STATIC / "question-copy.json").read_text())
        if copy["rubric_version"] != self.rubric["version"]:
            return None
        return {**copy, "sha256": digest(copy)}

    def context(self, pid: str, reveal: str) -> dict:
        case = self.cases[pid]
        if reveal == "comments":
            return {"comments": case["input"]["comment_evidence"]}
        return {k: case[k] for k in ("historical_label", "reviewed_at", "previous_feedback", "decisions", "components", "stratum")}

    def append(self, request: ReviewRequest) -> dict:
        case = self.cases.get(request.post_id)
        if not case or request.packet_id != self.manifest["packet_id"] or request.input_sha256 != case["input_sha256"]:
            raise ValueError("This review belongs to different evidence. Reload the page.")
        if request.kind not in {"feedback", "reveal"}:
            raise ValueError("Unknown event type")
        if request.kind == "reveal" and request.reveal not in {"comments", "opinions"}:
            raise ValueError("Unknown context type")
        if request.kind == "feedback" and request.reveal is not None:
            raise ValueError("Feedback cannot also be a reveal")
        for key, value in request.fields.items():
            if key not in self.rubric["fields"] or value not in self.rubric["fields"][key]["options"]:
                raise ValueError("Unknown feedback choice")
        if request.kind == "feedback" and not request.fields and not request.notes.strip():
            raise ValueError("Choose a judgment or add a note before saving.")
        request_payload = request.model_dump()
        if request.question_copy_sha256 is None:
            # Preserve retries sent by a page opened before the wording update.
            request_payload.pop("question_copy_sha256")
        request_hash = digest(request_payload)
        with self.lock, (self.packet / "events.jsonl").open("a+") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            events = self._read_events(handle)
            for old in events:
                if old["request_id"] == request.request_id:
                    if old["request_sha256"] != request_hash:
                        raise ConflictError("Request ID already used for different feedback")
                    return {"event": old, "state": self.state(request.post_id, events),
                            "context": self.context(request.post_id, request.reveal) if request.kind == "reveal" else None}
            state = self.state(request.post_id, events)
            revision = state["latest"]["event_id"] if state["latest"] else None
            if revision != request.base_revision:
                raise ConflictError("Feedback changed in another window. Your draft is kept here; copy it before reloading to compare.")
            copy = self.question_copy() if request.question_copy_sha256 else None
            if request.question_copy_sha256 and (copy is None or copy["sha256"] != request.question_copy_sha256):
                raise ConflictError("Question wording changed. Reload to see the current wording; your draft stays in this browser.")
            event = {**request.model_dump(), "schema_version": "curation-gallery-feedback-v1",
                "event_id": str(uuid.uuid4()), "request_sha256": request_hash,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "corpus_id": self.manifest["corpus_id"], "rubric_version": self.rubric["version"],
                "rubric_sha256": self.manifest["rubric_sha256"],
                "exposed_before": state["revealed"], "previously_discussed": state["previously_discussed"],
                "purpose": "development_feedback", "question_copy": copy}
            handle.write(canonical_json(event) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
            events.append(event)
            return {"event": event, "state": self.state(request.post_id, events),
                    "context": self.context(request.post_id, request.reveal) if request.kind == "reveal" else None}


def make_server(packet: Path, port: int, *, store: ReviewStore | None = None,
                static_dir: Path = STATIC) -> ThreadingHTTPServer:
    store = store if store is not None else ReviewStore(packet)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def reply(self, status, body, content_type="application/json"):
            if not isinstance(body, bytes):
                body = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)

        def allowed(self, *, write=False):
            actual_port = self.server.server_port
            hosts = {f"127.0.0.1:{actual_port}", f"localhost:{actual_port}"}
            if self.headers.get("Host") not in hosts:
                self.reply(403, {"error": "Use the local gallery URL."})
                return False
            origin = self.headers.get("Origin")
            if origin and origin not in {"http://" + h for h in hosts}:
                self.reply(403, {"error": "Cross-origin access is not allowed."})
                return False
            if write and (self.headers.get("Content-Type") != "application/json"
                          or not secrets.compare_digest(self.headers.get("X-Review-Token", ""), store.token)):
                self.reply(403, {"error": "Reload the gallery before saving."})
                return False
            return True

        def do_GET(self):
            if not self.allowed():
                return
            path = urlsplit(self.path).path
            static = {"/": ("index.html", "text/html; charset=utf-8"),
                      "/review.js": ("review.js", "text/javascript; charset=utf-8"),
                      "/review.css": ("review.css", "text/css; charset=utf-8")}
            try:
                if path in static:
                    name, mime = static[path]
                    asset = static_dir / name
                    self.reply(200, (asset if asset.is_file() else STATIC / name).read_bytes(), mime)
                elif path == "/api/cases":
                    self.reply(200, store.catalog())
                elif path.startswith("/image/") and path.removeprefix("/image/") in store.cases:
                    case = store.cases[path.removeprefix("/image/")]
                    self.reply(200, (packet / "images" / case["input"]["image_sha256"]).read_bytes(), case["image_mime"])
                else:
                    self.reply(404, {"error": "Not found"})
            except (OSError, ValueError):
                self.reply(500, {"error": "Could not read the local packet or feedback journal. Nothing was changed."})

        def do_POST(self):
            if not self.allowed(write=True):
                return
            if self.path != "/api/events":
                self.reply(404, {"error": "Not found"})
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if size <= 0 or size > 65536:
                    raise ValueError("Invalid feedback size")
                request = ReviewRequest.model_validate_json(self.rfile.read(size))
                self.reply(200, store.append(request))
            except ConflictError as exc:
                self.reply(409, {"error": str(exc)})
            except ValidationError:
                self.reply(400, {"error": "Invalid feedback fields. Your draft has not been saved."})
            except ValueError as exc:
                self.reply(400, {"error": str(exc)})
            except OSError:
                self.reply(500, {"error": "Could not confirm a save to disk. Keep this page open and retry."})

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    return server


def serve(packet: Path, port: int) -> None:
    server = make_server(packet, port)
    print(f"Curation review: http://127.0.0.1:{server.server_port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
