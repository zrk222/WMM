"""Owner-assigned search plan work, pulled through the existing scoped operation gateway."""

import json
import sqlite3
from typing import Any

from .agent_grants import current
from .common import Invalid, canonical, digest, now
from .db import connection
from .operation_authority import PROTECTED, check, protected, utc
from .store import Store

OPERATION = "search.plan.execute"


def _eligible(db: sqlite3.Connection, app_id: str) -> list[sqlite3.Row]:
    result = []
    for grant in db.execute("SELECT * FROM agent_grants WHERE app_id=? ORDER BY agent_id,id", (app_id,)):
        try:
            current(db, grant, {"app_id": app_id, "operation": OPERATION}, utc())
        except (Invalid, PermissionError):
            continue
        result.append(grant)
    return result


def _public(row: sqlite3.Row) -> dict[str, Any]:
    result = json.loads(row["result"]) if row["result"] is not None else None
    if row["status"] == "ASSIGNED":
        if result is not None or row["receipt_sha256"] is not None:
            raise Invalid("Unexpected result on an unexecuted assignment")
    else:
        keys = ("app_id", "review_hash", "action_id", "grant_id", "grant_version", "agent_id", "status")
        if not result or digest(result) != row["receipt_sha256"] or any(result[k] != row[k] for k in keys):
            raise Invalid("Assigned step result failed its integrity check")
    return dict(
        action_id=row["action_id"],
        review_hash=row["review_hash"],
        grant_id=row["grant_id"],
        agent_id=row["agent_id"],
        status=row["status"],
        receipt_sha256=row["receipt_sha256"],
        deliverable=result["deliverable"] if result else None,
    )


def team_view(db: sqlite3.Connection, app_id: str, review_hash: str) -> dict[str, Any]:
    agents = [dict(grant_id=r["id"], agent_id=r["agent_id"]) for r in _eligible(db, app_id)]
    return dict(team_agents=agents, assignments=assignments_for_plan(db, app_id, review_hash))


def assignments_for_plan(db: sqlite3.Connection, app_id: str, review_hash: str) -> dict[str, Any]:
    rows = db.execute("SELECT * FROM search_team_assignments WHERE app_id=? AND review_hash=?", (app_id, review_hash))
    return {r["action_id"]: _public(r) for r in rows}


def assign(db: sqlite3.Connection, bound: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    """Called immediately after the exact owner-authorized action save, under its writer lock."""
    context = PROTECTED.get()
    if not db.in_transaction or context is None or "grant_id" in context:
        raise PermissionError("Assigning plan work requires a current owner")
    envelope = json.loads(str(context["envelope"]))
    receipt = bound["receipt"]
    app_id = bound["app_id"]
    if envelope["operation"] != "apple.analytics.owner.search-review-assign" or envelope["app_id"] != app_id:
        raise PermissionError("Use the selected app's owner assignment operation")
    principal = check(db, context)
    grant = next((r for r in _eligible(db, app_id) if r["id"] == body["grant_id"]), None)
    if grant is None:
        raise Invalid("Choose a current app agent grant with search.plan.execute and remaining calls")
    key = (app_id, bound["review_hash"], receipt["action_id"])
    row = db.execute(
        "SELECT * FROM search_team_assignments WHERE app_id=? AND review_hash=? AND action_id=?", key
    ).fetchone()
    if row is None:
        db.execute(
            "INSERT INTO search_team_assignments(app_id,review_hash,action_id,grant_id,grant_version,agent_id,"
            "assigned_by,status) VALUES(?,?,?,?,?,?,?,'ASSIGNED')",
            (*key, grant["id"], grant["version"], grant["agent_id"], principal),
        )
    elif row["grant_id"] != grant["id"] or row["grant_version"] != grant["version"]:
        if row["status"] != "ASSIGNED":
            raise Invalid("An executed assignment already has a permanent receipt")
        db.execute(
            "UPDATE search_team_assignments SET grant_id=?,grant_version=?,agent_id=?,assigned_by=? "
            "WHERE app_id=? AND review_hash=? AND action_id=?",
            (grant["id"], grant["version"], grant["agent_id"], principal, *key),
        )
    return dict(bound, **team_view(db, app_id, bound["review_hash"]))


def run_assigned(store: Store, envelope: dict[str, Any]) -> dict[str, Any]:
    with protected(store, envelope):
        return _run(store, envelope)


def _run(store: Store, envelope: dict[str, Any]) -> dict[str, Any]:
    from .apple_metrics_http import search_review_snapshot
    from .search_store_actions import bind_review
    from .search_team_analysis import produce

    context = PROTECTED.get()
    if context is None or "grant_id" not in context or context["envelope"] != canonical(envelope):
        raise PermissionError("Only the exact assigned agent may execute this operation")
    body = envelope["input"]
    app_id = envelope["app_id"]
    scope = (app_id, context["grant_id"], context["grant_version"], context["agent_id"])
    with connection(store.path, write=True) as db:
        check(db, context)
        query = "SELECT * FROM search_team_assignments WHERE app_id=? AND grant_id=? AND grant_version=? AND agent_id=?"
        if not body:
            rows = db.execute(query + " ORDER BY review_hash,action_id", scope)
            return {"app_id": app_id, "assignments": [_public(r) for r in rows]}
        if set(body) != {"review_hash", "action_id"} or not all(isinstance(v, str) for v in body.values()):
            raise Invalid("Choose the exact review hash and assigned action ID")
        key = (body["review_hash"], body["action_id"])
        row = db.execute(query + " AND review_hash=? AND action_id=?", (*scope, *key)).fetchone()
        if row is None:
            raise PermissionError("This action is not assigned to this app and grant")
        assignment = _public(row)
        if assignment["status"] != "ASSIGNED":
            return dict(app_id=app_id, **body, assignment=assignment)
        task, checksum = db.execute(
            "SELECT data,hash FROM search_store_action_receipts WHERE app_id=? AND review_hash=? AND action_id=?",
            (app_id, *key),
        ).fetchone()
        task = json.loads(task)
        if digest(task) != checksum:
            raise Invalid("Assigned action failed its saved receipt check")
        snapshot, expected = search_review_snapshot(db, app_id, task)
        review = bind_review(db, snapshot, expected, {})["search_review"]
        if review["review_hash"] != key[0]:
            raise Invalid("Source evidence changed. Review and assign a current plan.")
        dependencies = {}
        for dep in task["action"]["depends_on"]:
            prior = review["assignments"].get(dep)
            if not prior or prior["status"] != "COMPLETED":
                raise Invalid("Waiting for completed prerequisite " + dep)
            dependencies[dep] = prior["receipt_sha256"]
        status, deliverable = produce(snapshot, task, {dep: review["assignments"][dep] for dep in dependencies})
        result = dict(
            app_id=app_id,
            review_hash=key[0],
            action_id=key[1],
            grant_id=row["grant_id"],
            grant_version=row["grant_version"],
            agent_id=row["agent_id"],
            status=status,
            task_sha256=checksum,
            dependencies=dependencies,
            deliverable=deliverable,
            created=now(),
        )
        db.execute(
            "UPDATE search_team_assignments SET status=?,result=?,receipt_sha256=? "
            "WHERE app_id=? AND review_hash=? AND action_id=?",
            (status, canonical(result), digest(result), app_id, *key),
        )
        return dict(
            app_id=app_id,
            **body,
            assignment=dict(assignment, status=status, deliverable=deliverable, receipt_sha256=digest(result)),
        )
