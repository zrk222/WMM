"""Private, integrity-checked publication report over the existing read authority."""

import json, re
from .common import Invalid, canonical, digest, safe_data
from .db import connection
from .operation_authority import check
from .publication_authority import Publications, _admit, _row as authority_row
from .publication_contract import channel_descriptor
from .publication_execution import initialize as initialize_intents, _row as intent_row, _view as intent_view, _public
from .publication_schedule import initialize as initialize_schedules, _summary


def _schedule_binding(summary, authority, draft):
    """Check the immutable schedule still identifies this approval and channel."""
    if summary.get("owner") != authority["owner"] or summary.get("approval_hash") != authority["approval_hash"]:
        raise Invalid("Publication schedule approval changed")
    if (
        summary.get("provider") != draft["provider"]
        or summary.get("destination_id") != draft["destination_id"]
        or summary.get("approved_due_at") != authority["due_at"]
    ):
        raise Invalid("Publication schedule destination changed")


def _schedule_job(db, app_id, authority, job_id):
    """Project only the exact queued publication job."""
    if not job_id:
        return None
    job = db.execute(
        "SELECT id,app_id,action,status,attempts,data,request_key FROM jobs WHERE id=? AND app_id=?", (job_id, app_id)
    ).fetchone()
    if job is None or job["action"] != "social_publication":
        raise Invalid("Publication schedule job changed")
    if (
        job["data"] != canonical({"publication_id": authority["id"]})
        or job["request_key"] != "social-publication-" + authority["id"]
    ):
        raise Invalid("Publication schedule job binding changed")
    return {"id": job["id"], "status": job["status"], "attempts": job["attempts"]}


def _schedule(db, app_id, authority, draft):
    """Expose only the schedule and worker statuses bound to this approval."""
    row = db.execute(
        "SELECT * FROM publication_schedules WHERE app_id=? AND authority_id=?", (app_id, authority["id"])
    ).fetchone()
    if row is None:
        return None
    _schedule_binding(_summary(row), authority, draft)
    return {
        "id": row["id"],
        "status": row["status"],
        "due": row["due"],
        "next_due": row["next_due"],
        "job": _schedule_job(db, app_id, authority, row["job_id"]),
    }


def _event_binding(data, intent, seq):
    """Check the immutable event belongs to the selected intent."""
    expected = {
        "intent_id": intent["id"],
        "app_id": intent["app_id"],
        "authority_id": intent["authority_id"],
        "request_hash": intent["request_hash"],
        "channel_hash": intent["channel_hash"],
    }
    if any(data.get(key) != value for key, value in expected.items()):
        raise Invalid("Publication event binding changed")
    if type(data.get("version")) is not int or data["version"] != seq:
        raise Invalid("Publication event version changed")
    if not isinstance(data.get("action"), str) or not re.fullmatch(r"[A-Za-z_]{1,80}", data["action"]):
        raise Invalid("Publication event action invalid")


def _event_data(row, previous, seq, intent):
    """Reject a broken chain, changed canonical event, or foreign identity."""
    try:
        data = json.loads(row["data"])
    except (TypeError, ValueError):
        raise Invalid("Publication event is malformed") from None
    if not isinstance(data, dict) or canonical(data) != row["data"] or digest(data) != row["hash"]:
        raise Invalid("Publication event integrity changed")
    if row["sequence"] != seq or row["previous_hash"] != previous or data.get("previous_hash") != previous:
        raise Invalid("Publication event chain is incomplete")
    _event_binding(data, intent, seq)
    state = data.get("state")
    if state is not None:
        if not isinstance(state, dict) or digest(state) != data.get("state_hash"):
            raise Invalid("Historical publication observation changed")
        if _public({**state, "session": None}) != state:
            raise Invalid("Historical publication observation is invalid")
    return data


