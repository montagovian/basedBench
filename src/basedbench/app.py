"""Gradio review UI — validator for meme ground truths.

Tabs:
- Review Queue: validate / exclude / skip unreviewed consensus results
- Browse: filter and search the meme database
- Prediction Comparison: compare model predictions side-by-side per meme
- Inspect: read-only viewer over ALL content (incl. excluded), flag filter misfires
- Stats & Leaderboard: corpus/prediction/judge stats
- AI Gloss Failures: consensus-gloss regression set
- Filter Misfires: flagged safety/consensus misfires, plus legacy quality-gate rows
- Consensus Eval: review and correct persistent consensus eval labels
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import gradio as gr

# Match common image URLs people drop in Reddit comments:
# - preview.redd.it / i.redd.it / i.imgur.com (host-based, takes query strings)
# - Any URL ending in a known image extension (with optional query string)
_IMAGE_URL_RE = re.compile(
    r"https?://(?:preview\.redd\.it|i\.redd\.it|i\.imgur\.com)/[^\s)\]]+"
    r"|https?://[^\s)\]]+\.(?:jpe?g|png|gif|webp)(?:\?[^\s)\]]*)?",
    re.IGNORECASE,
)


def _inline_image_urls(text: str) -> str:
    """Render bare image URLs inline as markdown images linked to themselves.

    Reviewers often need to see images reaction-commenters posted — they're
    part of the joke's context. Wraps the image in a link so clicking opens
    the original URL.
    """

    rendered: list[str] = []
    last = 0
    for match in _IMAGE_URL_RE.finditer(text):
        rendered.append(_escape_md_text(text[last:match.start()]))
        url = match.group(0)
        rendered.append(f"[![]({url})]({url})")
        last = match.end()
    rendered.append(_escape_md_text(text[last:]))
    return "".join(rendered)

_DB_PATH: Path = Path("data/basedbench.db")


def set_db_path(path: Path) -> None:
    """Override the database path (used by `basedbench review --db`)."""
    global _DB_PATH
    _DB_PATH = path


def _get_conn() -> sqlite3.Connection:
    """Open a per-request connection (Gradio uses worker threads)."""
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.row_factory = sqlite3.Row
    return conn


def _project_root() -> Path:
    return _DB_PATH.resolve().parent.parent


def _images_root() -> Path:
    return (_project_root() / "data" / "images").resolve()


def _resolve_image(local_image_path: str | None) -> str | None:
    if not local_image_path:
        return None
    path = Path(local_image_path)
    candidate = path.resolve() if path.is_absolute() else (_project_root() / path).resolve()
    images_root = _images_root()
    if candidate == images_root or images_root not in candidate.parents:
        return None
    return str(candidate) if candidate.exists() else None


def _escape_md_text(text: str | None) -> str:
    escaped = html.escape(text or "", quote=False)
    return re.sub(r"([\\`*_{}\[\]#!|])", r"\\\1", escaped)


def _source_comment_ids(raw_ids: str | None) -> list[str]:
    if not raw_ids:
        return []
    try:
        parsed = json.loads(raw_ids)
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [str(comment_id) for comment_id in parsed if comment_id]


def _comment_md(comment: sqlite3.Row, label: str | None = None) -> str:
    author = _escape_md_text(comment["author"] or "[deleted]")
    prefix = f"**{label}** - " if label else ""
    return (
        f"{prefix}**{author}** (score: {comment['score']})\n"
        f"> {_inline_image_urls(comment['body'])}"
    )


def _comments_for_review(
    conn: sqlite3.Connection,
    post_id: str,
    raw_source_comment_ids: str | None,
    other_limit: int = 5,
) -> str:
    """Render consensus source comments first, then other top comments."""
    source_ids = _source_comment_ids(raw_source_comment_ids)
    source_comments: list[sqlite3.Row] = []
    if source_ids:
        placeholders = ",".join("?" * len(source_ids))
        source_comments = conn.execute(
            f"""SELECT comment_id, body, score, author
                FROM comments
                WHERE post_id = ?
                  AND comment_id IN ({placeholders})
                ORDER BY score DESC""",
            (post_id, *source_ids),
        ).fetchall()

    source_seen = {comment["comment_id"] for comment in source_comments}
    if source_seen:
        placeholders = ",".join("?" * len(source_seen))
        other_comments = conn.execute(
            f"""SELECT comment_id, body, score, author
                FROM comments
                WHERE post_id = ?
                  AND comment_id NOT IN ({placeholders})
                ORDER BY score DESC
                LIMIT ?""",
            (post_id, *source_seen, other_limit),
        ).fetchall()
    else:
        other_comments = conn.execute(
            """SELECT comment_id, body, score, author
               FROM comments
               WHERE post_id = ?
               ORDER BY score DESC
               LIMIT ?""",
            (post_id, other_limit),
        ).fetchall()

    sections: list[str] = []
    if source_comments:
        sections.append(
            "### Consensus source comments\n\n"
            + "\n\n".join(
                _comment_md(comment, "Consensus source")
                for comment in source_comments
            )
        )
    if other_comments:
        heading = "### Other top comments" if source_comments else "### Top comments"
        sections.append(
            heading + "\n\n" + "\n\n".join(_comment_md(c) for c in other_comments)
        )
    return "\n\n---\n\n".join(sections)


# ── Tab 1: Review Queue ──────────────────────────────────────────────


def _remaining_count() -> int:
    conn = _get_conn()
    row = conn.execute(
        """SELECT COUNT(*) AS cnt FROM memes m
           JOIN ground_truths gt ON m.post_id = gt.post_id
           LEFT JOIN reviews r ON m.post_id = r.post_id
           WHERE r.post_id IS NULL"""
    ).fetchone()
    conn.close()
    return row["cnt"]


def load_next_unreviewed():
    conn = _get_conn()
    row = conn.execute(
        """SELECT m.post_id, m.title, m.subreddit, m.local_image_path,
                  gt.explanation, gt.consensus_confidence, gt.num_agreeing_comments,
                  gt.source_comment_ids
           FROM memes m
           JOIN ground_truths gt ON m.post_id = gt.post_id
           LEFT JOIN reviews r ON m.post_id = r.post_id
           WHERE r.post_id IS NULL
           ORDER BY RANDOM()
           LIMIT 1"""
    ).fetchone()

    if row is None:
        conn.close()
        empty_message = (
            "## ✅ Review queue empty\n\n"
            "No memes left to review. Next steps:\n\n"
            "- Run `basedbench predict <model>` against your validated set\n"
            "- Run `basedbench judge` to score predictions\n"
            "- Check the **Prediction Comparison** tab to see model results side-by-side\n"
            "- Or `basedbench ingest --limit 50` for a larger batch"
        )
        # Hide all the per-meme widgets and disable action buttons so the page
        # doesn't look mid-load.
        hide = gr.update(value="", visible=False)
        return (
            gr.update(value=None, visible=False),  # image
            gr.update(value=empty_message),  # info markdown — keep visible
            hide,  # ground truth
            hide,  # confidence
            hide,  # comments
            "",  # hidden post_id
            gr.update(value="", visible=False),  # exclude reason dropdown
            _remaining_count(),
            gr.update(interactive=False),  # validate btn
            gr.update(interactive=False),  # exclude btn
            gr.update(interactive=False),  # skip btn
        )

    post_id = row["post_id"]
    comments_text = _comments_for_review(conn, post_id, row["source_comment_ids"])
    conn.close()

    return (
        gr.update(value=_resolve_image(row["local_image_path"]), visible=True),
        gr.update(
            value=(
                f"**{_escape_md_text(row['title'])}**\n\n"
                f"r/{_escape_md_text(row['subreddit'])}"
            )
        ),
        gr.update(value=row["explanation"], visible=True),
        gr.update(
            value=f"Confidence: {row['consensus_confidence']:.2f} | "
            f"Agreeing comments: {row['num_agreeing_comments']}",
            visible=True,
        ),
        gr.update(value=comments_text, visible=True),
        post_id,
        gr.update(value="", visible=True),
        _remaining_count(),
        gr.update(interactive=True),
        gr.update(interactive=True),
        gr.update(interactive=True),
    )


def _write_review(post_id: str, status: str, reason: str | None = None) -> None:
    if not post_id:
        return
    conn = _get_conn()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT OR REPLACE INTO reviews (post_id, status, reason, reviewed_at) "
        "VALUES (?, ?, ?, ?)",
        (post_id, status, reason, now),
    )
    conn.commit()
    conn.close()


def validate_meme(post_id: str):
    _write_review(post_id, "validated")
    return load_next_unreviewed()


def exclude_meme(post_id: str, reason: str):
    _write_review(post_id, "excluded", reason or "other")
    return load_next_unreviewed()


def skip_meme():
    return load_next_unreviewed()


def _read_only_review_outputs():
    outputs = list(load_next_unreviewed())
    outputs[6] = gr.update(value="", visible=False)
    outputs[8] = gr.update(visible=False, interactive=False)
    outputs[9] = gr.update(visible=False, interactive=False)
    outputs[10] = gr.update(visible=False, interactive=False)
    return tuple(outputs)


def flag_consensus_failure(
    post_id: str,
    status: str,
    failure_modes: str,
    reviewer_notes: str,
    canonical_explanation: str,
) -> str:
    """Persist a consensus-regression entry for the current meme.

    Captures the current ground-truth explanation at flag-time so the regression
    eval can compare future re-runs against the version we caught failing.
    Returns a markdown status string for the UI.
    """
    if not post_id:
        return "_No meme loaded — switch tabs or pick a meme first._"

    conn = _get_conn()
    row = conn.execute(
        "SELECT explanation FROM ground_truths WHERE post_id = ?", (post_id,)
    ).fetchone()
    if row is None:
        conn.close()
        return f"_No ground truth exists for `{post_id}` to flag._"
    consensus_now = row["explanation"]
    now = datetime.now(timezone.utc).isoformat()

    conn.execute(
        """INSERT OR REPLACE INTO consensus_regression
           (post_id, status, canonical_explanation, failure_modes,
            reviewer_notes, consensus_at_annotation, annotated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            post_id,
            status,
            (canonical_explanation or None) and canonical_explanation.strip() or None,
            (failure_modes or None) and failure_modes.strip() or None,
            (reviewer_notes or None) and reviewer_notes.strip() or None,
            consensus_now,
            now,
        ),
    )
    conn.commit()
    conn.close()
    return (
        f"✅ Flagged `{post_id}` as **{status}** in the regression set "
        f"({now[:19]}Z)."
    )


