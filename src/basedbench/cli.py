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
from basedbench.pipeline import tracer as tracer_pipe

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
    time_filter: str = typer.Option(
        "year",
        "--time-filter",
        "-t",
        help="Reddit top window: hour, day, week, month, year, all.",
    ),
    after_date: str | None = typer.Option(
        None,
        "--after-date",
        help="Start of date range (YYYY-MM-DD, inclusive). Uses pullpush.io.",
    ),
    before_date: str | None = typer.Option(
        None,
        "--before-date",
        help="End of date range (YYYY-MM-DD, exclusive). Uses pullpush.io.",
    ),
) -> None:
    """Fetch memes from Reddit, download images, run quality gate + consensus."""
    _configure_logging()

    # Validate mode selection: date-range OR time-filter, not both.
    has_after = after_date is not None
    has_before = before_date is not None
    if has_after != has_before:
        raise typer.BadParameter(
            "--after-date and --before-date must be given together."
        )
    use_date_range = has_after and has_before

    after_unix: int | None = None
    before_unix: int | None = None
    if use_date_range:
        from datetime import datetime, timezone

        try:
            after_dt = datetime.strptime(after_date, "%Y-%m-%d").replace(
                tzinfo=timezone.utc
            )
            before_dt = datetime.strptime(before_date, "%Y-%m-%d").replace(
                tzinfo=timezone.utc
            )
        except ValueError as e:
            raise typer.BadParameter(f"Date must be YYYY-MM-DD: {e}") from e
        if after_dt >= before_dt:
            raise typer.BadParameter("--after-date must be before --before-date.")
        after_unix = int(after_dt.timestamp())
        before_unix = int(before_dt.timestamp())

    db, config = _load()
    asyncio.run(
        ingest_pipe.run(
            db,
            config,
            limit=limit,
            subreddit=subreddit,
            time_filter=time_filter,
            after_unix=after_unix,
            before_unix=before_unix,
        )
    )


# ───────────────────────── predict ─────────────────────────


