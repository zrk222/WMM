"""Immutable owner-authored automation rule sets; simulation remains separate."""
from __future__ import annotations

import json
import re

from .automation_rules import validate
from .common import Invalid, canonical, digest, now
from .db import connection
from .review_access import member
from .store import audit


def _metadata(row):
    return {key: row[key] for key in ("app_id", "version", "hash", "created", "created_by")}


def _author_condition(condition):
    kind = condition["kind"]
    if kind == "compare":
        return {key: condition[key] for key in ("fact", "op", "value")}
    if kind == "not":
        return {"not": _author_condition(condition["item"])}
    if kind in ("all", "any"):
        return {kind: [_author_condition(item) for item in condition["items"]]}
    raise Invalid("Saved rule condition is unavailable")


def _public(row):
    if row is None:
        return None
    try:
        normalized = json.loads(row["document"])
        if digest(normalized) != row["hash"]:
            raise Invalid("Saved rule fingerprint does not match its contents")
        rules = []
        for rule in normalized["rules"]:
            author = {key: rule[key] for key in ("id", "enabled", "priority", "cooldown", "expires_at")}
            author["when"] = _author_condition(rule["when"])
            author["then"] = {"propose": {key: rule[key] for key in ("action", "tool", "reason")},
                              "requires": rule["requires"]}
            rules.append(author)
        document = {**normalized, "rules": rules}
        if digest(validate(document)) != row["hash"]:
            raise Invalid("Saved rule cannot be reproduced")
    except (KeyError, ValueError, TypeError, RecursionError) as error:
        raise Invalid("Saved rule version cannot be verified") from error
    return {**_metadata(row), "document": document}


def version_in_snapshot(db, app_id, reference):
    """Load an exact version in the caller's authenticated app snapshot."""
    if not isinstance(reference, dict) or set(reference) != {"version", "hash"}:
        raise Invalid("Choose a saved version and its exact fingerprint")
    version, fingerprint = reference["version"], reference["hash"]
    if type(version) is not int or not 1 <= version < 2**63:
        raise Invalid("Choose a positive saved version number")
    if not isinstance(fingerprint, str) or not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
        raise Invalid("Choose a valid saved rule fingerprint")
    row = db.execute("SELECT * FROM automation_rule_sets WHERE app_id=? AND version=?",
                     (app_id, version)).fetchone()
    if row is None or row["hash"] != fingerprint:
        raise Invalid("Saved rule version or fingerprint is unavailable for this app")
    return _public(row)


def version_index(store, app_id, principal, before=None):
    """Return up to 25 immutable versions without copying their documents."""
    if before is not None and (type(before) is not int or not 1 <= before < 2**63):
        raise Invalid("Choose a valid rule version cursor")
    with connection(store.path) as db:
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        member(db, app_id, principal, "OWNER")
        if before is None:
            rows = db.execute("""SELECT app_id,version,hash,created,created_by FROM automation_rule_sets
                WHERE app_id=? ORDER BY version DESC LIMIT 26""", (app_id,)).fetchall()
        else:
            rows = db.execute("""SELECT app_id,version,hash,created,created_by FROM automation_rule_sets
                WHERE app_id=? AND version<? ORDER BY version DESC LIMIT 26""", (app_id,before)).fetchall()
    return {"app_id": app_id, "versions": [_metadata(row) for row in rows[:25]],
            "next_before": rows[24]["version"] if len(rows) > 25 else None}


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