# ── Tab 2: Browse ────────────────────────────────────────────────────


def _subreddits() -> list[str]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT DISTINCT subreddit FROM memes ORDER BY subreddit"
    ).fetchall()
    conn.close()
    return ["all"] + [r["subreddit"] for r in rows]


def _prediction_models() -> list[str]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT DISTINCT model_id FROM predictions ORDER BY model_id"
    ).fetchall()
    conn.close()
    return ["all"] + [r["model_id"] for r in rows]


def browse_memes(status_filter: str, subreddit_filter: str, search_text: str, page: int):
    per_page = 20
    offset = int(page) * per_page

    conditions: list[str] = []
    params: list[object] = []

    if status_filter == "validated":
        conditions.append("r.status = 'validated'")
    elif status_filter == "excluded":
        conditions.append("r.status = 'excluded'")
    elif status_filter == "unreviewed":
        conditions.append("r.post_id IS NULL")
        conditions.append("gt.post_id IS NOT NULL")

    if subreddit_filter and subreddit_filter != "all":
        conditions.append("m.subreddit = ?")
        params.append(subreddit_filter)

    if search_text:
        conditions.append("m.title LIKE ?")
        params.append(f"%{search_text}%")

    where = " AND ".join(conditions) if conditions else "1=1"

    conn = _get_conn()
    rows = conn.execute(
        f"""SELECT m.post_id, m.title, m.subreddit,
                   gt.explanation,
                   COALESCE(r.status,
                            CASE WHEN gt.post_id IS NOT NULL
                                 THEN 'unreviewed' ELSE 'no_consensus' END) AS review_status
            FROM memes m
            LEFT JOIN ground_truths gt ON m.post_id = gt.post_id
            LEFT JOIN reviews r ON m.post_id = r.post_id
            WHERE {where}
            ORDER BY m.post_id
            LIMIT ? OFFSET ?""",
        [*params, per_page, offset],
    ).fetchall()
    total = conn.execute(
        f"""SELECT COUNT(*) AS cnt
            FROM memes m
            LEFT JOIN ground_truths gt ON m.post_id = gt.post_id
            LEFT JOIN reviews r ON m.post_id = r.post_id
            WHERE {where}""",
        params,
    ).fetchone()["cnt"]
    conn.close()

    if not rows:
        return "No memes match the current filters.", ""

    badges = {
        "validated": "✅",
        "excluded": "❌",
        "unreviewed": "❓",
        "no_consensus": "⭕",
    }
    lines = []
    for r in rows:
        badge = badges.get(r["review_status"], "")
        explanation = (r["explanation"] or "No ground truth")[:100]
        lines.append(
            f"{badge} **{r['title']}** (r/{r['subreddit']})\n"
            f"  ID: `{r['post_id']}` | {explanation}..."
        )

    return "\n\n---\n\n".join(lines), f"Page {int(page) + 1} | Showing {len(rows)} of {total} memes"


# ── Tab 3: Prediction Comparison ─────────────────────────────────────


def _reviewed_memes() -> list[str]:
    conn = _get_conn()
    rows = conn.execute(
        """SELECT m.post_id, m.title FROM memes m
           JOIN reviews r ON m.post_id = r.post_id
           WHERE r.status = 'validated'
           ORDER BY m.title"""
    ).fetchall()
    conn.close()
    return [f"{r['post_id']} — {r['title']}" for r in rows]


def _badge(v: str | None) -> str:
    if v == "correct":
        return "\U0001f7e2"
    if v == "incorrect":
        return "\U0001f534"
    return "⚪"


def _prediction_markdown(conn: sqlite3.Connection, post_id: str) -> str:
    preds = conn.execute(
        """SELECT p.id, p.model_id, p.prediction
           FROM predictions p
           WHERE p.post_id = ? AND p.error IS NULL
           ORDER BY p.model_id""",
        (post_id,),
    ).fetchall()
    verdict_rows = conn.execute(
        """SELECT j.prediction_id, j.judge_model, j.verdict, j.judge_reasoning
           FROM judgments j
           JOIN predictions p ON j.prediction_id = p.id
           WHERE p.post_id = ?
             AND p.error IS NULL
             AND j.id = (
               SELECT MAX(j2.id) FROM judgments j2
               WHERE j2.prediction_id = j.prediction_id
                 AND j2.judge_model = j.judge_model
             )""",
        (post_id,),
    ).fetchall()

    verdicts_by_pred: dict[int, list[tuple[str, str | None, str | None]]] = {}
    for vr in verdict_rows:
        verdicts_by_pred.setdefault(vr["prediction_id"], []).append(
            (vr["judge_model"] or "(unknown)", vr["verdict"], vr["judge_reasoning"])
        )

    if not preds:
        return "_No successful predictions for this meme yet._"

    blocks = []
    for p in preds:
        verdicts = sorted(verdicts_by_pred.get(p["id"], []), key=lambda r: r[0])
        if not verdicts:
            header = f"### ⚪ `{_escape_md_text(p['model_id'])}`"
            verdict_section = "_unjudged_"
        else:
            distinct = {v for _, v, _ in verdicts if v is not None}
            agreement = (
                " · judges agree"
                if len(verdicts) > 1 and len(distinct) == 1
                else " · judges disagree"
                if len(verdicts) > 1
                else ""
            )
            badges = " ".join(_badge(v) for _, v, _ in verdicts)
            header = f"### {badges} `{_escape_md_text(p['model_id'])}`{agreement}"
            verdict_lines = []
            for judge_model, verdict, reasoning in verdicts:
                line = (
                    f"**{_badge(verdict)} {_escape_md_text(judge_model)}:** "
                    f"{_escape_md_text(verdict or 'unjudged')}"
                )
                if reasoning:
                    line += f"\n\n> {_escape_md_text(reasoning)}"
                verdict_lines.append(line)
            verdict_section = "\n\n".join(verdict_lines)

        blocks.append(
            f"{header}\n\n**Prediction:**\n\n{_escape_md_text(p['prediction'])}"
            f"\n\n{verdict_section}"
        )

    return "\n\n---\n\n".join(blocks)


