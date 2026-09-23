"""Offline release commands; no provider credentials or live database required."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from basedbench.pipeline.release_snapshot import (
    canonical_bytes,
    evaluation_inputs,
    freeze_release,
    load_release,
)

app = typer.Typer(help="Freeze, verify and export immutable local releases.", no_args_is_help=True)


def _read_object(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def _emit(value: object, output: Path | None = None) -> None:
    payload = canonical_bytes(value)
    if output is None:
        typer.echo(payload.decode("utf-8"), nl=False)
    else:
        # Exclusive creation preserves existing reports and inputs.
        with output.open("xb") as stream:
            stream.write(payload)


@app.command("freeze")
def freeze(
    selection: Path = typer.Argument(..., help="Private selection JSON."),
    source_root: Path = typer.Option(..., help="Root containing selected local images."),
    output: Path = typer.Option(..., help="New local release directory; never overwritten."),
) -> None:
    """Copy exact selected answers and images into a verified frozen release."""
    try:
        manifest = freeze_release(_read_object(selection), output, source_root=source_root)
        _emit({"content_sha256": manifest["content_sha256"], "items": len(manifest["items"]),
               "output": str(output)})
    except (ValueError, OSError, TypeError, KeyError) as exc:
        raise typer.BadParameter(str(exc)) from exc


@app.command("verify")
def verify(release: Path = typer.Argument(..., help="Frozen release directory.")) -> None:
    """Validate the schema, exact membership, text and all image hashes."""
    try:
        manifest = load_release(release)
        _emit({"content_sha256": manifest["content_sha256"], "items": len(manifest["items"]),
               "verified": True})
    except (ValueError, OSError, TypeError, KeyError) as exc:
        raise typer.BadParameter(str(exc)) from exc


@app.command("inputs")
def inputs(
    release: Path = typer.Argument(..., help="Frozen release directory."),
    output: Path | None = typer.Option(None, help="New private JSON file; stdout if omitted."),
) -> None:
    """Emit verified image-only predictor inputs; makes no model calls."""
    try:
        _emit(evaluation_inputs(release), output)
    except (ValueError, OSError, TypeError, KeyError) as exc:
        raise typer.BadParameter(str(exc)) from exc


@app.command("report")
def report(
    release: Path = typer.Argument(..., help="Frozen release directory."),
    evidence: Path | None = typer.Option(None, help="Private cached-evidence JSON; optional."),
    output: Path | None = typer.Option(None, help="New private report JSON; stdout if omitted."),
) -> None:
    """Report exact cache compatibility and cohort coverage without paid evaluation."""
    from basedbench.pipeline.release_report import build_report

    try:
        _emit(build_report(release, _read_object(evidence) if evidence else None), output)
    except (ValueError, OSError, TypeError, KeyError) as exc:
        raise typer.BadParameter(str(exc)) from exc


@app.command("export")
def export(
    release: Path = typer.Argument(..., help="Frozen release directory."),
    output: Path = typer.Option(..., help="New export directory; never overwritten."),
    evidence: Path | None = typer.Option(None, help="Private cached-evidence JSON; optional."),
) -> None:
    """Write allowlisted local tables, images and a dataset card; does not publish."""
    from basedbench.pipeline.release_report import export_release

    try:
        path = export_release(release, output, _read_object(evidence) if evidence else None)
        _emit({"output": str(path)})
    except (ValueError, OSError, TypeError, KeyError) as exc:
        raise typer.BadParameter(str(exc)) from exc