@app.command()
def predict(
    model: str = typer.Argument(..., help="Model id (e.g. gpt-5.5, claude-opus-4-7)."),
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
    judge_model: list[str] = typer.Option(  # noqa: B008
        None,
        "--judge-model",
        "-j",
        help="Judge model (repeat to use multiple). Defaults to config.judge_models.",
    ),
) -> None:
    """Judge predictions. Each prediction is scored by every judge model."""
    _configure_logging()
    db, config = _load()
    asyncio.run(
        judge_pipe.run(
            db,
            config,
            model=model,
            judge_models=judge_model or None,
            rejudge_prompt=rejudge_prompt,
        )
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
            label = f"{jc.model_id} ← {jc.judge_model}"
            console.print(
                f"  {label:<50} {jc.judged}/{total} judged "
                f"(accuracy: {jc.accuracy * 100:.1f}%)"
            )

        agreement = queries.get_judge_agreement(db)
        agreement_rows = [a for a in agreement if a.judged_by_multiple > 0]
        if agreement_rows:
            console.print("\n[bold]Judge agreement (predictions scored by ≥2 judges):[/bold]")
            for a in agreement_rows:
                console.print(
                    f"  {a.model_id:<30} {a.agreements}/{a.judged_by_multiple} "
                    f"({a.rate * 100:.1f}% agree)"
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


# ───────────────────────── tracer ─────────────────────────


@app.command()
def tracer(
    fetch: int = typer.Option(12, help="Max new posts to insert into the batch."),
    target_consensus: int = typer.Option(
        5, help="Stop curation after this many consensus-passed rows."
    ),
    predict: str = typer.Option(
        "gpt-5.5",
        "--predict",
        help="Model to run on consensus-passed tracer rows.",
    ),
    subreddit: list[str] = typer.Option(  # noqa: B008
        None,
        "--subreddit",
        "-r",
        help="Subreddit to fetch, repeatable. Defaults to pipeline defaults.",
    ),
    time_filter: list[str] = typer.Option(  # noqa: B008
        None,
        "--time-filter",
        "-t",
        help="Reddit top window to try, repeatable and ordered.",
    ),
    judge: bool = typer.Option(False, help="Also judge tracer predictions."),
    judge_model: list[str] = typer.Option(  # noqa: B008
        None,
        "--judge-model",
        "-j",
        help="Judge model, repeatable. Defaults to config.judge_models.",
    ),
    batch_id: str | None = typer.Option(None, help="Optional explicit batch id."),
) -> None:
    """Run a bounded fetch → consensus → prediction tracer bullet."""
    _configure_logging()
    db, config = _load()
    asyncio.run(
        tracer_pipe.run(
            db,
            config,
            fetch=fetch,
            target_consensus=target_consensus,
            predict_model=predict,
            subreddits=subreddit or None,
            time_filters=time_filter or None,
            judge=judge,
            judge_models=judge_model or None,
            batch_id=batch_id,
        )
    )


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


# ───────────────────────── cleanup ─────────────────────────


@app.command()
def cleanup(
    missing_images: bool = typer.Option(
        False,
        "--missing-images",
        help="Auto-exclude consensus-passed memes that have no local image file.",
    ),
) -> None:
    """Maintenance tasks for stale or unusable rows. At least one flag required."""
    _configure_logging()
    if not missing_images:
        raise typer.BadParameter(
            "No cleanup target selected. Pass --missing-images (or another flag)."
        )

    db, _ = _load()
    console = Console()
    if missing_images:
        n = queries.auto_exclude_missing_images(db)
        console.print(
            f"Auto-excluded {n} memes with missing images "
            "(reason='image_missing')."
        )


# ───────────────────────── regression-eval ─────────────────────────


@app.command(name="regression-eval")
def regression_eval(
    status_filter: str | None = typer.Option(
        None, "--status",
        help="Only test entries with this status (wrong/partial/correct).",
    ),
    limit: int | None = typer.Option(
        None, "--limit", help="Test only the first N entries (for fast iteration)."
    ),
) -> None:
    """Re-run consensus on the flagged regression set, show old vs new vs canonical.

    Useful for A/B-testing consensus prompt or model changes against a curated
    set of known failures. Doesn't write to the DB — read-only inspection.
    """
    _configure_logging()
    db, config = _load()
    console = Console()

    entries = queries.list_consensus_regressions(db, status=status_filter)
    if limit is not None:
        entries = entries[:limit]
    if not entries:
        console.print("[yellow]No regression entries to test.[/yellow]")
        return

    console.print(
        f"Re-running consensus on {len(entries)} flagged meme(s) "
        f"with model={config.consensus_model}...\n"
    )

    from basedbench.llm.consensus import ConsensusDetector

    detector = ConsensusDetector(config)
    changed = 0
    unchanged = 0

    async def run_one(entry):
        post = queries.reconstruct_raw_post(db, entry.post_id)
        if post is None:
            return None, "could not reconstruct post"
        result, _ = await detector.detect_consensus(post)
        return result, None

    for i, entry in enumerate(entries, 1):
        console.print(f"[bold cyan][{i}/{len(entries)}] {entry.post_id}[/bold cyan]")
        console.print(f"  flagged as: [bold]{entry.status}[/bold]")
        if entry.failure_modes:
            console.print(f"  failure modes: {entry.failure_modes}")
        console.print(f"\n  [dim]OLD consensus (at flag time):[/dim]")
        console.print(f"    {entry.consensus_at_annotation}")
        if entry.canonical_explanation:
            console.print(f"\n  [green]CANONICAL (user-provided):[/green]")
            console.print(f"    {entry.canonical_explanation}")

        result, err = asyncio.run(run_one(entry))
        if err is not None:
            console.print(f"  [red]Re-run failed: {err}[/red]\n")
            continue

        if result.has_consensus:
            new_text = result.selected_explanation or ""
            console.print(f"\n  [magenta]NEW consensus (current config):[/magenta]")
            console.print(f"    {new_text}")
            if new_text.strip() == entry.consensus_at_annotation.strip():
                console.print("  [yellow]→ unchanged[/yellow]\n")
                unchanged += 1
            else:
                console.print("  [bold green]→ CHANGED[/bold green]\n")
                changed += 1
        else:
            console.print("\n  [magenta]NEW: no consensus reached[/magenta]\n")
            changed += 1

    console.print(
        f"\n[bold]Summary:[/bold] {changed} changed, {unchanged} unchanged "
        f"(of {len(entries)} tested)"
    )


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
