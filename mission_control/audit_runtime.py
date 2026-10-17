"""Durable app-scoped REA jobs; frozen requests and explicit, bounded reruns."""
import json
import uuid
from .common import Invalid, canonical, digest, now
from .db import connection
from .pmf_research import app_snapshot, rows, task_source
from .audit_contract import scope, exact
from .audit_tools import capability, invoke
from .audit_ecc import review

ACTIVE = ("QUEUED", "RUNNING")


def decoded(row):
    """Decode only the bounded local operational record."""
    if row is None: raise Invalid("Inspection record not found in this app")
    result = dict(row)
    for key in ("data", "result"):
        if key in result and result[key] is not None: result[key] = json.loads(result[key])
    return result


def request_id(value):
    """Require canonical UUID idempotency keys; no client-supplied tool evidence."""
    try:
        if str(uuid.UUID(value)) != value: raise ValueError()
    except (ValueError, TypeError, AttributeError) as exc:
        raise Invalid("Use a fresh canonical request UUID") from exc
    return value


class Inspections:
    def __init__(self, store, detect=capability, execute=invoke):
        self.store, self.detect, self.execute = store, detect, execute

    def view(self, app_id):
        """Exclude native artifacts and executable paths from ordinary workspace refreshes."""
        self.store.app(app_id)
        with connection(self.store.path) as db:
            config = db.execute("SELECT * FROM inspection_config WHERE app_id=?", (app_id,)).fetchone()
            history = [dict(r) for r in db.execute("SELECT id,status,error,created,updated FROM inspection_runs WHERE app_id=? ORDER BY created DESC,id LIMIT 20", (app_id,))]
            archives = [dict(r) for r in db.execute("SELECT id,created FROM inspection_archives WHERE app_id=? ORDER BY created DESC,id LIMIT 1000", (app_id,))]
        saved = decoded(config) if config else None
        if saved: saved["data"].pop("tools", None)
        return {"config": saved, "runs": history, "archives": archives, "mode": "LOCAL_OPERATIONAL_STATE", "automatic_external_writes": False}

    def save(self, app_id, body):
        """Freeze source and detected tools under the same writer lock as configuration."""
        tools = self.detect()
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            app = app_snapshot(db, app_id)
            value = scope(body, app, tools)
            value.update(app_id=app_id, manifest_version=app["version"], task_source=task_source(self.store, db, app, rows(db, app_id)), tools=tools)
            self.inactive(db, app_id)
            prior = db.execute("SELECT version FROM inspection_config WHERE app_id=?", (app_id,)).fetchone()
            version = prior["version"] + 1 if prior else 1
            hashed = digest(value)
            db.execute("INSERT OR REPLACE INTO inspection_config VALUES(?,?,?,?,?)", (app_id, version, canonical(value), hashed, now()))
        return self.view(app_id)

    def inactive(self, db, app_id=None):
        """Serialize active runs, or prevent editing one active app's scope."""
        sql = "SELECT id FROM inspection_runs WHERE status IN ('QUEUED','RUNNING')"
        args = ()
        if app_id is not None: sql += " AND app_id=?"; args = (app_id,)
        if db.execute(sql, args).fetchone(): raise Invalid("Cancel or finish the active inspection first")

    def current(self, db, app_id, frozen, tools):
        """Recheck app, task source, tools and saved scope before accepting execution."""
        app = app_snapshot(db, app_id)
        source = task_source(self.store, db, app, rows(db, app_id))
        if app["version"] != frozen["manifest_version"] or source != frozen["task_source"]:
            raise Invalid("App evidence changed; save a new inspection scope")
        if tools.get("status") != "READY" or tools.get("id") != frozen["tool_id"]:
            raise Invalid("Detected tool bytes changed; refresh tools and save the scope again")
        config = decoded(db.execute("SELECT * FROM inspection_config WHERE app_id=?", (app_id,)).fetchone())
        if config["hash"] != frozen["scope_hash"]: raise Invalid("Saved inspection scope changed")

    def queue(self, app_id, body):
        """Immutable idempotency and one globally active run; never silently replay actions."""
        exact(body, ("request_key", "manifest_version", "scope_hash"))
        key = request_id(body["request_key"])
        tools = self.detect()
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT id FROM inspection_archives WHERE app_id=? AND id=?", (app_id, key)).fetchone():
                raise Invalid("Imported history cannot become an execution request; use a fresh request identity")
            existing = db.execute("SELECT * FROM inspection_runs WHERE app_id=? AND id=?", (app_id, key)).fetchone()
            if existing:
                run = decoded(existing)
                if run["data"]["queue_request"] != body: raise Invalid("Request identity already names a different scope")
                return run
            config = decoded(db.execute("SELECT * FROM inspection_config WHERE app_id=?", (app_id,)).fetchone())
            frozen = dict(config["data"], scope_hash=config["hash"], config_version=config["version"])
            if type(body["manifest_version"]) is not int or body["manifest_version"] != frozen["manifest_version"] or body["scope_hash"] != config["hash"]:
                raise Invalid("Inspection setup changed; reopen it before running")
            self.current(db, app_id, frozen, tools)
            self.inactive(db)
            if db.execute("SELECT count(*) FROM inspection_runs WHERE app_id=?", (app_id,)).fetchone()[0] >= 20:
                raise Invalid("Inspection history reached 20; export evidence before starting another workspace")
            frozen["queue_request"] = body
            stamp = now()
            db.execute("INSERT INTO inspection_runs VALUES(?,?,?,?,?,?,?,?,?)", (app_id, key, canonical(frozen), "QUEUED", None, None, stamp, stamp, digest(body)))
        return self.detail(app_id, key)

    def detail(self, app_id, key):
        """A passive per-run download carries full native evidence without execution authority."""
        request_id(key)
        with connection(self.store.path) as db:
            row = db.execute("SELECT * FROM inspection_runs WHERE app_id=? AND id=?", (app_id, key)).fetchone()
            if row is not None: return decoded(row)
            from .audit_portable import archive_detail
            return archive_detail(db, app_id, key)

    def cancel(self, app_id, body):
        """Durable cancellation cannot rewrite already terminal evidence."""
        exact(body, ("id",))
        key = request_id(body["id"])
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            decoded(db.execute("SELECT * FROM inspection_runs WHERE app_id=? AND id=?", (app_id, key)).fetchone())
            db.execute("UPDATE inspection_runs SET status='CANCELLED',error='Operator cancelled',updated=? WHERE app_id=? AND id=? AND status IN ('QUEUED','RUNNING')", (now(), app_id, key))
        return self.detail(app_id, key)

    def interrupt(self):
        """Mark abandoned work on startup; browser actions are never automatically retried."""
        with connection(self.store.path) as db:
            db.execute("UPDATE inspection_runs SET status='INTERRUPTED',error='Worker restarted; explicitly rerun with a new request key',updated=? WHERE status='RUNNING'", (now(),))

    def claim(self):
        """One atomic claim survives competing workers without duplicate execution."""
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT id FROM inspection_runs WHERE status='RUNNING'").fetchone(): return None
            row = db.execute("SELECT * FROM inspection_runs WHERE status='QUEUED' ORDER BY created,id LIMIT 1").fetchone()
            if row is None: return None
            db.execute("UPDATE inspection_runs SET status='RUNNING',updated=? WHERE app_id=? AND id=?", (now(), row["app_id"], row["id"]))
            return decoded(row)

    def alive(self, job, stopping):
        """Only the owned job's durable state or worker shutdown cancels its process."""
        if stopping(): raise Invalid("Worker stopping; explicitly rerun interrupted work")
        if self.detail(job["app_id"], job["id"])["status"] != "RUNNING": raise Invalid("Operator cancelled")

    def run_once(self, stopping=lambda: False):
        """Execute outside SQLite locks; accept results only after final transactional revalidation."""
        job = self.claim()
        if job is None: return False
        result = None
        try:
            tools = self.detect()
            with connection(self.store.path) as db: self.current(db, job["app_id"], job["data"], tools)
            self.alive(job, stopping)
            value = self.execute(tools, job["data"]["scenario"], lambda: self.alive(job, stopping))
            result = {"native": value, "native_sha256": digest(value), "accepted": False}
            result["ecc"] = review(value, job["data"], tools)
            self.finish(job, result, tools=self.detect())
        except (Invalid, OSError, ValueError, KeyError, TypeError) as exc:
            self.finish(job, result, error=str(exc), interrupted=stopping())
        return True

    def finish(self, job, result, tools=None, error=None, interrupted=False):
        """Retain raw evidence even on drift; cancellation always wins the acceptance race."""
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            row = decoded(db.execute("SELECT * FROM inspection_runs WHERE app_id=? AND id=?", (job["app_id"], job["id"])).fetchone())
            status = row["status"]
            if status == "RUNNING":
                if error is None: self.current(db, job["app_id"], job["data"], tools)
                status = ("INTERRUPTED" if interrupted else "BLOCKED") if error else result["ecc"]["status"]
                if result is not None: result["accepted"] = error is None
            db.execute("UPDATE inspection_runs SET status=?,error=?,result=?,updated=? WHERE app_id=? AND id=?", (status, error or row["error"], canonical(result) if result is not None else None, now(), job["app_id"], job["id"]))
