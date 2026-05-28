"""All database query methods, ported from v4 queries.rs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone

from basedbench.db.connection import Database
from basedbench.llm.record import LlmCallRecord
from basedbench.schemas import RawPost, RedditComment


# ═══════════════════════════════════════════════════════
# Supporting dataclasses for query results
# ═══════════════════════════════════════════════════════


@dataclass
class MemeForPrediction:
    post_id: str
    subreddit: str
    title: str
    image_url: str | None
    local_image_path: str | None
    permalink: str
    ground_truth_explanation: str
    consensus_confidence: float
    source_comment_ids: str  # JSON array
    num_agreeing_comments: int
    avg_comment_score: float
    created_utc: str | None
    ground_truth_created_at: str


@dataclass
class PredictionForJudging:
    prediction_id: int
    post_id: str
    model_id: str
    prediction: str
    ground_truth: str


@dataclass
class StatusCounts:
    total_memes: int
    with_consensus: int
    validated: int
    excluded: int
    unreviewed: int


@dataclass
class ModelPredictionCount:
    model_id: str
    predicted: int
    total_available: int


@dataclass
class ModelJudgmentCount:
    model_id: str
    judge_model: str
    judged: int
    correct: int
    incorrect: int
    accuracy: float


@dataclass
class JudgeAgreement:
    model_id: str
    judged_by_multiple: int
    agreements: int

    @property
    def rate(self) -> float:
        return self.agreements / self.judged_by_multiple if self.judged_by_multiple else 0.0


@dataclass
class SnapshotInfo:
    snapshot_id: str
    name: str
    description: str | None
    meme_count: int
    created_at: str


@dataclass
class ExportMeme:
    post_id: str
    title: str
    subreddit: str
    ground_truth: str
    local_image_path: str | None


@dataclass
class ExportPrediction:
    post_id: str
    prediction: str
    verdicts: dict[str, dict[str, str | None]]
    """Map of judge_model -> {"verdict": str, "reasoning": str | None}."""


@dataclass
class LeaderboardEntry:
    model_id: str
    judge_model: str
    correct: int
    total: int
    accuracy: float


@dataclass
class ConsensusQualityStats:
    n_grounded: int
    mean_confidence: float
    median_agreeing_comments: int
    confidence_histogram: list[int]
    """10 bins, each covering confidence range 0.0-0.1, 0.1-0.2, ... 0.9-1.0."""


@dataclass
class LlmCallSummary:
    id: int
    created_at: str
    role: str
    post_id: str
    model: str
    latency_ms: int
    verdict: str | None
    error: str | None


@dataclass
class ConsensusRegression:
    post_id: str
    status: str  # 'wrong' | 'partial' | 'correct'
    canonical_explanation: str | None
    failure_modes: str | None  # comma-separated tags, freeform
    reviewer_notes: str | None
    consensus_at_annotation: str  # snapshot of the gt explanation at flag time
    annotated_at: str


@dataclass
class LlmCallDetail:
    id: int
    created_at: str
    session_id: str
    role: str
    post_id: str
    model: str
    system_prompt: str
    user_prompt: str
    prompt_version: str
    latency_ms: int
    response: str | None
    error: str | None
    verdict: str | None
    reasoning: str | None
    image_path: str | None
    completion_tokens: int | None
    prompt_tokens: int | None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ═══════════════════════════════════════════════════════
# MEMES
# ═══════════════════════════════════════════════════════


def insert_meme(db: Database, post: RawPost) -> bool:
    """Insert a meme. Returns True if inserted, False if already existed."""
    cursor = db.conn.execute(
        """INSERT OR IGNORE INTO memes
           (post_id, subreddit, title, image_url, local_image_path,
            permalink, post_score, created_utc, retrieved_at)
           VALUES (?, ?, ?, ?, NULL, ?, ?, ?, ?)""",
        (
            post.post_id,
            post.subreddit,
            post.title,
            post.image_url,
            post.permalink,
            post.score,
            post.created_utc,
            post.retrieved_at,
        ),
    )
    return cursor.rowcount > 0


def update_meme_image_path(db: Database, post_id: str, path: str) -> None:
    """Update the local_image_path for a meme after downloading."""
    db.conn.execute(
        "UPDATE memes SET local_image_path = ? WHERE post_id = ?",
        (path, post_id),
    )


def meme_exists(db: Database, post_id: str) -> bool:
    """Check if a meme exists by post_id."""
    row = db.conn.execute(
        "SELECT COUNT(*) FROM memes WHERE post_id = ?", (post_id,)
    ).fetchone()
    return row[0] > 0


# ═══════════════════════════════════════════════════════
# COMMENTS
# ═══════════════════════════════════════════════════════


def insert_comment(db: Database, post_id: str, comment: RedditComment) -> bool:
    """Insert a comment. Uses INSERT OR IGNORE for idempotency."""
    cursor = db.conn.execute(
        """INSERT OR IGNORE INTO comments
           (comment_id, post_id, author, body, score, is_moderator, created_utc)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            comment.comment_id,
            post_id,
            comment.author,
            comment.body,
            comment.score,
            1 if comment.is_moderator else 0,
            comment.created_utc,
        ),
    )
    return cursor.rowcount > 0


