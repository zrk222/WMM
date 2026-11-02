"""Host-job retained monitor authority, charged before every provider boundary."""

from contextlib import contextmanager
from contextvars import ContextVar
import json
import time
from .common import digest, now
from .db import connection
from .operation_authority import store_identity
from .campaign_execution import CampaignExecutionService

CURRENT = ContextVar("wmm_campaign_monitor", default=None)


@contextmanager
def bound(store, job):
    """A worker binds exact leased job bytes, never an owner principal or bearer token."""
    data = job["data"]
    with connection(store.path) as db:
        from .campaign_monitor import checked

        row = db.execute(
            "SELECT * FROM campaign_monitors WHERE id=? AND app_id=?",
            (data["monitor_id"], job["app_id"]),
        ).fetchone()
        if row is None:
            raise PermissionError("Monitor is unavailable")
        summary = checked(db, row)
    value = dict(
        store=store_identity(store),
        job_id=job["id"],
        attempt=job["attempts"],
        input_hash=digest(data),
        scope_id=summary["proposal"]["scope_id"],
        summary=summary,
        intent_id=None,
        action=None,
    )
    token = CURRENT.set(value)
    try:
        yield value
    finally:
        CURRENT.reset(token)


def validate(db, store, app_id, actor, scope, action):
    """Check the current job and source revision at each original campaign guard."""
    from .campaign_monitor import target_row

    active = CURRENT.get()
    if active is None:
        return None
    if (
        active["store"] != store_identity(store)
        or actor != "monitor:" + active["job_id"]
    ):
        raise PermissionError("Monitor actor or host changed")
    if action not in ("RECONCILE", "PAUSE") or active["action"] != action:
        raise PermissionError("Monitor cannot authorize this campaign effect")
    job, data = _job(db, active, app_id)
    row, summary = _monitor(db, active, job, data, scope)
    targets = {target["intent_id"]: target for target in summary["proposal"]["targets"]}
    if active["intent_id"] not in targets:
        raise PermissionError("Monitor intent is outside exact approval")
    target_row(db, app_id, scope["scope_id"], targets[active["intent_id"]])
    if action == "PAUSE":
        _pause_evidence(active, summary)
    return row


def _pause_evidence(active, summary):
    from .campaign_monitor import pause_reason

    evidence = active.get("pause_observation")
    if not evidence or digest(evidence) != active.get("pause_evidence"):
        raise PermissionError("Protective observation changed")
    if pause_reason(
        evidence, summary["proposal"]["protective_conditions"]
    ) != active.get("pause_reason"):
        raise PermissionError("Fresh approved protective evidence is unavailable")


def _job(db, active, app_id):
    job = db.execute("SELECT * FROM jobs WHERE id=?", (active["job_id"],)).fetchone()
    if job is None or (job["app_id"], job["action"]) != (app_id, "campaign_monitor"):
        raise PermissionError("Monitor job belongs to another app or operation")
    if (job["status"], job["attempts"]) != ("RUNNING", active["attempt"]) or job[
        "lease"
    ] <= time.time():
        raise PermissionError("Monitor worker lease changed")
    data = json.loads(job["data"])
    if digest(data) != active["input_hash"]:
        raise PermissionError("Monitor job input changed")
    return job, data


def _monitor(db, active, job, data, scope):
    from .campaign_monitor import checked

    row = db.execute(
        "SELECT * FROM campaign_monitors WHERE id=?", (data["monitor_id"],)
    ).fetchone()
    summary = checked(db, row)
    actual = (row["version"], row["summary_hash"], row["last_job"], row["runs"])
    if actual != (
        data["monitor_version"],
        data["summary_hash"],
        job["id"],
        data["run"],
    ):
        raise PermissionError("Monitor job revision changed")
    if (scope["scope_id"], scope["approval_hash"]) != (
        active["scope_id"],
        summary["source"]["scope_hash"],
    ):
        raise PermissionError("Monitor cannot borrow another campaign scope")
    return row, summary


def check(store, app_id, actor, scope, action):
    """Policy-checker hook: inactive context falls through to existing authority."""
    if CURRENT.get() is None:
        return False
    with connection(store.path) as db:
        validate(db, store, app_id, actor, scope, action)
    return True


