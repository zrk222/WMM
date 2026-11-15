"""Secret-free task continuity for existing worker jobs; never grants execution."""

from datetime import datetime, timedelta, timezone
import json
import re

from .agent_grants import current
from .common import Invalid, canonical, digest, iso_time, uid
from .db import connection
from .marketing_agent_manifest import operating_manifest
from .operation_catalog import OPERATIONS, catalog, exact_keys, path_segment
from .review_access import exact_role, member
from .store import audit


def _utc():
    return datetime.now(timezone.utc)


def _app(db, app_id):
    row = db.execute("SELECT * FROM apps WHERE id=?", (app_id,)).fetchone()
    if not row:
        raise Invalid("App workspace is unavailable")
    app = dict(row)
    app["data"] = json.loads(app["data"])
    return app


def _job(db, app_id, identity):
    row = db.execute("SELECT * FROM jobs WHERE app_id=? AND id=?", (app_id, identity)).fetchone()
    if not row:
        raise Invalid("Choose an existing app-owned worker job; native-only jobs are not supported")
    return row


def _fingerprint(row):
    return digest({key: row[key] for key in ("id", "app_id", "action", "data", "request_key", "created")})


RESOURCE_TABLES = {
    "connection_id": (
        ("records", "id", "version,hash"),
        ("agent_connections", "id", "version"),
        ("drive_connections", "id", "version"),
        ("social_connections", "id", "version"),
    ),
    "experiment_id": (("experiments", "id", "version,hash"),),
    "brief_id": (("creative_briefs", "id", "version,hash"),),
    "project_id": (
        ("video_project_heads", "id", "revision"),
        ("studio_source_heads", "project_id", "version"),
        ("ios_studio_projects", "id", "revision,source_hash"),
    ),
    "media_id": (("managed_media", "id", "hash"),),
    "asset_id": (("managed_media", "id", "hash"),),
    "source_id": (
        ("insight_sources", "id", "version,hash"),
        ("records", "id", "version,hash"),
        ("storekit_sources", "id", "version,hash"),
        ("attribution_sources", "id", "version,hash"),
    ),
    "record_id": (("records", "id", "version,hash"),),
    "profile_id": (("production_profiles", "id", "version,hash"), ("agent_connections", "id", "version")),
}


def _resource_ids(value, found, unknown):
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str) and key.endswith("_id") and isinstance(item, str):
                if key in RESOURCE_TABLES:
                    found.add((key, item))
                elif key not in ("app_id", "job_id"):
                    unknown.add(key)
            elif isinstance(key, str) and key.endswith("_ids") and isinstance(item, list):
                singular = key[:-1]
                if singular in RESOURCE_TABLES:
                    found.update((singular, identity) for identity in item if isinstance(identity, str))
                elif key not in ("job_ids",):
                    unknown.add(key)
            _resource_ids(item, found, unknown)
    elif isinstance(value, list):
        for item in value:
            _resource_ids(item, found, unknown)


def _resources(db, app_id, job):
    found = set()
    unknown = set()
    _resource_ids(json.loads(job["data"]), found, unknown)
    if len(found) > 100:
        raise Invalid("Job references too many resources for a handoff")
    bindings = []
    for key, identity in sorted(found):
        for table, column, fields in RESOURCE_TABLES[key]:
            rows = db.execute(
                f"SELECT {fields} FROM {table} WHERE app_id=? AND {column}=? ORDER BY {fields}", (app_id, identity)
            ).fetchall()
            bindings.append([key, digest(identity), table, [list(row) for row in rows]])
    return dict(
        hash=digest(bindings),
        checked_fields=sorted({key for key, _ in found}),
        unverified_field_count=len(unknown),
        coverage="ALLOWLISTED_REFERENCES_ONLY",
    )


def _context(db, app_id, job):
    app = _app(db, app_id)
    return dict(
        app_version=app["version"],
        app_hash=digest(app["data"]),
        policy_hash=digest(operating_manifest(app)),
        catalog_hash=catalog()["catalog_sha256"],
        job_hash=_fingerprint(job),
        request_key_hash=digest(job["request_key"]),
        resources=_resources(db, app_id, job),
    )


def _names(value):
    if (
        not isinstance(value, list)
        or not value
        or len(value) > 100
        or any(
            not isinstance(x, str)
            or x not in OPERATIONS
            or x.startswith("handoff.")
            or x in ("experiment.schedule", "experiment.schedule-run")
            for x in value
        )
    ):
        raise Invalid("Choose 1 through 100 supported continuation operations")
    if len(value) != len(set(value)):
        raise Invalid("Continuation operations must be unique")
    return sorted(value)


