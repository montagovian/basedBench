"""Release-readiness audit for code, local DB, and export artifacts.

This script is intentionally non-mutating. It reads Git state, tracked files,
the optional local SQLite DB, and optional export artifacts, then exits nonzero
if a release-blocking hygiene, privacy, security, or correctness check fails.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SECRET_EXCLUDE_RE = (
    r"(^\.git/|^\.venv/|^data/|^export/|^uv\.lock$|"
    r"^\.pytest_cache/|^\.env(\..*)?$|^\.secrets\.baseline$)"
)
TRACKED_PRIVATE_PREFIXES = ("data/", "export/", ".venv/", ".claude/")
TRACKED_PRIVATE_NAMES = {".env"}
TRACKED_PRIVATE_SUFFIXES = (
    ".db",
    ".sqlite",
    ".sqlite3",
    ".db-wal",
    ".db-shm",
    ".sqlite-wal",
    ".sqlite-shm",
    ".log",
)
FORBIDDEN_EXPORT_KEYS = {
    "author",
    "authors",
    "body",
    "comment",
    "comments",
    "comment_body",
    "created_utc",
    "gate_feedback",
    "image_url",
    "llm_call",
    "llm_calls",
    "local_image_path",
    "permalink",
    "prompt",
    "request_id",
    "response",
    "review",
    "review_reason",
    "review_status",
    "reviewer_notes",
    "source_comment_ids",
    "system_prompt",
    "user_prompt",
}


class Audit:
    def __init__(self) -> None:
        self.failures: list[str] = []

    def ok(self, message: str) -> None:
        print(f"ok  {message}")

    def fail(self, message: str) -> None:
        print(f"ERR {message}")
        self.failures.append(message)

    def section(self, name: str) -> None:
        print(f"\n== {name} ==")


def _run(
    audit: Audit,
    cmd: list[str],
    *,
    label: str,
    check: bool = True,
) -> subprocess.CompletedProcess[str] | None:
    print(f"$ {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd,
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError:
        audit.fail(f"{label}: command not found: {cmd[0]}")
        return None

    if result.stdout.strip():
        print(result.stdout.rstrip())
    if result.stderr.strip():
        print(result.stderr.rstrip(), file=sys.stderr)
    if check and result.returncode != 0:
        audit.fail(f"{label} failed with exit code {result.returncode}")
    elif check:
        audit.ok(label)
    return result


def _secret_finding_key(finding: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(finding.get("filename", "")),
        str(finding.get("type", "")),
        str(finding.get("hashed_secret", "")),
    )


def _secret_finding_set(payload: dict[str, Any]) -> set[tuple[str, str, str]]:
    findings: set[tuple[str, str, str]] = set()
    for entries in payload.get("results", {}).values():
        for finding in entries:
            findings.add(_secret_finding_key(finding))
    return findings


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def check_git_hygiene(audit: Audit) -> None:
    audit.section("git hygiene")
    status = _run(
        audit,
        ["git", "status", "--porcelain"],
        label="git status",
        check=False,
    )
    if status and status.stdout.strip():
        audit.fail("working tree is dirty")
    else:
        audit.ok("working tree clean")

    tracked = _run(
        audit,
        ["git", "ls-files"],
        label="tracked file list",
        check=False,
    )
    if tracked is None or tracked.returncode != 0:
        audit.fail("could not list tracked files")
        return

    private = []
    for rel in tracked.stdout.splitlines():
        name = Path(rel).name
        if (
            rel.startswith(TRACKED_PRIVATE_PREFIXES)
            or name in TRACKED_PRIVATE_NAMES
            or rel.endswith(TRACKED_PRIVATE_SUFFIXES)
            or (name.startswith(".env.") and name != ".env.example")
        ):
            private.append(rel)
    if private:
        audit.fail(f"private/generated files are tracked: {', '.join(private[:20])}")
    else:
        audit.ok("no private/generated files tracked")

    if (ROOT / "LICENSE").exists():
        audit.ok("LICENSE exists")
    else:
        audit.fail("LICENSE is missing")
    if (ROOT / "HANDOFF.md").exists() or (ROOT / "PLAN.md").exists():
        audit.fail("stale root HANDOFF.md or PLAN.md still exists")
    else:
        audit.ok("stale root handoff/plan docs removed")


def check_secrets(audit: Audit) -> None:
    audit.section("secrets")
    baseline_path = ROOT / ".secrets.baseline"
    if not baseline_path.exists():
        audit.fail(".secrets.baseline is missing")
        return
    baseline = _load_json(baseline_path)
    result = _run(
        audit,
        [
            "detect-secrets",
            "scan",
            "--all-files",
            "--exclude-files",
            SECRET_EXCLUDE_RE,
        ],
        label="detect-secrets scan",
        check=False,
    )
    if result is None:
        return
    if result.returncode != 0:
        audit.fail(f"detect-secrets exited {result.returncode}")
        return
    current = json.loads(result.stdout)
    allowed = _secret_finding_set(baseline)
    observed = _secret_finding_set(current)
    new_findings = sorted(observed - allowed)
    if new_findings:
        formatted = ", ".join(f"{path}:{typ}" for path, typ, _ in new_findings[:20])
        audit.fail(f"new secret findings outside baseline: {formatted}")
    else:
        audit.ok("no new secret findings outside baseline")


def _connect_readonly(db_path: Path) -> sqlite3.Connection:
    uri = f"file:{db_path.resolve()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def _resolve_db_image_path(path_value: str | None) -> Path | None:
    if not path_value:
        return None
    path = Path(path_value)
    if not path.is_absolute():
        path = ROOT / path
    try:
        return path.resolve()
    except OSError:
        return None


def check_db(audit: Audit, db_path: Path, expected_validated: int | None) -> None:
    audit.section("local DB privacy/correctness")
    if not db_path.exists():
        audit.fail(f"DB does not exist: {db_path}")
        return

    conn = _connect_readonly(db_path)
    try:
        required = {"memes", "ground_truths", "reviews", "comments", "predictions"}
        missing = sorted(t for t in required if not _table_exists(conn, t))
        if missing:
            audit.fail(f"DB missing required tables: {', '.join(missing)}")
            return
        audit.ok("required tables present")

        validated = conn.execute(
            "SELECT COUNT(*) AS n FROM reviews WHERE status = 'validated'"
        ).fetchone()["n"]
        if expected_validated is not None and validated != expected_validated:
            audit.fail(
                f"validated count is {validated}, expected {expected_validated}"
            )
        else:
            audit.ok(f"validated count: {validated}")

        missing_gt = conn.execute(
            """SELECT COUNT(*) AS n
               FROM reviews r
               LEFT JOIN ground_truths gt ON gt.post_id = r.post_id
               WHERE r.status = 'validated'
                 AND (gt.explanation IS NULL OR trim(gt.explanation) = '')"""
        ).fetchone()["n"]
        if missing_gt:
            audit.fail(f"{missing_gt} validated rows lack ground truth")
        else:
            audit.ok("validated rows all have ground truth")

        bad_images: list[str] = []
        image_root = (ROOT / "data" / "images").resolve()
        for row in conn.execute(
            """SELECT m.post_id, m.local_image_path
               FROM memes m
               JOIN reviews r ON r.post_id = m.post_id
               WHERE r.status = 'validated'"""
        ):
            img = _resolve_db_image_path(row["local_image_path"])
            if img is None or not img.exists():
                bad_images.append(row["post_id"])
                continue
            try:
                img.relative_to(image_root)
            except ValueError:
                bad_images.append(row["post_id"])
        if bad_images:
            audit.fail(
                "validated rows missing on-disk images or outside data/images: "
                + ", ".join(bad_images[:20])
            )
        else:
            audit.ok("validated rows all have on-disk images under data/images")

        duplicate_validated = conn.execute(
            """SELECT COUNT(*) AS n
               FROM reviews
               WHERE status = 'validated'
                 AND COALESCE(reason, '') LIKE '%duplicate%'"""
        ).fetchone()["n"]
        if duplicate_validated:
            audit.fail(f"{duplicate_validated} validated rows carry duplicate reasons")
        else:
            audit.ok("validated rows do not carry duplicate-exclusion reasons")

        source_errors: list[str] = []
        for row in conn.execute(
            """SELECT gt.post_id, gt.source_comment_ids
               FROM ground_truths gt
               JOIN reviews r ON r.post_id = gt.post_id
               WHERE r.status = 'validated'"""
        ):
            try:
                ids = json.loads(row["source_comment_ids"] or "[]")
            except json.JSONDecodeError:
                source_errors.append(row["post_id"])
                continue
            if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
                source_errors.append(row["post_id"])
                continue
            if ids:
                placeholders = ",".join("?" for _ in ids)
                count = conn.execute(
                    f"""SELECT COUNT(*) AS n FROM comments
                        WHERE post_id = ? AND comment_id IN ({placeholders})""",
                    (row["post_id"], *ids),
                ).fetchone()["n"]
                if count != len(set(ids)):
                    source_errors.append(row["post_id"])
        if source_errors:
            audit.fail(
                "consensus source IDs malformed or missing comments: "
                + ", ".join(source_errors[:20])
            )
        else:
            audit.ok("consensus source IDs parse and refer to stored comments")
    finally:
        conn.close()


def _iter_json_values(value: Any) -> Iterable[Any]:
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from _iter_json_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_json_values(child)


def _check_forbidden_keys(audit: Audit, path: Path, value: Any) -> None:
    bad: set[str] = set()
    for item in _iter_json_values(value):
        if isinstance(item, dict):
            bad.update(k for k in item if k in FORBIDDEN_EXPORT_KEYS)
    if bad:
        audit.fail(f"{path.relative_to(ROOT)} contains forbidden keys: {sorted(bad)}")


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open() as f:
        for line_number, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number} is not a JSON object")
            rows.append(value)
    return rows


def check_export(
    audit: Audit,
    export_dir: Path,
    expected_validated: int | None,
) -> None:
    audit.section("export privacy/correctness")
    if not export_dir.exists():
        audit.fail(f"export directory does not exist: {export_dir}")
        return
    memes_path = export_dir / "data" / "memes.jsonl"
    predictions_path = export_dir / "data" / "predictions.jsonl"
    judgments_path = export_dir / "data" / "judgments.jsonl"
    leaderboard_path = export_dir / "data" / "leaderboard.jsonl"
    readme_path = export_dir / "README.md"
    for path in (
        memes_path,
        predictions_path,
        judgments_path,
        leaderboard_path,
        readme_path,
    ):
        if not path.exists():
            audit.fail(f"export missing {path.relative_to(export_dir)}")
            return
    audit.ok("required export files present")

    try:
        meme_rows = _load_jsonl(memes_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        audit.fail(f"could not parse memes.jsonl: {exc}")
        return
    for row in meme_rows:
        _check_forbidden_keys(audit, memes_path, row)
    if expected_validated is not None and len(meme_rows) != expected_validated:
        audit.fail(
            f"export memes row count is {len(meme_rows)}, expected {expected_validated}"
        )
    else:
        audit.ok(f"export memes row count: {len(meme_rows)}")

    image_files = [p for p in (export_dir / "images").glob("*") if p.is_file()]
    if len(image_files) != len(meme_rows):
        audit.fail(
            f"export copied {len(image_files)} images for {len(meme_rows)} meme rows"
        )
    else:
        audit.ok("export image count matches meme row count")

    try:
        prediction_rows = _load_jsonl(predictions_path)
        judgment_rows = _load_jsonl(judgments_path)
        leaderboard_rows = _load_jsonl(leaderboard_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        audit.fail(f"could not parse normalized export tables: {exc}")
        return

    for path, rows in (
        (predictions_path, prediction_rows),
        (judgments_path, judgment_rows),
        (leaderboard_path, leaderboard_rows),
    ):
        for row in rows:
            _check_forbidden_keys(audit, path, row)

    meme_ids = {row.get("post_id") for row in meme_rows}
    prediction_ids = {row.get("prediction_id") for row in prediction_rows}
    if any(row.get("post_id") not in meme_ids for row in prediction_rows):
        audit.fail("predictions table contains post IDs absent from memes table")
    elif any(row.get("prediction_id") is None for row in prediction_rows):
        audit.fail("predictions table contains a null prediction ID")
    else:
        audit.ok(f"predictions table checked ({len(prediction_rows)} rows)")

    if any(row.get("prediction_id") not in prediction_ids for row in judgment_rows):
        audit.fail("judgments table contains prediction IDs absent from predictions table")
    else:
        audit.ok(f"judgments table checked ({len(judgment_rows)} rows)")
    audit.ok(f"leaderboard table checked ({len(leaderboard_rows)} rows)")

    readme = readme_path.read_text().lower()
    required_note_terms = (
        "raw reddit comments",
        "reddit authors",
        "intentionally omitted",
    )
    if all(term in readme for term in required_note_terms):
        audit.ok("dataset card includes privacy note")
    else:
        audit.fail("dataset card is missing the privacy note")


def check_static_tools(audit: Audit) -> None:
    audit.section("security/static checks")
    _run(audit, ["bandit", "-q", "-r", "src", "-s", "B608"], label="Bandit")
    _run(audit, ["pip-audit"], label="pip-audit")


def check_tests(audit: Audit) -> None:
    audit.section("tests")
    _run(audit, ["pytest"], label="pytest")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, help="Optional local SQLite DB to inspect")
    parser.add_argument(
        "--export-dir",
        type=Path,
        help="Optional generated export directory to validate",
    )
    parser.add_argument(
        "--expected-validated",
        type=int,
        default=500,
        help="Expected validated row count for the current release target",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    audit = Audit()
    check_git_hygiene(audit)
    check_secrets(audit)
    check_static_tools(audit)
    check_tests(audit)
    if args.db:
        check_db(audit, args.db, args.expected_validated)
    if args.export_dir:
        check_export(audit, args.export_dir, args.expected_validated)

    if audit.failures:
        print("\nRelease audit failed:")
        for failure in audit.failures:
            print(f"- {failure}")
        return 1
    print("\nRelease audit passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
