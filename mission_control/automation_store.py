"""Immutable owner-authored automation rule sets; simulation remains separate."""
from __future__ import annotations

import json

from .automation_rules import validate
from .common import Invalid, canonical, digest, now
from .db import connection
from .store import audit


def _public(row):
    if row is None:
        return None
    return {"app_id": row["app_id"], "version": row["version"], "hash": row["hash"],
            "created": row["created"], "created_by": row["created_by"],
            "document": json.loads(row["document"])}


def current(store, app_id):
    """Return the latest saved rule set, or None."""
    store.app(app_id)
    with connection(store.path) as db:
        row = db.execute("SELECT * FROM automation_rule_sets WHERE app_id=? ORDER BY version DESC LIMIT 1",
                         (app_id,)).fetchone()
    return _public(row)


def history(store, app_id):
    """Return immutable rule versions without executing anything."""
    store.app(app_id)
    with connection(store.path) as db:
        rows = db.execute("SELECT * FROM automation_rule_sets WHERE app_id=? ORDER BY version DESC LIMIT 100",
                          (app_id,)).fetchall()
    return [_public(row) for row in rows]


def save(store, app_id, user, document):
    """Validate and append one owner-authored version; no evaluation or effect."""
    store.app(app_id)
    if not isinstance(user, dict) or not isinstance(user.get("principal"), str) or not user["principal"]:
        raise PermissionError("A verified owner is required")
    rules = validate(document)
    value = canonical(rules)
    value_hash = digest(rules)
    with connection(store.path) as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT version FROM automation_rule_sets WHERE app_id=? ORDER BY version DESC LIMIT 1",
                         (app_id,)).fetchone()
        version = (row["version"] + 1) if row else 1
        db.execute("INSERT INTO automation_rule_sets VALUES(?,?,?,?,?,?)",
                   (app_id, version, value, value_hash, now(), user["principal"]))
        audit(db, app_id, "automation.rules.saved", {"version": version, "hash": value_hash,
                                                      "rules": len(rules["rules"])})
        saved = db.execute("SELECT * FROM automation_rule_sets WHERE app_id=? AND version=?",
                           (app_id, version)).fetchone()
    return _public(saved)
