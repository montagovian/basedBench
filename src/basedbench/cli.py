"""Typer CLI — entrypoint for `basedbench` script."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import typer
from rich.console import Console

from basedbench.config import Config
from basedbench.db import queries
from basedbench.db.connection import Database
from basedbench.pipeline import export as export_pipe
from basedbench.pipeline import hf_push as hf_push_pipe
from basedbench.pipeline import ingest as ingest_pipe
from basedbench.pipeline import judge as judge_pipe
from basedbench.pipeline import predict as predict_pipe
from basedbench.pipeline import snapshot as snapshot_pipe

app = typer.Typer(
    name="basedbench",
    help="VLM Meme Understanding Benchmark.",
    no_args_is_help=True,
    add_completion=False,
)
snapshot_app = typer.Typer(help="Manage snapshots.", no_args_is_help=True)
app.add_typer(snapshot_app, name="snapshot")


def _load() -> tuple[Database, Config]:
    config = Config()  # type: ignore[call-arg]
    config.ensure_dirs()
    db = Database.open(config.database_path)
    return db, config


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )


# ───────────────────────── ingest ─────────────────────────


@app.command()
def ingest(
    limit: int = typer.Option(50, help="Max posts to fetch per subreddit."),
    subreddit: str | None = typer.Option(None, help="Single subreddit (defaults to all)."),
) -> None:
    """Fetch memes from Reddit, download images, run quality gate + consensus."""
    _configure_logging()
    db, config = _load()
    asyncio.run(ingest_pipe.run(db, config, limit=limit, subreddit=subreddit))


# ───────────────────────── predict ─────────────────────────


@app.command()
def predict(
    model: str = typer.Argument(..., help="Model id (e.g. gpt-4o, claude-3-5-sonnet)."),
    snapshot: str | None = typer.Option(None, help="Restrict to a snapshot."),
    include_unreviewed: bool = typer.Option(
        False, help="Include memes with unreviewed ground truth."
    ),
) -> None:
    """Run a VLM over memes that need a prediction."""
    _configure_logging()
    db, config = _load()
    asyncio.run(
        predict_pipe.run(
            db,
            config,
            model=model,
            snapshot=snapshot,
            include_unreviewed=include_unreviewed,
        )
    )


# ───────────────────────── judge ─────────────────────────


@app.command()
def judge(
    model: str | None = typer.Argument(None, help="Only judge this model's predictions."),
    rejudge_prompt: str | None = typer.Option(
        None, help="Re-judge predictions whose judge used this prompt id."
    ),
) -> None:
    """Judge unjudged predictions with the LLM judge."""
    _configure_logging()
    db, config = _load()
    asyncio.run(
        judge_pipe.run(db, config, model=model, rejudge_prompt=rejudge_prompt)
    )


# ───────────────────────── status ─────────────────────────


@app.command()
def status() -> None:
    """Show pipeline state."""
    db, config = _load()
    console = Console()
    counts = queries.get_status_counts(db)
    pred_counts = queries.get_prediction_counts(db)
    judge_counts = queries.get_judgment_counts(db)
    snapshots = queries.list_snapshots(db)

    console.print(f"Database: {config.database_path}")
    console.print(f"Memes:        {counts.total_memes} total")
    console.print(f"  With consensus: {counts.with_consensus}")
    console.print(f"  Validated:      {counts.validated}")
    console.print(f"  Excluded:       {counts.excluded}")
    console.print(f"  Unreviewed:     {counts.unreviewed}")

    if pred_counts:
        console.print("\n[bold]Predictions:[/bold]")
        for pc in pred_counts:
            console.print(f"  {pc.model_id:<30} {pc.predicted}/{pc.total_available} predicted")

    if judge_counts:
        console.print("\n[bold]Judgments:[/bold]")
        for jc in judge_counts:
            total = next(
                (pc.predicted for pc in pred_counts if pc.model_id == jc.model_id),
                jc.judged,
            )
            console.print(
                f"  {jc.model_id:<30} {jc.judged}/{total} judged "
                f"(accuracy: {jc.accuracy * 100:.1f}%)"
            )

    console.print("\n[bold]Snapshots:[/bold]")
    if not snapshots:
        console.print("  (none)")
    else:
        for s in snapshots:
            console.print(f"  {s.name} ({s.created_at[:10]}) — {s.meme_count} memes")

    hints: list[str] = []
    if counts.unreviewed > 0:
        hints.append(
            f"→ {counts.unreviewed} memes need review before prediction "
            "(run: basedbench review)"
        )
    for pc in pred_counts:
        remaining = pc.total_available - pc.predicted
        if remaining > 0:
            hints.append(f"→ {remaining} predictions needed for {pc.model_id}")
    if hints:
        console.print("\n[bold]Needs attention:[/bold]")
        for h in hints:
            console.print(f"  {h}")


# ───────────────────────── run (full pipeline) ─────────────────────────


@app.command()
def run(
    model: str = typer.Argument(..., help="Model id to predict + judge."),
) -> None:
    """Full pipeline: ingest → predict → judge → status."""
    _configure_logging()
    db, config = _load()

    async def _full() -> None:
        await ingest_pipe.run(db, config, limit=50)
        await predict_pipe.run(db, config, model=model)
        await judge_pipe.run(db, config, model=model)

    asyncio.run(_full())
    status()


# ───────────────────────── snapshot ─────────────────────────


@snapshot_app.command("create")
def snapshot_create(
    name: str = typer.Option(..., help="Snapshot name."),
    description: str | None = typer.Option(None, help="Free-text description."),
) -> None:
    """Freeze validated memes into an immutable snapshot."""
    db, _ = _load()
    snapshot_pipe.create(db, name=name, description=description)


@snapshot_app.command("list")
def snapshot_list() -> None:
    """List all snapshots."""
    db, _ = _load()
    snapshot_pipe.list_snapshots(db)


# ───────────────────────── export ─────────────────────────


@app.command()
def export(
    snapshot: str = typer.Argument(..., help="Snapshot name or id."),
    output: Path = typer.Option(Path("export"), help="Output directory."),
) -> None:
    """Export a snapshot to disk (JSONL + images + dataset card)."""
    db, config = _load()
    export_pipe.run(db, config, snapshot, output)


# ───────────────────────── hf push ─────────────────────────


@app.command()
def push(
    snapshot: str = typer.Argument(..., help="Snapshot name or id."),
    repo: str | None = typer.Option(
        None, help="HF dataset repo (e.g. user/basedbench). Defaults to HF_DATASET_REPO."
    ),
    private: bool = typer.Option(False, help="Push as a private dataset."),
) -> None:
    """Push a snapshot to the HuggingFace Hub as a multi-config dataset."""
    db, config = _load()
    hf_push_pipe.run(db, config, snapshot, repo_id=repo, private=private)


# ───────────────────────── traces ─────────────────────────


@app.command()
def traces(
    id: int | None = typer.Option(None, help="Show full detail for this call id."),
    role: str | None = typer.Option(
        None, help="Filter by role (quality_gate, consensus, prediction, judge)."
    ),
    post_id: str | None = typer.Option(None, "--post-id", help="Filter by post id."),
    session: str | None = typer.Option(None, help="Filter by session id."),
    errors: bool = typer.Option(False, help="Show only errors."),
    limit: int = typer.Option(20, help="Max rows to show in list mode."),
) -> None:
    """Inspect LLM call history stored in the database."""
    db, _ = _load()
    console = Console()
    if id is not None:
        call = queries.get_llm_call(db, id)
        if call is None:
            console.print(f"No LLM call found with ID {id}")
            return
        console.print(f"LLM Call #{call.id}")
        console.print(f"  Timestamp:     {call.created_at}")
        console.print(f"  Session:       {call.session_id}")
        console.print(f"  Role:          {call.role}")
        console.print(f"  Post ID:       {call.post_id}")
        console.print(f"  Model:         {call.model}")
        console.print(f"  Prompt Ver:    {call.prompt_version}")
        console.print(f"  Latency:       {call.latency_ms}ms")
        if call.verdict:
            console.print(f"  Verdict:       {call.verdict}")
        if call.error:
            console.print(f"  Error:         {call.error}")
        if call.image_path:
            console.print(f"  Image:         {call.image_path}")
        if call.completion_tokens is not None:
            console.print(f"  Comp Tokens:   {call.completion_tokens}")
        if call.prompt_tokens is not None:
            console.print(f"  Prompt Tokens: {call.prompt_tokens}")
        if call.reasoning:
            console.print(f"\n--- Reasoning ---\n{call.reasoning}")
        console.print(f"\n--- System Prompt ---\n{call.system_prompt}")
        console.print(f"\n--- User Prompt ---\n{call.user_prompt}")
        if call.response:
            console.print(f"\n--- Response ---\n{call.response}")
        return

    rows = queries.list_llm_calls(
        db, role=role, post_id=post_id, session=session, errors_only=errors, limit=limit
    )
    if not rows:
        console.print("No LLM calls found.")
        return

    header = (
        f"{'ID':<5} {'Timestamp':<20} {'Role':<14} {'Post ID':<14} "
        f"{'Model':<18} {'Latency':>8} {'Verdict':<12} Error"
    )
    console.print(header)
    console.print("-" * 105)
    for c in rows:
        post = c.post_id[:12] + "..." if len(c.post_id) > 12 else c.post_id
        model = c.model[:16] + "..." if len(c.model) > 16 else c.model
        ts = c.created_at[:19]
        verdict = c.verdict or "-"
        err = c.error or "-"
        if len(err) > 30:
            err = err[:30] + "..."
        latency = f"{c.latency_ms}ms"
        console.print(
            f"{c.id:<5} {ts:<20} {c.role:<14} {post:<14} {model:<18} "
            f"{latency:>8} {verdict:<12} {err}"
        )
    console.print(f"\n{len(rows)} calls shown (use --id N for full detail)")


# ───────────────────────── review / view (Phase 6 — Gradio) ─────────────────────────


@app.command()
def review() -> None:
    """Launch the Gradio review UI."""
    db, _ = _load()
    db.close()
    from basedbench import app as gradio_app

    gradio_app.launch()


@app.command()
def view(snapshot: str | None = typer.Argument(None)) -> None:
    """Launch the Gradio UI (read-only view; ignores --snapshot for now)."""
    review()


if __name__ == "__main__":
    app()
