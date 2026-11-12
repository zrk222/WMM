"""Durable opt-in local analysis; provider execution is outside this scheduler."""

from datetime import timedelta
import time
from .common import Invalid, canonical, digest, iso_time, now, safe_data, uid
from .db import connection
from .experiments import lookup

STATUSES = {"ENABLED", "PAUSED", "BLOCKED", "RESTORED_PAUSED", "CANCELLED", "EXPIRED", "EXHAUSTED"}


def configuration(body):
    """Require explicit enable, bounded cadence and optimistic configuration version."""
    safe_data(body)
    base = {"enabled", "interval_hours", "version"}
    if not base.issubset(body) or type(body["enabled"]) is not bool:
        raise Invalid("Choose enabled, interval and current version")
    expected = base | ({"manifest_version", "expires_at", "max_observations"} if body["enabled"] else set())
    if set(body) != expected:
        raise Invalid("Use the exact schedule authorization fields")
    if type(body["interval_hours"]) is not int or not 1 <= body["interval_hours"] <= 168:
        raise Invalid("Choose an interval from 1 to 168 whole hours")
    if body["version"] is not None and type(body["version"]) is not int:
        raise Invalid("Invalid schedule version")
    if body["enabled"]:
        validate_enable(body)
    return body


def validate_enable(body):
    """Validate the finite authorization supplied for a new enabled schedule."""
    if type(body["manifest_version"]) is not int or body["manifest_version"] < 1:
        raise Invalid("Use the current app version")
    if type(body["max_observations"]) is not int or not 1 <= body["max_observations"] <= 30:
        raise Invalid("Choose 1 to 30 observations")
    iso_time(body["expires_at"])


def schedule_audit(db, app_id, experiment_id, operation, detail):
    """Retain public schedule evidence separately from experiment definitions."""
    db.execute(
        "INSERT INTO audit(app_id,action,detail,created) VALUES(?,?,?,?)",
        (app_id, "schedule." + operation, canonical(dict(detail, experiment_id=experiment_id)), now()),
    )


def pause_queued(db, row):
    """Cancel only this schedule's queued job; running assessment may finish."""
    if not row or not row["last_job"]:
        return
    db.execute(
        "UPDATE jobs SET status='CANCELLED',updated=? WHERE app_id=? AND id=? AND status='QUEUED'",
        (now(), row["app_id"], row["last_job"]),
    )


def public_limit(limit, row):
    """Show finite capacity without exposing owner identity or credentials."""
    if not limit or limit["schedule_version"] != row["version"]:
        return None
    return {
        "expires_at": limit["expires"],
        "max_observations": limit["max_observations"],
        "reserved": limit["reserved"],
        "remaining": max(0, limit["max_observations"] - limit["reserved"]),
    }


def live_limit(db, row, current):
    """Reject legacy, changed-owner, app or experiment authority inside a transaction."""
    from .review_access import exact_role

    limit = db.execute(
        "SELECT * FROM experiment_schedule_limits WHERE app_id=? AND experiment_id=?",
        (row["app_id"], row["experiment_id"]),
    ).fetchone()
    if not limit or limit["schedule_version"] != row["version"]:
        raise Invalid("Fresh finite schedule authorization is required")
    try:
        exact_role(db, row["app_id"], limit["owner"], limit["owner_version"], "OWNER")
    except (Invalid, PermissionError) as exc:
        raise Invalid("Schedule owner authorization changed") from exc
    app = db.execute("SELECT version FROM apps WHERE id=?", (row["app_id"],)).fetchone()
    if not app or app["version"] != limit["app_version"] or current["hash"] != limit["experiment_hash"]:
        raise Invalid("Scheduled app or experiment changed")
    validate_limit(limit)
    iso_time(limit["expires"])
    return limit


def validate_limit(limit):
    """Reject incoherent or exhausted reservation metadata before use."""
    if (
        type(limit["max_observations"]) is not int
        or not 1 <= limit["max_observations"] <= 30
        or type(limit["reserved"]) is not int
        or not 0 <= limit["reserved"] <= limit["max_observations"]
    ):
        raise Invalid("Invalid finite observation limit")


