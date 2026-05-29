"""Gradio review UI — validator for meme ground truths.

Three tabs:
- Review Queue: validate / exclude / skip unreviewed consensus results
- Browse: filter and search the meme database
- Prediction Comparison: compare model predictions side-by-side per meme
"""

from __future__ import annotations

import argparse
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

    def repl(match: re.Match[str]) -> str:
        url = match.group(0)
        return f"[![]({url})]({url})"

    return _IMAGE_URL_RE.sub(repl, text)

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


def _resolve_image(local_image_path: str | None) -> str | None:
    if not local_image_path:
        return None
    abs_path = _project_root() / local_image_path
    return str(abs_path) if abs_path.exists() else None


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
                  gt.explanation, gt.consensus_confidence, gt.num_agreeing_comments
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
    comments = conn.execute(
        "SELECT body, score, author FROM comments WHERE post_id = ? ORDER BY score DESC LIMIT 5",
        (post_id,),
    ).fetchall()
    conn.close()

    comments_text = "\n\n".join(
        f"**{c['author']}** (score: {c['score']})\n> {_inline_image_urls(c['body'])}"
        for c in comments
    )

    return (
        gr.update(value=_resolve_image(row["local_image_path"]), visible=True),
        gr.update(value=f"**{row['title']}**\n\nr/{row['subreddit']}"),
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
             AND j.id = (
               SELECT MAX(j2.id) FROM judgments j2
               WHERE j2.prediction_id = j.prediction_id
                 AND j2.judge_model = j.judge_model
             )""",
        (post_id,),
    ).fetchall()
    conn.close()

    verdicts_by_pred: dict[int, list[tuple[str, str | None, str | None]]] = {}
    for vr in verdict_rows:
        verdicts_by_pred.setdefault(vr["prediction_id"], []).append(
            (vr["judge_model"] or "(unknown)", vr["verdict"], vr["judge_reasoning"])
        )

    img = _resolve_image(meme["local_image_path"])
    gt_text = f"**Ground Truth:**\n\n{meme['explanation']}"
    if not preds:
        return (
            gr.update(value=img, visible=True),
            gr.update(value=gt_text, visible=True),
            gr.update(value="_No predictions for this meme yet. Run `basedbench predict <model>`._", visible=True),
        )

    def _badge(v: str | None) -> str:
        if v == "correct":
            return "\U0001f7e2"
        if v == "incorrect":
            return "\U0001f534"
        return "⚪"

    blocks = []
    for p in preds:
        verdicts = sorted(verdicts_by_pred.get(p["id"], []), key=lambda r: r[0])
        if not verdicts:
            header = f"### ⚪ {p['model_id']}"
            verdict_section = "_unjudged_"
            agreement = ""
        else:
            distinct = {v for _, v, _ in verdicts if v is not None}
            if len(verdicts) > 1:
                agreement = (
                    " · ✅ judges agree"
                    if len(distinct) == 1
                    else " · ⚠️ judges disagree"
                )
            else:
                agreement = ""
            badges = " ".join(_badge(v) for _, v, _ in verdicts)
            header = f"### {badges} {p['model_id']}{agreement}"
            verdict_lines = []
            for judge_model, verdict, reasoning in verdicts:
                line = f"**{_badge(verdict)} {judge_model}:** {verdict or 'unjudged'}"
                if reasoning:
                    line += f"\n  - _reasoning:_ {reasoning}"
                verdict_lines.append(line)
            verdict_section = "\n\n".join(verdict_lines)

        blocks.append(
            f"{header}\n\n**Prediction:** {p['prediction']}\n\n{verdict_section}"
        )

    return (
        gr.update(value=img, visible=True),
        gr.update(value=gt_text, visible=True),
        gr.update(value="\n\n---\n\n".join(blocks), visible=True),
    )


# ── Tab 4: Stats & Leaderboard ───────────────────────────────────────


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

    return corpus_md, predictions_md, leaderboard_md, consensus_md


# ── Build Gradio App ─────────────────────────────────────────────────


def build_app() -> gr.Blocks:
    with gr.Blocks(title="basedBench Review UI") as app:
        gr.Markdown("# basedBench Review UI")

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
                btn_validate = gr.Button("Validate", variant="primary")
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
                )
                btn_exclude = gr.Button("Exclude", variant="stop")
                btn_skip = gr.Button("Skip")

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
            btn_validate.click(validate_meme, inputs=[review_post_id], outputs=review_outputs)
            btn_exclude.click(
                exclude_meme, inputs=[review_post_id, exclude_reason], outputs=review_outputs
            )
            btn_skip.click(skip_meme, inputs=[], outputs=review_outputs)
            app.load(load_next_unreviewed, outputs=review_outputs)

            with gr.Accordion(
                "🚩 Flag this meme's ground-truth explanation (consensus failure)",
                open=False,
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

    return app


CSS = """
.constrained-meme img {
    max-height: 60vh !important;
    object-fit: contain !important;
}
"""


def launch(db_path: Path | None = None) -> None:
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
    project_root = str(_DB_PATH.resolve().parent.parent)
    build_app().launch(css=CSS, allowed_paths=[project_root])


def main() -> None:
    parser = argparse.ArgumentParser(description="basedBench Review UI")
    parser.add_argument("--db", help="Path to SQLite database")
    args = parser.parse_args()
    launch(Path(args.db) if args.db else None)


if __name__ == "__main__":
    main()
