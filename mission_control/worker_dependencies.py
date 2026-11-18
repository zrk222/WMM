"""Immutable prerequisite admission and claim checks for the shared job queue."""

import json
from typing import cast

from .agent_task_dependencies import bind_dependencies, dependency_receipts, dependency_status
from .common import Invalid, canonical, digest, now, required

READY = "DEPENDENCIES_READY"
REVIEW = "DEPENDENCY_NEEDS_REVIEW"
REPAIR = "Inspect the saved prerequisite and reconcile uncertain effects before admitting a new job."


def _record(db, job_id):
    return db.execute("SELECT * FROM worker_job_dependencies WHERE job_id=?", (job_id,)).fetchone()


def _bindings(row):
    bindings = json.loads(row["bindings"])
    if digest(bindings) != row["bindings_sha256"]:
        raise Invalid("Saved prerequisite bindings failed their integrity check")
    return bindings


def _owner(db, job, requested):
    from .operation_authority import PROTECTED, check

    context = PROTECTED.get()
    if context is None or "grant_id" in context:
        raise PermissionError("Prerequisite admission requires the current app owner")
    envelope = json.loads(cast(str, context["envelope"]))
    admitted = envelope["input"]
    if (
        envelope["app_id"] != job["app_id"]
        or envelope["operation"] != "job.dependencies.admit"
        or required(admitted.get("request_key"), "Request key", 120) != job["request_key"]
        or admitted.get("action") != job["action"]
        or admitted.get("depends_on_jobs") != requested
    ):
        raise PermissionError("Use the owner job admission for this app")
    return check(db, context), context["role_version"]


def _admit(db, job, requested, *, inserted):
    record = None if inserted else _record(db, job["id"])
    if requested is None:
        if record is not None:
            raise Invalid("Request key already used for different job prerequisites")
        return
    if job["action"] not in ("pipeline", "sync"):
        raise Invalid("Only a local pipeline or supported read may name prerequisites")
    owner, version = _owner(db, job, requested)
    # Bind only previously admitted jobs. Replay cannot add or remove edges.
    bindings = bind_dependencies(db, job["app_id"], job["id"], requested)
    if not inserted:
        existing = _bindings(record) if record else []
        if bindings != existing:
            raise Invalid("Request key already used for different job prerequisites")
    elif bindings:
        db.execute(
            "INSERT INTO worker_job_dependencies(job_id,owner,owner_version,bindings,bindings_sha256) "
            "VALUES(?,?,?,?,?)",
            (job["id"], owner, version, canonical(bindings), digest(bindings)),
        )


def _read(db, job, record):
    """Verify current input bindings and separate result receipts from prerequisites."""
    try:
        bindings = _bindings(record)
        if record["claimed_receipts"] is not None:
            claimed = json.loads(record["claimed_receipts"])
            if digest(claimed) != record["claimed_receipts_sha256"]:
                raise Invalid("Saved prerequisite receipts failed their integrity check")
        else:
            claimed = None
        receipts = dependency_receipts(db, job["app_id"], bindings)
    except (Invalid, ValueError, TypeError, KeyError):
        return [], [{"status": "BINDING_INVALID", "result_hash": None}], REVIEW
    status = dependency_status(receipts)
    if claimed is not None and claimed != receipts:
        receipts.append({"status": "CLAIMED_RECEIPTS_CHANGED", "result_hash": None})
        return bindings, receipts, REVIEW
    return bindings, receipts, status


def _before_claim(db, job, record):
    if record is None:
        return True
    from .review_access import exact_role

    _, receipts, status = _read(db, job, record)
    try:
        exact_role(db, job["app_id"], record["owner"], record["owner_version"], "OWNER")
    except (Invalid, PermissionError):
        status = REVIEW
        receipts.append({"status": "OWNER_SCOPE_CHANGED", "result_hash": None})
    if status == REVIEW:
        from .store import audit

        result = {"status": REVIEW, "dependency_receipts": receipts, "next_action": REPAIR}
        db.execute(
            "UPDATE jobs SET status='BLOCKED',lease=0,result=?,updated=? WHERE id=?",
            (canonical(result), now(), job["id"]),
        )
        audit(
            db, job["app_id"], "job.blocked", {"id": job["id"], "action": job["action"], "result_hash": digest(result)}
        )
        return False
    if status is not None:
        return False
    if record["claimed_receipts"] is None:
        db.execute(
            "UPDATE worker_job_dependencies SET claimed_receipts=?,claimed_receipts_sha256=? WHERE job_id=?",
            (canonical(receipts), digest(receipts), job["id"]),
        )
    return True


def _view(db, job, record):
    if record is None:
        return job
    bindings, receipts, status = _read(db, job, record)
    if job["status"] == "BLOCKED" and (job["result"] or {}).get("status") == REVIEW:
        status = REVIEW
        receipts = job["result"]["dependency_receipts"]
    return {
        **job,
        "depends_on_jobs": [binding["job_id"] for binding in bindings],
        "dependency_status": status or READY,
        "dependency_receipts": receipts,
    }