def approved_expiry(db, app_id, body, stamp, due):
    """Bind a new enabled schedule to the current app and a finite horizon."""
    from .automation_policy import check_manifest_version

    check_manifest_version(db, app_id, body["manifest_version"])
    expiry = iso_time(body["expires_at"])
    if not iso_time(stamp) < expiry <= iso_time(stamp) + timedelta(days=90) or expiry <= iso_time(due):
        raise Invalid("Expiry must follow the first due time and be within 90 days")
    return expiry


def saved_detail(body, version, due, owner, role, experiment, expiry):
    """Construct a truthful audit record for the owner's saved authorization."""
    detail = {"enabled": body["enabled"], "version": version, "next_due": due, "owner": owner}
    if body["enabled"]:
        detail.update(
            owner_version=role["version"],
            manifest_version=body["manifest_version"],
            experiment_hash=experiment["hash"],
            expires_at=expiry.isoformat(),
            max_observations=body["max_observations"],
        )
    return detail


class Schedules:
    def __init__(self, store):
        self.store = store

    def list(self, app_id):
        """Return persistent scoped public settings and exact latest job status."""
        self.store.app(app_id)
        with connection(self.store.path) as db:
            rows = [
                dict(r)
                for r in db.execute(
                    "SELECT * FROM experiment_schedules WHERE app_id=? ORDER BY experiment_id", (app_id,)
                )
            ]
            for row in rows:
                row["enabled"] = bool(row["enabled"])
                job = db.execute(
                    "SELECT status FROM jobs WHERE app_id=? AND id=?", (app_id, row["last_job"])
                ).fetchone()
                row["last_job_status"] = job["status"] if job else None
                limit = db.execute(
                    "SELECT * FROM experiment_schedule_limits WHERE app_id=? AND experiment_id=?",
                    (app_id, row["experiment_id"]),
                ).fetchone()
                row["finite_limit"] = public_limit(limit, row)
            return rows

    def save(self, app_id, experiment_id, body, *, owner=None):
        """Explicitly enable/resume or pause an observed test without external effects."""
        self.store.app(app_id)
        body = configuration(body)
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            from .review_access import member

            if not isinstance(owner, str):
                raise PermissionError("A freshly authenticated app owner is required")
            role = member(db, app_id, owner, "OWNER")
            experiment = lookup(db, app_id, experiment_id)
            if experiment["state"] in ("PLANNED", "CANCELLED"):
                raise Invalid("Record exposure first; cancelled tests cannot be scheduled")
            old = db.execute(
                "SELECT * FROM experiment_schedules WHERE app_id=? AND experiment_id=?", (app_id, experiment_id)
            ).fetchone()
            expected = old["version"] if old else None
            if body["version"] != expected:
                raise Invalid("Schedule changed; reload before saving")
            pause_queued(db, old)
            stamp = now()
            due = max(iso_time(stamp), iso_time(experiment["data"]["analysis_at"])).isoformat()
            expiry = approved_expiry(db, app_id, body, stamp, due) if body["enabled"] else None
            status = "ENABLED" if body["enabled"] else "PAUSED"
            version = (expected or 0) + 1
            last_job = existing_job(db, old)
            db.execute(
                "INSERT OR REPLACE INTO experiment_schedules VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    app_id,
                    experiment_id,
                    int(body["enabled"]),
                    body["interval_hours"],
                    version,
                    due,
                    last_job,
                    last_job,
                    0,
                    status,
                    stamp,
                ),
            )
            if body["enabled"]:
                db.execute(
                    "INSERT OR REPLACE INTO experiment_schedule_limits VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (
                        app_id,
                        experiment_id,
                        version,
                        owner,
                        role["version"],
                        body["manifest_version"],
                        experiment["hash"],
                        expiry.isoformat(),
                        body["max_observations"],
                        0,
                    ),
                )
            schedule_audit(
                db, app_id, experiment_id, "saved", saved_detail(body, version, due, owner, role, experiment, expiry)
            )
        return next(s for s in self.list(app_id) if s["experiment_id"] == experiment_id)

    def tick(self, app_id=None, experiment_id=None):
        """Reconcile and atomically dispatch at most one pending run per active test."""
        if (app_id is None) != (experiment_id is None):
            raise Invalid("Choose an exact app and experiment")
        count = 0
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            if app_id is None:
                rows = db.execute(
                    "SELECT * FROM experiment_schedules WHERE enabled=1 ORDER BY next_due LIMIT 100"
                ).fetchall()
            else:
                rows = db.execute(
                    "SELECT * FROM experiment_schedules WHERE enabled=1 AND app_id=? AND experiment_id=?",
                    (app_id, experiment_id),
                ).fetchall()
            for row in rows:
                count += tick_schedule(db, row)
        return count

    def run_foreground(self, app_id, experiment_id, *, owner):
        """Execute only this owner's reserved local observation while the native host is active."""
        from .worker import json_job

        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            foreground_owner(db, app_id, experiment_id, owner)
        self.tick(app_id, experiment_id)
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM experiment_schedules WHERE app_id=? AND experiment_id=?", (app_id, experiment_id)
            ).fetchone()
            if not row or not row["enabled"] or not row["last_job"]:
                return {"status": row["status"] if row else "NOT_SCHEDULED", "job_id": None}
            foreground_owner(db, app_id, experiment_id, owner)
            job = db.execute(
                "SELECT * FROM jobs WHERE app_id=? AND id=? AND action='experiment'", (app_id, row["last_job"])
            ).fetchone()
            early = foreground_lease(db, job)
            if early:
                return early
            claimed = json_job(job)
            claimed["attempts"] += 1
        return finish_foreground(self.store, app_id, experiment_id, claimed)


