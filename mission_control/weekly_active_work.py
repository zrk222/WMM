"""Bounded owner-private active jobs and expiring authority for the weekly inbox."""

from __future__ import annotations

import json
from datetime import timedelta
from typing import TYPE_CHECKING

from .common import Invalid, digest, iso_time, now

if TYPE_CHECKING:
    from .store import Store

EXPIRY_HORIZON = timedelta(days=7)


def _soon(value, current):
    """Return a future expiry inside the review horizon; anything else stays absent."""
    try:
        at = iso_time(value)
    except (Invalid, OverflowError):
        return None
    return at if current < at <= current + EXPIRY_HORIZON else None


def _work(app, kind, identity, state, title, reason, next_action, route, updated, priority, expires_at=None):
    """Describe one current local work item without any stored payload."""
    source = dict(status=state, updated=updated)
    if expires_at is not None:
        source["expires"] = expires_at
    return dict(
        id=digest([app["id"], kind, identity]),
        app_id=app["id"],
        app_name=app["data"]["name"],
        kind=kind,
        state=state,
        title=title,
        reason=reason,
        next_action=next_action,
        resolution_route=route,
        updated_at=updated,
        expires_at=expires_at,
        priority=priority,
        source_receipt=dict(
            app_id=app["id"],
            manifest_version=app["version"],
            source_hash=digest(source),
            observed_at=now(),
            source_updated_at=updated,
        ),
    )


def _active_work_items(db, app, tables):
    """Project active jobs, saved sequences and approvals expiring within seven days."""
    current = iso_time(now())
    items = []
    for row in db.execute(
        "SELECT id,action,status,attempts,created,updated FROM jobs "
        "WHERE app_id=? AND status IN ('QUEUED','RUNNING') ORDER BY updated DESC,id DESC LIMIT 50",
        (app["id"],),
    ):
        items.append(
            _work(
                app,
                "JOB",
                row["id"],
                row["status"],
                "Run in progress" if row["status"] == "RUNNING" else "Run queued",
                "{} · attempt {} · queued {}".format(row["action"], row["attempts"], row["created"]),
                "Inspect the saved run; a queued or running job is not a completed result.",
                "activity",
                row["updated"],
                3,
            )
        )
    if "campaign_sequences" in tables:
        for row in db.execute(
            "SELECT id,state,updated FROM campaign_sequences "
            "WHERE app_id=? AND state IN ('QUEUED','WAITING') ORDER BY updated DESC,id DESC LIMIT 50",
            (app["id"],),
        ):
            items.append(
                _work(
                    app,
                    "SEQUENCE",
                    row["id"],
                    row["state"],
                    "Saved sequence still active",
                    "Sequence state {} · updated {}".format(row["state"], row["updated"]),
                    "Inspect the saved sequence checkpoints; a waiting sequence is not completed.",
                    "activity",
                    row["updated"],
                    3,
                )
            )
    if "agent_grants" in tables:
        for row in db.execute(
            "SELECT id,expires,updated FROM agent_grants "
            "WHERE app_id=? AND status='ACTIVE' ORDER BY expires,id LIMIT 50",
            (app["id"],),
        ):
            at = _soon(row["expires"], current)
            if at is not None:
                items.append(
                    _work(
                        app,
                        "AGENT_GRANT",
                        row["id"],
                        "EXPIRING",
                        "Agent grant expires soon",
                        "Grant {} expires {}".format(row["id"], at.isoformat()),
                        "Renew or revoke the current owner grant before it expires.",
                        "agents",
                        row["updated"],
                        2,
                        at.isoformat(),
                    )
                )
    if "automation_policies" in tables:
        for row in db.execute(
            "SELECT id,summary,updated FROM automation_policies "
            "WHERE app_id=? AND status='ACTIVE' ORDER BY updated DESC,id LIMIT 50",
            (app["id"],),
        ):
            try:
                summary = json.loads(row["summary"])
            except (TypeError, ValueError):
                continue
            at = _soon(summary.get("stops_at") if isinstance(summary, dict) else None, current)
            if at is not None:
                items.append(
                    _work(
                        app,
                        "AUTOMATION",
                        row["id"],
                        "EXPIRING",
                        "Standing approval expires soon",
                        "Policy {} stops at {}".format(row["id"], at.isoformat()),
                        "Review the standing scope and renew only if the owner still approves it.",
                        "workspace",
                        row["updated"],
                        2,
                        at.isoformat(),
                    )
                )
    return sorted(
        {item["id"]: item for item in items}.values(), key=lambda item: (item["priority"], item["kind"], item["id"])
    )


def active_work(store: Store, app: dict, user: object) -> list[dict]:
    """Read only bounded owner-scoped work; anonymous, maker and checker callers see none."""
    principal = trusted_principal(user)
    if principal is None or not hasattr(store, "path"):
        return []
    from .db import connection
    from .review_access import member

    with connection(store.path) as db:
        db.execute("BEGIN")
        try:
            role = member(db, app["id"], principal)["role"]
        except PermissionError:
            return []
        if role != "OWNER":
            return []
        tables = {row["name"] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        return _active_work_items(db, app, tables)


def trusted_principal(user: object) -> str | None:
    """Only the server-supplied authenticated session principal enables private reads."""
    if not isinstance(user, dict):
        return None
    value = user.get("principal")
    return value if isinstance(value, str) and 1 <= len(value) <= 200 else None