def compare_predictions(meme_selection: str):
    if not meme_selection:
        empty = gr.update(value="", visible=False)
        return (
            gr.update(value=None, visible=False),
            empty,
            empty,
        )

    post_id = meme_selection.split(" — ", 1)[0].strip()
    conn = _get_conn()
    meme = conn.execute(
        """SELECT m.post_id, m.title, m.local_image_path, gt.explanation
           FROM memes m
           JOIN ground_truths gt ON m.post_id = gt.post_id
           WHERE m.post_id = ?""",
        (post_id,),
    ).fetchone()
    if meme is None:
        conn.close()
        return (
            gr.update(value=None, visible=False),
            gr.update(value="Meme not found.", visible=True),
            gr.update(value="", visible=False),
        )

    predictions_md = _prediction_markdown(conn, post_id)
    conn.close()

    img = _resolve_image(meme["local_image_path"])
    gt_text = f"**Ground Truth:**\n\n{meme['explanation']}"

    return (
        gr.update(value=img, visible=True),
        gr.update(value=gt_text, visible=True),
        gr.update(value=predictions_md, visible=True),
    )


# ── Tab 4: Inspect (read-only viewer over ALL content) ───────────────

# Every meme falls into exactly one state, derived from its review/ground-truth
# rows plus whether the consensus model ever ran on it. The labels mirror how
# the ingest pipeline records each decision (see pipeline/ingest.py).
_INSPECT_STATES: list[tuple[str, str]] = [
    ("all", "All content"),
    ("unreviewed", "❓ In review queue"),
    ("validated", "✅ Validated"),
    ("no_consensus", "⭕ No consensus"),
    ("quality_excluded", "❌ Legacy quality gate excluded"),
    ("safety_excluded", "❌ Safety gate excluded"),
    ("human_excluded", "❌ Reviewer excluded"),
    ("image_missing", "❌ Image missing"),
    ("pending", "⏳ Not yet processed"),
]
_INSPECT_STATE_LABELS = dict(_INSPECT_STATES)

# Common FROM clause: left-joins so memes with no ground truth / no review still
# appear, plus a derived "did consensus ever run" flag to separate genuine
# no-consensus memes from ones that were never processed.
_INSPECT_FROM = """
    FROM memes m
    LEFT JOIN ground_truths gt ON m.post_id = gt.post_id
    LEFT JOIN reviews r ON m.post_id = r.post_id
    LEFT JOIN (
        SELECT DISTINCT post_id FROM llm_calls WHERE role = 'consensus'
    ) cc ON cc.post_id = m.post_id
"""


def _inspect_where(
    status: str,
    subreddit: str,
    search: str,
    prediction_filter: str = "all",
    model_id: str = "all",
) -> tuple[str, list[object]]:
    conds: list[str] = []
    params: list[object] = []

    state_conds = {
        "validated": "r.status = 'validated'",
        "safety_excluded": "r.status = 'excluded' AND r.reason LIKE 'safety:%'",
        "quality_excluded": "r.status = 'excluded' AND r.reason LIKE 'auto:%'",
        "image_missing": "r.status = 'excluded' AND r.reason = 'image_missing'",
        "human_excluded": (
            "r.status = 'excluded' AND r.reason NOT LIKE 'safety:%' "
            "AND r.reason NOT LIKE 'auto:%' AND r.reason <> 'image_missing'"
        ),
        "unreviewed": "r.post_id IS NULL AND gt.post_id IS NOT NULL",
        "no_consensus": (
            "r.post_id IS NULL AND gt.post_id IS NULL AND cc.post_id IS NOT NULL"
        ),
        "pending": (
            "r.post_id IS NULL AND gt.post_id IS NULL AND cc.post_id IS NULL"
        ),
    }
    if status in state_conds:
        conds.append(state_conds[status])

    if subreddit and subreddit != "all":
        conds.append("m.subreddit = ?")
        params.append(subreddit)
    if search:
        conds.append("m.title LIKE ?")
        params.append(f"%{search}%")

    model_clause = ""
    model_params: list[object] = []
    if model_id and model_id != "all":
        model_clause = " AND p.model_id = ?"
        model_params.append(model_id)
    pred_exists = (
        "EXISTS (SELECT 1 FROM predictions p "
        "WHERE p.post_id = m.post_id AND p.error IS NULL"
        f"{model_clause})"
    )
    pred_missing = (
        "NOT EXISTS (SELECT 1 FROM predictions p "
        "WHERE p.post_id = m.post_id AND p.error IS NULL"
        f"{model_clause})"
    )
    if prediction_filter == "with_predictions":
        conds.append(pred_exists)
        params.extend(model_params)
    elif prediction_filter == "without_predictions":
        conds.append(pred_missing)
        params.extend(model_params)
    elif model_id and model_id != "all":
        conds.append(pred_exists)
        params.extend(model_params)

    where = " AND ".join(conds) if conds else "1=1"
    return where, params


# Hard cap on how many post_ids we stash in browser State for stepping. Plenty
# for review work; if a filter matches more, we note the truncation.
_INSPECT_CAP = 3000


def _inspect_ids(
    status: str,
    subreddit: str,
    search: str,
    prediction_filter: str,
    model_id: str,
) -> tuple[list[str], int]:
    """Return (post_ids matching the filter, total matches before the cap)."""
    where, params = _inspect_where(
        status, subreddit, search, prediction_filter, model_id
    )
    conn = _get_conn()
    total = conn.execute(
        f"SELECT COUNT(*) AS cnt {_INSPECT_FROM} WHERE {where}", params
    ).fetchone()["cnt"]
    rows = conn.execute(
        f"SELECT m.post_id {_INSPECT_FROM} WHERE {where} "
        f"ORDER BY m.post_id DESC LIMIT ?",
        [*params, _INSPECT_CAP],
    ).fetchall()
    conn.close()
    return [r["post_id"] for r in rows], total


def _classify_state(row: sqlite3.Row) -> str:
    """Derive the display state for one inspect-detail row."""
    status = row["review_status"]
    reason = row["review_reason"]
    if status == "validated":
        return "validated"
    if status == "excluded":
        if reason and reason.startswith("safety:"):
            return "safety_excluded"
        if reason and reason.startswith("auto:"):
            return "quality_excluded"
        if reason == "image_missing":
            return "image_missing"
        return "human_excluded"
    if row["explanation"] is not None:
        return "unreviewed"
    if row["consensus_ran"]:
        return "no_consensus"
    return "pending"


# Which gate each state implicates by default when flagging a misfire.
_STATE_TO_GATE = {
    "safety_excluded": "safety",
    "quality_excluded": "quality",
    "no_consensus": "consensus",
}


def _inspect_detail(post_id: str) -> dict | None:
    conn = _get_conn()
    row = conn.execute(
        f"""SELECT m.post_id, m.title, m.subreddit, m.local_image_path,
                   gt.explanation, gt.consensus_confidence, gt.num_agreeing_comments,
                   gt.source_comment_ids,
                   r.status AS review_status, r.reason AS review_reason,
                   (cc.post_id IS NOT NULL) AS consensus_ran
            {_INSPECT_FROM}
            WHERE m.post_id = ?""",
        (post_id,),
    ).fetchone()
    if row is None:
        conn.close()
        return None

    # Latest gate/consensus reasoning, most recent call per role.
    call_rows = conn.execute(
        """SELECT role, verdict, reasoning, error FROM llm_calls
           WHERE post_id = ? AND role IN ('safety_gate', 'quality_gate', 'consensus')
           ORDER BY id DESC""",
        (post_id,),
    ).fetchall()
    comments_text = _comments_for_review(conn, post_id, row["source_comment_ids"])
    predictions_text = _prediction_markdown(conn, post_id)
    conn.close()

    latest_by_role: dict[str, sqlite3.Row] = {}
    for cr in call_rows:
        latest_by_role.setdefault(cr["role"], cr)

    return {
        "row": row,
        "state": _classify_state(row),
        "calls": latest_by_role,
        "comments_text": comments_text,
        "predictions_text": predictions_text,
    }


