"""One due-time binding over the existing campaign tick and durable job queue."""

import json, time, math
from .campaign_access import identity, scope_owner
from .common import Invalid, canonical, digest, iso_time, now, uid, safe_data
from .db import connection
from .operation_authority import check
from .publication_authority import current
from .social_contract import reference

SCHEMA = """
CREATE TABLE IF NOT EXISTS publication_schedules(
 id TEXT PRIMARY KEY, app_id TEXT NOT NULL, authority_id TEXT NOT NULL UNIQUE,
 summary TEXT NOT NULL, summary_hash TEXT NOT NULL, due REAL NOT NULL,
 status TEXT NOT NULL, job_id TEXT UNIQUE, created TEXT NOT NULL, updated TEXT NOT NULL, next_due REAL);
CREATE INDEX IF NOT EXISTS publication_schedule_due ON publication_schedules(status,due);
CREATE TRIGGER IF NOT EXISTS publication_schedule_no_rewrite BEFORE UPDATE ON publication_schedules
 WHEN NEW.id!=OLD.id OR NEW.app_id!=OLD.app_id OR NEW.authority_id!=OLD.authority_id
 OR NEW.summary!=OLD.summary OR NEW.summary_hash!=OLD.summary_hash OR NEW.due!=OLD.due OR NEW.created!=OLD.created
 BEGIN SELECT RAISE(ABORT,'Publication schedule binding is immutable'); END;
CREATE TRIGGER IF NOT EXISTS publication_schedule_no_delete BEFORE DELETE ON publication_schedules
 BEGIN SELECT RAISE(ABORT,'Publication schedule is immutable'); END;
CREATE TRIGGER IF NOT EXISTS publication_schedule_no_replace BEFORE INSERT ON publication_schedules
 WHEN EXISTS(SELECT 1 FROM publication_schedules WHERE id=NEW.id OR authority_id=NEW.authority_id)
 BEGIN SELECT RAISE(ABORT,'Publication schedule already exists'); END;
"""


def initialize(store):
    with connection(store.path) as db:
        db.executescript(SCHEMA)
        columns = {row["name"] for row in db.execute("PRAGMA table_info(publication_schedules)")}
        if "next_due" not in columns:
            db.execute("ALTER TABLE publication_schedules ADD COLUMN next_due REAL")
        db.execute("UPDATE publication_schedules SET next_due=due WHERE next_due IS NULL")


def _summary(row):
    value = json.loads(row["summary"])
    if (
        canonical(value) != row["summary"]
        or digest(value) != row["summary_hash"]
        or value.get("schedule_id") != row["id"]
        or value.get("app_id") != row["app_id"]
        or value.get("authority_id") != row["authority_id"]
        or value.get("due_timestamp") != row["due"]
    ):
        raise Invalid("Publication schedule binding changed")
    return value


def _view(row):
    return {
        key: row[key]
        for key in ("id", "app_id", "authority_id", "status", "due", "next_due", "job_id", "created", "updated")
    }


def _validated(db, store, row):
    summary = _summary(row)
    authority = current(db, store, row["app_id"], row["authority_id"], owner=summary["owner"])
    saved = authority["authority"]
    draft = authority["draft"]
    if (
        saved["approval_hash"] != summary["approval_hash"]
        or saved["owner"] != summary["owner"]
        or saved["due_at"] != summary["approved_due_at"]
        or draft["provider"] != summary["provider"]
        or draft["destination_id"] != summary["destination_id"]
    ):
        raise PermissionError("Publication schedule no longer matches approval")
    return summary, authority


def _queue(db, row):
    key = "social-publication-" + row["authority_id"]
    payload = {"publication_id": row["authority_id"]}
    existing = db.execute("SELECT * FROM jobs WHERE app_id=? AND request_key=?", (row["app_id"], key)).fetchone()
    if existing:
        if existing["action"] != "social_publication" or existing["data"] != canonical(payload):
            raise Invalid("Publication job request key was reused")
        job_id = existing["id"]
    else:
        job_id = uid()
        stamp = now()
        db.execute(
            "INSERT INTO jobs(id,app_id,action,data,status,created,updated,request_key) VALUES(?,?,?,?,?,?,?,?)",
            (job_id, row["app_id"], "social_publication", canonical(payload), "QUEUED", stamp, stamp, key),
        )
    db.execute(
        "UPDATE publication_schedules SET status='QUEUED',job_id=?,updated=? WHERE id=? AND status='READY'",
        (job_id, now(), row["id"]),
    )
    return job_id