def tick_schedule(db, row):
    """Reconcile one authorized schedule and reserve at most one observation."""
    current = lookup(db, row["app_id"], row["experiment_id"])
    if current["state"] == "CANCELLED":
        disable(db, row, "CANCELLED")
        return 0
    try:
        limit = live_limit(db, row, current)
    except Invalid:
        disable(db, row, "BLOCKED")
        return 0
    if iso_time(limit["expires"]) <= iso_time(now()):
        disable(db, row, "EXPIRED")
        return 0
    if not reconcile(db, row):
        return 0
    fresh = db.execute(
        "SELECT * FROM experiment_schedules WHERE app_id=? AND experiment_id=?", (row["app_id"], row["experiment_id"])
    ).fetchone()
    if limit["reserved"] >= limit["max_observations"]:
        disable(db, fresh, "EXHAUSTED")
        return 0
    if iso_time(fresh["next_due"]) > iso_time(now()):
        return 0
    dispatch(db, fresh, current)
    return 1


def foreground_owner(db, app_id, experiment_id, owner):
    """Check the exact owner and source inside the foreground write transaction."""
    row = db.execute(
        "SELECT * FROM experiment_schedules WHERE app_id=? AND experiment_id=?", (app_id, experiment_id)
    ).fetchone()
    if not row:
        raise Invalid("No finite schedule is saved")
    limit = live_limit(db, row, lookup(db, app_id, experiment_id))
    if limit["owner"] != owner:
        raise PermissionError("Only the approving owner can run this observation")


def foreground_lease(db, job):
    """Lease only this due observation; report terminal and in-flight states."""
    if not job:
        raise Invalid("Scheduled observation receipt is unavailable")
    if job["status"] not in ("QUEUED", "RUNNING"):
        return {"status": "NOT_DUE", "job_id": job["id"]}
    if job["status"] == "RUNNING" and job["lease"] > time.time():
        return {"status": "RUNNING", "job_id": job["id"]}
    if job["attempts"] >= 3:
        db.execute("UPDATE jobs SET status='FAILED',lease=0,updated=? WHERE id=?", (now(), job["id"]))
        return {"status": "FAILED", "job_id": job["id"]}
    db.execute(
        "UPDATE jobs SET status='RUNNING',attempts=attempts+1,lease=?,updated=? WHERE id=?",
        (time.time() + 60, now(), job["id"]),
    )