def _render_inspect(post_id: str | None):
    """Render one meme into the inspect widgets (read-only)."""
    blank = gr.update(value=None, visible=False)
    if not post_id:
        return (
            blank,
            gr.update(value="_No meme to show for this filter._", visible=True),
            gr.update(value="", visible=False),
            gr.update(value="", visible=False),
            gr.update(value="", visible=False),
            gr.update(value="", visible=False),
            "",
            gr.update(value="consensus"),
        )

    detail = _inspect_detail(post_id)
    if detail is None:
        return (
            blank,
            gr.update(value=f"_Meme `{post_id}` not found._", visible=True),
            gr.update(value="", visible=False),
            gr.update(value="", visible=False),
            gr.update(value="", visible=False),
            gr.update(value="", visible=False),
            "",
            gr.update(value="consensus"),
        )

    row = detail["row"]
    state = detail["state"]
    calls = detail["calls"]

    banner = _INSPECT_STATE_LABELS.get(state, state)
    info_lines = [
        f"**{_escape_md_text(row['title'])}**",
        f"r/{_escape_md_text(row['subreddit'])}",
        f"**Status:** {banner}",
    ]
    if row["review_reason"]:
        info_lines.append(f"_reason:_ `{row['review_reason']}`")
    # Surface the gate/consensus model's own reasoning so you can judge whether
    # the decision was right.
    role_label = {
        "safety_gate": "Safety gate",
        "quality_gate": "Quality gate",
        "consensus": "Consensus",
    }
    for role in ("safety_gate", "quality_gate", "consensus"):
        cr = calls.get(role)
        if cr is None:
            continue
        verdict = cr["verdict"] or ("error" if cr["error"] else "—")
        reasoning = (cr["reasoning"] or cr["error"] or "").strip()
        if reasoning:
            info_lines.append(
                f"**{role_label[role]}:** _{verdict}_ — {reasoning[:400]}"
            )
        else:
            info_lines.append(f"**{role_label[role]}:** _{verdict}_")
    info_md = "\n\n".join(info_lines)

    if row["explanation"] is not None:
        gt_update = gr.update(value=row["explanation"], visible=True)
        conf = row["consensus_confidence"]
        meta_update = gr.update(
            value=(
                f"Confidence: {conf:.2f} | Agreeing comments: "
                f"{row['num_agreeing_comments']}"
                if conf is not None
                else ""
            ),
            visible=conf is not None,
        )
    else:
        gt_update = gr.update(
            value="— no ground truth (meme has no consensus explanation) —",
            visible=True,
        )
        meta_update = gr.update(value="", visible=False)

    return (
        gr.update(value=_resolve_image(row["local_image_path"]), visible=True),
        gr.update(value=info_md, visible=True),
        gt_update,
        meta_update,
        gr.update(value=detail["predictions_text"], visible=True),
        gr.update(value=detail["comments_text"] or "_no comments_", visible=True),
        post_id,
        gr.update(value=_STATE_TO_GATE.get(state, "consensus")),
    )


def _position_text(idx: int, ids: list[str], total: int) -> str:
    if not ids:
        return "0 / 0"
    shown = len(ids)
    suffix = f" (capped from {total})" if total > shown else ""
    return f"{idx + 1} / {shown}{suffix}"


def inspect_apply(
    status: str,
    subreddit: str,
    search: str,
    prediction_filter: str,
    model_id: str,
):
    ids, total = _inspect_ids(status, subreddit, search, prediction_filter, model_id)
    first = ids[0] if ids else None
    return (ids, 0, *_render_inspect(first), _position_text(0, ids, total))


def inspect_step(ids: list[str], idx: int, delta: int):
    if not ids:
        return (idx, *_render_inspect(None), _position_text(idx, ids, len(ids)))
    new_idx = max(0, min(int(idx) + delta, len(ids) - 1))
    return (
        new_idx,
        *_render_inspect(ids[new_idx]),
        _position_text(new_idx, ids, len(ids)),
    )


