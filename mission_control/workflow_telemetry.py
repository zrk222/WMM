"""Durable worker observations with fixed public labels, never model or secret text."""

from .common import Invalid, now
from .db import connection
from .catalog import stages

MAX_JOBS = 100
MAX_EVENTS = 200
EVENTS = {
    'EDIT_PROOF': 'Checking the exact current edit revision and its source rights.',
    'EDIT_SOURCES': 'Copying and verifying the selected source videos for editing.',
    'EDIT_ENCODING': 'Rendering the timeline cuts, speed, framing and color adjustments.',
    'EDIT_COMMIT': 'Rechecking the project and saving the validated edited MP4.',
    "NATIVE_PROOF": "Checking the approved video brief, screen rights and current source evidence.",
    "NATIVE_SCREENS": "Copying the selected app screens and verifying their saved file hashes.",
    "NATIVE_ENCODING": "Encoding the app-screen video and checking the MP4 output.",
    "NATIVE_COMMIT": "Rechecking approval and source evidence before saving the video artifact.",
    "STARTED": "Worker started this attempt.",
    "STAGE_STARTED": "Checking stage evidence and preparing its packet.",
    "STAGE_PREPARED": "Stage packet prepared from current evidence.",
    "STAGE_BLOCKED": "Stage checked; required evidence is missing. Inspect its packet.",
    "SUCCEEDED": "Worker finished; inspect the saved output.",
    "BLOCKED": "Worker stopped at a validation or access boundary. Inspect the job.",
    "FAILED": "Worker failed. Inspect the saved result before retrying.",
    "CANCELLED": "Work was cancelled.",
    "RETRY_WAIT": "Worker is waiting for its permitted retry.",
}


def append(db, job, code, stage=None):
    """Save finite application events attached to an exact actual job attempt."""
    if code not in EVENTS or (
        stage is not None and (type(stage) is not int or not 1 <= stage <= 12)
    ):
        raise Invalid("Unknown workflow progress event")
    db.execute(
        "INSERT INTO workflow_events(app_id,job_id,attempt,code,stage,observed_at) VALUES(?,?,?,?,?,?)",
        (job["app_id"], job["id"], job["attempts"], code, stage, now()),
    )


def emit(store, job, code, stage=None):
    """Cancelled and superseded attempts cannot claim new progress."""
    with connection(store.path) as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT status,attempts FROM jobs WHERE app_id=? AND id=?",
            (job["app_id"], job["id"]),
        ).fetchone()
        if not row or row["status"] != "RUNNING" or row["attempts"] != job["attempts"]:
            raise Invalid("Workflow attempt stopped or changed")
        append(db, job, code, stage)


def monitor(store, app_id):
    """Project bounded public progress without queued input or raw result errors."""
    store.app(app_id)
    with connection(store.path) as db:
        db.execute("BEGIN")
        jobs = db.execute(
            "SELECT id,action,status,attempts,created,updated FROM jobs WHERE app_id=? ORDER BY created DESC,id LIMIT ?",
            (app_id, MAX_JOBS),
        ).fetchall()
        runs = [run_view(db, app_id, dict(job)) for job in jobs]
    return dict(
        schema="wmm.workflow-telemetry.v1",
        app_id=app_id,
        observed_at=now(),
        runs=runs,
        scope="Actual local worker events; processed stages do not establish business outcomes.",
    )


def run_view(db, app_id, job):
    """Separate processed/blocked stages from elapsed-time estimates and job success."""
    rows = db.execute(
        "SELECT id,attempt,code,stage,observed_at FROM workflow_events WHERE app_id=? AND job_id=? ORDER BY id DESC LIMIT ?",
        (app_id, job["id"], MAX_EVENTS),
    ).fetchall()
    names = {row["id"]: row["title"] for row in stages()}
    events = [
        dict(
            row,
            message=EVENTS.get(row["code"], "Unknown retained event; inspect job."),
            stage_title=names.get(row["stage"]),
        )
        for row in reversed(rows)
    ]
    current = [row for row in events if row["attempt"] == job["attempts"]]
    finished = {
        row["stage"]
        for row in current
        if row["code"] in ("STAGE_PREPARED", "STAGE_BLOCKED")
    }
    blocked = {row["stage"] for row in current if row["code"] == "STAGE_BLOCKED"}
    latest = current[-1] if current else None
    return dict(
        job,
        events=events,
        latest=latest,
        processed_stages=len(finished),
        blocked_stages=len(blocked),
        telemetry="OBSERVED" if latest else "NO_STAGE_EVENTS",
        activity=latest["message"]
        if latest
        else "No worker step event recorded for this attempt yet.",
    )