def enqueue_approved(store, app_id, authority_id):
    """Retain a schedule only from its exact protected execute/activation admission."""
    reference(authority_id)
    context, actor = identity(store, app_id)
    owner = scope_owner(store, context, actor)
    envelope = json.loads(context["envelope"])
    body = envelope["input"]
    if (
        envelope["operation"] not in ("publication.execute", "publication.activate")
        or not isinstance(body, dict)
        or body.get("id") != authority_id
    ):
        raise PermissionError("Publication schedule is outside the protected operation")
    initialize(store)
    with connection(store.path) as db:
        db.execute("BEGIN IMMEDIATE")
        check(db, context)
        approved = current(db, store, app_id, authority_id, owner=owner)
        old = db.execute("SELECT * FROM publication_schedules WHERE authority_id=?", (authority_id,)).fetchone()
        if old:
            _validated(db, store, old)
            return _view(old)
        value = approved["authority"]
        draft = approved["draft"]
        due = value["due_at"]
        stamp = time.time()
        due_ts = iso_time(due).timestamp() if due else stamp
        identity_value = uid()
        summary = dict(
            schedule_id=identity_value,
            app_id=app_id,
            authority_id=authority_id,
            owner=owner,
            approval_hash=value["approval_hash"],
            approved_due_at=due,
            due_timestamp=due_ts,
            provider=draft["provider"],
            destination_id=draft["destination_id"],
            operation="publication.execute",
            kind="MULTICHANNEL_PUBLICATION",
        )
        db.execute(
            "INSERT INTO publication_schedules(id,app_id,authority_id,summary,summary_hash,due,status,job_id,created,updated,next_due) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                identity_value,
                app_id,
                authority_id,
                canonical(summary),
                digest(summary),
                due_ts,
                "READY",
                None,
                now(),
                now(),
                due_ts,
            ),
        )
        row = db.execute("SELECT * FROM publication_schedules WHERE id=?", (identity_value,)).fetchone()
        if due_ts <= stamp:
            _queue(db, row)
        return _view(db.execute("SELECT * FROM publication_schedules WHERE id=?", (identity_value,)).fetchone())


def advance(db, store):
    """Called by the existing campaign tick in its transaction; no provider calls."""
    if not db.in_transaction:
        raise Invalid("Schedule advancement requires the campaign tick transaction")
    count = 0
    rows = db.execute(
        "SELECT * FROM publication_schedules WHERE status='READY' AND due<=? ORDER BY due,id LIMIT 20", (time.time(),)
    ).fetchall()
    for row in rows:
        try:
            _validated(db, store, row)
            _queue(db, row)
            count += 1
        except (Invalid, PermissionError, ValueError, TypeError, KeyError, OverflowError, OSError, ImportError):
            db.execute(
                "UPDATE publication_schedules SET status='BLOCKED',updated=? WHERE id=? AND status='READY'",
                (now(), row["id"]),
            )
    return count


def disable_db(db, app_id, authority_id):
    """Host revocation hook; must be called inside its owner-authorized transaction."""
    if not db.in_transaction:
        raise Invalid("Schedule disable requires the owner transaction")
    row = db.execute(
        "SELECT * FROM publication_schedules WHERE app_id=? AND authority_id=?", (app_id, authority_id)
    ).fetchone()
    if not row:
        return False
    _summary(row)
    db.execute("UPDATE publication_schedules SET status='OFF',updated=? WHERE id=?", (now(), row["id"]))
    if row["job_id"]:
        db.execute(
            "UPDATE jobs SET status='CANCELLED',updated=? WHERE id=? AND status='QUEUED'", (now(), row["job_id"])
        )
    return True


def _job_identity(job):
    if not isinstance(job, dict) or job.get("action") != "social_publication":
        raise PermissionError("Publication job input is invalid")
    data = job.get("data")
    if not isinstance(data, dict) or set(data) != {"publication_id"}:
        raise PermissionError("Publication job input is invalid")
    return reference(data["publication_id"])


def _schedule_job(db, job, identity, statuses=("QUEUED",)):
    row = db.execute(
        "SELECT * FROM publication_schedules WHERE app_id=? AND authority_id=?", (job.get("app_id"), identity)
    ).fetchone()
    if not row or row["status"] not in statuses or row["job_id"] != job.get("id"):
        raise PermissionError("Publication schedule is not available")
    return row