def _source(db, app_id, user):
    if user is not None:
        role = member(db, app_id, user["principal"], "OWNER")
        return dict(kind="OWNER", principal=user["principal"], role_version=role["version"])
    from .operation_authority import PROTECTED, check

    context = PROTECTED.get()
    if not context or "grant_id" not in context:
        raise PermissionError("Current scoped agent admission is required")
    check(db, context)
    row = db.execute("SELECT * FROM agent_grants WHERE id=?", (context["grant_id"],)).fetchone()
    if not row or row["app_id"] != app_id:
        raise PermissionError("Source grant is unavailable")
    from .authority_expiry import effective_expiry

    expiry = effective_expiry(db, "AGENT_GRANT", row, row["expires"])["expires"]
    return dict(kind="AGENT", grant_id=row["id"], grant_version=row["version"], expires=expiry)


def _check_source(db, app_id, source, observed):
    if source["kind"] == "OWNER":
        exact_role(db, app_id, source["principal"], source["role_version"], "OWNER")
        return
    row = db.execute("SELECT * FROM agent_grants WHERE id=?", (source["grant_id"],)).fetchone()
    if row is None or row["version"] != source["grant_version"]:
        raise PermissionError("Source grant changed; ask the owner to prepare a fresh handoff")
    current(db, row, dict(app_id=app_id, operation="handoff.create"), observed, check_quota=False)


def _read(row):
    payload = json.loads(row["payload"])
    if digest(payload) != row["payload_hash"]:
        raise Invalid("Handoff integrity failed")
    return payload


def _view(db, row, job, observed):
    payload = _read(row)
    current_context = _context(db, row["app_id"], job)
    changes = sorted(key for key in payload["context"] if payload["context"][key] != current_context[key])
    effective = row["status"]
    if effective != "REVOKED":
        if iso_time(row["expires"]) <= observed:
            effective = "EXPIRED"
        elif changes:
            effective = "CONTEXT_CHANGED"
        else:
            try:
                _check_source(db, row["app_id"], payload["source"], observed)
            except (Invalid, PermissionError, KeyError):
                effective = "SOURCE_INVALID"
        if effective == "CLAIMED":
            try:
                grant = db.execute("SELECT * FROM agent_grants WHERE id=?", (row["claimed_grant_id"],)).fetchone()
                if not grant or grant["agent_id"] != row["recipient"]:
                    raise PermissionError("Recipient changed")
                current(db, grant, dict(app_id=row["app_id"], operation="handoff.resume"), observed, check_quota=False)
            except (Invalid, PermissionError, KeyError):
                effective = "RECIPIENT_INVALID"
    next_action = (
        "Prepare a fresh handoff after reviewing current authority and context."
        if effective in ("EXPIRED", "CONTEXT_CHANGED", "SOURCE_INVALID", "RECIPIENT_INVALID")
        else "Inspect the original job and reconcile uncertain work before any separately authorized action."
    )
    return dict(
        id=row["id"],
        app_id=row["app_id"],
        recipient=row["recipient"],
        version=row["version"],
        status=row["status"],
        effective_status=effective,
        payload_hash=row["payload_hash"],
        created=row["created"],
        expires=row["expires"],
        job_id=payload["job_id"],
        job_action=payload["job_action"],
        job_status=job["status"],
        request_key_hash=payload["context"]["request_key_hash"],
        context=payload["context"],
        operations=payload["operations"],
        source_kind=payload["source"]["kind"],
        context_status="CHANGED" if changes else "CURRENT",
        context_changes=changes,
        authority_issued=False,
        execution="NOT_STARTED_BY_HANDOFF",
        next_action=next_action,
    )


def _resume_row(db, app_id, body, context, observed):
    row = db.execute("SELECT * FROM agent_handoffs WHERE app_id=? AND id=?", (app_id, body["id"])).fetchone()
    if (
        not row
        or row["status"] == "REVOKED"
        or row["payload_hash"] != body["payload_hash"]
        or iso_time(row["expires"]) <= observed
    ):
        raise PermissionError("Handoff is unavailable, changed or expired")
    payload = _read(row)
    grant = db.execute("SELECT * FROM agent_grants WHERE id=?", (context["grant_id"],)).fetchone()
    if not grant or grant["agent_id"] != row["recipient"]:
        raise PermissionError("Handoff belongs to another recipient")
    _check_source(db, app_id, payload["source"], observed)
    job = _job(db, app_id, payload["job_id"])
    if _context(db, app_id, job) != payload["context"]:
        raise Invalid("Handoff context changed; prepare a fresh handoff")
    return row, payload, grant, job