def flag_gate_misfire(post_id: str, gate: str, correct_decision: str, notes: str):
    """Record that a gate/consensus decision was wrong, capturing what it decided.

    Returns (feedback_md, cleared_correct, cleared_notes) so the form resets after
    a submit and the confirmation is timestamped (so repeat flags visibly update).
    """
    if not post_id:
        return ("_No meme loaded._", gr.update(), gr.update())

    detail = _inspect_detail(post_id)
    gate_decision = None
    if detail is not None:
        role = {"safety": "safety_gate", "quality": "quality_gate", "consensus": "consensus"}[gate]
        cr = detail["calls"].get(role)
        if cr is not None:
            gate_decision = cr["verdict"] or (cr["error"] and "error") or None
        elif gate == "consensus":
            gate_decision = "no_consensus" if detail["state"] == "no_consensus" else None

    now = datetime.now(timezone.utc).isoformat()
    conn = _get_conn()
    conn.execute(
        """INSERT OR REPLACE INTO gate_feedback
           (post_id, gate, gate_decision, correct_decision, notes, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            post_id,
            gate,
            gate_decision,
            (correct_decision or "").strip() or None,
            (notes or "").strip() or None,
            now,
        ),
    )
    conn.commit()
    conn.close()
    return (
        f"✅ Flagged `{post_id}` — **{gate}** gate marked wrong. ({now[11:19]}Z)",
        gr.update(value=""),
        gr.update(value=""),
    )


# ── Tab 5: Stats & Leaderboard ───────────────────────────────────────


def _load_stats() -> tuple[str, str, str, str]:
    """Render the four markdown blocks shown on the Stats tab.

    Returns (corpus, predictions, leaderboard, consensus_quality).
    """
    from basedbench.db import Database
    from basedbench.db import queries

    db = Database.open(_DB_PATH)
    try:
        counts = queries.get_status_counts(db)
        pred_counts = queries.get_prediction_counts(db)
        judge_counts = queries.get_judgment_counts(db)
        agreement = queries.get_judge_agreement(db)
        consensus = queries.consensus_quality_stats(db)
    finally:
        db.close()

    # ─── Corpus snapshot ───
    corpus_md = (
        f"### Corpus\n\n"
        f"| | |\n"
        f"|---|---|\n"
        f"| Total memes | **{counts.total_memes:,}** |\n"
        f"| With consensus | **{counts.with_consensus:,}** |\n"
        f"| Validated | **{counts.validated:,}** |\n"
        f"| Excluded | {counts.excluded:,} |\n"
        f"| Unreviewed (queue) | {counts.unreviewed:,} |\n"
    )

    # ─── Predictions status ───
    if pred_counts:
        pred_lines = [
            f"| `{p.model_id}` | {p.predicted:,} / {p.total_available:,} |"
            for p in pred_counts
        ]
        predictions_md = (
            "### Predictions (against validated set)\n\n"
            "| Target model | Done / Total |\n|---|---|\n"
            + "\n".join(pred_lines)
        )
    else:
        predictions_md = (
            "### Predictions\n\n_No predictions yet. "
            "Run `basedbench predict <model>` to start._"
        )

    # ─── Leaderboard: pivot per-(target, judge) into a matrix ───
    if judge_counts:
        judges = sorted({jc.judge_model for jc in judge_counts})
        targets = sorted({jc.model_id for jc in judge_counts})
        by_pair = {(jc.model_id, jc.judge_model): jc for jc in judge_counts}
        agreement_by_target = {a.model_id: a for a in agreement}

        # Compute the per-target Combined (mean) score first so we can sort
        # the leaderboard by it. Simple mean of per-judge accuracies — close
        # enough to a strict per-prediction mean even when judge denominators
        # differ slightly (off by <0.5% in practice).
        combined_by_target: dict[str, float | None] = {}
        for target in targets:
            accs = [
                by_pair[(target, j)].accuracy
                for j in judges
                if (target, j) in by_pair and by_pair[(target, j)].judged > 0
            ]
            combined_by_target[target] = sum(accs) / len(accs) if accs else None

        # Sort highest combined score first; targets without scores fall to the
        # bottom but stay alphabetized among themselves.
        ranked_targets = sorted(
            targets,
            key=lambda t: (
                -(combined_by_target[t] or -1),
                t,
            ),
        )

        header = (
            "| Target model | "
            + " | ".join(f"vs. {j}" for j in judges)
            + " | **Combined** | Agreement |"
        )
        sep = "|---|" + "|".join(["---"] * len(judges)) + "|---|---|"
        body_rows = []
        for target in ranked_targets:
            cells = []
            for j in judges:
                jc = by_pair.get((target, j))
                if jc is None or jc.judged == 0:
                    cells.append("—")
                else:
                    cells.append(f"{jc.correct}/{jc.judged} ({jc.accuracy * 100:.1f}%)")
            combined = combined_by_target[target]
            combined_cell = (
                f"**{combined * 100:.1f}%**" if combined is not None else "—"
            )
            agree = agreement_by_target.get(target)
            if agree is not None and agree.judged_by_multiple > 0:
                agree_cell = (
                    f"{agree.agreements}/{agree.judged_by_multiple} "
                    f"({agree.rate * 100:.1f}%)"
                )
            else:
                agree_cell = "—"
            body_rows.append(
                f"| `{target}` | "
                + " | ".join(cells)
                + f" | {combined_cell} | {agree_cell} |"
            )
        leaderboard_md = (
            "### Leaderboard\n\n"
            + header + "\n" + sep + "\n"
            + "\n".join(body_rows)
            + "\n\n_**Combined** = mean across judges. Agreement = fraction "
            "of predictions where both judges returned the same verdict._"
        )
    else:
        leaderboard_md = (
            "### Leaderboard\n\n_No judgments yet. "
            "Run `basedbench judge` after predictions to populate._"
        )

    # ─── Consensus quality ───
    if consensus.n_grounded > 0:
        # Log-scaled bar chart: any non-zero bin gets at least ▁ so highly
        # skewed distributions (typical here, since strict-criteria
        # consensus piles confidence near 1.0) stay readable.
        import math

        bars = "▁▂▃▄▅▆▇█"
        max_count = max(consensus.confidence_histogram) or 1
        log_max = math.log1p(max_count)
        hist_chars = "".join(
            " " if c == 0
            else bars[min(int(math.log1p(c) / log_max * (len(bars) - 1)), len(bars) - 1)]
            for c in consensus.confidence_histogram
        )
        # Also surface the raw bin counts so the bar chart's shape isn't the
        # only signal
        bin_labels = [f"{i/10:.1f}" for i in range(10)]
        raw_counts = ", ".join(
            f"{label}: {n}"
            for label, n in zip(bin_labels, consensus.confidence_histogram)
            if n > 0
        )
        consensus_md = (
            f"### Consensus quality\n\n"
            f"| | |\n|---|---|\n"
            f"| N grounded memes | {consensus.n_grounded:,} |\n"
            f"| Mean confidence | {consensus.mean_confidence:.3f} |\n"
            f"| Median agreeing comments | {consensus.median_agreeing_comments} |\n"
            f"| Confidence distribution (0.0 → 1.0) | `{hist_chars}` (log-scaled) |\n"
            f"| Non-empty bins | {raw_counts} |\n"
        )
    else:
        consensus_md = "### Consensus quality\n\n_No grounded memes yet._"

    return corpus_md, predictions_md, leaderboard_md, consensus_md


# ── Tab 5: AI Gloss Failures (regression set) ────────────────────────


def _load_regressions() -> str:
    """Render the table of flagged consensus failures."""
    from basedbench.db import Database
    from basedbench.db import queries

    db = Database.open(_DB_PATH)
    try:
        entries = queries.list_consensus_regressions(db)
    finally:
        db.close()

    if not entries:
        return (
            "### AI Gloss Failures\n\n"
            "_None flagged yet. Use the **🚩 Flag this meme's ground-truth** "
            "accordion under Review Queue to add cases where the consensus "
            "model produced a wrong gloss._"
        )

    by_status: dict[str, int] = {}
    for e in entries:
        by_status[e.status] = by_status.get(e.status, 0) + 1
    counts = " · ".join(
        f"**{by_status.get(s, 0)}** {s}" for s in ("wrong", "partial", "correct")
    )

    rows = []
    for e in entries:
        # Truncate long fields for readability; full text still in DB.
        snippet = (e.consensus_at_annotation or "").replace("\n", " ").strip()
        if len(snippet) > 220:
            snippet = snippet[:220] + "…"
        notes = (e.reviewer_notes or "—").replace("\n", " ").strip()
        if len(notes) > 120:
            notes = notes[:120] + "…"
        canonical = (e.canonical_explanation or "—").replace("\n", " ").strip()
        if len(canonical) > 120:
            canonical = canonical[:120] + "…"
        modes = e.failure_modes or "—"
        rows.append(
            f"| `{e.post_id}` | **{e.status}** | {snippet} | "
            f"{canonical} | {modes} | {notes} | {e.annotated_at[:10]} |"
        )

    return (
        "### AI Gloss Failures\n\n"
        f"{len(entries)} flagged · {counts}\n\n"
        "| post_id | status | consensus at flag time | canonical | "
        "failure modes | notes | date |\n"
        "|---|---|---|---|---|---|---|\n"
        + "\n".join(rows)
        + "\n\n_Run `basedbench regression-eval` (coming) to re-test these "
        "against current consensus config._"
    )


# ── Tab 6: Filter Misfires (gate-feedback set) ───────────────────────


def _load_gate_feedback() -> str:
    """Render the table of flagged safety/consensus misfires."""
    from basedbench.db import Database
    from basedbench.db import queries

    db = Database.open(_DB_PATH)
    try:
        entries = queries.list_gate_feedback(db)
    finally:
        db.close()

    if not entries:
        return (
            "### Filter Misfires\n\n"
            "_None flagged yet. In the **Inspect** tab, open the "
            "**🚩 A filter got this wrong** accordion to flag a meme the "
            "safety/consensus filter handled incorrectly._"
        )

    by_gate: dict[str, int] = {}
    for e in entries:
        by_gate[e.gate] = by_gate.get(e.gate, 0) + 1
    counts = " · ".join(
        f"**{by_gate.get(g, 0)}** {g}" for g in ("safety", "quality", "consensus")
    )

    rows = []
    for e in entries:
        notes = (e.notes or "—").replace("\n", " ").strip()
        if len(notes) > 160:
            notes = notes[:160] + "…"
        correct = (e.correct_decision or "—").replace("\n", " ").strip()
        rows.append(
            f"| `{e.post_id}` | **{e.gate}** | {e.gate_decision or '—'} | "
            f"{correct} | {notes} | {e.created_at[:10]} |"
        )

    return (
        "### Filter Misfires\n\n"
        f"{len(entries)} flagged · {counts}\n\n"
        "| post_id | gate | gate decided | should have been | notes | date |\n"
        "|---|---|---|---|---|---|\n"
        + "\n".join(rows)
    )


# ── Tab 8: Consensus Eval (label review) ─────────────────────────────


_EVAL_CATEGORIES: list[tuple[str, str]] = [
    ("All active eval items", "all"),
    ("Bad gloss", "bad_gloss"),
    ("Easy yes consensus", "easy_yes_consensus"),
    ("Hard yes consensus", "hard_yes_consensus"),
    ("True no consensus", "true_no_consensus"),
    ("False positive consensus", "false_positive_consensus"),
    ("Source comment mismatch", "source_comment_mismatch"),
]


def _eval_where(category: str, search: str) -> tuple[str, list[object]]:
    conds = ["cei.active = 1"]
    params: list[object] = []
    if category and category != "all":
        conds.append("cei.category = ?")
        params.append(category)
    if search:
        conds.append("(m.title LIKE ? OR m.post_id LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%"])
    return " AND ".join(conds), params


def _eval_ids(category: str, search: str) -> tuple[list[str], int]:
    where, params = _eval_where(category, search)
    conn = _get_conn()
    total = conn.execute(
        f"""SELECT COUNT(*) AS cnt
            FROM consensus_eval_items cei
            JOIN memes m ON m.post_id = cei.post_id
            WHERE {where}""",
        params,
    ).fetchone()["cnt"]
    rows = conn.execute(
        f"""SELECT cei.post_id
            FROM consensus_eval_items cei
            JOIN memes m ON m.post_id = cei.post_id
            WHERE {where}
            ORDER BY cei.category, cei.updated_at DESC, cei.post_id
            LIMIT ?""",
        [*params, _INSPECT_CAP],
    ).fetchall()
    conn.close()
    return [r["post_id"] for r in rows], total


def _eval_expected_label(expected_has_consensus: int | bool) -> str:
    return "consensus" if bool(expected_has_consensus) else "no_consensus"


def _eval_detail(post_id: str) -> dict | None:
    conn = _get_conn()
    row = conn.execute(
        """SELECT cei.post_id, cei.category, cei.expected_has_consensus,
                  cei.expected_explanation, cei.source, cei.notes, cei.updated_at,
                  m.title, m.subreddit, m.local_image_path,
                  gt.explanation AS ground_truth,
                  gt.source_comment_ids
           FROM consensus_eval_items cei
           JOIN memes m ON m.post_id = cei.post_id
           LEFT JOIN ground_truths gt ON gt.post_id = cei.post_id
           WHERE cei.post_id = ?""",
        (post_id,),
    ).fetchone()
    if row is None:
        conn.close()
        return None

    results = conn.execute(
        """SELECT r.run_id, run.prompt_label, r.actual_has_consensus,
                  r.actual_explanation, r.confidence, r.passed, r.error, r.created_at
           FROM consensus_eval_results r
           JOIN consensus_eval_runs run ON run.run_id = r.run_id
           WHERE r.post_id = ?
           ORDER BY r.created_at DESC
           LIMIT 5""",
        (post_id,),
    ).fetchall()
    comments_text = _comments_for_review(conn, post_id, row["source_comment_ids"])
    conn.close()
    return {"row": row, "results": results, "comments_text": comments_text}


def _render_eval_item(post_id: str | None):
    blank_image = gr.update(value=None, visible=False)
    if not post_id:
        return (
            blank_image,
            gr.update(value="_No eval item matches this filter._", visible=True),
            gr.update(value="", visible=False),
            gr.update(value="", visible=False),
            gr.update(value="", visible=False),
            "",
            gr.update(value=""),
        )

    detail = _eval_detail(post_id)
    if detail is None:
        return (
            blank_image,
            gr.update(value=f"_Eval item `{post_id}` not found._", visible=True),
            gr.update(value="", visible=False),
            gr.update(value="", visible=False),
            gr.update(value="", visible=False),
            "",
            gr.update(value=""),
        )

    row = detail["row"]
    expected = _eval_expected_label(row["expected_has_consensus"])
    info = [
        f"**{_escape_md_text(row['title'])}**",
        f"r/{_escape_md_text(row['subreddit'])}",
        f"ID: `{row['post_id']}`",
        f"**Category:** `{row['category']}`",
        f"**Expected:** `{expected}`",
        f"**Source:** `{row['source']}`",
    ]
    if row["notes"]:
        info.append(f"**Notes:** {_escape_md_text(row['notes'])}")

    expected_text = row["expected_explanation"] or ""
    if row["ground_truth"] and row["ground_truth"] != expected_text:
        expected_text = (
            (expected_text + "\n\n" if expected_text else "")
            + f"Current ground truth:\n{row['ground_truth']}"
        )

    result_rows = []
    for result in detail["results"]:
        actual = _eval_expected_label(result["actual_has_consensus"])
        verdict = "pass" if result["passed"] else "fail"
        conf = (
            f"{result['confidence']:.2f}"
            if result["confidence"] is not None
            else "—"
        )
        snippet = (result["actual_explanation"] or result["error"] or "—").replace(
            "\n", " "
        )
        if len(snippet) > 180:
            snippet = snippet[:180] + "…"
        result_rows.append(
            f"| `{result['prompt_label']}` | **{verdict}** | `{actual}` | "
            f"{conf} | {snippet} |"
        )
    if result_rows:
        results_md = (
            "| run | result | actual | conf | explanation/error |\n"
            "|---|---|---|---|---|\n"
            + "\n".join(result_rows)
        )
    else:
        results_md = "_No eval runs for this item yet._"

    return (
        gr.update(value=_resolve_image(row["local_image_path"]), visible=True),
        gr.update(value="\n\n".join(info), visible=True),
        gr.update(value=expected_text or "— no expected explanation —", visible=True),
        gr.update(value=results_md, visible=True),
        gr.update(value=detail["comments_text"] or "_no comments_", visible=True),
        post_id,
        gr.update(value=row["expected_explanation"] or ""),
    )


def eval_apply(category: str, search: str):
    ids, total = _eval_ids(category, search)
    first = ids[0] if ids else None
    return (ids, 0, *_render_eval_item(first), _position_text(0, ids, total))


def eval_step(ids: list[str], idx: int, delta: int):
    if not ids:
        return (idx, *_render_eval_item(None), _position_text(idx, ids, len(ids)))
    new_idx = max(0, min(int(idx) + delta, len(ids) - 1))
    return (
        new_idx,
        *_render_eval_item(ids[new_idx]),
        _position_text(new_idx, ids, len(ids)),
    )


def _read_only_eval_apply(category: str, search: str):
    outputs = list(eval_apply(category, search))
    outputs[8] = gr.update(value="", visible=False)
    return tuple(outputs)


def _read_only_eval_step(ids: list[str], idx: int, delta: int):
    outputs = list(eval_step(ids, idx, delta))
    outputs[7] = gr.update(value="", visible=False)
    return tuple(outputs)


def _append_eval_note(existing: str | None, action: str, reviewer_notes: str) -> str:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    note = f"{now} eval_review: {action}"
    if reviewer_notes.strip():
        note += f" - {reviewer_notes.strip()}"
    return "\n".join(part for part in ((existing or "").strip(), note) if part)


def update_eval_item(
    post_id: str,
    category_filter: str,
    search: str,
    action: str,
    expected_explanation: str,
    reviewer_notes: str,
):
    if not post_id:
        return (*eval_apply(category_filter, search), "_No eval item loaded._")

    conn = _get_conn()
    row = conn.execute(
        """SELECT category, expected_has_consensus, expected_explanation, notes
           FROM consensus_eval_items WHERE post_id = ?""",
        (post_id,),
    ).fetchone()
    if row is None:
        conn.close()
        return (*eval_apply(category_filter, search), f"_Eval item `{post_id}` not found._")

    explanation = expected_explanation.strip() or row["expected_explanation"]
    notes = _append_eval_note(row["notes"], action, reviewer_notes)
    if action == "Confirm expected label":
        conn.execute(
            """UPDATE consensus_eval_items
               SET expected_explanation = ?, notes = ?, updated_at = ?
               WHERE post_id = ?""",
            (explanation, notes, datetime.now(timezone.utc).isoformat(), post_id),
        )
    elif action == "Reclassify as consensus":
        conn.execute(
            """UPDATE consensus_eval_items
               SET category = 'hard_yes_consensus',
                   expected_has_consensus = 1,
                   expected_explanation = ?,
                   notes = ?,
                   active = 1,
                   updated_at = ?
               WHERE post_id = ?""",
            (explanation, notes, datetime.now(timezone.utc).isoformat(), post_id),
        )
    elif action == "Reclassify as no consensus":
        conn.execute(
            """UPDATE consensus_eval_items
               SET category = 'true_no_consensus',
                   expected_has_consensus = 0,
                   expected_explanation = NULL,
                   notes = ?,
                   active = 1,
                   updated_at = ?
               WHERE post_id = ?""",
            (notes, datetime.now(timezone.utc).isoformat(), post_id),
        )
    elif action == "Deactivate from eval":
        conn.execute(
            """UPDATE consensus_eval_items
               SET active = 0, notes = ?, updated_at = ?
               WHERE post_id = ?""",
            (notes, datetime.now(timezone.utc).isoformat(), post_id),
        )
    else:
        conn.close()
        return (*eval_apply(category_filter, search), f"_Unknown action: {action}_")

    conn.commit()
    conn.close()
    feedback = f"✅ `{post_id}` updated: **{action}**"
    return (*eval_apply(category_filter, search), feedback)


# ── Build Gradio App ─────────────────────────────────────────────────


def build_app(read_only: bool = False) -> gr.Blocks:
    with gr.Blocks(title="basedBench Review UI") as app:
        gr.Markdown("# basedBench Review UI")
        if read_only:
            gr.Markdown("_Read-only mode: review and labeling controls are disabled._")

        with gr.Tab("Review Queue"):
            with gr.Row():
                with gr.Column(scale=1):
                    review_image = gr.Image(
                        label="Meme", type="filepath", elem_classes="constrained-meme"
                    )
                with gr.Column(scale=1):
                    review_info = gr.Markdown()
                    review_gt = gr.Textbox(label="Ground Truth", lines=4, interactive=False)
                    review_confidence = gr.Markdown()
                    review_comments = gr.Markdown(label="Top Comments")

            review_post_id = gr.Textbox(visible=False)
            review_remaining = gr.Number(label="Remaining to review", interactive=False)

            with gr.Row():
                btn_validate = gr.Button(
                    "Validate", variant="primary", visible=not read_only
                )
                exclude_reason = gr.Dropdown(
                    choices=[
                        "bad image",
                        "wrong explanation",
                        "not a meme",
                        "duplicate",
                        "other",
                    ],
                    label="Exclude reason",
                    value="other",
                    allow_custom_value=True,
                    visible=not read_only,
                )
                btn_exclude = gr.Button(
                    "Exclude", variant="stop", visible=not read_only
                )
                btn_skip = gr.Button("Skip", visible=not read_only)

            review_outputs = [
                review_image,
                review_info,
                review_gt,
                review_confidence,
                review_comments,
                review_post_id,
                exclude_reason,
                review_remaining,
                btn_validate,
                btn_exclude,
                btn_skip,
            ]
            if not read_only:
                btn_validate.click(
                    validate_meme, inputs=[review_post_id], outputs=review_outputs
                )
                btn_exclude.click(
                    exclude_meme,
                    inputs=[review_post_id, exclude_reason],
                    outputs=review_outputs,
                )
            if not read_only:
                btn_skip.click(skip_meme, inputs=[], outputs=review_outputs)
            app.load(
                _read_only_review_outputs if read_only else load_next_unreviewed,
                outputs=review_outputs,
            )

            with gr.Accordion(
                "🚩 Flag this meme's ground-truth explanation (consensus failure)",
                open=False,
                visible=not read_only,
            ):
                gr.Markdown(
                    "_Use this when the consensus model's gloss is wrong, "
                    "missing the joke, or merging incompatible interpretations. "
                    "Flagged memes go into the regression set for testing future "
                    "consensus prompt/model changes._"
                )
                flag_status = gr.Radio(
                    choices=["wrong", "partial", "correct"],
                    value="wrong",
                    label="Status",
                    info="`wrong` = gloss misses the joke; `partial` = "
                    "gloss captures part but not the full picture; "
                    "`correct` = surprisingly good (use sparingly, as positive controls).",
                )
                flag_failure_modes = gr.Textbox(
                    label="Failure modes (comma-separated tags)",
                    placeholder="e.g. vote_bias, merged_views, ignored_kym_link",
                )
                flag_canonical = gr.Textbox(
                    label="Canonical explanation (optional)",
                    placeholder="What the gloss SHOULD have said — e.g. linked KYM "
                    "explanation, your own correction…",
                    lines=3,
                )
                flag_notes = gr.Textbox(
                    label="Reviewer notes",
                    placeholder="Why this is wrong, what the model missed, etc.",
                    lines=2,
                )
                btn_flag = gr.Button("Flag for regression set", variant="secondary")
                flag_feedback = gr.Markdown()
                btn_flag.click(
                    flag_consensus_failure,
                    inputs=[
                        review_post_id, flag_status, flag_failure_modes,
                        flag_notes, flag_canonical,
                    ],
                    outputs=[flag_feedback],
                )

        with gr.Tab("Browse") as browse_tab:
            with gr.Row():
                browse_status = gr.Dropdown(
                    choices=["all", "validated", "excluded", "unreviewed"],
                    value="all",
                    label="Status",
                )
                browse_subreddit = gr.Dropdown(
                    choices=_subreddits() if _DB_PATH.exists() else ["all"],
                    value="all",
                    label="Subreddit",
                )
                browse_search = gr.Textbox(
                    label="Search title", placeholder="Type to search..."
                )
                browse_page = gr.Number(value=0, label="Page", precision=0)

            btn_browse = gr.Button("Search")
            browse_results = gr.Markdown()
            browse_page_info = gr.Markdown()
            btn_browse.click(
                browse_memes,
                inputs=[browse_status, browse_subreddit, browse_search, browse_page],
                outputs=[browse_results, browse_page_info],
            )
            # Refresh subreddit options whenever the user activates the tab —
            # otherwise the dropdown is frozen at app-startup state.
            browse_tab.select(
                lambda: gr.update(choices=_subreddits()),
                outputs=[browse_subreddit],
            )

        with gr.Tab("Prediction Comparison") as compare_tab:
            _initial_choices = _reviewed_memes() if _DB_PATH.exists() else []
            _initial_value = _initial_choices[0] if _initial_choices else None
            meme_selector = gr.Dropdown(
                choices=_initial_choices,
                value=_initial_value,
                label="Select a validated meme",
            )
            compare_empty = gr.Markdown(
                visible=not _initial_choices,
                value=(
                    "_No validated memes yet. Use the Review Queue tab to validate at least "
                    "one meme, then come back here._"
                ),
            )

            def _refresh_compare_choices():
                """Re-query validated memes when the user opens this tab."""
                choices = _reviewed_memes()
                # Preserve the current selection if it's still valid; else pick the first.
                return (
                    gr.update(choices=choices),
                    gr.update(visible=not choices),
                )

            compare_tab.select(
                _refresh_compare_choices,
                outputs=[meme_selector, compare_empty],
            )
            with gr.Row():
                with gr.Column(scale=1):
                    compare_image = gr.Image(
                        label="Meme",
                        type="filepath",
                        elem_classes="constrained-meme",
                        visible=False,
                    )
                with gr.Column(scale=1):
                    compare_gt = gr.Markdown(visible=False)
                    compare_preds = gr.Markdown(visible=False)
            # Auto-fire on selection change AND on initial app load so the user
            # doesn't have to click a button to see anything.
            meme_selector.change(
                compare_predictions,
                inputs=[meme_selector],
                outputs=[compare_image, compare_gt, compare_preds],
            )
            if _initial_value is not None:
                app.load(
                    compare_predictions,
                    inputs=[meme_selector],
                    outputs=[compare_image, compare_gt, compare_preds],
                )

        with gr.Tab("Inspect") as inspect_tab:
            gr.Markdown(
                "_Read-only meme viewer over **all** content — image, metadata, "
                "ground truth, predictions, judgments, and comments. Filters "
                "choose which memes you step through; no review state changes "
                "happen here._"
            )
            inspect_ids_state = gr.State([])
            inspect_idx_state = gr.State(0)

            with gr.Row():
                inspect_status = gr.Dropdown(
                    choices=[(label, key) for key, label in _INSPECT_STATES],
                    value="all",
                    label="Status",
                )
                inspect_subreddit = gr.Dropdown(
                    choices=_subreddits() if _DB_PATH.exists() else ["all"],
                    value="all",
                    label="Subreddit",
                )
                inspect_search = gr.Textbox(
                    label="Search title", placeholder="Type to search..."
                )

            with gr.Row():
                inspect_prediction_filter = gr.Dropdown(
                    choices=[
                        ("All prediction coverage", "all"),
                        ("Has successful prediction", "with_predictions"),
                        ("Missing successful prediction", "without_predictions"),
                    ],
                    value="all",
                    label="Prediction coverage",
                )
                inspect_model = gr.Dropdown(
                    choices=_prediction_models() if _DB_PATH.exists() else ["all"],
                    value="all",
                    label="Prediction model",
                )
                btn_inspect_apply = gr.Button("Apply filters", variant="primary")

            with gr.Row():
                btn_inspect_prev = gr.Button("← Prev")
                inspect_position = gr.Markdown("0 / 0")
                btn_inspect_next = gr.Button("Next →")

            with gr.Row():
                with gr.Column(scale=1):
                    inspect_image = gr.Image(
                        label="Meme",
                        type="filepath",
                        elem_classes="constrained-meme",
                        visible=False,
                    )
                with gr.Column(scale=1):
                    inspect_info = gr.Markdown()
                    inspect_gt = gr.Textbox(
                        label="Ground Truth", lines=4, interactive=False, visible=False
                    )
                    inspect_meta = gr.Markdown(visible=False)
                    inspect_predictions = gr.Markdown(visible=False)
                    inspect_comments = gr.Markdown(visible=False)

            inspect_post_id = gr.Textbox(visible=False)

            with gr.Accordion(
                "🚩 A filter got this wrong", open=False, visible=not read_only
            ):
                gr.Markdown(
                    "_Flag a meme the safety/consensus filter handled "
                    "incorrectly — e.g. excluded a good meme, kept a bad one, or "
                    "missed a real consensus. Goes into the **Filter Misfires** "
                    "set for tuning the gates/consensus. Use `quality` only for "
                    "legacy quality-gate rows._"
                )
                misfire_gate = gr.Radio(
                    choices=["safety", "consensus", "quality"],
                    value="consensus",
                    label="Which filter got it wrong?",
                    info="Defaults to whichever filter acted on this meme.",
                )
                misfire_correct = gr.Textbox(
                    label="What should have happened? (optional)",
                    placeholder="e.g. 'keep — this has a real joke', "
                    "'exclude — pure nonsense', 'there IS a clear consensus'",
                )
                misfire_notes = gr.Textbox(
                    label="Notes", lines=2, placeholder="Why the filter was wrong…"
                )
                btn_misfire = gr.Button("Flag misfire", variant="secondary")
                misfire_feedback = gr.Markdown()

            # The render tuple shape shared by apply/prev/next (minus the state
            # and position values those handlers prepend/append).
            inspect_render_outputs = [
                inspect_image,
                inspect_info,
                inspect_gt,
                inspect_meta,
                inspect_predictions,
                inspect_comments,
                inspect_post_id,
                misfire_gate,
            ]
            btn_inspect_apply.click(
                inspect_apply,
                inputs=[
                    inspect_status,
                    inspect_subreddit,
                    inspect_search,
                    inspect_prediction_filter,
                    inspect_model,
                ],
                outputs=[
                    inspect_ids_state,
                    inspect_idx_state,
                    *inspect_render_outputs,
                    inspect_position,
                ],
            )
            btn_inspect_prev.click(
                lambda ids, idx: inspect_step(ids, idx, -1),
                inputs=[inspect_ids_state, inspect_idx_state],
                outputs=[inspect_idx_state, *inspect_render_outputs, inspect_position],
            )
            btn_inspect_next.click(
                lambda ids, idx: inspect_step(ids, idx, 1),
                inputs=[inspect_ids_state, inspect_idx_state],
                outputs=[inspect_idx_state, *inspect_render_outputs, inspect_position],
            )
            if not read_only:
                btn_misfire.click(
                    flag_gate_misfire,
                    inputs=[inspect_post_id, misfire_gate, misfire_correct, misfire_notes],
                    outputs=[misfire_feedback, misfire_correct, misfire_notes],
                )
            # Refresh subreddit options + load the first page on tab activation.
            inspect_tab.select(
                lambda: (
                    gr.update(choices=_subreddits()),
                    gr.update(choices=_prediction_models()),
                ),
                outputs=[inspect_subreddit, inspect_model],
            )

        with gr.Tab("Stats & Leaderboard") as stats_tab:
            gr.Markdown(
                "_Refreshes when you switch to this tab — newly judged "
                "predictions appear here automatically._"
            )
            with gr.Row():
                stats_corpus = gr.Markdown()
                stats_predictions = gr.Markdown()
            stats_leaderboard = gr.Markdown()
            stats_consensus = gr.Markdown()

            stats_outputs = [
                stats_corpus,
                stats_predictions,
                stats_leaderboard,
                stats_consensus,
            ]
            stats_tab.select(_load_stats, outputs=stats_outputs)
            app.load(_load_stats, outputs=stats_outputs)

        with gr.Tab("AI Gloss Failures") as regressions_tab:
            gr.Markdown(
                "_Curated regression set of memes whose consensus gloss missed "
                "the joke. Used to A/B future consensus prompt/model changes._"
            )
            regressions_md = gr.Markdown()
            regressions_tab.select(_load_regressions, outputs=[regressions_md])
            app.load(_load_regressions, outputs=[regressions_md])

        with gr.Tab("Filter Misfires") as misfires_tab:
            gr.Markdown(
                "_Memes the safety/consensus filters got wrong, flagged from "
                "the Inspect tab. Historical quality-gate rows remain visible. "
                "Use these to tune the gate prompts and consensus criteria._"
            )
            misfires_md = gr.Markdown()
            misfires_tab.select(_load_gate_feedback, outputs=[misfires_md])
            app.load(_load_gate_feedback, outputs=[misfires_md])

        with gr.Tab("Consensus Eval") as eval_tab:
            gr.Markdown(
                "_Review the persistent consensus eval labels before tuning "
                "prompts. Sampled no-consensus controls are especially worth "
                "checking: reclassify any that actually have comment consensus, "
                "or deactivate ambiguous rows._"
            )
            eval_ids_state = gr.State([])
            eval_idx_state = gr.State(0)

            with gr.Row():
                eval_category = gr.Dropdown(
                    choices=[(label, key) for label, key in _EVAL_CATEGORIES],
                    value="true_no_consensus",
                    label="Category",
                )
                eval_search = gr.Textbox(
                    label="Search title or post id", placeholder="Optional search..."
                )
                btn_eval_apply = gr.Button("Apply filters", variant="primary")

            with gr.Row():
                btn_eval_prev = gr.Button("← Prev")
                eval_position = gr.Markdown("0 / 0")
                btn_eval_next = gr.Button("Next →")

            with gr.Row():
                with gr.Column(scale=1):
                    eval_image = gr.Image(
                        label="Meme",
                        type="filepath",
                        elem_classes="constrained-meme",
                        visible=False,
                    )
                with gr.Column(scale=1):
                    eval_info = gr.Markdown()
                    eval_expected = gr.Textbox(
                        label="Expected / current ground truth",
                        lines=5,
                        interactive=False,
                        visible=False,
                    )
                    eval_results = gr.Markdown(visible=False)
                    eval_comments = gr.Markdown(visible=False)

            eval_post_id = gr.Textbox(visible=False)

            with gr.Row():
                eval_action = gr.Radio(
                    choices=[
                        "Confirm expected label",
                        "Reclassify as consensus",
                        "Reclassify as no consensus",
                        "Deactivate from eval",
                    ],
                    value="Confirm expected label",
                    label="Action",
                    visible=not read_only,
                )
            eval_expected_edit = gr.Textbox(
                label="Expected explanation override (optional)",
                lines=3,
                placeholder="Use when reclassifying a no-consensus control as consensus.",
                visible=not read_only,
            )
            eval_notes = gr.Textbox(
                label="Reviewer notes",
                lines=2,
                placeholder="Why this label is right/wrong, or why the item is ambiguous.",
                visible=not read_only,
            )
            btn_eval_update = gr.Button(
                "Save eval label", variant="secondary", visible=not read_only
            )
            eval_feedback = gr.Markdown()

            eval_render_outputs = [
                eval_image,
                eval_info,
                eval_expected,
                eval_results,
                eval_comments,
                eval_post_id,
                eval_expected_edit,
            ]
            btn_eval_apply.click(
                _read_only_eval_apply if read_only else eval_apply,
                inputs=[eval_category, eval_search],
                outputs=[
                    eval_ids_state,
                    eval_idx_state,
                    *eval_render_outputs,
                    eval_position,
                ],
            )
            btn_eval_prev.click(
                (lambda ids, idx: _read_only_eval_step(ids, idx, -1))
                if read_only
                else (lambda ids, idx: eval_step(ids, idx, -1)),
                inputs=[eval_ids_state, eval_idx_state],
                outputs=[eval_idx_state, *eval_render_outputs, eval_position],
            )
            btn_eval_next.click(
                (lambda ids, idx: _read_only_eval_step(ids, idx, 1))
                if read_only
                else (lambda ids, idx: eval_step(ids, idx, 1)),
                inputs=[eval_ids_state, eval_idx_state],
                outputs=[eval_idx_state, *eval_render_outputs, eval_position],
            )
            if not read_only:
                btn_eval_update.click(
                    update_eval_item,
                    inputs=[
                        eval_post_id,
                        eval_category,
                        eval_search,
                        eval_action,
                        eval_expected_edit,
                        eval_notes,
                    ],
                    outputs=[
                        eval_ids_state,
                        eval_idx_state,
                        *eval_render_outputs,
                        eval_position,
                        eval_feedback,
                    ],
                )
            eval_tab.select(
                _read_only_eval_apply if read_only else eval_apply,
                inputs=[eval_category, eval_search],
                outputs=[
                    eval_ids_state,
                    eval_idx_state,
                    *eval_render_outputs,
                    eval_position,
                ],
            )
            app.load(
                eval_apply,
                inputs=[eval_category, eval_search],
                outputs=[
                    eval_ids_state,
                    eval_idx_state,
                    *eval_render_outputs,
                    eval_position,
                ],
            )

    return app


CSS = """
.constrained-meme,
.constrained-meme > div {
    width: 100% !important;
}

.constrained-meme img {
    display: block !important;
    width: min(100%, 640px) !important;
    min-width: min(100%, 420px) !important;
    height: auto !important;
    max-height: none !important;
    object-fit: contain !important;
    object-position: center !important;
    margin-inline: auto !important;
}

@media (max-width: 640px) {
    .constrained-meme img {
        width: 100% !important;
        min-width: 100% !important;
    }
}
"""


def launch(db_path: Path | None = None, *, read_only: bool = False) -> None:
    if db_path is None:
        # Lazy-import Config so the Space env (only HF secrets) doesn't fail early.
        from basedbench.config import Config

        try:
            db_path = Config().database_path  # type: ignore[call-arg]
        except Exception:
            db_path = _DB_PATH
    set_db_path(db_path)
    if not _DB_PATH.exists():
        raise SystemExit(
            f"Database not found at {_DB_PATH}. "
            f"Run `basedbench ingest` first to create it."
        )
    build_app(read_only=read_only).launch(css=CSS, allowed_paths=[str(_images_root())])


def main() -> None:
    parser = argparse.ArgumentParser(description="basedBench Review UI")
    parser.add_argument("--db", help="Path to SQLite database")
    args = parser.parse_args()
    launch(Path(args.db) if args.db else None)


if __name__ == "__main__":
    main()
