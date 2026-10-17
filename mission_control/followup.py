"""Durable local follow-up preparation; deliberately no outbound delivery adapter."""
import json
from datetime import datetime, timezone
from .common import Invalid, canonical, digest, identifier, uid
from .db import connection
from .automation_policy import check_manifest_version
from .followup_policy import validate
from .followup_eligibility import eligibility

TABLES = {kind: "followup_" + kind for kind in ("policy", "subject", "task", "handoff")}


def rows(db, app_id, kind):
    """Only static table names and app-scoped parameterized identities are allowed."""
    result = []
    for row in db.execute("SELECT * FROM " + TABLES[kind] + " WHERE app_id=? ORDER BY updated,id", (app_id,)):
        item = dict(row); item["data"] = json.loads(item["data"]); result.append(item)
    return result


def snapshot(db, app_id):
    """Read the same transaction snapshot used for atomic preparation."""
    return {kind: rows(db, app_id, kind) for kind in TABLES}


def current_app(db, app_id):
    """Read the manifest in the same transaction as consent and checkpoint state."""
    row = db.execute("SELECT * FROM apps WHERE id=?", (app_id,)).fetchone()
    if not row: raise Invalid("App workspace not found")
    app = dict(row); app["data"] = json.loads(app["data"])
    return app


def context(app, data, task, observed, exclude=None):
    """Select only this checkpoint's subject; do not inherit another subject's consent."""
    policy = next(iter(data["policy"]), None)
    subject = next((s for s in data["subject"] if s["id"] == task["data"]["subject_id"]), None)
    return eligibility(app, policy, subject, task, data["handoff"], observed, exclude)


class Followup:
    def __init__(self, store, clock=None):
        self.store = store
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def list(self, app_id):
        """Show current eligibility without reserving any work on a GET."""
        app = self.store.app(app_id)
        with connection(self.store.path) as db:
            data = snapshot(db, app_id)
        observed = self.clock()
        handoff_status = {}
        tasks = {t["id"]: t for t in data["task"]}
        for h in data["handoff"]:
            check = context(app, data, tasks[h["data"]["task_id"]], observed, h["id"])
            value = check["status"]
            if value == "ELIGIBLE" and check["source_hash"] != h["data"]["source_hash"]: value = "INVALIDATED_SOURCE"
            handoff_status[h["id"]] = "IMPORTED_HISTORY" if h["imported"] else value
        return {**data, "handoff_status": handoff_status, "eligibility": {t["id"]: context(app, data, t, observed) for t in data["task"]},
                "delivery": "MANUAL_HANDOFF_ONLY", "automatic_external_writes": False, "daily_cap": 1}

    def save(self, app_id, kind, body):
        """Version-check app and row before persisting explicitly supplied setup."""
        if kind not in ("policy", "subject", "task"):
            raise Invalid("Unsupported follow-up setup")
        self.store.app(app_id); observed = self.clock()
        identity = "policy" if kind == "policy" else identifier(body.get("id"))
        value = validate(kind, body.get("data"), observed)
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE"); self.check_app(db, app_id, body)
            old = next((r for r in rows(db, app_id, kind) if r["id"] == identity), None)
            if (old["version"] if old else None) != body.get("version"):
                raise Invalid("Follow-up changed. Refresh and reopen; your input is preserved.")
            if kind == "task" and not any(s["id"] == value["subject_id"] for s in rows(db, app_id, "subject")):
                raise Invalid("Register this app's consent subject before creating a checkpoint")
            version = old["version"] + 1 if old else 1
            db.execute("INSERT OR REPLACE INTO " + TABLES[kind] + " VALUES(?,?,?,?,?,?,?,?)",
                       (app_id, identity, canonical(value), digest(value), version, 0, old["created"] if old else observed.isoformat(), observed.isoformat()))
            self.event(db, app_id, kind + ".saved", {"id": identity, "version": version, "hash": digest(value)})
        return self.list(app_id)

    def event(self, db, app_id, action, data):
        """Persist a minimal local audit event without personal message content."""
        db.execute("INSERT INTO audit(app_id,action,detail,created) VALUES(?,?,?,?)",
                   (app_id, "followup." + action, canonical(data), self.clock().isoformat()))

    def check_app(self, db, app_id, body):
        """App binding is mandatory for every follow-up write, including new rows."""
        if type(body.get("manifest_version")) is not int:
            raise Invalid("Refresh this app before saving follow-up work")
        check_manifest_version(db, app_id, body["manifest_version"])

    def prepare(self, app_id, body):
        """Reserve one current handoff under an exclusive transaction and daily cap."""
        observed = self.clock()
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            self.check_app(db, app_id, body)
            app = current_app(db, app_id)
            data = snapshot(db, app_id)
            task = next((t for t in data["task"] if t["id"] == body.get("id")), None)
            if not task: raise Invalid("Choose a checkpoint in this app")
            status = context(app, data, task, observed)
            if status["status"] != "ELIGIBLE": raise Invalid("Follow-up suppressed: " + status["status"])
            if body.get("source_hash") != status["source_hash"]: raise Invalid("Follow-up inputs changed; refresh before preparing")
            value = {"task_id": task["id"], "subject_id": task["data"]["subject_id"], "source_hash": status["source_hash"],
                     "action": task["data"]["action"], "prompt": data["policy"][0]["data"]["prompt"],
                     "delivery": "MANUAL_HANDOFF_UNSENT", "local_date": status["local_date"]}
            identity = uid()
            db.execute("INSERT INTO followup_handoff VALUES(?,?,?,?,?,?,?,?)",
                       (app_id, identity, canonical(value), digest(value), 1, 0, observed.isoformat(), observed.isoformat()))
            self.event(db, app_id, "prepared", {"id": identity, "task_id": task["id"], "source_hash": status["source_hash"]})
        return self.list(app_id)

    def download(self, app_id, identity):
        """Recheck consent/quiet hours/expiration/source before releasing a handoff."""
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            app = current_app(db, app_id); data = snapshot(db, app_id)
        handoff = next((h for h in data["handoff"] if h["id"] == identity and not h["imported"]), None)
        if not handoff: raise Invalid("Current handoff unavailable; imported history has no authority")
        task = next(t for t in data["task"] if t["id"] == handoff["data"]["task_id"])
        status = context(app, data, task, self.clock(), identity)
        if status["status"] != "ELIGIBLE" or status["source_hash"] != handoff["data"]["source_hash"]:
            raise Invalid("Handoff is no longer eligible; refresh consent, checkpoint and app setup")
        return {"app_id": app_id, "handoff": handoff, "delivery": "NOT_SENT", "recall": "Previously exported files cannot be recalled"}

    def tick(self):
        """Prepare bounded eligible work; a failed app does not starve another app."""
        failures = []
        for app in self.store.apps():
            try:
                state = self.list(app["id"])
                candidates = [t for t in state["task"] if state["eligibility"][t["id"]]["status"] == "ELIGIBLE"]
                for task in candidates[:25]:
                    status = self.list(app["id"])["eligibility"][task["id"]]
                    if status["status"] == "ELIGIBLE":
                        self.prepare(app["id"], {"id": task["id"], "manifest_version": app["version"], "source_hash": status["source_hash"]})
            except Exception:
                failures.append(app["id"])
        if failures: raise Invalid("Follow-up preparation failed for " + ", ".join(failures))
