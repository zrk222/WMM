"""Read-only, tamper-evident evidence bundle for one app; not an audit opinion."""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import re
import sqlite3

SCHEMA = "wmm.audit-bundle.v1"
KEY_TABLES = (
    "apps", "records", "audit", "agent_grants", "agent_review_requests", "verified_reviews",
    "provider_actions", "provider_action_events", "growth_review_entries",
    "install_attribution_batches", "install_attribution_rows",
    "observational_campaign_studies", "observational_campaign_batches", "observational_campaign_events",
    "operator_roles", "team_sessions",
)


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def digest(value) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def connect(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise FileNotFoundError("Database is missing")
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)


def schema_sha256(db) -> str:
    rows = db.execute("SELECT type,name,sql FROM sqlite_master ORDER BY type,name").fetchall()
    return digest(rows)


def table_names(db) -> list[str]:
    return [row[0] for row in db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]


def app_columns(db, table: str, app_id: str) -> list[str]:
    columns = [row[1] for row in db.execute('PRAGMA table_info("' + table.replace('"', '""') + '")')]
    if "app_id" in columns:
        return columns
    if table == "apps" and "id" in columns:
        return columns
    return []


def table_state(db, table: str, app_id: str) -> dict:
    columns = app_columns(db, table, app_id)
    if not columns:
        return {"count": None, "digest": None, "scope": "NO_APP_COLUMN"}
    quoted = ", ".join('"' + column.replace('"', '""') + '"' for column in columns)
    key = "id" if table == "apps" else "app_id"
    rows = db.execute('SELECT ' + quoted + ' FROM "' + table.replace('"', '""') + '" WHERE ' + key + '=? ORDER BY ' + quoted,
                      (app_id,)).fetchall()
    if not rows:
        return {"count": 0, "digest": None, "scope": "APP_SCOPED"}
    return {"count": len(rows), "digest": digest([list(row) for row in rows]), "scope": "APP_SCOPED"}


def audit_summary(db, app_id: str) -> dict:
    if "audit" not in table_names(db):
        return {"count": 0, "chain_sha256": None}
    previous, count, first, last = "", 0, None, None
    for row in db.execute("SELECT id,action,detail,created FROM audit WHERE app_id=? ORDER BY id", (app_id,)):
        previous = hashlib.sha256((previous + canonical(list(row))).encode("utf-8")).hexdigest()
        count += 1
        first = row[0] if first is None else first
        last = row[0]
    return {"count": count, "first_id": first, "last_id": last, "chain_sha256": previous or None}


def attribution(db, app_id: str) -> dict:
    names = set(table_names(db))
    studies = []
    if "observational_campaign_studies" in names:
        for study_id, value_hash, data in db.execute(
                "SELECT study_id,hash,data FROM observational_campaign_studies WHERE app_id=? ORDER BY study_id",
                (app_id,)):
            try:
                value = json.loads(data)
            except (TypeError, ValueError):
                value = {}
            studies.append({"study_id": study_id, "hash": value_hash,
                            "source": value.get("source"), "creative_id": value.get("creative_id"),
                            "starts_at": value.get("starts_at"), "ends_at": value.get("ends_at")})
    batches = []
    if "install_attribution_batches" in names:
        for batch_id, token, source, value_hash, created in db.execute(
                "SELECT id,campaign_token,source,hash,created FROM install_attribution_batches "
                "WHERE app_id=? ORDER BY created,id", (app_id,)):
            batches.append({"id": batch_id, "campaign_token": token, "source": source,
                            "hash": value_hash, "created": created})
    states = {}
    if "install_attribution_rows" in names:
        states = {state: count for state, count in db.execute(
            "SELECT state,count(*) FROM install_attribution_rows WHERE app_id=? GROUP BY state ORDER BY state",
            (app_id,))}
    study_ids = {row["study_id"] for row in studies}
    tokens = {row["campaign_token"] for row in batches}
    return {"studies": studies, "batches": batches, "install_states": states,
            "linked_studies": sorted(study_ids & tokens),
            "unlinked_campaign_tokens": sorted(tokens - study_ids)}


def build(database: Path, app_id: str) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", app_id or ""):
        raise ValueError("Use a simple app id")
    with closing(connect(database)) as db:
        names = table_names(db)
        if "apps" not in names or db.execute("SELECT 1 FROM apps WHERE id=?", (app_id,)).fetchone() is None:
            raise ValueError("App is not in this database")
        value = {
            "schema": SCHEMA,
            "app_id": app_id,
            "database_schema_sha256": schema_sha256(db),
            "tables": {name: table_state(db, name, app_id) for name in names},
            "audit": audit_summary(db, app_id),
            "attribution": attribution(db, app_id),
            "limitations": [
                "Read-only snapshot manifest, not an independent audit or certification.",
                "Digests prove the supplied database content at export time; they do not prove earlier history.",
                "No raw evidence, credentials, token hashes or customer identifiers are emitted.",
            ],
        }
    value["manifest_sha256"] = digest(value)
    return value


def verify(database: Path, app_id: str, bundle: dict) -> dict:
    if bundle.get("schema") != SCHEMA or bundle.get("app_id") != app_id:
        raise ValueError("Bundle schema or app does not match")
    claimed = bundle.get("manifest_sha256")
    body = {key: value for key, value in bundle.items() if key != "manifest_sha256"}
    if claimed != digest(body):
        raise ValueError("Bundle manifest hash does not match its contents")
    fresh = build(database, app_id)
    if fresh["manifest_sha256"] != claimed:
        raise ValueError("Database no longer matches the bundle; evidence changed")
    return {"status": "MATCH", "app_id": app_id, "manifest_sha256": claimed,
            "audit_chain_sha256": fresh["audit"]["chain_sha256"]}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    export = sub.add_parser("export")
    export.add_argument("--database", required=True)
    export.add_argument("--app", required=True)
    export.add_argument("--out", required=True)
    check = sub.add_parser("verify")
    check.add_argument("--database", required=True)
    check.add_argument("--app", required=True)
    check.add_argument("--bundle", required=True)
    args = parser.parse_args(argv)
    if args.command == "export":
        value = build(Path(args.database), args.app)
        Path(args.out).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"status": "EXPORTED", "app_id": args.app,
                          "manifest_sha256": value["manifest_sha256"]}, sort_keys=True))
        return 0
    value = json.loads(Path(args.bundle).read_text(encoding="utf-8"))
    print(json.dumps(verify(Path(args.database), args.app, value), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
