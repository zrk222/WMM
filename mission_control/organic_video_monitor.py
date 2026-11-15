"""Bounded phase continuations on the existing campaign queue, never blind retries."""

import json
import time

from .common import Invalid, canonical, digest, iso_time, now, uid

VIDEO_PHASE_OBSERVATION_SECONDS = 30
VIDEO_PHASE_FOLLOWUP_JOB_LIMIT = 12
CONFIG = dict(interval_seconds=VIDEO_PHASE_OBSERVATION_SECONDS, max_followup_jobs=VIDEO_PHASE_FOLLOWUP_JOB_LIMIT)
PENDING = {"PROCESSING", "FINISH_ACKNOWLEDGED"}


def schema(db):
    db.execute("""CREATE TABLE IF NOT EXISTS campaign_video_observations(
        item_id TEXT PRIMARY KEY REFERENCES campaign_schedule_items(id),
        job_id TEXT NOT NULL, sequence INTEGER NOT NULL,
        next_due REAL, state TEXT NOT NULL, reason TEXT NOT NULL, updated TEXT NOT NULL)""")


def save(db, row, state, reason, *, due=None, sequence=None, job_id=None):
    count = (row["sequence"] or 0) if sequence is None else sequence
    db.execute(
        """INSERT INTO campaign_video_observations VALUES(?,?,?,?,?,?,?)
        ON CONFLICT(item_id) DO UPDATE SET job_id=excluded.job_id,sequence=excluded.sequence,
        next_due=excluded.next_due,state=excluded.state,reason=excluded.reason,updated=excluded.updated""",
        (row["item_id"], job_id or row["job_id"], count, due, state, reason, now()),
    )


def checked_summary(row):
    from .organic_video_schedule import KIND, OPERATION

    summary, item, data = [json.loads(row[key]) for key in ("summary", "body", "job_data")]
    if (
        summary.get("kind") != KIND
        or digest(summary) != row["summary_hash"]
        or summary["batch_id"] != row["batch_id"]
        or summary["app_id"] != row["app_id"]
    ):
        raise Invalid("Video observation summary changed")
    checked_item(row, summary, item)
    expected = dict(
        batch_id=row["batch_id"],
        item_id=row["item_id"],
        scope_id=summary["scope_id"],
        operation=OPERATION,
        request=item["request"],
    )
    if data != expected or item["operation"] != OPERATION:
        raise Invalid("Video observation worker inputs changed")
    return summary, item


def checked_item(row, summary, item):
    if (
        digest(item) != row["body_hash"]
        or item not in summary["items"]
        or item["item_id"] != row["item_id"]
        or row["due"] != iso_time(item["due_at"]).timestamp()
    ):
        raise Invalid("Video observation item changed")


def checked_intent(db, row, summary, item):
    from .campaign_video_execution import _row

    intent = _row(db, row["app_id"], item["request"]["intent_id"])
    request = json.loads(intent["data"])["request"]
    if intent["hash"] != item["request"]["intent_hash"]:
        raise Invalid("Video observation intent changed")
    if (request["policy_id"], request["policy_hash"]) != (summary["scope_id"], summary["scope_hash"]):
        raise Invalid("Video observation policy changed")
    prior = json.loads(row["result"])
    if not isinstance(prior, dict) or prior.get("id") != intent["id"] or prior.get("app_id") != row["app_id"]:
        raise Invalid("Video observation result is not bound to this intent")
    if row["cursor_job"] is not None and row["cursor_job"] != row["job_id"]:
        raise Invalid("Video observation cursor changed")
    return intent, request


def current_budget(db, store, row, summary, intent, request):
    from .organic_video_policy import Policies, _saved

    policy = Policies(store)._current(
        db,
        db.execute(
            "SELECT * FROM organic_video_policies WHERE app_id=? AND id=?", (row["app_id"], summary["scope_id"])
        ).fetchone(),
        verify_bytes=False,
    )
    if policy["hash"] != summary["scope_hash"] or policy["data"]["owner"] != summary["owner"]:
        raise PermissionError("Video observation owner or policy changed")
    admission = _saved(
        db.execute(
            "SELECT * FROM organic_video_admissions WHERE app_id=? AND id=?", (row["app_id"], request["admission_id"])
        ).fetchone()
    )
    if (
        admission["hash"] != request["admission_hash"]
        or intent["calls"] >= admission["data"]["provider_calls_reserved"]
    ):
        raise PermissionError("Video observation allowance is unavailable or exhausted")


def observe(db, store, row):
    if row["job_status"] != "SUCCEEDED":
        save(db, row, "BLOCKED", "Previous worker did not complete; inspect its retained intent before recovery")
        return 0
    summary, item = checked_summary(row)
    if summary.get("monitoring") != CONFIG:
        save(db, row, "OFF", "Follow-up observations were not approved in this exact schedule")
        return 0
    intent, request = checked_intent(db, row, summary, item)
    if intent["stage"] == "PROVIDER_PHASE_COMPLETE":
        save(
            db, row, "COMPLETE", "Provider phases observed complete; public visibility and app outcomes remain separate"
        )
        return 0
    if intent["stage"] not in PENDING:
        save(db, row, "BLOCKED", "The retained provider stage needs owner inspection; no automatic mutation retry")
        return 0
    current_budget(db, store, row, summary, intent, request)
    return pending(db, row)


