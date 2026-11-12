"""Ordered, transactional SQLite migrations with a durable checksum ledger.

The baseline is the idempotent assembled schema in ``db.py`` (plus domain
schema modules such as ``onesignal_setup``). Ordered ``NNNN_*.sql`` files are
applied once each, in filename order, inside one transaction per file. Applied
file checksums are immutable: editing a released migration fails startup so
history cannot silently diverge from the code.
"""

import re
import sqlite3
from collections.abc import Callable, Iterator
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, TypeVar

DIRECTORY = Path(__file__).resolve().parent
BASELINE_VERSION = 0
PATTERN = re.compile(r"^(\d{4})_([a-z0-9_]+)\.sql$")
LEDGER = (
    "CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY,"
    "name TEXT NOT NULL,checksum TEXT NOT NULL,applied_at TEXT NOT NULL) WITHOUT ROWID"
)


class SchemaMigrationError(RuntimeError):
    """The ledger or an applied migration does not match the declared files."""


def discovered() -> list[tuple[int, str, Path]]:
    """Return ``(version, name, path)`` for every ordered migration file."""
    entries = []
    for path in sorted(DIRECTORY.iterdir()):
        match = PATTERN.fullmatch(path.name)
        if match:
            entries.append((int(match.group(1)), match.group(2), path))
    versions = [version for version, _, _ in entries]
    if versions != list(range(1, len(versions) + 1)):
        raise SchemaMigrationError("Migration versions must be contiguous from 0001")
    return entries


def statements(sql: str) -> Iterator[str]:
    """Split one migration into complete statements without executing them early."""
    buffer = ""
    for line in sql.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            value = buffer.strip()
            if value:
                yield value
            buffer = ""
    if buffer.strip():
        raise SchemaMigrationError("Migration ends with an incomplete statement")


def schema_digest(db: sqlite3.Connection) -> str:
    """Hash the actual schema objects, independent of source formatting."""
    rows = db.execute(
        "SELECT type,name,tbl_name,sql FROM sqlite_master "
        "WHERE name NOT LIKE 'sqlite_%' AND name!='schema_migrations' "
        "AND sql IS NOT NULL ORDER BY type,name"
    ).fetchall()
    payload = "\n".join("|".join("" if value is None else str(value) for value in row) for row in rows)
    return sha256(payload.encode("utf-8")).hexdigest()


def applied(db: sqlite3.Connection) -> list[dict[str, Any]]:
    """Return the durable ledger rows in version order."""
    try:
        rows = db.execute("SELECT version,name,checksum,applied_at FROM schema_migrations ORDER BY version").fetchall()
    except sqlite3.OperationalError:
        return []
    return [dict(version=row[0], name=row[1], checksum=row[2], applied_at=row[3]) for row in rows]


T = TypeVar("T")


def _atomic(db: sqlite3.Connection, work: Callable[[], T]) -> T:
    """Run one unit inside the caller's transaction or its own immediate one."""
    outer = db.in_transaction
    if not outer:
        db.execute("BEGIN IMMEDIATE")
    try:
        result = work()
    except BaseException:
        if not outer and db.in_transaction:
            db.execute("ROLLBACK")
        raise
    if not outer:
        db.execute("COMMIT")
    return result


def _record(db: sqlite3.Connection, version: int, name: str, checksum: str) -> None:
    db.execute(
        "INSERT INTO schema_migrations(version,name,checksum,applied_at) VALUES(?,?,?,?)",
        (version, name, checksum, datetime.now(timezone.utc).isoformat()),
    )


def _ensure_baseline(db: sqlite3.Connection, checksum: str) -> bool:
    """Record the baseline once, including across concurrent initializers."""
    if db.execute("SELECT 1 FROM schema_migrations WHERE version=?", (BASELINE_VERSION,)).fetchone() is not None:
        return False
    _record(db, BASELINE_VERSION, "baseline", checksum)
    return True


def _apply_migration(db: sqlite3.Connection, version: int, name: str, sql: str, checksum: str) -> bool:
    """Apply one file exactly once, rechecking under the write lock."""
    row = db.execute("SELECT checksum FROM schema_migrations WHERE version=?", (version,)).fetchone()
    if row is not None:
        if row[0] != checksum:
            raise SchemaMigrationError(f"Applied migration {version:04d} was edited")
        return False
    for statement in statements(sql):
        db.execute(statement)
    _record(db, version, name, checksum)
    return True


def apply(db: sqlite3.Connection, *, baseline_checksum: str | None = None) -> list[int]:
    """Record the baseline, then apply every missing migration exactly once."""
    db.execute(LEDGER)
    baseline = baseline_checksum or schema_digest(db)
    _atomic(db, lambda: _ensure_baseline(db, baseline))
    entries = discovered()
    pending = []
    for version, name, path in entries:
        sql = path.read_text(encoding="utf-8")
        checksum = sha256(path.read_bytes()).hexdigest()

        def work(version=version, name=name, sql=sql, checksum=checksum):
            return _apply_migration(db, version, name, sql, checksum)

        if _atomic(db, work):
            pending.append(version)
    db.execute("PRAGMA user_version=%d" % (entries[-1][0] if entries else BASELINE_VERSION))
    return pending
