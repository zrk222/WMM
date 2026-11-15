"""Immutable owner-selected local write review policy, separate from bearer secrets."""

import json
import sqlite3
from typing import cast

from .common import Invalid, canonical
from .operation_catalog import OPERATIONS


def validate(body: object) -> list[str]:
    """Select only a unique subset of this grant's fixed local writes."""
    if not isinstance(body, dict):
        raise Invalid("Review operations must be a subset of granted operations")
    body = cast(dict[str, object], body)
    selected = body.get("review_operations", [])
    if not isinstance(selected, list):
        raise Invalid("Review operations must be a subset of granted operations")
    if selected:
        granted = body.get("operations")
        if not isinstance(granted, list) or any(not isinstance(name, str) or name not in granted for name in selected):
            raise Invalid("Review operations must be a subset of granted operations")
    if len(selected) != len(set(selected)) or any(OPERATIONS[name]["method"] != "POST" for name in selected):
        raise Invalid("Review policy accepts unique local write operations only")
    return sorted(cast(list[str], selected))


def save(db: sqlite3.Connection, grant_id: str, body: object) -> None:
    """Persist once in the same transaction as credential issuance."""
    db.execute("INSERT INTO agent_grant_review_policy VALUES(?,?)", (grant_id, canonical(validate(body))))


def operations(db: sqlite3.Connection, grant_id: str) -> list[str]:
    """Legacy grants have no required review operations; imports cannot create policy."""
    row = db.execute("SELECT operations FROM agent_grant_review_policy WHERE grant_id=?", (grant_id,)).fetchone()
    return cast(list[str], json.loads(row["operations"])) if row else []


def ordinary_dispatch(db: sqlite3.Connection, grant_id: str, operation: str) -> None:
    """An ordinary bearer call may never bypass the owner's required checkpoint."""
    if operation in operations(db, grant_id):
        raise PermissionError("Independent human review required; prepare and resume an exact agent review request")
