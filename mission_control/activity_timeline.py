"""Read-only chronology over existing app-owned local records.

The projection never rewrites a domain table, never fetches a provider and never
invents a causal edge. A link is reported only when one stored detail identifies
exactly one other projected event.
"""
import base64
import json
import re
from .common import Invalid
from .db import connection

KINDS = ("AUDIT", "JOB", "APPROVAL", "VERIFIED_REVIEW", "PROVIDER_ACTION", "AGENT_GRANT", "SOURCE_READ")
SOURCE_LIMIT = 500
MAX_LIMIT = 200
DEFAULT_LIMIT = 20
SHA256 = re.compile(r"[a-f0-9]{64}")
STATUS = re.compile(r"[A-Z][A-Z0-9_]{0,31}")


def sha(value):
    """Return only a full lowercase digest; anything else stays absent."""
    return value if isinstance(value, str) and SHA256.fullmatch(value) else None


def detail(value):
    """Decode stored audit detail without exposing any other field."""
    try:
        result = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return result if isinstance(result, dict) else {}


def event(kind, raw_id, action, status, at, receipt_hash=None):
    """Keep the event schema closed and payload-free."""
    return {"id": kind + ":" + str(raw_id), "kind": kind, "action": action,
            "status": str(status).upper() if status else None, "at": at,
            "receipt": {"kind": kind, "id": str(raw_id), "sha256": sha(receipt_hash)},
            "caused_by": []}


def rows(db, table, columns, app_id, order="created"):
    """Read a bounded newest-first slice from one app-scoped table."""
    sql = "SELECT " + ",".join(columns) + " FROM " + table + " WHERE app_id=?" + \
          (" AND action!='drive_import'" if table == "jobs" else "") + \
          " ORDER BY " + order + " DESC,id DESC LIMIT " + str(SOURCE_LIMIT)
    return [dict(r) for r in db.execute(sql, (app_id,))]


def collect(db, app_id):
    """Project each supported source once and retain its own bounded coverage."""
    events = []
    counts = {}
    truncated = []
    sources = (
        ("AUDIT", "audit", ("id", "action", "detail", "created")),
        ("JOB", "jobs", ("id", "action", "status", "created")),
        ("APPROVAL", "approvals", ("id", "status", "created", "hash")),
        ("VERIFIED_REVIEW", "verified_reviews", ("id", "status", "created", "hash")),
        ("PROVIDER_ACTION", "provider_actions", ("id", "status", "created", "hash")),
        ("AGENT_GRANT", "agent_grants", ("id", "status", "created")),
        ("SOURCE_READ", "insight_reports", ("id", "created", "hash")),
    )
    for kind, table, columns in sources:
        stored = rows(db, table, columns, app_id)
        counts[kind] = len(stored)
        if len(stored) == SOURCE_LIMIT:
            truncated.append(kind)
        for row in stored:
            if kind == "AUDIT":
                parsed = detail(row["detail"])
                item = event(kind, row["id"], row["action"], None, row["created"],
                             parsed.get("hash") or parsed.get("result_hash") or parsed.get("receipt_hash"))
                item["subject"] = parsed.get("id") if isinstance(parsed.get("id"), str) else None
            elif kind == "JOB":
                item = event(kind, row["id"], row["action"], row["status"], row["created"])
            elif kind == "SOURCE_READ":
                item = event(kind, row["id"], "source.read", None, row["created"], row.get("hash"))
            else:
                item = event(kind, row["id"], kind.lower(), row["status"], row["created"], row.get("hash"))
            events.append(item)
    return events, counts, truncated


def link(events):
    """Attach one exact stored reference; ambiguous or absent references stay absent."""
    index = {}
    for item in events:
        if item["kind"] != "AUDIT":
            index.setdefault(item["receipt"]["id"], []).append(item["id"])
    for item in events:
        subject = item.pop("subject", None)
        if not subject or subject not in index:
            continue
        matches = index[subject]
        if len(matches) == 1 and matches[0] != item["id"]:
            item["caused_by"] = matches
    return events


def encode(value):
    """Encode a stable cursor from the last returned event's sort key."""
    return base64.urlsafe_b64encode(json.dumps(value, separators=(",", ":")).encode()).decode()


def decode(value):
    """Reject malformed or oversized cursors before touching stored rows."""
    if not isinstance(value, str) or not value or len(value) > 512:
        raise Invalid("Activity cursor is invalid")
    try:
        result = json.loads(base64.urlsafe_b64decode(value.encode()))
    except (ValueError, TypeError) as exc:
        raise Invalid("Activity cursor is invalid") from exc
    if (not isinstance(result, list) or len(result) != 3
            or not all(isinstance(part, str) for part in result)):
        raise Invalid("Activity cursor is invalid")
    return tuple(result)


def read(store, app_id, *, kind=None, status=None, cursor=None, limit=DEFAULT_LIMIT):
    """Return one stable page of app-owned events with explicit coverage."""
    store.app(app_id)
    if kind is not None and kind not in KINDS:
        raise Invalid("Activity kind must be one of: " + ", ".join(KINDS))
    if status is not None and (not isinstance(status, str) or not STATUS.fullmatch(status)):
        raise Invalid("Activity status must be an uppercase token")
    if not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
        raise Invalid("Activity limit must be between 1 and " + str(MAX_LIMIT))
    point = decode(cursor) if cursor is not None else None
    with connection(store.path) as db:
        events, counts, truncated = collect(db, app_id)
    events = link(events)
    if kind is not None:
        events = [item for item in events if item["kind"] == kind]
    if status is not None:
        events = [item for item in events if item["status"] == status]
    events.sort(key=lambda item: (item["at"], item["kind"], item["id"]), reverse=True)
    if point is not None:
        events = [item for item in events if (item["at"], item["kind"], item["id"]) < point]
    page = events[:limit]
    more = len(events) > len(page)
    next_cursor = encode([page[-1]["at"], page[-1]["kind"], page[-1]["id"]]) if more else None
    return {"schema": "growth.activity-timeline.v1", "app_id": app_id, "events": page,
            "filters": {"kind": kind, "status": status},
            "next_cursor": next_cursor, "complete": not more,
            "coverage": {"scope": "APP_OWNED_LOCAL_RECORDS_ONLY", "counts": counts,
                         "truncated_sources": truncated},
            "boundary": "Joined local records only; provider effects, missing links and external activity are not inferred."}