def _events(db, intent, view):
    """Reconstruct the complete bounded hash chain and match its retained head."""
    rows = db.execute(
        "SELECT * FROM publication_events WHERE intent_id=? ORDER BY sequence LIMIT 10001", (intent["id"],)
    ).fetchall()
    if not rows or len(rows) > 10000:
        raise Invalid("Publication event chain is unavailable or too large")
    prior = ""
    events = []
    for seq, row in enumerate(rows, 1):
        data = _event_data(row, prior, seq, intent)
        events.append(
            {
                "sequence": seq,
                "hash": row["hash"],
                "previous_hash": prior,
                "action": data["action"],
                "status": data.get("status"),
                "observed_at": data.get("observed_at"),
                "state": data.get("state"),
            }
        )
        prior = row["hash"]
    if (
        prior != view["receipt_hash"]
        or data.get("state_hash") != intent["state_hash"]
        or data.get("version") != intent["version"]
        or data.get("status") != intent["status"]
    ):
        raise Invalid("Publication event head differs from retained state")
    return events


def _intent(db, app_id, authority, channel_hash, draft):
    """Read only a matching intent and its sanitized hash-verified observations."""
    existing = db.execute(
        "SELECT id FROM publication_intents WHERE app_id=? AND authority_id=?", (app_id, authority["id"])
    ).fetchone()
    if existing is None:
        return None, []
    row, state = intent_row(db, app_id, existing["id"])
    if (
        row["owner"] != authority["owner"]
        or row["channel_hash"] != channel_hash
        or row["request_hash"] != digest({"approval": authority["approval_hash"], "draft": draft})
    ):
        raise Invalid("Publication intent does not match approval")
    if _public({**state, "session": None}) != state:
        raise Invalid("Publication observation is invalid")
    view = intent_view(db, row)
    return view, _events(db, row, view)


def report(store, app_id, identity):
    """Return a protected owner/agent report, never provider credentials or checkpoints."""
    base = Publications(store).get(app_id, identity)
    admitted, _, owner = _admit(store, app_id, "publication.get", {"id": identity})
    initialize_schedules(store)
    initialize_intents(store)
    with connection(store.path) as db:
        check(db, admitted)
        row, draft, binding = authority_row(db, app_id, identity)
        if row["owner"] != owner or base["review_hash"] != row["review_hash"]:
            raise PermissionError("Publication belongs to another owner")
        channel = channel_descriptor(draft)
        channel_hash = digest(channel)
        intent, events = _intent(db, app_id, base, channel_hash, draft)
        schedule = _schedule(db, app_id, base, draft)
    metrics = intent["observation"].get("metrics") if intent else None
    history = _metric_history(events)
    latest_sample = (
        history[-1]
        if history
        else {
            "receipt_hash": None,
            "observed_at": None,
            "metrics": None,
            "reason": "NO_PROVIDER_READ_RECORDED",
        }
    )
    proof = binding.get("proof", {})
    detail = {
        "schema": "wmm.publication-report.v1",
        "channel": channel,
        "channel_hash": channel_hash,
        "content": {
            "artifact": draft["artifact"],
            "rights_hashes": draft["rights_hashes"],
            "source_hashes": draft["source_hashes"],
            "rights_basis": proof.get("rights_basis"),
        },
        "approval": {
            "id": base["id"],
            "review_hash": base["review_hash"],
            "approval_hash": base["approval_hash"],
            "owner": base["owner"],
            "status": base["status"],
            "expires": base["expires"],
            "max_calls": base["max_calls"],
            "calls_used": base["calls_used"],
        },
        "schedule": schedule,
        "intent": intent,
        "events": events,
        "latest_metrics": metrics,
        "metric_history": history,
        "latest_metric_sample": latest_sample,
        "public_visibility": "NOT_INDEPENDENTLY_VERIFIED",
        "attribution": {"installs": None, "revenue": None, "reason": "NOT_MEASURED_BY_PUBLICATION_PROVIDER"},
    }
    safe_data(detail)
    if len(canonical(detail).encode()) > 2_000_000:
        raise Invalid("Publication report exceeds its bound")
    return {**base, "report": detail}


def _metric_history(events):
    """Keep each saved provider read, including reads that returned no metrics."""
    result = []
    for event in events:
        if event["action"] != "read" or not event.get("state"):
            continue
        metrics = event["state"]["observation"].get("metrics")
        result.append(
            {
                "receipt_hash": event["hash"],
                "observed_at": event["observed_at"],
                "metrics": metrics,
                "reason": "PROVIDER_READ_RETURNED_NO_METRICS" if metrics is None else None,
            }
        )
    return result