def _claim(db, app_id, body, row, grant, observed):
    if row["status"] == "READY":
        if row["version"] != body["version"]:
            raise Invalid("Handoff revision changed; reload")
        db.execute(
            "UPDATE agent_handoffs SET status='CLAIMED',claimed_grant_id=?,claimed_at=?,version=version+1 WHERE id=?",
            (grant["id"], observed.isoformat(), row["id"]),
        )
        audit(db, app_id, "agent_handoff.claimed", dict(id=row["id"], grant_id=grant["id"]))
    elif row["claimed_grant_id"] != grant["id"] or body["version"] not in (row["version"], row["version"] - 1):
        raise PermissionError("Handoff was already claimed by another grant")


def _report_item(db, app_id, row, observed):
    from uuid import UUID

    if str(UUID(row["id"])) != row["id"]:
        raise ValueError()
    payload = _read(row)
    job = _job(db, app_id, payload["job_id"])
    if str(UUID(job["id"])) != job["id"]:
        raise ValueError()
    view = _view(db, row, job, observed)
    action = (
        job["action"]
        if job["action"]
        in (
            "pipeline",
            "sync",
            "render",
            "hypit_render",
            "edit_render",
            "drive_import",
            "agent_run",
            "resolution",
            "experiment",
            "experiment_tracking",
            "campaign_post",
            "campaign_ad",
            "campaign_monitor",
            "campaign_owner_report",
        )
        else "OTHER"
    )
    state = (
        job["status"]
        if job["status"] in ("QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED", "BLOCKED", "PREPARED", "UNKNOWN")
        else "UNKNOWN"
    )
    if view["source_kind"] not in ("OWNER", "AGENT"):
        raise ValueError()
    return dict(
        id=row["id"],
        job_id=job["id"],
        job_action=action,
        job_status=state,
        status=view["effective_status"],
        source_kind=view["source_kind"],
        created=iso_time(row["created"]).isoformat(),
        expires=iso_time(row["expires"]).isoformat(),
        context_status=view["context_status"],
        context_changes=view["context_changes"],
    )


def report_summary(db, app_id, observed):
    """Project only bounded app-owned task receipts for the existing report permission."""
    total = db.execute("SELECT count(*) FROM agent_handoffs WHERE app_id=?", (app_id,)).fetchone()[0]
    counts = {key: 0 for key in ("READY", "CLAIMED", "REVOKED")}
    for count in db.execute(
        "SELECT status,count(*) AS n FROM agent_handoffs WHERE app_id=? GROUP BY status", (app_id,)
    ):
        if count["status"] in counts:
            counts[count["status"]] = count["n"]
    rows = db.execute(
        "SELECT * FROM agent_handoffs WHERE app_id=? ORDER BY created DESC,id LIMIT 20", (app_id,)
    ).fetchall()
    items = []
    for row in rows:
        try:
            items.append(_report_item(db, app_id, row, observed))
        except (Invalid, PermissionError, ValueError, KeyError, TypeError):
            items.append(dict(status="UNAVAILABLE"))
    attention = any(
        item["status"] in ("UNAVAILABLE", "EXPIRED", "SOURCE_INVALID", "RECIPIENT_INVALID", "CONTEXT_CHANGED")
        for item in items
    )
    action = (
        "Review changed, expired or unavailable handoffs before continuing."
        if attention
        else "Inspect the original job and reconcile uncertain work before any separately authorized action."
        if items
        else "No handoffs are recorded for this app."
    )
    effective_counts = {
        key: sum(item["status"] == key for item in items)
        for key in (
            "READY",
            "CLAIMED",
            "REVOKED",
            "EXPIRED",
            "SOURCE_INVALID",
            "RECIPIENT_INVALID",
            "CONTEXT_CHANGED",
            "UNAVAILABLE",
        )
    }
    return dict(
        total=total,
        returned=len(items),
        truncated=total > len(items),
        status_counts=counts,
        recent_effective_counts=effective_counts,
        items=items,
        scope="TASK_CONTEXT_ONLY_NO_PROVIDER_EFFECT_OR_EXECUTION_AUTHORITY",
        next_action=action,
    )