def admit(store, remote=None):
    """Conservatively reserve one unit immediately before original provider admission."""
    active = CURRENT.get()
    if active is None:
        raise PermissionError("Retained monitor authority is required")
    from .campaign_execution import row_scope

    with connection(store.path) as db:
        db.execute("BEGIN IMMEDIATE")
        job = db.execute(
            "SELECT app_id FROM jobs WHERE id=?", (active["job_id"],)
        ).fetchone()
        if job is None:
            raise PermissionError("Monitor job is unavailable")
        scope = row_scope(
            db.execute(
                "SELECT * FROM campaign_scopes WHERE app_id=? AND id=?",
                (job["app_id"], active["scope_id"]),
            ).fetchone()
        )
        row = validate(
            db,
            store,
            job["app_id"],
            "monitor:" + active["job_id"],
            scope,
            active["action"],
        )
        if remote is not None:
            _remote(db, job["app_id"], active, remote)
        if row["units"] >= active["summary"]["proposal"]["max_provider_units"]:
            raise PermissionError("Monitor provider boundary allowance exhausted")
        db.execute(
            "UPDATE campaign_monitors SET units=units+1,updated=? WHERE id=?",
            (now(), row["id"]),
        )


def _remote(db, app_id, active, remote):
    from .campaign_monitor import target_row

    targets = {
        value["intent_id"]: value for value in active["summary"]["proposal"]["targets"]
    }
    row, paid = target_row(db, app_id, active["scope_id"], targets[active["intent_id"]])
    kind, identity, page_hash = remote
    if paid:
        expected = json.loads(row["ids"]).get(kind)
        if kind not in ("campaign", "adset", "creative", "ad") or identity != expected:
            raise PermissionError("Provider object is outside the exact monitor target")
    elif (kind, identity, page_hash) != (
        "post",
        row["remote_id"],
        (row["page_id"], row["content_hash"]),
    ):
        raise PermissionError("Provider post is outside the exact monitor target")


class MonitorService(CampaignExecutionService):
    """Charge original provider guards including organic identity preflight reads."""

    def _alive(self, app_id, actor, scope_id, action, active=True):
        admit(self.store)
        return super()._alive(app_id, actor, scope_id, action, active)


def remote_check(store, remote):
    active = CURRENT.get()
    if active is None:
        raise PermissionError("Monitor target capability is unavailable")
    with connection(store.path) as db:
        job = db.execute(
            "SELECT app_id FROM jobs WHERE id=?", (active["job_id"],)
        ).fetchone()
        if job is None:
            raise PermissionError("Monitor job is unavailable")
        _remote(db, job["app_id"], active, remote)


class BoundaryTransport:
    """Expose only reads and PAUSED-campaign status; charge before each delegate call."""

    def __init__(self, store, transport=None):
        from .campaign_transport import MetaTransport

        self.store = store
        self.transport = transport or MetaTransport()

    def boundary(self, alive, kind, identity, page_hash=None):
        def guarded():
            remote_check(self.store, (kind, identity, page_hash))
            alive()

        return guarded

    def read_paid(self, kind, identity, token, secret, alive):
        return self.transport.read_paid(
            kind, identity, token, secret, self.boundary(alive, kind, identity)
        )

    def ad_insights(self, identity, token, secret, alive):
        return self.transport.ad_insights(
            identity, token, secret, self.boundary(alive, "ad", identity)
        )

    def read_post(self, page, identity, content_hash, token, secret, alive):
        return self.transport.read_post(
            page,
            identity,
            content_hash,
            token,
            secret,
            self.boundary(alive, "post", identity, (page, content_hash)),
        )

    def set_paid_status(self, kind, identity, status, token, secret, alive):
        active = CURRENT.get()
        if (
            kind != "campaign"
            or status != "PAUSED"
            or not active
            or active["action"] != "PAUSE"
        ):
            raise PermissionError("Monitor cannot activate or alter provider objects")
        return self.transport.set_paid_status(
            kind, identity, status, token, secret, self.boundary(alive, kind, identity)
        )