def finish_foreground(store, app_id, experiment_id, claimed):
    """Commit the real local observation or its bounded operational failure."""
    from .worker import persist_job_result, failed_result

    try:
        from .experiments import Experiments

        result = Experiments(store).evaluate(app_id, experiment_id, scheduled=claimed["data"])
        status = "SUCCEEDED"
        delay = 0
    except Exception as exc:
        result, status, delay = failed_result(claimed, exc)
    persist_job_result(store, claimed, result, status, delay)
    with connection(store.path) as db:
        saved = db.execute("SELECT status FROM jobs WHERE app_id=? AND id=?", (app_id, claimed["id"])).fetchone()
        if not saved:
            raise Invalid("Scheduled observation receipt is unavailable")
        return {"status": saved["status"], "job_id": claimed["id"]}


def disable(db, row, status):
    """Preserve failed receipts while preventing unbounded retry or cancellation loops."""
    pause_queued(db, row)
    db.execute(
        "UPDATE experiment_schedules SET enabled=0,status=?,updated=? WHERE app_id=? AND experiment_id=?",
        (status, now(), row["app_id"], row["experiment_id"]),
    )
    schedule_audit(db, row["app_id"], row["experiment_id"], "disabled", {"status": status})


def existing_job(db, row):
    """Explicit resume retires a missing receipt without pretending it completed."""
    if not row or not row["last_job"]:
        return None
    job = db.execute("SELECT id FROM jobs WHERE app_id=? AND id=?", (row["app_id"], row["last_job"])).fetchone()
    return job["id"] if job else None


def reconcile(db, row):
    """Apply each terminal result once and disable after three operational failures."""
    if not row["last_job"]:
        return True
    job = db.execute("SELECT status FROM jobs WHERE app_id=? AND id=?", (row["app_id"], row["last_job"])).fetchone()
    if not job:
        disable(db, row, "BLOCKED")
        return False
    if job["status"] in ("QUEUED", "RUNNING"):
        return False
    if row["reconciled_job"] == row["last_job"]:
        return True
    failures = 0 if job["status"] == "SUCCEEDED" else row["failures"] + 1
    db.execute(
        "UPDATE experiment_schedules SET failures=?,reconciled_job=?,updated=? WHERE app_id=? AND experiment_id=?",
        (failures, row["last_job"], now(), row["app_id"], row["experiment_id"]),
    )
    schedule_audit(
        db,
        row["app_id"],
        row["experiment_id"],
        "reconciled",
        {"job_id": row["last_job"], "status": job["status"], "failures": failures},
    )
    if job["status"] == "CANCELLED":
        disable(db, row, "PAUSED")
        return False
    if failures >= 3:
        disable(db, row, "BLOCKED")
        return False
    return True


def dispatch(db, row, experiment):
    """Commit one leased-job input and future due time in the same transaction."""
    data = {
        "experiment_id": row["experiment_id"],
        "schedule_version": row["version"],
        "due": row["next_due"],
        "source_hash": experiment["hash"],
    }
    request_key = "schedule-" + digest(dict(data, app_id=row["app_id"]))
    job_id = uid()
    stamp = now()
    db.execute(
        "INSERT OR IGNORE INTO jobs(id,app_id,action,data,status,created,updated,request_key) VALUES(?,?,?,?,?,?,?,?)",
        (job_id, row["app_id"], "experiment", canonical(data), "QUEUED", stamp, stamp, request_key),
    )
    saved = db.execute("SELECT id FROM jobs WHERE app_id=? AND request_key=?", (row["app_id"], request_key)).fetchone()[
        0
    ]
    if saved != job_id:
        raise Invalid("Scheduled observation identity was already used")
    updated = db.execute(
        "UPDATE experiment_schedule_limits SET reserved=reserved+1 WHERE app_id=? AND experiment_id=? AND schedule_version=? AND reserved<max_observations",
        (row["app_id"], row["experiment_id"], row["version"]),
    )
    if updated.rowcount != 1:
        raise Invalid("Observation limit exhausted or replaced")
    next_due = (iso_time(stamp) + timedelta(hours=row["interval_hours"])).isoformat()
    db.execute(
        "UPDATE experiment_schedules SET last_job=?,next_due=?,updated=? WHERE app_id=? AND experiment_id=?",
        (saved, next_due, stamp, row["app_id"], row["experiment_id"]),
    )
    schedule_audit(db, row["app_id"], row["experiment_id"], "queued", {"job_id": saved, "request_key": request_key})


