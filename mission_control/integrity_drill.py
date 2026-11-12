"""Repeatable integrity, backup/restore and migration replay receipt."""

import json
import sqlite3
import tempfile
from pathlib import Path
from typing import Any, TypedDict

from . import migrations
from .db import connection, initialize
from .store import Store


class Inspection(TypedDict):
    integrity_check: list[str]
    foreign_key_violations: list[tuple[Any, ...]]
    counts: dict[str, int]


class BackupReceipt(TypedDict):
    integrity_check: list[str]
    foreign_key_violations: list[tuple[Any, ...]]
    counts_match: bool


class DrillReceipt(TypedDict):
    schema: str
    ok: bool
    app_receipt: str
    integrity_check: list[str]
    foreign_key_violations: list[tuple[Any, ...]]
    table_count: int
    schema_digest: str
    backup: BackupReceipt
    migrations: list[int]
    user_version: int
    replay_after_backup: list[int]
    replay_digest_match: bool


def tables(db: sqlite3.Connection) -> list[str]:
    return [
        str(row[0])
        for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]


def inspect(path: Path) -> Inspection:
    db = sqlite3.connect(str(path))
    try:
        integrity = [str(row[0]) for row in db.execute("PRAGMA integrity_check")]
        foreign = [tuple(row) for row in db.execute("PRAGMA foreign_key_check")]
        counts = {name: int(db.execute(f"SELECT COUNT(*) FROM '{name}'").fetchone()[0]) for name in tables(db)}
        return Inspection(integrity_check=integrity, foreign_key_violations=foreign, counts=counts)
    finally:
        db.close()


def copy(source: Path, target: Path) -> None:
    origin = sqlite3.connect(str(source))
    destination = sqlite3.connect(str(target))
    try:
        origin.backup(destination)
    finally:
        destination.close()
        origin.close()


def run(root: Path | None = None) -> DrillReceipt:
    """Run the drill and return a bounded receipt; never touches an owner database."""
    with tempfile.TemporaryDirectory() as temporary:
        folder = Path(temporary) if root is None else Path(root)
        folder.mkdir(parents=True, exist_ok=True)
        primary = folder / "primary.sqlite"
        backup = folder / "backup.sqlite"
        store = Store(primary)
        app_id = str(store.apps()[0]["id"])
        with connection(primary) as db:
            primary_state = inspect(primary)
            digest = migrations.schema_digest(db)
            versions = [int(row["version"]) for row in migrations.applied(db)]
            user_version = int(db.execute("PRAGMA user_version").fetchone()[0])
        copy(primary, backup)
        restored = inspect(backup)
        initialize(backup)
        with connection(backup) as db:
            replay = migrations.apply(db)
            restored_digest = migrations.schema_digest(db)
        fresh = folder / "fresh.sqlite"
        initialize(fresh)
        with connection(fresh) as db:
            fresh_digest = migrations.schema_digest(db)
        ok = (
            primary_state["integrity_check"] == ["ok"]
            and primary_state["foreign_key_violations"] == []
            and restored["integrity_check"] == ["ok"]
            and restored["foreign_key_violations"] == []
            and primary_state["counts"] == restored["counts"]
            and replay == []
            and digest == restored_digest == fresh_digest
            and versions == list(range(len(versions)))
            and user_version == (versions[-1] if versions else 0)
        )
        return DrillReceipt(
            schema="wmm.integrity-drill.v1",
            ok=ok,
            app_receipt=app_id,
            integrity_check=primary_state["integrity_check"],
            foreign_key_violations=primary_state["foreign_key_violations"],
            table_count=len(primary_state["counts"]),
            schema_digest=digest,
            backup=BackupReceipt(
                integrity_check=restored["integrity_check"],
                foreign_key_violations=restored["foreign_key_violations"],
                counts_match=primary_state["counts"] == restored["counts"],
            ),
            migrations=versions,
            user_version=user_version,
            replay_after_backup=replay,
            replay_digest_match=digest == restored_digest == fresh_digest,
        )


def main() -> int:
    value = run()
    print("INTEGRITY_DRILL " + json.dumps(value, sort_keys=True))
    return 0 if value["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
