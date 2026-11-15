"""Generate TypedDict row types from the assembled core SQLite schema."""

import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mission_control.db import initialize  # noqa: E402

TARGET = ROOT / "mission_control/schema_types.py"
HEADER = '''"""Generated row types for the assembled core schema.

Regenerate with ``python tools/generate_schema_types.py`` after any schema
change. The core scope is ``db.py`` plus the host-installed ``onesignal_setup``
schema; domain modules that install their own tables remain separate.
"""
from typing import TypedDict
'''


def python_type(declared, nullable):
    value = (declared or "").upper()
    if "INT" in value:
        base = "int"
    elif any(word in value for word in ("CHAR", "CLOB", "TEXT")):
        base = "str"
    elif "BLOB" in value or not value:
        base = "bytes"
    elif any(word in value for word in ("REAL", "FLOA", "DOUB", "NUM", "DEC")):
        base = "float"
    else:
        base = "object"
    return f"{base} | None" if nullable else base


def class_name(table):
    return "".join(part.capitalize() for part in table.split("_")) + "Row"


def render():
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "schema.sqlite"
        initialize(path)
        db = sqlite3.connect(str(path))
        try:
            tables = [
                row[0]
                for row in db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' "
                    "AND name!='schema_migrations' ORDER BY name"
                )
            ]
            blocks = [HEADER]
            for table in tables:
                columns = list(db.execute(f"PRAGMA table_info('{table}')"))
                lines = [f"class {class_name(table)}(TypedDict):"]
                for column in columns:
                    name, declared, notnull, _, primary = column[1:6]
                    nullable = not notnull and not primary
                    lines.append(f"    {name}: {python_type(declared, nullable)}")
                blocks.append("\n".join(lines) + "\n")
        finally:
            db.close()
    return "\n\n".join(blocks).rstrip() + "\n"


def main(argv):
    value = render()
    if "--check" in argv:
        current = TARGET.read_text(encoding="utf-8") if TARGET.exists() else ""
        if current != value:
            print("SCHEMA_TYPES_DRIFT regenerate mission_control/schema_types.py", file=sys.stderr)
            return 1
        print("SCHEMA_TYPES_CURRENT")
        return 0
    TARGET.write_text(value, encoding="utf-8")
    print(f"WROTE {TARGET.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
