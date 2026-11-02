"""Finite exact-intent owner monitoring; never publish, create or activate effects."""

import json
import time
from .common import Invalid, canonical, digest, iso_time, now, uid
from .db import connection
from .review_access import member
from .social_contract import reference

SCHEMA = """
CREATE TABLE IF NOT EXISTS campaign_monitors (
 id TEXT PRIMARY KEY, app_id TEXT NOT NULL, owner TEXT NOT NULL,
 summary TEXT NOT NULL, summary_hash TEXT NOT NULL, status TEXT NOT NULL,
 version INTEGER NOT NULL, due REAL NOT NULL, runs INTEGER NOT NULL DEFAULT 0,
 units INTEGER NOT NULL DEFAULT 0, pauses INTEGER NOT NULL DEFAULT 0,
 last_job TEXT, created TEXT NOT NULL, updated TEXT NOT NULL);
"""
CONDITIONS = ("configuration_drift", "active_after_end")
FIELDS = (
    "scope_id",
    "targets",
    "cadence_seconds",
    "expires_at",
    "max_runs",
    "max_provider_units",
    "max_pause_attempts",
    "protective_conditions",
)


def initialize(store):
    with connection(store.path) as db:
        db.executescript(SCHEMA)


def whole(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise Invalid("Monitor resource allowance is outside its supported bounds")


def proposal(body):
    """Close finite choices before inspecting exact existing resources."""
    if not isinstance(body, dict) or set(body) != set(FIELDS):
        raise Invalid("Use the exact monitor proposal fields")
    reference(body["scope_id"])
    whole(body["cadence_seconds"], 30, 3600)
    whole(body["max_runs"], 1, 100)
    whole(body["max_provider_units"], 1, 160)
    whole(body["max_pause_attempts"], 0, 20)
    _targets(body["targets"])
    _conditions(body["protective_conditions"], body["max_pause_attempts"])
    iso_time(body["expires_at"])
    return json.loads(canonical(body))


def _targets(targets):
    if not isinstance(targets, list) or not 1 <= len(targets) <= 20:
        raise Invalid("Select one to twenty existing campaign intents")
    from .campaign_contract import hashes

    for target in targets:
        if not isinstance(target, dict) or set(target) != {"intent_id", "request_hash"}:
            raise Invalid("Bind each exact intent ID and request hash")
        reference(target["intent_id"])
        hashes([target["request_hash"]], True)
    if len({target["intent_id"] for target in targets}) != len(targets):
        raise Invalid("Monitor intent IDs must be distinct")


def _conditions(conditions, attempts):
    if not isinstance(conditions, list) or any(
        not isinstance(c, str) for c in conditions
    ):
        raise Invalid("Protective conditions must be named strings")
    if len(set(conditions)) != len(conditions) or any(
        c not in CONDITIONS for c in conditions
    ):
        raise Invalid("Select only the displayed protective conditions")
    if bool(conditions) != bool(attempts):
        raise Invalid(
            "Approve protective conditions and finite pause attempts together"
        )


def actor(store, app_id):
    from .campaign_access import identity

    context, principal = identity(store, app_id)
    if "principal" not in context:
        raise PermissionError(
            "Only a freshly authenticated owner may manage monitoring"
        )
    return principal


def source(db, app_id, principal, scope_id):
    """Bind exact app, owner, connection/config revisions and campaign summary."""
    role = member(db, app_id, principal, "OWNER")
    row = db.execute(
        "SELECT * FROM campaign_scopes WHERE app_id=? AND id=? AND owner=?",
        (app_id, scope_id, principal),
    ).fetchone()
    if row is None:
        raise Invalid("Campaign scope is unavailable for this owner")
    scope = json.loads(row["summary"])
    if digest(scope) != row["summary_hash"]:
        raise Invalid("Campaign approval integrity changed")
    app = db.execute("SELECT * FROM apps WHERE id=?", (app_id,)).fetchone()
    if (
        scope["owner_principal"],
        scope["owner_version"],
        scope["app_version"],
        scope["app_hash"],
    ) != (principal, role["version"], app["version"], digest(json.loads(app["data"]))):
        raise PermissionError("Campaign app or owner revision changed")
    if (
        row["status"] != "ACTIVE"
        or iso_time(scope["expires_at"]).timestamp() <= time.time()
    ):
        raise PermissionError("Campaign approval is OFF or expired")
    connection_row = db.execute(
        "SELECT * FROM social_connections WHERE app_id=? AND id=?",
        (app_id, scope["connection_id"]),
    ).fetchone()
    config = db.execute(
        "SELECT * FROM social_configs WHERE app_id=? AND provider='facebook'", (app_id,)
    ).fetchone()
    check_connection(connection_row, config, scope)
    return dict(
        scope_id=scope_id,
        scope_hash=row["summary_hash"],
        app_version=app["version"],
        app_hash=scope["app_hash"],
        owner_version=role["version"],
        connection_hash=digest(dict(connection_row)),
        config_hash=digest(dict(config)),
    ), scope


def check_connection(row, config, scope):
    """Saved identity is a dispatch prerequisite, never new provider authority."""
    if row is None or config is None:
        raise PermissionError("Campaign connection is unavailable")
    data = json.loads(row["data"])
    expected = (
        scope["connection_version"],
        "CONNECTED_READ_TESTED",
        "facebook",
        scope["page_id"],
    )
    if (
        row["version"],
        row["status"],
        row["provider"],
        data["destination"]["id"],
    ) != expected:
        raise PermissionError("Campaign connection identity changed")
    if row["lease"] or row["expires"] is None or row["expires"] <= time.time():
        raise PermissionError("Campaign connection expiry or renewal needs review")
    if config["version"] != row["config_version"] or config["status"] == "DISCONNECTED":
        raise PermissionError("Campaign developer configuration changed")


def target_row(db, app_id, scope_id, target):
    """Never resolve a target outside its app, scope and immutable request hash."""
    for table in ("campaign_paid_intents", "campaign_intents"):
        row = db.execute(
            "SELECT * FROM "
            + table
            + " WHERE app_id=? AND scope_id=? AND id=? AND request_hash=?",
            (app_id, scope_id, target["intent_id"], target["request_hash"]),
        ).fetchone()
        if row is not None:
            if (
                table == "campaign_paid_intents"
                and digest(json.loads(row["data"])) != row["request_hash"]
            ):
                raise PermissionError("Paid request integrity changed")
            return row, table == "campaign_paid_intents"
    raise PermissionError("Monitor target changed or is outside its campaign scope")


def checked(db, row):
    """Recheck retained owner authority without taking the owner's actor identity."""
    if row is None:
        raise PermissionError("Monitor is unavailable")
    summary = json.loads(row["summary"])
    if (summary["app_id"], summary["owner"]) != (row["app_id"], row["owner"]):
        raise PermissionError("Monitor summary ownership changed")
    if digest(summary) != row["summary_hash"]:
        raise PermissionError("Monitor approval integrity changed")
    if (
        row["status"] != "ACTIVE"
        or iso_time(summary["proposal"]["expires_at"]).timestamp() <= time.time()
    ):
        raise PermissionError("Monitor is OFF or expired")
    current, _ = source(
        db, row["app_id"], row["owner"], summary["proposal"]["scope_id"]
    )
    if current != summary["source"]:
        raise PermissionError("Monitor source revisions changed")
    for target in summary["proposal"]["targets"]:
        target_row(db, row["app_id"], summary["proposal"]["scope_id"], target)
    return summary


def view(db, row):
    summary = json.loads(row["summary"])
    effective = row["status"]
    if effective == "ACTIVE":
        try:
            checked(db, row)
        except (Invalid, PermissionError, ValueError, KeyError):
            effective = "BLOCKED"
    return dict(
        id=row["id"],
        version=row["version"],
        status=row["status"],
        effective_status=effective,
        summary=summary,
        summary_hash=row["summary_hash"],
        runs=row["runs"],
        provider_units=row["units"],
        pause_attempts=row["pauses"],
        last_job=row["last_job"],
        last_observation=last_observation(db, row, summary),
        next_due=row["due"],
    )


def last_observation(db, row, summary):
    """Project only exact owned monitor-job receipts, never arbitrary raw results."""
    if not row["last_job"]:
        return None
    job = db.execute(
        "SELECT id,app_id,action,data,status,result,updated FROM jobs WHERE id=?",
        (row["last_job"],),
    ).fetchone()
    if job is None or (job["app_id"], job["action"]) != (
        row["app_id"],
        "campaign_monitor",
    ):
        return None
    if not _observation_job(job, row):
        return None
    raw = _small_object(job["result"])
    observations = raw.get("observations", [])
    if not isinstance(observations, list) or len(observations) > 20:
        observations = []
    targets = {value["intent_id"] for value in summary["proposal"]["targets"]}
    safe = [
        value
        for item in observations
        if (value := _observation(item, targets)) is not None
    ]
    return dict(
        job_id=job["id"],
        status=job["status"],
        updated=job["updated"],
        observations=safe,
    )


def _observation_job(job, row):
    data = _small_object(job["data"])
    expected = {"monitor_id", "monitor_version", "summary_hash", "run"}
    if set(data) != expected or (data["monitor_id"], data["summary_hash"]) != (
        row["id"],
        row["summary_hash"],
    ):
        return False
    if (
        type(data["monitor_version"]) is not int
        or not 1 <= data["monitor_version"] <= row["version"]
    ):
        return False
    if type(data["run"]) is not int or not 1 <= data["run"] <= row["runs"]:
        return False
    states = (
        "QUEUED",
        "RUNNING",
        "SUCCEEDED",
        "BLOCKED",
        "FAILED",
        "CANCELLED",
        "UNKNOWN",
    )
    if job["status"] not in states:
        return False
    return True


def _small_object(raw):
    if not isinstance(raw, str) or len(raw) > 65536:
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _observation(item, targets):
    if not isinstance(item, dict) or not isinstance(item.get("intent_id"), str):
        return None
    if item["intent_id"] not in targets or not isinstance(item.get("status"), str):
        return None
    states = {
        "UNKNOWN",
        "DISPATCHING",
        "ACKNOWLEDGED",
        "VERIFYING",
        "VERIFIED",
        "RESERVED",
        "CREATED_campaign",
        "CREATED_adset",
        "CREATED_creative",
        "CREATED_ad",
        "ACTIVE_adset",
        "ACTIVE_ad",
        "ACTIVE_campaign",
        "ACK_ACTIVE_adset",
        "ACK_ACTIVE_ad",
        "ACK_ACTIVE_campaign",
        "ACK_PAUSED_campaign",
        "PAUSED_campaign",
    }
    pending = {
        "PENDING_" + step
        for step in (
            "CREATE_campaign",
            "CREATE_adset",
            "CREATE_creative",
            "CREATE_ad",
            "ACTIVE_adset",
            "ACTIVE_ad",
            "ACTIVE_campaign",
            "PAUSED_campaign",
        )
    }
    if item.get("status") not in states | pending:
        return None
    result = dict(intent_id=item["intent_id"], status=item["status"])
    recovery = item.get("recovery")
    if isinstance(recovery, str) and recovery in (
        "IN_FLIGHT",
        "OWNER_UNVERIFIED",
        "LEASE_STATE_CONFLICT",
        "ABANDONED_UNKNOWN",
    ):
        result["recovery"] = recovery
    if item.get("protective_pause") == "PAUSED_campaign":
        result["protective_pause"] = "PAUSED_campaign"
    commitment = item.get("commitment_held_minor")
    if type(commitment) is int and 0 <= commitment <= 100000000:
        result["commitment_held_minor"] = commitment
    return result


class Monitors:
    """Fresh-owner prepare/activate/OFF with a finite retained monitoring capability."""

    def __init__(self, store):
        self.store = store
        initialize(store)

    def prepare(self, app_id, body):
        principal = actor(self.store, app_id)
        chosen = proposal(body)
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            binding, scope = source(db, app_id, principal, chosen["scope_id"])
            expiry = iso_time(chosen["expires_at"]).timestamp()
            if not time.time() < expiry <= iso_time(scope["expires_at"]).timestamp():
                raise Invalid(
                    "Monitor expiry must be future and within campaign expiry"
                )
            for target in chosen["targets"]:
                target_row(db, app_id, chosen["scope_id"], target)
            identity = uid()
            summary = dict(
                schema="wmm.campaign-monitor.v1",
                app_id=app_id,
                owner=principal,
                source=binding,
                proposal=chosen,
                effects=["RECONCILE"]
                + (["PROTECTIVE_PAUSE"] if chosen["protective_conditions"] else []),
                limitations="Saved identity and fresh provider readback required. No spend-threshold conversion, causal lift, creation, publication or activation.",
            )
            stamp = now()
            db.execute(
                "INSERT INTO campaign_monitors VALUES(?,?,?,?,?,?,1,?,0,0,0,NULL,?,?)",
                (
                    identity,
                    app_id,
                    principal,
                    canonical(summary),
                    digest(summary),
                    "DRAFT",
                    time.time(),
                    stamp,
                    stamp,
                ),
            )
            return view(
                db,
                db.execute(
                    "SELECT * FROM campaign_monitors WHERE id=?", (identity,)
                ).fetchone(),
            )

    def activate(self, app_id, identity, summary_hash):
        principal = actor(self.store, app_id)
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            row = owned(db, app_id, principal, identity)
            if row["status"] != "DRAFT" or row["summary_hash"] != summary_hash:
                raise Invalid("Monitor approval changed; review the exact plan")
            candidate = dict(row, status="ACTIVE")
            checked(db, candidate)
            db.execute(
                "UPDATE campaign_monitors SET status='ACTIVE',version=version+1,updated=? WHERE id=?",
                (now(), identity),
            )
        return self.status(app_id, identity)

    def status(self, app_id, identity):
        principal = actor(self.store, app_id)
        with connection(self.store.path) as db:
            return view(db, owned(db, app_id, principal, identity))

    def history(self, app_id):
        principal = actor(self.store, app_id)
        with connection(self.store.path) as db:
            member(db, app_id, principal, "OWNER")
            return dict(
                monitors=[
                    view(db, row)
                    for row in db.execute(
                        "SELECT * FROM campaign_monitors WHERE app_id=? AND owner=? ORDER BY created DESC,id LIMIT 50",
                        (app_id, principal),
                    )
                ]
            )

    def off(self, app_id, identity, version):
        principal = actor(self.store, app_id)
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            row = owned(db, app_id, principal, identity)
            if type(version) is not int or row["version"] != version:
                raise Invalid("Monitor revision changed")
            db.execute(
                "UPDATE campaign_monitors SET status='OFF',version=version+1,updated=? WHERE id=?",
                (now(), identity),
            )
            db.execute(
                "UPDATE jobs SET status='CANCELLED',updated=? WHERE app_id=? AND id=? AND status='QUEUED'",
                (now(), app_id, row["last_job"]),
            )
        return self.status(app_id, identity)


def owned(db, app_id, principal, identity):
    reference(identity)
    member(db, app_id, principal, "OWNER")
    row = db.execute(
        "SELECT * FROM campaign_monitors WHERE app_id=? AND owner=? AND id=?",
        (app_id, principal, identity),
    ).fetchone()
    if row is None:
        raise Invalid("Monitor is unavailable for this owner")
    return row


def tick(store):
    """Queue at most twenty due finite runs; interrupted attempts stop without replay."""
    initialize(store)
    count = 0
    with connection(store.path) as db:
        db.execute("BEGIN IMMEDIATE")
        rows = db.execute(
            "SELECT * FROM campaign_monitors WHERE status='ACTIVE' AND due<=? ORDER BY due,id LIMIT 20",
            (time.time(),),
        ).fetchall()
        for row in rows:
            if not eligible(db, row):
                continue
            count += queue(db, row)
    return count


def eligible(db, row):
    try:
        summary = checked(db, row)
    except (Invalid, PermissionError, ValueError, KeyError):
        block(db, row["id"])
        return False
    if not _previous_finished(db, row):
        return False
    limits = summary["proposal"]
    if (
        row["runs"] >= limits["max_runs"]
        or row["units"] >= limits["max_provider_units"]
    ):
        block(db, row["id"])
        return False
    return True


def _previous_finished(db, row):
    if not row["last_job"]:
        return True
    old = db.execute(
        "SELECT status,lease FROM jobs WHERE id=?", (row["last_job"],)
    ).fetchone()
    if old and old["status"] in ("QUEUED", "RUNNING"):
        if old["status"] == "RUNNING" and old["lease"] <= time.time():
            block(db, row["id"])
            db.execute(
                "UPDATE jobs SET status='BLOCKED',updated=? WHERE id=?",
                (now(), row["last_job"]),
            )
        return False
    if old is None or old["status"] != "SUCCEEDED":
        block(db, row["id"])
        return False
    return True


def block(db, identity):
    db.execute(
        "UPDATE campaign_monitors SET status='BLOCKED',updated=? WHERE id=? AND status='ACTIVE'",
        (now(), identity),
    )


def queue(db, row):
    summary = json.loads(row["summary"])
    identity = uid()
    data = dict(
        monitor_id=row["id"],
        monitor_version=row["version"],
        summary_hash=row["summary_hash"],
        run=row["runs"] + 1,
    )
    stamp = now()
    db.execute(
        "INSERT INTO jobs(id,app_id,action,data,status,created,updated,request_key) VALUES(?,?,?,?,?,?,?,?)",
        (
            identity,
            row["app_id"],
            "campaign_monitor",
            canonical(data),
            "QUEUED",
            stamp,
            stamp,
            "campaign-monitor-" + row["id"] + "-" + str(data["run"]),
        ),
    )
    db.execute(
        "UPDATE campaign_monitors SET runs=runs+1,last_job=?,due=?,updated=? WHERE id=?",
        (
            identity,
            time.time() + summary["proposal"]["cadence_seconds"],
            stamp,
            row["id"],
        ),
    )
    return 1


def execute(store, job, transport=None):
    """Only reconcile and specifically approved pause; never resume an uncertain mutation."""
    from .campaign_monitor_authority import bound, BoundaryTransport, MonitorService
    from .campaign_access import policy_checker

    results = []
    with bound(store, job) as capability:
        service = MonitorService(
            store, policy_checker(store), BoundaryTransport(store, transport)
        )
        try:
            for target in capability["summary"]["proposal"]["targets"]:
                capability.update(intent_id=target["intent_id"], action="RECONCILE")
                result = service.reconcile(
                    job["app_id"],
                    "monitor:" + job["id"],
                    capability["scope_id"],
                    target["intent_id"],
                )
                results.append(
                    dict(
                        intent_id=target["intent_id"],
                        status=result["status"],
                        recovery=result.get("recovery"),
                    )
                )
                paused = protect(store, job, service, capability, result)
                if paused is not None:
                    results[-1]["protective_pause"] = paused["status"]
                    results[-1]["commitment_held_minor"] = paused["commitment"]
            return dict(
                status="OBSERVED",
                observations=results,
                authority="EXACT_RETAINED_MONITOR_ONLY",
            )
        except Exception:
            with connection(store.path) as db:
                block(db, job["data"]["monitor_id"])
            return dict(
                status="BLOCKED",
                observations=results,
                next_action="Inspect retained monitor and campaign receipts; no mutation is automatically retried.",
            )


def protect(store, job, service, capability, result):
    if result.get("recovery") == "IN_FLIGHT":
        return
    if result.get("recovery") in ("OWNER_UNVERIFIED", "LEASE_STATE_CONFLICT"):
        raise PermissionError("Campaign dispatch ownership needs reconciliation")
    conditions = capability["summary"]["proposal"]["protective_conditions"]
    reason = pause_reason(result, conditions)
    if not reason:
        if result["status"] == "UNKNOWN" or result.get("recovery") in (
            "OWNER_UNVERIFIED",
            "LEASE_STATE_CONFLICT",
        ):
            raise PermissionError("Campaign dispatch requires owner reconciliation")
        return
    with connection(store.path) as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT * FROM campaign_monitors WHERE id=?", (job["data"]["monitor_id"],)
        ).fetchone()
        checked(db, row)
        if row["pauses"] >= capability["summary"]["proposal"]["max_pause_attempts"]:
            raise PermissionError("Monitor pause allowance exhausted")
        db.execute(
            "UPDATE campaign_monitors SET pauses=pauses+1,updated=? WHERE id=?",
            (now(), row["id"]),
        )
    capability.update(
        action="PAUSE",
        pause_evidence=digest(result),
        pause_reason=reason,
        pause_observation=json.loads(canonical(result)),
    )
    paused = service.run_pause(
        job["app_id"], "monitor:" + job["id"], capability["scope_id"], result["id"]
    )
    if paused["status"] != "PAUSED_campaign":
        raise PermissionError("Protective pause was not verified")
    return paused


def pause_reason(result, conditions):
    """Only fresh identity-matched saved observations can satisfy approved predicates."""
    if not _fresh_active_observation(result):
        return None
    data = result["result"]
    if (
        "configuration_drift" in conditions
        and data.get("configuration") == "CHANGED_OR_UNCONFIRMED_PAUSE_RECOMMENDED"
    ):
        return "configuration_drift"
    if (
        "active_after_end" in conditions
        and iso_time(result["data"]["end_time"]).timestamp() <= time.time()
    ):
        return "active_after_end"
    return None


def _fresh_active_observation(result):
    data = result.get("result") or {}
    observed = data.get("observed_at")
    if not observed or not 0 <= time.time() - iso_time(observed).timestamp() <= 30:
        return False
    return bool(
        result.get("ids", {}).get("campaign")
        and data.get("objects", {}).get("campaign", {}).get("status") == "ACTIVE"
    )