def check_scheduled(db, current, data):
    """Validate current schedule authorization inside the actual assessment transaction."""
    if set(data) != {"experiment_id", "schedule_version", "due", "source_hash"}:
        raise Invalid("Invalid scheduled analysis input")
    row = db.execute(
        "SELECT * FROM experiment_schedules WHERE app_id=? AND experiment_id=?", (current["app_id"], current["id"])
    ).fetchone()
    if not row or not row["enabled"] or row["version"] != data["schedule_version"]:
        raise Invalid("Schedule paused or replaced; reload current configuration")
    limit = live_limit(db, row, current)
    if iso_time(limit["expires"]) <= iso_time(now()):
        raise Invalid("Schedule authorization expired")
    key = "schedule-" + digest(dict(data, app_id=current["app_id"]))
    job = db.execute(
        "SELECT id,data,status FROM jobs WHERE app_id=? AND request_key=?", (current["app_id"], key)
    ).fetchone()
    validate_reservation(job, row, data, limit)
    if current["hash"] != data["source_hash"] or current["id"] != data["experiment_id"]:
        raise Invalid("Scheduled experiment source changed")
    if iso_time(data["due"]) > iso_time(now()):
        raise Invalid("Scheduled analysis is not due")


def validate_reservation(job, row, data, limit):
    """Match a scheduled assessment to its exact reserved job and finite capacity."""
    if (
        not job
        or job["id"] != row["last_job"]
        or job["data"] != canonical(data)
        or job["status"] not in ("QUEUED", "RUNNING")
        or not 1 <= limit["reserved"] <= limit["max_observations"]
    ):
        raise Invalid("Scheduled observation reservation is unavailable")


def export_schedules(store, app_id):
    """Export settings and recovery state without claiming transferable job authority."""
    return [
        {k: v for k, v in row.items() if k not in ("last_job_status", "finite_limit")}
        for row in Schedules(store).list(app_id)
    ]


def restore_schedules(db, app_id, items):
    """Restore disabled settings: exported job IDs cannot authorize another workstation."""
    if items is None:
        return
    if not isinstance(items, list) or len(items) > 1000:
        raise Invalid("Invalid schedule collection")
    seen = set()
    for row in items:
        validate_restored_schedule(db, app_id, row)
        if row["experiment_id"] in seen:
            raise Invalid("Duplicate restored schedule")
        seen.add(row["experiment_id"])
        db.execute(
            "INSERT INTO experiment_schedules VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                app_id,
                row["experiment_id"],
                0,
                row["interval_hours"],
                row["version"],
                row["next_due"],
                None,
                None,
                0,
                "RESTORED_PAUSED",
                now(),
            ),
        )


def validate_restored_schedule(db, app_id, row):
    """Require exact scoped setting schema, integer limits and valid history references."""
    fields = {
        "app_id",
        "experiment_id",
        "enabled",
        "interval_hours",
        "version",
        "next_due",
        "last_job",
        "reconciled_job",
        "failures",
        "status",
        "updated",
    }
    if not isinstance(row, dict) or set(row) != fields or row["app_id"] != app_id or type(row["enabled"]) is not bool:
        raise Invalid("Restored schedule scope or schema mismatch")
    configuration({"enabled": False, "interval_hours": row["interval_hours"], "version": row["version"]})
    restored_limits(row)
    iso_time(row["next_due"])
    iso_time(row["updated"])
    experiment = lookup(db, app_id, row["experiment_id"])
    if experiment["state"] == "PLANNED" or row["enabled"] and experiment["state"] == "CANCELLED":
        raise Invalid("Restored schedule conflicts with experiment state")


def restored_limits(row):
    """Reject incoherent enable/status combinations and invalid recovery bounds."""
    if (
        row["version"] is None
        or row["version"] < 1
        or type(row["failures"]) is not int
        or not 0 <= row["failures"] <= 3
    ):
        raise Invalid("Invalid restored schedule version or failures")
    if row["status"] not in STATUSES or bool(row["enabled"]) != (row["status"] == "ENABLED"):
        raise Invalid("Invalid restored schedule status")