def _live_job(db, job, identity):
    saved = db.execute("SELECT * FROM jobs WHERE id=? AND app_id=?", (job.get("id"), job.get("app_id"))).fetchone()
    if not saved or saved["action"] != "social_publication" or saved["data"] != canonical(job["data"]):
        raise PermissionError("Publication job identity changed")
    if saved["status"] != "RUNNING" or type(job.get("attempts")) is not int or saved["attempts"] != job["attempts"]:
        raise PermissionError("Publication job lease changed")
    if saved["lease"] <= time.time() or saved["request_key"] != "social-publication-" + identity:
        raise PermissionError("Publication job lease changed")
    return saved


def _due(row):
    return row["due"] <= time.time() and row["next_due"] is not None and row["next_due"] <= time.time()


def check_job(db, store, job):
    """Derive owner only from a matching retained approval and live worker lease."""
    identity = _job_identity(job)
    row = _schedule_job(db, job, identity)
    if not _due(row):
        raise PermissionError("Publication schedule is not due")
    _live_job(db, job, identity)
    summary, _ = _validated(db, store, row)
    return summary["owner"]


def _queued_job(db, job):
    saved = db.execute("SELECT * FROM jobs WHERE id=? AND app_id=?", (job.get("id"), job.get("app_id"))).fetchone()
    if not saved or saved["status"] != "QUEUED" or saved["action"] != "social_publication":
        return False
    return saved["data"] == canonical(job["data"])


def ready_job(db, job):
    """Cheap due-time fence for worker claim; no proof reads before due."""
    try:
        job = dict(job)
        if isinstance(job.get("data"), str):
            job["data"] = json.loads(job["data"])
        identity = _job_identity(job)
        row = _schedule_job(db, job, identity)
        if not _due(row) or not _queued_job(db, job):
            return False
        _summary(row)
        return True
    except (ValueError, TypeError, KeyError, Invalid, PermissionError):
        return False


def _next_time(value, expiry):
    return type(value) in (int, float) and math.isfinite(value) and time.time() <= value < expiry


def _monitor_time(authority):
    due = time.time() + 3600
    if (
        authority["status"] != "APPROVED"
        or authority["calls_used"] >= authority["max_calls"]
        or due >= authority["expires"]
    ):
        return None
    return due


def _finish_status(row, result, when_ok):
    if row["status"] == "OFF":
        return "CANCELLED", "OFF"
    attention = result.get("requires_attention", False)
    if type(attention) is not bool or attention:
        return "BLOCKED", "BLOCKED"
    status = result.get("status")
    if status == "PUBLISHED":
        if result.get("monitoring") is True and when_ok:
            return "QUEUED", "QUEUED"
        return "SUCCEEDED", "COMPLETE"
    safe = {"CREATED", "UPLOAD_IN_PROGRESS", "UPLOADED", "PROCESSING", "READY_TO_PUBLISH", "PUBLISH_ACKNOWLEDGED"}
    if status in safe and when_ok:
        return "QUEUED", "QUEUED"
    return "BLOCKED", "BLOCKED"


def finish_step(db, store, job, result, reschedule_at):
    """Persist a retained executor receipt under the matching live worker lease."""
    if not db.in_transaction:
        raise Invalid("Finishing publication requires the worker transaction")
    safe_data(result)
    authority_id = _job_identity(job)
    row = _schedule_job(db, job, authority_id, ("QUEUED", "OFF"))
    _live_job(db, job, authority_id)
    summary = _summary(row)
    from .publication_authority import _row

    authority, _, _ = _row(db, row["app_id"], authority_id)
    if authority["approval_hash"] != summary["approval_hash"]:
        raise PermissionError("Publication approval changed")
    from .publication_execution import verified_result

    verified_result(db, row["app_id"], authority_id, result)
    if result["status"] == "PUBLISHED":
        # Monitoring is a server decision, not a caller-supplied receipt field.
        reschedule_at = None if result["requires_attention"] else _monitor_time(authority)
        result = {**result, "monitoring": reschedule_at is not None}
    job_status, schedule_status = _finish_status(row, result, _next_time(reschedule_at, authority["expires"]))
    stamp = now()
    changed = db.execute(
        "UPDATE jobs SET status=?,result=?,lease=0,updated=? WHERE id=? AND status='RUNNING' AND attempts=? AND lease>?",
        (job_status, canonical(result), stamp, job["id"], job["attempts"], time.time()),
    ).rowcount
    if not changed:
        raise PermissionError("Publication job lease changed")
    db.execute(
        "UPDATE publication_schedules SET status=?,next_due=?,updated=? WHERE id=?",
        (schedule_status, reschedule_at if job_status == "QUEUED" else row["next_due"], stamp, row["id"]),
    )
    return {"job_status": job_status, "schedule_status": schedule_status}