def get_comments(db: Database, post_id: str) -> list[RedditComment]:
    """Get all comments for a post, ordered by score descending."""
    rows = db.conn.execute(
        """SELECT comment_id, author, body, score, is_moderator, created_utc
           FROM comments WHERE post_id = ? ORDER BY score DESC""",
        (post_id,),
    ).fetchall()
    return [
        RedditComment(
            comment_id=r[0],
            author=r[1] or "",
            body=r[2],
            score=r[3],
            is_moderator=bool(r[4]),
            created_utc=r[5],
        )
        for r in rows
    ]


# ═══════════════════════════════════════════════════════
# GROUND TRUTHS
# ═══════════════════════════════════════════════════════


def upsert_ground_truth(
    db: Database,
    post_id: str,
    explanation: str,
    confidence: float,
    source_comment_ids: list[str],
    num_agreeing: int,
    avg_score: float,
    model: str,
    prompt_version: str,
) -> None:
    """Insert or replace ground truth."""
    ids_json = json.dumps(source_comment_ids)
    db.conn.execute(
        """INSERT OR REPLACE INTO ground_truths
           (post_id, explanation, consensus_confidence, source_comment_ids,
            num_agreeing_comments, avg_comment_score, consensus_model,
            consensus_prompt_version, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            post_id,
            explanation,
            confidence,
            ids_json,
            num_agreeing,
            avg_score,
            model,
            prompt_version,
            _now(),
        ),
    )


def get_all_ground_truths(db: Database) -> list[tuple[str, str]]:
    """Get all (post_id, explanation) pairs for computing DatasetVersion."""
    rows = db.conn.execute(
        "SELECT post_id, explanation FROM ground_truths ORDER BY post_id"
    ).fetchall()
    return [(r[0], r[1]) for r in rows]


def memes_without_ground_truth(db: Database) -> list[str]:
    """Find memes that have no ground truth, excluding already-excluded memes."""
    rows = db.conn.execute(
        """SELECT m.post_id FROM memes m
           LEFT JOIN ground_truths gt ON m.post_id = gt.post_id
           LEFT JOIN reviews r ON m.post_id = r.post_id
           WHERE gt.post_id IS NULL
             AND (r.status IS NULL OR r.status != 'excluded')"""
    ).fetchall()
    return [r[0] for r in rows]


def reconstruct_raw_post(db: Database, post_id: str) -> RawPost | None:
    """Reconstruct a RawPost from memes + comments tables."""
    row = db.conn.execute(
        """SELECT post_id, subreddit, title, image_url, permalink,
                  post_score, created_utc, retrieved_at
           FROM memes WHERE post_id = ?""",
        (post_id,),
    ).fetchone()
    if row is None:
        return None
    comments = get_comments(db, post_id)
    return RawPost(
        post_id=row[0],
        subreddit=row[1],
        title=row[2],
        image_url=row[3],
        permalink=row[4] or "",
        score=row[5] or 0,
        created_utc=row[6],
        retrieved_at=row[7],
        comments=comments,
    )


# ═══════════════════════════════════════════════════════
# REVIEWS
# ═══════════════════════════════════════════════════════


def _memes_pending_gate(db: Database) -> list[str]:
    """Shared predicate: memes with no review row and no ground truth."""
    rows = db.conn.execute(
        """SELECT m.post_id FROM memes m
           LEFT JOIN reviews r ON m.post_id = r.post_id
           LEFT JOIN ground_truths gt ON m.post_id = gt.post_id
           WHERE r.post_id IS NULL
             AND gt.post_id IS NULL"""
    ).fetchall()
    return [r[0] for r in rows]


def memes_needing_safety_gate(db: Database) -> list[str]:
    """Memes pending a safety-appropriateness decision (no prior auto/human review)."""
    return _memes_pending_gate(db)


def memes_needing_quality_gate(db: Database) -> list[str]:
    """Memes pending a quality-gate decision (no prior auto/human review).

    Same predicate as memes_needing_safety_gate; safety runs first in the
    pipeline so its exclusions are already in the reviews table by the
    time this is called.
    """
    return _memes_pending_gate(db)


def auto_exclude_missing_images(db: Database) -> int:
    """Mark consensus-passed memes that never got a local image as excluded.

    These show up in the review queue as broken placeholders since there's
    no file on disk. They're also unusable for `basedbench predict` (which
    requires the image). Returns the count of newly-excluded memes.
    """
    rows = db.conn.execute(
        """SELECT m.post_id FROM memes m
           JOIN ground_truths gt ON m.post_id = gt.post_id
           LEFT JOIN reviews r ON m.post_id = r.post_id
           WHERE r.post_id IS NULL
             AND (m.local_image_path IS NULL OR m.local_image_path = '')"""
    ).fetchall()
    count = 0
    for (post_id,) in rows:
        if insert_auto_review(db, post_id, "image_missing"):
            count += 1
    return count


def insert_auto_review(db: Database, post_id: str, reason: str) -> bool:
    """Insert an auto-exclusion review.

    Uses INSERT OR IGNORE to never overwrite a human review (TOCTOU-safe).
    Returns True if the review was written, False if one already existed.
    """
    cursor = db.conn.execute(
        """INSERT OR IGNORE INTO reviews (post_id, status, reason, reviewed_at)
           VALUES (?, 'excluded', ?, ?)""",
        (post_id, reason, _now()),
    )
    return cursor.rowcount > 0


def upsert_review(
    db: Database, post_id: str, status: str, reason: str | None = None
) -> None:
    """Validate or exclude a meme."""
    db.conn.execute(
        """INSERT OR REPLACE INTO reviews (post_id, status, reason, reviewed_at)
           VALUES (?, ?, ?, ?)""",
        (post_id, status, reason, _now()),
    )


# ═══════════════════════════════════════════════════════
# PREDICTIONS
# ═══════════════════════════════════════════════════════


def insert_prediction(db: Database, pred: "ModelPrediction") -> bool:
    """Insert a prediction. Upsert: overwrites only if existing row has an error.

    Successful predictions are never overwritten.
    """
    from basedbench.schemas import ModelPrediction  # noqa: F811

    cursor = db.conn.execute(
        """INSERT INTO predictions
           (post_id, model_id, prediction, latency_ms, token_count, error,
            dataset_version, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(post_id, model_id) DO UPDATE SET
               prediction = excluded.prediction,
               latency_ms = excluded.latency_ms,
               token_count = excluded.token_count,
               error = excluded.error,
               dataset_version = excluded.dataset_version,
               created_at = excluded.created_at
           WHERE predictions.error IS NOT NULL""",
        (
            pred.post_id,
            pred.model_id,
            pred.prediction,
            pred.latency_ms,
            pred.token_count,
            pred.error,
            pred.dataset_version,
            pred.timestamp,
        ),
    )
    return cursor.rowcount > 0


def find_prediction_id(db: Database, post_id: str, model_id: str) -> int | None:
    """Find the prediction ID for a given post_id + model_id."""
    row = db.conn.execute(
        "SELECT id FROM predictions WHERE post_id = ? AND model_id = ?",
        (post_id, model_id),
    ).fetchone()
    return row[0] if row else None


def memes_needing_prediction(
    db: Database,
    model_id: str,
    snapshot_id: str | None = None,
    validated_only: bool = True,
) -> list[MemeForPrediction]:
    """Query memes that need prediction for a given model.

    When snapshot_id is set, only returns memes within that snapshot.
    When validated_only is True, only returns memes with a 'validated' review.
    When False, returns any non-excluded meme.
    """
    review_filter = (
        "AND r.status = 'validated'"
        if validated_only
        else "AND (r.status IS NULL OR r.status != 'excluded')"
    )
    review_join = (
        "JOIN reviews r ON m.post_id = r.post_id"
        if validated_only
        else "LEFT JOIN reviews r ON m.post_id = r.post_id"
    )

    if snapshot_id is not None:
        query = f"""
            SELECT m.post_id, m.subreddit, m.title, m.image_url, m.local_image_path,
                   m.permalink, gt.explanation, gt.consensus_confidence,
                   gt.source_comment_ids, gt.num_agreeing_comments,
                   gt.avg_comment_score, m.created_utc, gt.created_at
            FROM memes m
            JOIN ground_truths gt ON m.post_id = gt.post_id
            JOIN snapshot_memes sm ON m.post_id = sm.post_id AND sm.snapshot_id = ?
            {review_join}
            LEFT JOIN predictions p ON m.post_id = p.post_id AND p.model_id = ?
                AND p.error IS NULL
            WHERE p.id IS NULL
              {review_filter}"""
        params: tuple = (snapshot_id, model_id)
    else:
        query = f"""
            SELECT m.post_id, m.subreddit, m.title, m.image_url, m.local_image_path,
                   m.permalink, gt.explanation, gt.consensus_confidence,
                   gt.source_comment_ids, gt.num_agreeing_comments,
                   gt.avg_comment_score, m.created_utc, gt.created_at
            FROM memes m
            JOIN ground_truths gt ON m.post_id = gt.post_id
            {review_join}
            LEFT JOIN predictions p ON m.post_id = p.post_id AND p.model_id = ?
                AND p.error IS NULL
            WHERE p.id IS NULL
              {review_filter}"""
        params = (model_id,)

    rows = db.conn.execute(query, params).fetchall()
    return [
        MemeForPrediction(
            post_id=r[0],
            subreddit=r[1],
            title=r[2],
            image_url=r[3],
            local_image_path=r[4],
            permalink=r[5] or "",
            ground_truth_explanation=r[6],
            consensus_confidence=r[7],
            source_comment_ids=r[8] or "[]",
            num_agreeing_comments=r[9] or 0,
            avg_comment_score=r[10] or 0.0,
            created_utc=r[11],
            ground_truth_created_at=r[12],
        )
        for r in rows
    ]


# ═══════════════════════════════════════════════════════
# JUDGMENTS
# ═══════════════════════════════════════════════════════


def insert_judgment(
    db: Database,
    prediction_id: int,
    verdict: str,
    reasoning: str,
    judge_model: str,
    prompt_version: str,
) -> None:
    """Insert a judgment. NOT idempotent — allows multiple judgments per prediction."""
    db.conn.execute(
        """INSERT INTO judgments
           (prediction_id, verdict, judge_reasoning, judge_model,
            judge_prompt_version, judged_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (prediction_id, verdict, reasoning, judge_model, prompt_version, _now()),
    )


def predictions_needing_judgment(
    db: Database,
    model_id: str | None = None,
    judge_model: str | None = None,
) -> list[PredictionForJudging]:
    """Query predictions that need judgment from a particular judge.

    Only returns validated memes. When `judge_model` is provided, "needs
    judgment" means no judgment row exists for this prediction *from that
    specific judge model* — letting a second judge fill in alongside an
    existing first judge's verdict. When `judge_model` is None, falls back
    to "no judgments at all".
    """
    if judge_model is not None:
        joins_and_filter = """
            LEFT JOIN judgments j
              ON p.id = j.prediction_id AND j.judge_model = ?
            WHERE j.id IS NULL
              AND p.error IS NULL
              AND r.status = 'validated'"""
        params: tuple = (judge_model,)
    else:
        joins_and_filter = """
            LEFT JOIN judgments j ON p.id = j.prediction_id
            WHERE j.id IS NULL
              AND p.error IS NULL
              AND r.status = 'validated'"""
        params = ()

    query = (
        """SELECT p.id, p.post_id, p.model_id, p.prediction, gt.explanation
            FROM predictions p
            JOIN ground_truths gt ON p.post_id = gt.post_id
            JOIN reviews r ON p.post_id = r.post_id"""
        + joins_and_filter
    )

    if model_id is not None:
        query += " AND p.model_id = ?"
        params = (*params, model_id)

    rows = db.conn.execute(query, params).fetchall()
    return [
        PredictionForJudging(
            prediction_id=r[0],
            post_id=r[1],
            model_id=r[2],
            prediction=r[3],
            ground_truth=r[4],
        )
        for r in rows
    ]


def predictions_needing_rejudgment(
    db: Database, old_prompt_id: str
) -> list[PredictionForJudging]:
    """Predictions where any judge's latest verdict used the old prompt version."""
    rows = db.conn.execute(
        """SELECT DISTINCT p.id, p.post_id, p.model_id, p.prediction, gt.explanation
           FROM predictions p
           JOIN ground_truths gt ON p.post_id = gt.post_id
           JOIN reviews r ON p.post_id = r.post_id
           JOIN judgments j ON p.id = j.prediction_id
           WHERE r.status = 'validated'
             AND j.id = (
               SELECT MAX(j2.id) FROM judgments j2
               WHERE j2.prediction_id = p.id AND j2.judge_model = j.judge_model
             )
             AND j.judge_prompt_version = ?""",
        (old_prompt_id,),
    ).fetchall()
    return [
        PredictionForJudging(
            prediction_id=r[0],
            post_id=r[1],
            model_id=r[2],
            prediction=r[3],
            ground_truth=r[4],
        )
        for r in rows
    ]


# ═══════════════════════════════════════════════════════
# PROMPT VERSIONS
# ═══════════════════════════════════════════════════════


def register_prompt(
    db: Database,
    prompt_id: str,
    role: str,
    system_prompt: str,
    user_prompt_template: str,
    version: str,
) -> None:
    """Register a prompt version. Uses INSERT OR IGNORE."""
    db.conn.execute(
        """INSERT OR IGNORE INTO prompt_versions
           (prompt_id, role, system_prompt, user_prompt_template, version, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (prompt_id, role, system_prompt, user_prompt_template, version, _now()),
    )


# ═══════════════════════════════════════════════════════
# SNAPSHOTS
# ═══════════════════════════════════════════════════════


def validated_meme_pairs(db: Database) -> list[tuple[str, str]]:
    """Get all validated memes with ground truths as (post_id, explanation) pairs."""
    rows = db.conn.execute(
        """SELECT m.post_id, gt.explanation
           FROM memes m
           JOIN ground_truths gt ON m.post_id = gt.post_id
           JOIN reviews r ON m.post_id = r.post_id
           WHERE r.status = 'validated'
           ORDER BY m.post_id"""
    ).fetchall()
    return [(r[0], r[1]) for r in rows]


def create_snapshot(
    db: Database, name: str, description: str | None = None
) -> str:
    """Create a snapshot from all validated memes. Uses a transaction."""
    from basedbench.errors import ConfigError
    from basedbench.schemas import dataset_version

    pairs = validated_meme_pairs(db)
    if not pairs:
        raise ConfigError("No validated memes to snapshot")

    snapshot_id = dataset_version(pairs)
    meme_count = len(pairs)

    # Explicit transaction so a partial failure can't leave an orphan snapshot
    # with missing snapshot_memes rows. (Connection is in autocommit mode,
    # so `with db.conn:` would be a no-op here.)
    db.conn.execute("BEGIN")
    try:
        db.conn.execute(
            """INSERT INTO snapshots (snapshot_id, name, description, meme_count, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (snapshot_id, name, description, meme_count, _now()),
        )
        for post_id, _ in pairs:
            db.conn.execute(
                "INSERT INTO snapshot_memes (snapshot_id, post_id) VALUES (?, ?)",
                (snapshot_id, post_id),
            )
    except Exception:
        db.conn.execute("ROLLBACK")
        raise
    db.conn.execute("COMMIT")

    return snapshot_id


def list_snapshots(db: Database) -> list[SnapshotInfo]:
    """List all snapshots."""
    rows = db.conn.execute(
        """SELECT snapshot_id, name, description, meme_count, created_at
           FROM snapshots ORDER BY created_at DESC"""
    ).fetchall()
    return [
        SnapshotInfo(
            snapshot_id=r[0], name=r[1], description=r[2],
            meme_count=r[3], created_at=r[4],
        )
        for r in rows
    ]


def snapshot_meme_ids(db: Database, snapshot_id: str) -> list[str]:
    """Get meme post_ids in a snapshot."""
    rows = db.conn.execute(
        "SELECT post_id FROM snapshot_memes WHERE snapshot_id = ? ORDER BY post_id",
        (snapshot_id,),
    ).fetchall()
    return [r[0] for r in rows]


def snapshot_ground_truths(db: Database, snapshot_id: str) -> list[tuple[str, str]]:
    """Get ground truths for memes in a snapshot."""
    rows = db.conn.execute(
        """SELECT gt.post_id, gt.explanation
           FROM ground_truths gt
           JOIN snapshot_memes sm ON gt.post_id = sm.post_id
           WHERE sm.snapshot_id = ?
           ORDER BY gt.post_id""",
        (snapshot_id,),
    ).fetchall()
    return [(r[0], r[1]) for r in rows]


def find_snapshot(db: Database, name_or_id: str) -> SnapshotInfo | None:
    """Look up a snapshot by name or ID prefix."""
    # Try exact name match first
    row = db.conn.execute(
        """SELECT snapshot_id, name, description, meme_count, created_at
           FROM snapshots WHERE name = ?""",
        (name_or_id,),
    ).fetchone()
    if row:
        return SnapshotInfo(
            snapshot_id=row[0], name=row[1], description=row[2],
            meme_count=row[3], created_at=row[4],
        )

    # Try ID prefix match
    row = db.conn.execute(
        """SELECT snapshot_id, name, description, meme_count, created_at
           FROM snapshots WHERE snapshot_id LIKE ?""",
        (f"{name_or_id}%",),
    ).fetchone()
    if row:
        return SnapshotInfo(
            snapshot_id=row[0], name=row[1], description=row[2],
            meme_count=row[3], created_at=row[4],
        )
    return None


# ═══════════════════════════════════════════════════════
# EXPORT HELPERS
# ═══════════════════════════════════════════════════════


def snapshot_meme_details(db: Database, snapshot_id: str) -> list[ExportMeme]:
    """Get full meme details for all memes in a snapshot."""
    rows = db.conn.execute(
        """SELECT m.post_id, m.title, m.subreddit, gt.explanation,
                  m.local_image_path
           FROM snapshot_memes sm
           JOIN memes m ON sm.post_id = m.post_id
           JOIN ground_truths gt ON m.post_id = gt.post_id
           WHERE sm.snapshot_id = ?
           ORDER BY m.post_id""",
        (snapshot_id,),
    ).fetchall()
    return [
        ExportMeme(
            post_id=r[0], title=r[1], subreddit=r[2],
            ground_truth=r[3], local_image_path=r[4],
        )
        for r in rows
    ]


def snapshot_model_ids(db: Database, snapshot_id: str) -> list[str]:
    """Get all distinct model IDs that have predictions for memes in a snapshot."""
    rows = db.conn.execute(
        """SELECT DISTINCT p.model_id
           FROM predictions p
           JOIN snapshot_memes sm ON p.post_id = sm.post_id
           WHERE sm.snapshot_id = ?
           ORDER BY p.model_id""",
        (snapshot_id,),
    ).fetchall()
    return [r[0] for r in rows]


def snapshot_predictions_for_model(
    db: Database, snapshot_id: str, model_id: str
) -> list[ExportPrediction]:
    """Predictions for a model within a snapshot, with verdicts from every judge.

    Returns one ExportPrediction per (post_id); the `verdicts` dict carries
    one entry per judge_model. Latest judgment per (prediction, judge) wins.
    """
    pred_rows = db.conn.execute(
        """SELECT p.id, p.post_id, p.prediction
           FROM predictions p
           JOIN snapshot_memes sm ON p.post_id = sm.post_id
           WHERE sm.snapshot_id = ? AND p.model_id = ?
           ORDER BY p.post_id""",
        (snapshot_id, model_id),
    ).fetchall()

    verdict_rows = db.conn.execute(
        """SELECT j.prediction_id, j.judge_model, j.verdict, j.judge_reasoning
           FROM judgments j
           JOIN predictions p ON p.id = j.prediction_id
           JOIN snapshot_memes sm ON p.post_id = sm.post_id
           WHERE sm.snapshot_id = ? AND p.model_id = ?
             AND j.id = (
               SELECT MAX(j2.id) FROM judgments j2
               WHERE j2.prediction_id = j.prediction_id
                 AND j2.judge_model = j.judge_model
             )""",
        (snapshot_id, model_id),
    ).fetchall()

    verdicts_by_pred: dict[int, dict[str, dict[str, str | None]]] = {}
    for prediction_id, judge_model, verdict, reasoning in verdict_rows:
        key = judge_model or "(unknown)"
        verdicts_by_pred.setdefault(prediction_id, {})[key] = {
            "verdict": verdict,
            "reasoning": reasoning,
        }

    return [
        ExportPrediction(
            post_id=r[1],
            prediction=r[2],
            verdicts=verdicts_by_pred.get(r[0], {}),
        )
        for r in pred_rows
    ]


def snapshot_leaderboard(db: Database, snapshot_id: str) -> list[LeaderboardEntry]:
    """Per-(target, judge) accuracy for a snapshot. Latest judgment per pair wins."""
    rows = db.conn.execute(
        """SELECT p.model_id,
                  j.judge_model,
                  SUM(CASE WHEN j.verdict = 'correct' THEN 1 ELSE 0 END) as correct,
                  COUNT(j.verdict) as total
           FROM predictions p
           JOIN snapshot_memes sm ON p.post_id = sm.post_id
           JOIN judgments j ON p.id = j.prediction_id
           WHERE sm.snapshot_id = ?
             AND j.id = (
               SELECT MAX(j2.id) FROM judgments j2
               WHERE j2.prediction_id = p.id AND j2.judge_model = j.judge_model
             )
           GROUP BY p.model_id, j.judge_model
           ORDER BY p.model_id, j.judge_model""",
        (snapshot_id,),
    ).fetchall()
    return [
        LeaderboardEntry(
            model_id=r[0],
            judge_model=r[1] or "(unknown)",
            correct=r[2],
            total=r[3],
            accuracy=r[2] / r[3] if r[3] > 0 else 0.0,
        )
        for r in rows
    ]


# ═══════════════════════════════════════════════════════
# LLM CALL LOGGING
# ═══════════════════════════════════════════════════════


def insert_llm_call(db: Database, record: LlmCallRecord) -> None:
    """Insert an LLM API call record."""
    db.conn.execute(
        """INSERT INTO llm_calls
           (session_id, role, post_id, model, system_prompt, user_prompt,
            prompt_version, latency_ms, response, error, verdict, reasoning,
            image_path, completion_tokens, prompt_tokens)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            record.session_id,
            record.role,
            record.post_id,
            record.model,
            record.system_prompt,
            record.user_prompt,
            record.prompt_version,
            record.latency_ms,
            record.response,
            record.error,
            record.verdict,
            record.reasoning,
            record.image_path,
            record.completion_tokens,
            record.prompt_tokens,
        ),
    )


def list_llm_calls(
    db: Database,
    role: str | None = None,
    post_id: str | None = None,
    session: str | None = None,
    errors_only: bool = False,
    limit: int = 20,
) -> list[LlmCallSummary]:
    """Query LLM calls with optional filters."""
    conditions: list[str] = []
    params: list[str | int] = []

    if role is not None:
        conditions.append("role = ?")
        params.append(role)
    if post_id is not None:
        conditions.append("post_id = ?")
        params.append(post_id)
    if session is not None:
        conditions.append("session_id = ?")
        params.append(session)
    if errors_only:
        conditions.append("error IS NOT NULL")

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"""SELECT id, created_at, role, post_id, model, latency_ms, verdict, error
                FROM llm_calls {where}
                ORDER BY id DESC LIMIT ?"""
    params.append(limit)

    rows = db.conn.execute(query, params).fetchall()
    return [
        LlmCallSummary(
            id=r[0], created_at=r[1], role=r[2], post_id=r[3],
            model=r[4], latency_ms=r[5], verdict=r[6], error=r[7],
        )
        for r in rows
    ]


def get_llm_call(db: Database, call_id: int) -> LlmCallDetail | None:
    """Get full details of a single LLM call."""
    row = db.conn.execute(
        """SELECT id, created_at, session_id, role, post_id, model,
                  system_prompt, user_prompt, prompt_version, latency_ms,
                  response, error, verdict, reasoning, image_path,
                  completion_tokens, prompt_tokens
           FROM llm_calls WHERE id = ?""",
        (call_id,),
    ).fetchone()
    if row is None:
        return None
    return LlmCallDetail(
        id=row[0], created_at=row[1], session_id=row[2], role=row[3],
        post_id=row[4], model=row[5], system_prompt=row[6],
        user_prompt=row[7], prompt_version=row[8], latency_ms=row[9],
        response=row[10], error=row[11], verdict=row[12],
        reasoning=row[13], image_path=row[14],
        completion_tokens=row[15], prompt_tokens=row[16],
    )


# ═══════════════════════════════════════════════════════
# STATUS / REPORTING
# ═══════════════════════════════════════════════════════


def consensus_quality_stats(db: Database) -> ConsensusQualityStats:
    """Aggregate quality stats over all ground_truths rows.

    Returns mean confidence, median agreeing-comments count, and a 10-bin
    histogram of confidence values (bin i covers [i/10, (i+1)/10)).
    """
    rows = db.conn.execute(
        "SELECT consensus_confidence, num_agreeing_comments FROM ground_truths"
    ).fetchall()
    n = len(rows)
    if n == 0:
        return ConsensusQualityStats(
            n_grounded=0,
            mean_confidence=0.0,
            median_agreeing_comments=0,
            confidence_histogram=[0] * 10,
        )

    confidences = [r[0] or 0.0 for r in rows]
    agreeing = sorted(r[1] or 0 for r in rows)
    median_agreeing = agreeing[n // 2]
    mean_conf = sum(confidences) / n

    histogram = [0] * 10
    for c in confidences:
        bucket = min(int(c * 10), 9)  # 1.0 falls into bin 9, not 10
        histogram[bucket] += 1

    return ConsensusQualityStats(
        n_grounded=n,
        mean_confidence=mean_conf,
        median_agreeing_comments=median_agreeing,
        confidence_histogram=histogram,
    )


def get_status_counts(db: Database) -> StatusCounts:
    """Get aggregate counts for the status command."""
    total_memes = db.conn.execute("SELECT COUNT(*) FROM memes").fetchone()[0]
    with_consensus = db.conn.execute("SELECT COUNT(*) FROM ground_truths").fetchone()[0]
    validated = db.conn.execute(
        "SELECT COUNT(*) FROM reviews WHERE status = 'validated'"
    ).fetchone()[0]
    excluded = db.conn.execute(
        "SELECT COUNT(*) FROM reviews WHERE status = 'excluded'"
    ).fetchone()[0]
    # Memes that have ground truth but no review row yet. Computing this
    # directly (not as a subtraction) avoids going negative when there are
    # more auto-excluded memes than there were consensus-found ones.
    unreviewed = db.conn.execute(
        """SELECT COUNT(*) FROM ground_truths gt
           LEFT JOIN reviews r ON gt.post_id = r.post_id
           WHERE r.post_id IS NULL"""
    ).fetchone()[0]

    return StatusCounts(
        total_memes=total_memes,
        with_consensus=with_consensus,
        validated=validated,
        excluded=excluded,
        unreviewed=unreviewed,
    )


def get_prediction_counts(db: Database) -> list[ModelPredictionCount]:
    """Get per-model prediction counts. total_available only counts validated memes."""
    total_available = db.conn.execute(
        """SELECT COUNT(*) FROM ground_truths gt
           JOIN reviews r ON gt.post_id = r.post_id
           WHERE r.status = 'validated'"""
    ).fetchone()[0]

    rows = db.conn.execute(
        """SELECT model_id, COUNT(*) as predicted
           FROM predictions
           WHERE error IS NULL
           GROUP BY model_id
           ORDER BY model_id"""
    ).fetchall()
    return [
        ModelPredictionCount(
            model_id=r[0], predicted=r[1], total_available=total_available,
        )
        for r in rows
    ]


def get_judgment_counts(db: Database) -> list[ModelJudgmentCount]:
    """Per-(target model, judge model) judgment counts. Only validated memes.

    Latest-per-(prediction, judge) wins, so re-judging the same prediction
    with the same judge model is idempotent for stats purposes.
    """
    rows = db.conn.execute(
        """SELECT p.model_id,
                  j.judge_model,
                  COUNT(*) as judged,
                  SUM(CASE WHEN j.verdict = 'correct' THEN 1 ELSE 0 END) as correct,
                  SUM(CASE WHEN j.verdict = 'incorrect' THEN 1 ELSE 0 END) as incorrect
           FROM predictions p
           JOIN judgments j ON p.id = j.prediction_id
           JOIN reviews r ON p.post_id = r.post_id
           WHERE r.status = 'validated'
             AND j.id = (
               SELECT MAX(j2.id) FROM judgments j2
               WHERE j2.prediction_id = p.id AND j2.judge_model = j.judge_model
             )
           GROUP BY p.model_id, j.judge_model
           ORDER BY p.model_id, j.judge_model"""
    ).fetchall()
    return [
        ModelJudgmentCount(
            model_id=r[0],
            judge_model=r[1] or "(unknown)",
            judged=r[2],
            correct=r[3],
            incorrect=r[4],
            accuracy=r[3] / r[2] if r[2] > 0 else 0.0,
        )
        for r in rows
    ]


def get_judge_agreement(
    db: Database, snapshot_id: str | None = None
) -> list[JudgeAgreement]:
    """Per-target-model agreement rate across judges.

    A prediction "agrees" if every judge that scored it returned the same
    verdict. Predictions scored by only one judge are excluded from the
    denominator. If `snapshot_id` is given, restricts to that snapshot;
    otherwise considers all validated memes.
    """
    if snapshot_id is not None:
        scope_join = "JOIN snapshot_memes sm ON p.post_id = sm.post_id"
        scope_filter = "AND sm.snapshot_id = ?"
        params: tuple = (snapshot_id,)
    else:
        scope_join = "JOIN reviews r ON p.post_id = r.post_id"
        scope_filter = "AND r.status = 'validated'"
        params = ()

    query = f"""
        WITH latest_per_judge AS (
            SELECT j.prediction_id, p.model_id, j.judge_model, j.verdict
            FROM predictions p
            JOIN judgments j ON p.id = j.prediction_id
            {scope_join}
            WHERE j.id = (
                SELECT MAX(j2.id) FROM judgments j2
                WHERE j2.prediction_id = p.id AND j2.judge_model = j.judge_model
            )
            {scope_filter}
        ),
        per_prediction AS (
            SELECT prediction_id, model_id,
                   COUNT(DISTINCT judge_model) as n_judges,
                   COUNT(DISTINCT verdict) as n_verdicts
            FROM latest_per_judge
            GROUP BY prediction_id, model_id
        )
        SELECT model_id,
               SUM(CASE WHEN n_judges > 1 THEN 1 ELSE 0 END) as judged_by_multiple,
               SUM(CASE WHEN n_judges > 1 AND n_verdicts = 1 THEN 1 ELSE 0 END) as agreements
        FROM per_prediction
        GROUP BY model_id
        ORDER BY model_id
    """
    rows = db.conn.execute(query, params).fetchall()
    return [
        JudgeAgreement(model_id=r[0], judged_by_multiple=r[1], agreements=r[2])
        for r in rows
    ]


# ═══════════════════════════════════════════════════════
# DATASET PUSHES (HuggingFace Hub)
# ═══════════════════════════════════════════════════════


def insert_dataset_push(
    db: Database,
    snapshot_id: str,
    hf_repo: str,
    meme_count: int,
    model_count: int,
) -> int:
    """Record a successful HuggingFace push. Returns the row id."""
    cursor = db.conn.execute(
        """INSERT INTO dataset_pushes (snapshot_id, hf_repo, pushed_at, meme_count, model_count)
           VALUES (?, ?, ?, ?, ?)""",
        (snapshot_id, hf_repo, _now(), meme_count, model_count),
    )
    return int(cursor.lastrowid or 0)


def list_dataset_pushes(db: Database, snapshot_id: str | None = None) -> list[tuple[str, str, str, int, int]]:
    """List dataset pushes. Returns (snapshot_id, hf_repo, pushed_at, meme_count, model_count)."""
    if snapshot_id is not None:
        rows = db.conn.execute(
            """SELECT snapshot_id, hf_repo, pushed_at, meme_count, model_count
               FROM dataset_pushes WHERE snapshot_id = ? ORDER BY id DESC""",
            (snapshot_id,),
        ).fetchall()
    else:
        rows = db.conn.execute(
            """SELECT snapshot_id, hf_repo, pushed_at, meme_count, model_count
               FROM dataset_pushes ORDER BY id DESC"""
        ).fetchall()
    return [(r[0], r[1], r[2], r[3], r[4]) for r in rows]


# ═══════════════════════════════════════════════════════
# Consensus regression set
# ═══════════════════════════════════════════════════════


def flag_consensus_regression(
    db: Database,
    post_id: str,
    status: str,
    consensus_at_annotation: str,
    canonical_explanation: str | None = None,
    failure_modes: str | None = None,
    reviewer_notes: str | None = None,
) -> None:
    """Flag a meme's consensus output as wrong/partial/correct.

    Captures the consensus explanation at flag-time so future re-runs can
    be compared against the version we caught failing.
    """
    if status not in ("wrong", "partial", "correct"):
        raise ValueError(f"invalid status: {status!r}")
    db.conn.execute(
        """INSERT OR REPLACE INTO consensus_regression
           (post_id, status, canonical_explanation, failure_modes,
            reviewer_notes, consensus_at_annotation, annotated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            post_id, status, canonical_explanation, failure_modes,
            reviewer_notes, consensus_at_annotation, _now(),
        ),
    )


def get_consensus_regression(db: Database, post_id: str) -> ConsensusRegression | None:
    row = db.conn.execute(
        """SELECT post_id, status, canonical_explanation, failure_modes,
                  reviewer_notes, consensus_at_annotation, annotated_at
           FROM consensus_regression WHERE post_id = ?""",
        (post_id,),
    ).fetchone()
    if row is None:
        return None
    return ConsensusRegression(*row)


def list_consensus_regressions(
    db: Database, status: str | None = None
) -> list[ConsensusRegression]:
    if status is not None:
        rows = db.conn.execute(
            """SELECT post_id, status, canonical_explanation, failure_modes,
                      reviewer_notes, consensus_at_annotation, annotated_at
               FROM consensus_regression WHERE status = ?
               ORDER BY annotated_at DESC""",
            (status,),
        ).fetchall()
    else:
        rows = db.conn.execute(
            """SELECT post_id, status, canonical_explanation, failure_modes,
                      reviewer_notes, consensus_at_annotation, annotated_at
               FROM consensus_regression
               ORDER BY annotated_at DESC"""
        ).fetchall()
    return [ConsensusRegression(*r) for r in rows]


def unflag_consensus_regression(db: Database, post_id: str) -> bool:
    """Remove a regression entry. Returns True if a row was deleted."""
    cursor = db.conn.execute(
        "DELETE FROM consensus_regression WHERE post_id = ?", (post_id,)
    )
    return cursor.rowcount > 0
