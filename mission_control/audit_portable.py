"""Portable inspection assertions never become native jobs or execution authority."""
import json
import uuid
from .common import Invalid, canonical, digest, iso_time
from .audit_contract import exact, scope
from .audit_ecc import native

STATES = ("QUEUED", "RUNNING", "SUCCEEDED", "INCOMPLETE", "BLOCKED", "CANCELLED", "INTERRUPTED")
AUTHORITY = {"execution": False, "readiness": False, "publication": False}


def archive_entry(app_id, row):
    """Freeze original state without copying any runnable configuration table."""
    data = {key: row[key] for key in ("status", "error", "created", "updated")}
    data["frozen"] = json.loads(row["data"])
    data["result"] = json.loads(row["result"]) if row["result"] is not None else None
    return {"app_id": app_id, "id": row["id"], "data": data, "hash": digest(data), "origin": "IMPORTED_ASSERTION"}


def export_archives(db, app_id):
    """Export complete app-owned history; refuse overflow rather than silently truncate."""
    archived = [dict(row) for row in db.execute("SELECT app_id,id,data,hash FROM inspection_archives WHERE app_id=? ORDER BY id", (app_id,))]
    for row in archived:
        row["data"] = json.loads(row["data"])
        row["origin"] = "IMPORTED_ASSERTION"
    live = [archive_entry(app_id, row) for row in db.execute("SELECT * FROM inspection_runs WHERE app_id=? ORDER BY id", (app_id,))]
    entries = archived + live
    validate_archives(app_id, entries)
    return entries


def validate_frozen(app_id, key, frozen):
    """Revalidate historical request shape without resolving or executing its stored tool paths."""
    fields = ("mode", "request", "scenario", "tool_id", "app_id", "manifest_version", "task_source", "tools", "scope_hash", "config_version", "queue_request")
    exact(frozen, fields)
    archive_versions(frozen)
    if frozen["app_id"] != app_id or frozen["queue_request"].get("request_key") != key:
        raise Invalid("Inspection archive request belongs elsewhere")
    base = {k: v for k, v in frozen.items() if k not in ("scope_hash", "config_version", "queue_request")}
    if digest(base) != frozen["scope_hash"]:
        raise Invalid("Inspection archive frozen scope changed")
    if frozen["queue_request"] != {"request_key": key, "manifest_version": frozen["manifest_version"], "scope_hash": frozen["scope_hash"]}:
        raise Invalid("Inspection archive queue binding changed")
    app = {"version": frozen["manifest_version"], "data": {"website": frozen["scenario"]["start_url"]["url"]}}
    rebuilt = scope(frozen["request"], app, frozen["tools"])
    if any(rebuilt[k] != frozen[k] for k in rebuilt):
        raise Invalid("Inspection archive scenario differs from its declared request")


def archive_versions(frozen):
    """Historical revisions are positive integers, never booleans or inferred defaults."""
    for field in ("manifest_version", "config_version"):
        if type(frozen[field]) is not int or frozen[field] < 1:
            raise Invalid("Inspection archive version is invalid")


def validate_result(data):
    """A supplied successful result must be internally consistent, but remains unauthenticated."""
    result = data["result"]
    if result is None:
        if data["status"] in ("SUCCEEDED", "INCOMPLETE"):
            raise Invalid("Completed inspection archive has no evidence")
        return
    if not isinstance(result, dict) or digest(result.get("native")) != result.get("native_sha256"):
        raise Invalid("Inspection archive native hash differs")
    if data["status"] not in ("SUCCEEDED", "INCOMPLETE"):
        return
    _, observed = native(result["native"], data["frozen"]["scenario"])
    complete = observed["completeness"].get("status") == "complete" and all(s.get("status") == "completed" for s in observed["steps"])
    if complete != (data["status"] == "SUCCEEDED"):
        raise Invalid("Inspection archive completeness contradicts its original state")
    validate_review(data)


def validate_review(data):
    """Keep historical review provenance bound without granting its original acceptance flag authority."""
    result, frozen = data["result"], data["frozen"]
    ecc = result.get("ecc", {})
    expected = {"native_sha256": result["native_sha256"], "app_id": frozen["app_id"],
                "scope_hash": frozen["scope_hash"], "task_source": frozen["task_source"],
                "skills": frozen["tools"]["skills"], "status": data["status"],
                "mode": "DETERMINISTIC_SKILL_RULE_REVIEW", "publication_authority": False, "readiness_authority": False}
    if any(ecc.get(key) != value for key, value in expected.items()):
        raise Invalid("Inspection archive review binding or authority differs")
    if result.get("accepted") is not True:
        raise Invalid("Inspection archive original acceptance differs")


def validate_archives(app_id, entries):
    """Validate every row before the caller commits any part of its workspace restore."""
    if not isinstance(entries, list) or len(entries) > 1000:
        raise Invalid("Inspection archives allow at most 1000 records")
    seen = set()
    for row in entries:
        validate_archive(app_id, row, seen)


def validate_archive(app_id, row, seen):
    """Reject scope, duplicate, size, hash and timestamp tampering before storage."""
    try:
        exact(row, ("app_id", "id", "data", "hash", "origin"))
        key = archive_identity(app_id, row, seen)
        data = row["data"]
        exact(data, ("status", "error", "created", "updated", "frozen", "result"))
        if len(canonical(data).encode()) > 8388608 or row["hash"] != digest(data) or data["status"] not in STATES:
            raise Invalid("Inspection archive state, size or hash differs")
        if iso_time(data["updated"]) < iso_time(data["created"]):
            raise Invalid("Inspection archive timestamps are reversed")
        validate_frozen(app_id, key, data["frozen"])
        validate_result(data)
        seen.add(key)
    except (KeyError, TypeError, AttributeError, ValueError, RecursionError) as exc:
        if isinstance(exc, Invalid): raise
        raise Invalid("Inspection archive is malformed") from None


def archive_identity(app_id, row, seen):
    """Validate canonical, unique app-owned identities without trusting a supplied provenance label."""
    key = str(uuid.UUID(row["id"]))
    if key != row["id"] or key in seen or row["app_id"] != app_id or row["origin"] != "IMPORTED_ASSERTION":
        raise Invalid("Inspection archive identity or provenance differs")
    return key


def restore_archives(db, app_id, entries):
    """Restore only inert assertions inside the caller's atomic transaction."""
    if entries is None: return
    validate_archives(app_id, entries)
    for row in entries:
        db.execute("INSERT INTO inspection_archives VALUES(?,?,?,?,?)", (app_id, row["id"], canonical(row["data"]), row["hash"], row["data"]["created"]))


def archive_detail(db, app_id, key):
    """Separate imported evidence from the native execution record envelope."""
    row = db.execute("SELECT * FROM inspection_archives WHERE app_id=? AND id=?", (app_id, key)).fetchone()
    if row is None: raise Invalid("Inspection record not found in this app")
    data = json.loads(row["data"])
    if digest(data) != row["hash"]: raise Invalid("Imported inspection integrity differs")
    return {"app_id": app_id, "id": key, "status": "IMPORTED_ASSERTION", "authority": dict(AUTHORITY), "original": data, "hash": row["hash"]}
