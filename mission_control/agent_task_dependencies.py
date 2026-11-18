"""Prerequisite receipts for named continuations of existing worker jobs."""

import json
from sqlite3 import Connection, Row
from typing import Any

from .common import Invalid, digest

UNVERIFIED_RESULTS = frozenset(
    {
        "BLOCKED",
        "CANCELLED",
        "FAILED",
        "NEEDS_EXTERNAL_VERIFICATION",
        "RECONCILE_REQUIRED",
        "REJECTED",
        "UNCONFIRMED",
        "UNCERTAIN",
        "UNKNOWN",
    }
)


def _unverified_result(result: dict) -> bool:
    for signal in (result.get("status"), result.get("external_execution")):
        if isinstance(signal, str) and (
            signal in UNVERIFIED_RESULTS
            or signal.startswith(("UNKNOWN_", "RECONCILE_"))
            or signal.endswith(("_UNKNOWN", "_UNCONFIRMED", "_MAY_HAVE_OCCURRED"))
        ):
            return True
    return bool(result.get("error"))


def job_fingerprint(row: Row) -> str:
    return digest({key: row[key] for key in ("id", "app_id", "action", "data", "request_key", "created")})


def bind_dependencies(db: Connection, app_id: str, job_id: str, value: object) -> list[dict[str, str]]:
    if not isinstance(value, list) or len(value) > 20 or any(not isinstance(item, str) for item in value):
        raise Invalid("Choose up to 20 prerequisite jobs")
    if job_id in value or len(value) != len(set(value)):
        raise Invalid("Choose distinct prerequisite jobs other than this task")
    bindings = []
    for identity in sorted(value):
        row = db.execute("SELECT * FROM jobs WHERE app_id=? AND id=?", (app_id, identity)).fetchone()
        if row is None:
            raise Invalid("Each prerequisite must belong to this app")
        bindings.append(dict(job_id=identity, job_hash=job_fingerprint(row)))
    return bindings


def dependency_receipts(db: Connection, app_id: str, bindings: list[dict[str, str]]) -> list[dict[str, Any]]:
    receipts = []
    for binding in bindings:
        row = db.execute("SELECT * FROM jobs WHERE app_id=? AND id=?", (app_id, binding["job_id"])).fetchone()
        result_hash = None
        if row is None or job_fingerprint(row) != binding["job_hash"]:
            status = "CHANGED"
        else:
            status = row["status"]
            if status == "SUCCEEDED":
                try:
                    result = json.loads(row["result"] or "null")
                except (TypeError, ValueError):
                    result = None
                if isinstance(result, dict) and result and _unverified_result(result):
                    status = "UNVERIFIED_RESULT"
                elif isinstance(result, dict) and result:
                    result_hash = digest(result)
                else:
                    status = "MISSING_RESULT"
        receipts.append(dict(job_id=binding["job_id"], status=status, result_hash=result_hash))
    return receipts


def dependency_status(receipts: list[dict[str, Any]]) -> str | None:
    if any(item["status"] not in ("SUCCEEDED", "RUNNING", "QUEUED") for item in receipts):
        return "DEPENDENCY_NEEDS_REVIEW"
    if any(item["result_hash"] is None for item in receipts):
        return "WAITING_FOR_DEPENDENCIES"
    return None
