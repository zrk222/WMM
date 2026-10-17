"""Portable follow-up history is passive, never transferred consent authority."""
import json
import re
from datetime import date
from .common import Invalid, canonical, digest, identifier, iso_time
from .followup_policy import validate

KINDS = ("policy", "subject", "task", "handoff")


def export_followup(db, app_id):
    """Serialize exact immutable handoff history plus current versioned inputs."""
    result = {}
    for kind in KINDS:
        result[kind] = []
        for row in db.execute("SELECT * FROM followup_" + kind + " WHERE app_id=? ORDER BY id", (app_id,)):
            item = dict(row); item["data"] = json.loads(item["data"]); result[kind].append(item)
    return result


def validate_rows(app_id, kind, items):
    """Reject hash, scope, identity, version and date tampering before any inserts."""
    if not isinstance(items, list) or len(items) > 1000: raise Invalid("Follow-up snapshot table exceeds 1000 rows")
    ids = set()
    for row in items:
        identity = identifier(row.get("id")); value = row.get("data")
        validate_metadata(app_id, row, identity, ids)
        observed = iso_time(row["updated"]); iso_time(row["created"])
        if kind != "handoff" and validate(kind, value, observed) != value:
            raise Invalid("Follow-up snapshot data is not canonical")
        if kind == "policy" and identity != "policy": raise Invalid("Follow-up policy identity invalid")
        if kind == "handoff": validate_handoff(value)
        ids.add(identity)
    return ids


def validate_metadata(app_id, row, identity, ids):
    """Keep identity and version validation distinct from typed row contents."""
    if row.get("app_id") != app_id or identity in ids or row.get("hash") != digest(row.get("data")):
        raise Invalid("Follow-up snapshot scope, identity or hash mismatch")
    if type(row.get("version")) is not int or row["version"] < 1 or type(row.get("imported")) is not int or row["imported"] not in (0, 1):
        raise Invalid("Follow-up snapshot version invalid")


def validate_handoff(value):
    """An imported handoff is history; it cannot introduce provider actions."""
    expected = {"task_id", "subject_id", "source_hash", "action", "prompt", "delivery", "local_date"}
    if not isinstance(value, dict) or set(value) != expected or value["delivery"] != "MANUAL_HANDOFF_UNSENT":
        raise Invalid("Follow-up handoff snapshot invalid")
    identifier(value["task_id"]); identifier(value["subject_id"])
    from .common import required
    required(value["action"], "Useful checkpoint action", 500); required(value["prompt"], "Checkpoint prompt", 500)
    try: date.fromisoformat(value["local_date"])
    except (ValueError, TypeError) as exc: raise Invalid("Follow-up local date invalid") from exc
    if not isinstance(value["source_hash"], str) or not re.fullmatch(r"[a-f0-9]{64}", value["source_hash"]):
        raise Invalid("Follow-up handoff source binding invalid")


def restore_followup(db, app_id, data):
    """Validate all references, then restore within the caller's atomic transaction."""
    if data is None: return
    if not isinstance(data, dict) or set(data) != set(KINDS): raise Invalid("Follow-up snapshot shape invalid")
    ids = {kind: validate_rows(app_id, kind, data[kind]) for kind in KINDS}
    tasks = {t["id"]: t["data"] for t in data["task"]}
    if any(t["subject_id"] not in ids["subject"] for t in tasks.values()):
        raise Invalid("Follow-up checkpoint subject missing")
    for handoff in data["handoff"]:
        value = handoff["data"]; task = tasks.get(value["task_id"])
        if not task or task["subject_id"] != value["subject_id"]: raise Invalid("Follow-up handoff checkpoint mismatch")
    for kind in KINDS:
        for row in data[kind]:
            db.execute("INSERT INTO followup_" + kind + " VALUES(?,?,?,?,?,?,?,?)",
                       (app_id, row["id"], canonical(row["data"]), row["hash"], row["version"], 1, row["created"], row["updated"]))