def pending(db, row):
    if row["sequence"] is None:
        save(
            db,
            row,
            "WAITING",
            "Waiting for the next approved provider phase observation",
            due=time.time() + CONFIG["interval_seconds"],
        )
        return 0
    if row["sequence"] >= CONFIG["max_followup_jobs"]:
        save(db, row, "BLOCKED", "Approved follow-up job ceiling reached; review the retained intent")
        return 0
    return enqueue(db, row)


def enqueue(db, row):
    sequence, identity, stamp = row["sequence"] + 1, uid(), now()
    data = json.loads(row["job_data"])
    key = "campaign-video-observation:" + row["item_id"] + ":" + str(sequence)
    db.execute(
        "INSERT INTO jobs(id,app_id,action,data,status,created,updated,request_key) VALUES(?,?,?,?,?,?,?,?)",
        (identity, row["app_id"], "campaign_post", canonical(data), "QUEUED", stamp, stamp, key),
    )
    db.execute(
        "UPDATE campaign_schedule_items SET job_id=?,updated=? WHERE id=? AND job_id=?",
        (identity, stamp, row["item_id"], row["job_id"]),
    )
    save(
        db,
        row,
        "WAITING",
        "Approved phase observation queued",
        due=time.time() + CONFIG["interval_seconds"],
        sequence=sequence,
        job_id=identity,
    )
    from .campaign_schedule import audit

    audit(
        db,
        row["app_id"],
        "video_observation_queued",
        dict(item_id=row["item_id"], prior_job_id=row["job_id"], job_id=identity, sequence=sequence),
    )
    return 1


def advance(db, store):
    """Called only within the existing scheduler's immediate transaction."""
    if db.execute("SELECT 1 FROM sqlite_master WHERE name='campaign_video_schedule_bindings'").fetchone() is None:
        return 0
    schema(db)
    from .campaign_schedule import MAX_ITEMS

    rows = db.execute(
        """SELECT i.id AS item_id,i.body,i.body_hash,i.due,i.job_id,
        b.id AS batch_id,b.app_id,b.summary,b.summary_hash,j.data AS job_data,j.result,j.status AS job_status,
        p.sequence,p.job_id AS cursor_job
        FROM campaign_video_schedule_bindings v JOIN campaign_schedule_items i ON i.id=v.item_id
        JOIN campaign_schedule_batches b ON b.id=i.batch_id JOIN jobs j ON j.id=i.job_id
        LEFT JOIN campaign_video_observations p ON p.item_id=i.id
        WHERE b.status='ACTIVE' AND i.status='QUEUED' AND j.status IN ('SUCCEEDED','BLOCKED','FAILED','CANCELLED')
        AND (p.item_id IS NULL OR (p.state='WAITING' AND p.next_due<=?))
        ORDER BY i.due,i.id LIMIT ?""",
        (time.time(), MAX_ITEMS),
    ).fetchall()
    count = 0
    for row in rows:
        try:
            count += observe(db, store, row)
        except (Invalid, PermissionError) as error:
            save(db, row, "BLOCKED", str(error)[:240])
        except (ValueError, TypeError, KeyError):
            save(db, row, "BLOCKED", "Retained video evidence changed; inspect the original intent and schedule")
    return count


def status(db, app_id, item_id):
    schema(db)
    row = db.execute(
        """SELECT p.*,b.status AS batch_status FROM campaign_schedule_items i
        JOIN campaign_schedule_batches b ON b.id=i.batch_id
        LEFT JOIN campaign_video_observations p ON p.item_id=i.id
        WHERE i.id=? AND b.app_id=?""",
        (item_id, app_id),
    ).fetchone()
    jobs = db.execute(
        """SELECT id,status,created FROM jobs WHERE app_id=? AND action='campaign_post'
        AND (request_key=? OR request_key LIKE ?) ORDER BY created,id""",
        (app_id, "campaign-schedule-" + item_id, "campaign-video-observation:" + item_id + ":%"),
    ).fetchall()
    observation = dict(row) if row and row["item_id"] is not None else None
    if observation is not None:
        observation.pop("batch_status")
    effective = observation["state"] if observation else "NOT_STARTED"
    if row and row["batch_status"] != "ACTIVE":
        effective = row["batch_status"]
    return dict(
        observation=observation,
        effective_state=effective,
        jobs=[dict(job) for job in jobs],
        meaning="Provider phases; at most twelve follow-up jobs within the reserved call allowance. Not impressions, public visibility or measured app outcomes.",
    )
