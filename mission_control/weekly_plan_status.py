"""Project saved monitor and report job exceptions."""

import json
from collections.abc import Callable
from sqlite3 import Connection, Row

from .common import Invalid, iso_time


def saved(raw: object) -> dict:
    if not isinstance(raw, str) or len(raw) > 65536:
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def owned_job(db: Connection, app_id: str, row: Row, tool: str) -> Row | None:
    if not row["last_job"]:
        return None
    job = db.execute(
        "SELECT id,app_id,action,status,data,updated FROM jobs WHERE id=? AND app_id=?",
        (row["last_job"], app_id),
    ).fetchone()
    if job is None:
        return None
    expected = "campaign_monitor" if tool == "monitor" else "campaign_owner_report"
    data = saved(job["data"])
    key = "monitor_id" if tool == "monitor" else "plan_id"
    if (
        job["status"]
        not in {
            "QUEUED",
            "RUNNING",
            "SUCCEEDED",
            "FAILED",
            "BLOCKED",
            "UNKNOWN",
            "CANCELLED",
            "INTERRUPTED",
        }
        or job["action"] != expected
        or data.get(key) != row["id"]
        or data.get("summary_hash") != row["summary_hash"]
    ):
        return None
    return job


def plan_issue(
    row: Row, proposal: dict[str, object], job: Row | None, tool: str, clock: Callable[[], str]
) -> tuple[str, str, str, str] | None:
    name = "Campaign monitor" if tool == "monitor" else "Private report plan"
    repair = (
        "Open the exact monitor controls and inspect its last observation before approving replacement work."
        if tool == "monitor"
        else "Open private reports, inspect the failed snapshot job and review current source bindings before another plan."
    )
    limit = proposal.get("max_runs" if tool == "monitor" else "max_reports")
    finished = type(limit) is int and row["runs"] >= limit and (job is None or job["status"] == "SUCCEEDED")
    if finished:
        return None
    if row["status"] == "BLOCKED" or (job and job["status"] in ("FAILED", "BLOCKED", "UNKNOWN")):
        return (
            "BLOCKED",
            name + " needs a decision",
            "Saved local work stopped at a validation, authority or execution boundary.",
            repair,
        )
    if row["status"] != "ACTIVE":
        return None
    try:
        expired = iso_time(proposal["expires_at"]) <= iso_time(clock())
    except (Invalid, KeyError, TypeError):
        return (
            "INTEGRITY_REVIEW_REQUIRED",
            name + " needs review",
            "Saved expiry could not be verified.",
            repair,
        )
    limit = proposal.get("max_runs" if tool == "monitor" else "max_reports")
    if expired and type(limit) is int and row["runs"] < limit:
        return (
            "EXPIRED",
            name + " expired with unfinished planned work",
            "The finite approval ended before all planned runs were dispatched.",
            repair,
        )
    return None
