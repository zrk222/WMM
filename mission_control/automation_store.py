"""Immutable owner-authored automation rule sets; simulation remains separate."""
from __future__ import annotations

import json

from .automation_rules import validate
from .common import Invalid, canonical, digest, now
from .db import connection
from .review_access import member
from .store import audit


def _public(row):
    if row is None:
        return None
    return {"app_id": row["app_id"], "version": row["version"], "hash": row["hash"],
            "created": row["created"], "created_by": row["created_by"],
            "document": json.loads(row["document"])}


def current(store, app_id, principal):
    """Read the latest saved rules in the same snapshot as the owner check."""
    with connection(store.path) as db:
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        member(db, app_id, principal, "OWNER")
        row = db.execute("SELECT * FROM automation_rule_sets WHERE app_id=? ORDER BY version DESC LIMIT 1",
                         (app_id,)).fetchone()
    return _public(row)


def history(store, app_id, principal):
    """Read immutable rule versions in the same snapshot as the owner check."""
    with connection(store.path) as db:
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        member(db, app_id, principal, "OWNER")
        rows = db.execute("SELECT * FROM automation_rule_sets WHERE app_id=? ORDER BY version DESC LIMIT 100",
                          (app_id,)).fetchall()
    return [_public(row) for row in rows]


def save(store, app_id, user, document, *, commit_check=None):
    """Validate and append one owner-authored version; no evaluation or effect."""
    if not isinstance(user, dict) or not isinstance(user.get("principal"), str) or not user["principal"]:
        raise PermissionError("A verified owner is required")
    rules = validate(document)
    value = canonical(rules)
    value_hash = digest(rules)
    with connection(store.path) as db:
        db.execute("BEGIN IMMEDIATE")
        member(db, app_id, user["principal"], "OWNER")
        row = db.execute("SELECT version FROM automation_rule_sets WHERE app_id=? ORDER BY version DESC LIMIT 1",
                         (app_id,)).fetchone()
        version = (row["version"] + 1) if row else 1
        db.execute("INSERT INTO automation_rule_sets VALUES(?,?,?,?,?,?)",
                   (app_id, version, value, value_hash, now(), user["principal"]))
        audit(db, app_id, "automation.rules.saved", {"version": version, "hash": value_hash,
                                                      "rules": len(rules["rules"])})
        saved = db.execute("SELECT * FROM automation_rule_sets WHERE app_id=? AND version=?",
                           (app_id, version)).fetchone()
        if commit_check is not None:
            commit_check()
    return _public(saved)