class Handoffs:
    def __init__(self, store, clock=None):
        self.store = store
        self.clock = clock or _utc

    def create(self, app_id, user, body):
        exact_keys(body, ("job_id", "recipient", "operations", "expires"))
        path_segment(app_id)
        path_segment(body["job_id"])
        path_segment(body["recipient"])
        names = _names(body["operations"])
        observed = self.clock()
        expires = iso_time(body["expires"])
        if not observed < expires <= observed + timedelta(hours=24):
            raise Invalid("Handoff expiry must be within 24 hours")
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            source = _source(db, app_id, user)
            job = _job(db, app_id, body["job_id"])
            if source["kind"] == "AGENT":
                grant = db.execute("SELECT * FROM agent_grants WHERE id=?", (source["grant_id"],)).fetchone()
                if not set(names).issubset(json.loads(grant["operations"])) or expires > iso_time(source["expires"]):
                    raise PermissionError("Handoff cannot exceed source grant scope or expiry")
            payload = dict(
                schema="growth.agent-handoff.v1",
                job_id=job["id"],
                job_action=job["action"],
                context=_context(db, app_id, job),
                source=source,
                operations=names,
            )
            identity = uid()
            stamp = observed.isoformat()
            encoded = canonical(payload)
            db.execute(
                "INSERT INTO agent_handoffs VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    identity,
                    app_id,
                    source.get("grant_id"),
                    body["recipient"],
                    encoded,
                    digest(payload),
                    stamp,
                    expires.isoformat(),
                    "READY",
                    None,
                    None,
                    1,
                ),
            )
            audit(db, app_id, "agent_handoff.created", dict(id=identity, job_id=job["id"]))
            return _view(
                db, db.execute("SELECT * FROM agent_handoffs WHERE id=?", (identity,)).fetchone(), job, observed
            )

    def list(self, app_id, user):
        with connection(self.store.path) as db:
            member(db, app_id, user["principal"], "OWNER")
            rows = db.execute(
                "SELECT * FROM agent_handoffs WHERE app_id=? ORDER BY created DESC,id LIMIT 100", (app_id,)
            ).fetchall()
            observed = self.clock()
            return dict(
                handoffs=[_view(db, row, _job(db, app_id, _read(row)["job_id"]), observed) for row in rows], limit=100
            )

    def revoke(self, app_id, user, body):
        exact_keys(body, ("id", "version"))
        path_segment(body["id"])
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            member(db, app_id, user["principal"], "OWNER")
            row = db.execute("SELECT * FROM agent_handoffs WHERE app_id=? AND id=?", (app_id, body["id"])).fetchone()
            if (
                not row
                or type(body["version"]) is not int
                or row["version"] != body["version"]
                or row["status"] == "REVOKED"
            ):
                raise Invalid("Handoff revision changed; reload")
            db.execute("UPDATE agent_handoffs SET status='REVOKED',version=version+1 WHERE id=?", (row["id"],))
            audit(db, app_id, "agent_handoff.revoked", dict(id=row["id"]))
            return _view(
                db,
                db.execute("SELECT * FROM agent_handoffs WHERE id=?", (row["id"],)).fetchone(),
                _job(db, app_id, _read(row)["job_id"]),
                self.clock(),
            )

    def resume(self, app_id, body):
        exact_keys(body, ("id", "version", "payload_hash"))
        path_segment(body["id"])
        if (
            type(body["version"]) is not int
            or not isinstance(body["payload_hash"], str)
            or not re.fullmatch("[a-f0-9]{64}", body["payload_hash"])
        ):
            raise Invalid("Use the exact handoff version and hash")
        from .operation_authority import PROTECTED, check

        context = PROTECTED.get()
        if not context or "grant_id" not in context:
            raise PermissionError("Current recipient grant is required")
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            check(db, context)
            observed = self.clock()
            row, payload, grant, job = _resume_row(db, app_id, body, context, observed)
            _claim(db, app_id, body, row, grant, observed)
            updated = db.execute("SELECT * FROM agent_handoffs WHERE id=?", (row["id"],)).fetchone()
            value = _view(db, updated, job, observed)
            value.update(
                resume="RESUME_ADMITTED",
                operations=sorted(set(payload["operations"]) & set(json.loads(grant["operations"]))),
            )
            return value
