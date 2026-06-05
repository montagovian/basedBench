"""Consensus eval harness: seed balanced cases, run prompts, report results."""

from __future__ import annotations

import asyncio
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.table import Table

from basedbench.config import Config
from basedbench.db import queries
from basedbench.db.connection import Database
from basedbench.errors import OpenAIError
from basedbench.llm.consensus import ConsensusDetector
from basedbench.llm.prompts import CONSENSUS_SYSTEM_PROMPT, CONSENSUS_USER_TEMPLATE


def _new_run_id(label: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_") else "-" for ch in label)
    safe = safe.strip("-") or "consensus"
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"consensus-eval-{safe}-{ts}"


def _prompt_text(prompt_file: Path | None) -> tuple[str, str]:
    if prompt_file is None:
        return CONSENSUS_SYSTEM_PROMPT, "current"
    return prompt_file.read_text(), prompt_file.stem


def seed(
    db: Database,
    yes_controls: int = 20,
    no_controls: int = 20,
    include_flagged: bool = True,
    console: Console | None = None,
) -> None:
    console = console or Console()
    flagged = queries.seed_consensus_eval_from_regressions(db) if include_flagged else 0
    yes = queries.seed_consensus_eval_yes_controls(db, yes_controls)
    no = queries.seed_consensus_eval_no_controls(db, no_controls)
    counts = queries.consensus_eval_category_counts(db)

    console.print("[bold green]Consensus eval seed complete[/bold green]")
    console.print(f"  Flagged/misfire rows considered: {flagged}")
    console.print(f"  Yes controls added:             {yes}")
    console.print(f"  No-consensus controls added:    {no}")
    _print_counts(counts, console)


def list_items(db: Database, console: Console | None = None) -> None:
    console = console or Console()
    counts = queries.consensus_eval_category_counts(db)
    _print_counts(counts, console)


def list_runs(
    db: Database,
    limit: int = 10,
    console: Console | None = None,
) -> None:
    console = console or Console()
    runs = queries.list_consensus_eval_runs(db, limit=limit)
    if not runs:
        console.print("[yellow]No consensus eval runs found.[/yellow]")
        return

    table = Table(title="Consensus Eval Runs")
    table.add_column("Created")
    table.add_column("Run ID")
    table.add_column("Label")
    table.add_column("Items", justify="right")
    table.add_column("Model")
    table.add_column("Notes")
    for run in runs:
        table.add_row(
            run.created_at[:19],
            run.run_id,
            run.prompt_label,
            str(run.item_count),
            run.model,
            run.notes or "",
        )
    console.print(table)


def _print_counts(counts: dict[str, int], console: Console) -> None:
    table = Table(title="Active Consensus Eval Items")
    table.add_column("Category")
    table.add_column("Count", justify="right")
    for category, count in counts.items():
        table.add_row(category, str(count))
    table.add_row("[bold]total[/bold]", f"[bold]{sum(counts.values())}[/bold]")
    console.print(table)


async def run(
    db: Database,
    config: Config,
    prompt_file: Path | None = None,
    label: str | None = None,
    category: str | None = None,
    limit: int | None = None,
    notes: str | None = None,
    console: Console | None = None,
) -> str:
    console = console or Console()
    system_prompt, default_label = _prompt_text(prompt_file)
    prompt_label = label or default_label
    detector = ConsensusDetector(
        config,
        system_prompt=system_prompt,
        user_template=CONSENSUS_USER_TEMPLATE,
    )
    items = queries.list_consensus_eval_items(
        db,
        active_only=True,
        category=category,
        limit=limit,
    )
    if not items:
        console.print("[yellow]No active consensus eval items to run.[/yellow]")
        return ""

    run_id = _new_run_id(prompt_label)
    queries.create_consensus_eval_run(
        db,
        run_id=run_id,
        model=config.consensus_model,
        prompt_version=detector.prompt_id,
        prompt_label=prompt_label,
        system_prompt=system_prompt,
        user_prompt_template=CONSENSUS_USER_TEMPLATE,
        item_count=len(items),
        notes=notes,
    )

    console.print(
        f"[bold]Consensus eval:[/bold] {run_id}\n"
        f"  Items: {len(items)}\n"
        f"  Model: {config.consensus_model}\n"
        f"  Prompt: {prompt_label} ({detector.prompt_id})"
    )

    passed = 0
    failed = 0
    for idx, item in enumerate(items, start=1):
        console.print(f"[cyan][{idx}/{len(items)}][/cyan] {item.post_id} {item.category}")
        post = queries.reconstruct_raw_post(db, item.post_id)
        if post is None:
            queries.insert_consensus_eval_result(
                db,
                run_id,
                item,
                actual_has_consensus=False,
                actual_explanation=None,
                confidence=None,
                agreeing_comment_ids=[],
                reasoning=None,
                passed=False,
                error="could not reconstruct post",
            )
            failed += 1
            continue

        try:
            result, record = await detector.detect_consensus(post)
        except OpenAIError as e:
            queries.insert_consensus_eval_result(
                db,
                run_id,
                item,
                actual_has_consensus=False,
                actual_explanation=None,
                confidence=None,
                agreeing_comment_ids=[],
                reasoning=None,
                passed=False,
                error=str(e),
            )
            failed += 1
            continue

        call_id = queries.insert_llm_call(db, record) if record is not None else None
        ok = result.has_consensus == item.expected_has_consensus
        queries.insert_consensus_eval_result(
            db,
            run_id,
            item,
            actual_has_consensus=result.has_consensus,
            actual_explanation=result.selected_explanation,
            confidence=result.confidence,
            agreeing_comment_ids=result.agreeing_comment_ids,
            reasoning=result.reasoning,
            passed=ok,
            latency_ms=record.latency_ms if record is not None else None,
            llm_call_id=call_id,
        )
        if ok:
            passed += 1
        else:
            failed += 1

    console.print(f"\n[bold]Summary:[/bold] {passed} passed, {failed} failed")
    report(db, run_id, console=console)
    return run_id


def report(
    db: Database,
    run_id: str | None = None,
    failed_only: bool = False,
    console: Console | None = None,
) -> None:
    console = console or Console()
    run_id = run_id or queries.latest_consensus_eval_run_id(db)
    if run_id is None:
        console.print("[yellow]No consensus eval runs found.[/yellow]")
        return
    results = queries.list_consensus_eval_results(db, run_id)
    if not results:
        console.print(f"[yellow]No results for run {run_id}.[/yellow]")
        return

    total = len(results)
    passed = sum(1 for r in results if r.passed)
    expected_yes = sum(1 for r in results if r.expected_has_consensus)
    expected_no = total - expected_yes
    false_positive = sum(
        1
        for r in results
        if not r.expected_has_consensus and r.actual_has_consensus
    )
    false_negative = sum(
        1
        for r in results
        if r.expected_has_consensus and not r.actual_has_consensus
    )

    console.print(f"\n[bold]Consensus Eval Report:[/bold] {run_id}")
    console.print(f"  Accuracy:        {passed}/{total} ({passed / total:.1%})")
    console.print(f"  Expected yes/no: {expected_yes}/{expected_no}")
    console.print(f"  False positive:  {false_positive}")
    console.print(f"  False negative:  {false_negative}")

    by_category: dict[str, Counter[str]] = defaultdict(Counter)
    for result in results:
        by_category[result.category]["total"] += 1
        by_category[result.category]["passed" if result.passed else "failed"] += 1

    table = Table(title="By Category")
    table.add_column("Category")
    table.add_column("Passed", justify="right")
    table.add_column("Failed", justify="right")
    table.add_column("Accuracy", justify="right")
    for category, counts in sorted(by_category.items()):
        cat_total = counts["total"]
        cat_passed = counts["passed"]
        table.add_row(
            category,
            str(cat_passed),
            str(counts["failed"]),
            f"{cat_passed / cat_total:.1%}",
        )
    console.print(table)

    detail_results = [r for r in results if not r.passed] if failed_only else results
    failures = [r for r in detail_results if not r.passed]
    if failures:
        console.print("\n[bold]Failures:[/bold]")
        for result in failures[:25]:
            expected = "consensus" if result.expected_has_consensus else "no_consensus"
            actual = "consensus" if result.actual_has_consensus else "no_consensus"
            console.print(
                f"- {result.post_id} [{result.category}] expected={expected} "
                f"actual={actual}",
                markup=False,
            )
            if result.actual_explanation:
                console.print(
                    f"  actual: {result.actual_explanation[:300]}",
                    markup=False,
                )


def run_sync(*args, **kwargs) -> str:
    return asyncio.run(run(*args, **kwargs))
