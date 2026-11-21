"""Private immutable marketing evidence. No credentials or provider effects."""

import json
from sqlite3 import Connection
from typing import Any

from .common import Invalid, canonical, digest, now


def decoded(row: Any) -> dict[str, Any]:
    """Validate saved bytes before using a local evidence record."""
    if row is None:
        raise Invalid("Marketing review evidence is unavailable for this owner")
    data = json.loads(row["data"])
    if not isinstance(data, dict) or digest(data) != row["hash"]:
        raise Invalid("Marketing review evidence integrity changed")
    return dict(id=row["id"], hash=row["hash"], created=row["created"], data=data)


def save(db: Connection, app: str, owner: str, kind: str, identity: str, scope: str, data: dict) -> dict:
    """Replay exact local requests only; conflicting identities never overwrite."""
    old = db.execute(
        "SELECT * FROM marketing_review_evidence WHERE app_id=? AND owner=? AND kind=? AND id=?",
        (app, owner, kind, identity),
    ).fetchone()
    if old:
        result = decoded(old)
        if result["data"] != data or old["scope_id"] != scope:
            raise Invalid("Marketing evidence identity already has different inputs")
        return result
    stamp = now()
    db.execute(
        "INSERT INTO marketing_review_evidence VALUES(?,?,?,?,?,?,?,?)",
        (app, owner, kind, identity, scope, canonical(data), digest(data), stamp),
    )
    return dict(id=identity, hash=digest(data), created=stamp, data=data)


def rows(db: Connection, app: str, owner: str, scope: str, kind: str) -> list[dict]:
    """Read exact owned scope, keeping other apps and owners private."""
    return [
        decoded(row)
        for row in db.execute(
            "SELECT * FROM marketing_review_evidence WHERE app_id=? AND owner=? AND scope_id=? AND kind=? ORDER BY created,id",
            (app, owner, scope, kind),
        )
    ]
