"""Snapshot pipeline: freeze validated memes as a content-addressed dataset version."""

from __future__ import annotations

from rich.console import Console

from basedbench.db import queries
from basedbench.db.connection import Database
from basedbench.schemas import dataset_version


def create(
    db: Database, name: str, description: str | None = None, console: Console | None = None
) -> str | None:
    """Create a new snapshot over all validated memes.

    Returns the snapshot id, or None if there was nothing to snapshot or the
    same content was already snapshotted.
    """
    console = console or Console()
    pairs = queries.validated_meme_pairs(db)
    if not pairs:
        console.print("No validated memes to snapshot.")
        return None

    version = dataset_version(pairs)
    if queries.find_snapshot(db, version) is not None:
        console.print(
            f"Snapshot with identical content already exists (hash: {version})"
        )
        return None

    snapshot_id = queries.create_snapshot(db, name, description)
    info = queries.find_snapshot(db, snapshot_id)
    count = info.meme_count if info else 0
    console.print(
        f'Created snapshot "{name}" with {count} memes (hash: {snapshot_id})'
    )
    return snapshot_id


def list_snapshots(db: Database, console: Console | None = None) -> None:
    console = console or Console()
    snapshots = queries.list_snapshots(db)
    if not snapshots:
        console.print("No snapshots.")
        return
    console.print("Snapshots:")
    for s in snapshots:
        short = s.snapshot_id[:8]
        date = s.created_at[:10]
        console.print(f"  {s.name:<12} {short}  {s.meme_count} memes  {date}")
        if s.description:
            console.print(f"             {s.description}")
