"""App-isolated native credentials, durable read leases and opt-in analytics refresh."""
import hashlib
import json
import threading
import time
from .common import Invalid, canonical, digest, now, uid
from .credential_vault import Vault, namespace
from .db import connection
from .store import audit
from .insights_contract import config, PROVIDERS
from .insights_transport import read, ProviderFailure
from .event_mapping import mapping, coverage, ROLES, DEFAULTS

LOCK = threading.RLock()


def decoded(row):
    """Verify public configuration integrity before resolving a protected key."""
    result = dict(row)
    result["data"] = json.loads(result["data"])
    if digest(result["data"]) != result["hash"]:
        raise Invalid("Analytics configuration integrity differs; reconnect")
    return result


class Insights:
    def __init__(self, store):
        self.store = store

    def name(self, app, reference):
        """Compute credential targets only from owned database and opaque generated IDs."""
        return "AppGrowthInsights/" + namespace(self.store.path) + "/" + app + "/" + reference

    def list(self, app):
        """Expose sanitized reports, presence and schedule only; never credentials or fingerprints."""
        self.store.app(app)
        with connection(self.store.path) as db:
            sources = [decoded(r) for r in db.execute("SELECT * FROM insight_sources WHERE app_id=? ORDER BY provider", (app,))]
            reports = [decoded(r) for r in db.execute("SELECT * FROM insight_reports WHERE app_id=? ORDER BY rowid DESC LIMIT 300", (app,))]
        safe = [{key: row[key] for key in ("id", "provider", "data", "version", "status", "next_due", "last_error", "updated")} for row in sources]
        for row in safe:
            if row["provider"] == "posthog":
                row["event_coverage"] = coverage(row, reports)
        return {"sources": safe, "reports": reports,
                "providers": PROVIDERS, "event_roles": ROLES, "event_defaults": DEFAULTS, "automatic_interval_seconds": 21600,
                "scope": "Dedicated project aggregates; separate from transaction and causal outcome ledgers",
                "portable": "Reports can be downloaded. Credentials and scheduled authority are not restored by workspace snapshots."}

    def setup(self, app, body):
        """Validate a replacement before committing; preserve the active connection on failure."""
        self.store.app(app)
        if not isinstance(body, dict):
            raise Invalid("Use the guided analytics setup")
        data = config({key: value for key, value in body.items() if key != "version"})
        with LOCK:
            candidate, old = self.stage_candidate(app, data, body)
            try:
                result = self.read_candidate(app, candidate, data)
                self.activate_candidate(app, candidate, data, body, result)
            except Exception as exc:
                cleanup_pending = self.discard_candidate(app, candidate)
                raise Invalid(self.candidate_failure(old, exc, cleanup_pending)) from exc
            cleanup = self.retire(app, old)
            return {"source_id": candidate["id"], "read": {"status": "CONNECTED", "report": result}, "cleanup": cleanup}

    def stage_candidate(self, app, data, body):
        """Store a protected candidate without changing the active source or its schedule."""
        self.cleanup_unbound(app)
        scope = digest({key: data[key] for key in ("provider", "project_id", "region")})
        sha, reference = digest(data), uid()
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            old_row = db.execute("SELECT * FROM insight_sources WHERE app_id=? AND provider=?", (app, data["provider"])).fetchone()
            old = decoded(old_row) if old_row else None
            self.check_stage(db, app, scope, old, body.get("version"))
            sid = old["id"] if old else uid()
        self.cleanup_source(app, sid)
        value = {"api_key": body["api_key"], "binding": {"app_id": app, "id": sid, "hash": sha}}
        Vault().put(self.name(app, reference), value)
        return {"id": sid, "credential_ref": reference, "hash": sha, "scope": scope}, old

    def cleanup_source(self, app, sid):
        """Retire previously recorded inactive references before staging another candidate."""
        with connection(self.store.path) as db:
            stale_refs = db.execute("SELECT credential_ref FROM insight_cleanup WHERE app_id=? AND source_id=?", (app, sid)).fetchall()
        for (reference,) in stale_refs:
            Vault().delete(self.name(app, reference))
            with connection(self.store.path) as db:
                db.execute("DELETE FROM insight_cleanup WHERE app_id=? AND source_id=? AND credential_ref=?", (app, sid, reference))

    def read_candidate(self, app, candidate, data):
        """Count a permitted read and validate its protected binding outside a DB transaction."""
        self.reserve_candidate_read(candidate["scope"], data["provider"])
        secret = Vault().get(self.name(app, candidate["credential_ref"]))
        expected = {"app_id": app, "id": candidate["id"], "hash": candidate["hash"]}
        if not secret or secret.get("binding") != expected:
            raise ProviderFailure("PERMISSION_REQUIRED", "Protected candidate key could not be verified")
        return read(data, secret["api_key"])

    def activate_candidate(self, app, candidate, data, body, result):
        """Recheck ownership/version and commit the successful observation and binding together."""
        sid = candidate["id"]
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            latest_row = db.execute("SELECT * FROM insight_sources WHERE app_id=? AND provider=?", (app, data["provider"])).fetchone()
            latest = decoded(latest_row) if latest_row else None
            self.check_stage(db, app, candidate["scope"], latest, body.get("version"))
            if latest and latest["id"] != sid:
                raise Invalid("Connection changed; reload before replacing its key")
            version = latest["version"] + 1 if latest else 1
            timestamp = now()
            next_due = time.time() + 21600 if data["automatic"] else 0
            db.execute("INSERT INTO insight_sources VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(app_id,provider) DO UPDATE SET data=excluded.data,hash=excluded.hash,scope_key=excluded.scope_key,credential_ref=excluded.credential_ref,version=excluded.version,status='CONNECTED',lease=0,next_due=excluded.next_due,last_error=NULL,updated=excluded.updated",
                       (app, sid, data["provider"], canonical(data), candidate["hash"], candidate["scope"], candidate["credential_ref"], version, "CONNECTED", 0, next_due, None, timestamp, timestamp))
            self.report(db, app, {"id": sid, "version": version, "hash": candidate["hash"], "provider": data["provider"]}, result)
            audit(db, app, "insights.configured", {"id": sid, "provider": data["provider"], "automatic": data["automatic"]})

    def candidate_failure(self, old, exc, cleanup_pending):
        """Describe failed activation without claiming the candidate was saved."""
        if isinstance(exc, ProviderFailure):
            detail = f"Candidate read failed ({exc.code}): {exc}"
        elif isinstance(exc, Invalid):
            detail = str(exc) if str(exc).startswith(("Connection changed;", "This provider project belongs")) else "Provider data or candidate key did not pass validation; check permissions and retry"
        else:
            detail = "Candidate could not be safely activated; retry setup"
        if old:
            message = "Replacement not activated; the existing connection, schedule, and reports remain in use. " + detail
        else:
            message = "SOURCE_NOT_SAVED: no connection was saved. Enter the key again to retry. " + detail
        if cleanup_pending:
            message += " Candidate-key cleanup is recorded and will be retried before another setup."
        return message

    def reserve_candidate_read(self, scope, provider):
        """Charge a candidate read without mutating an active source's lease or schedule."""
        current = time.time()
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            count = db.execute("SELECT COUNT(*) FROM insight_requests WHERE scope_key=? AND attempted>?", (scope, current - 86400)).fetchone()[0]
            if provider == "clarity" and count >= 10:
                raise ProviderFailure("LOCAL_RATE_LIMITED", "Clarity's ten daily requests are reserved; wait for the rolling quota to reset")
            db.execute("INSERT INTO insight_requests(scope_key,attempted) VALUES(?,?)", (scope, current))
            db.execute("DELETE FROM insight_requests WHERE attempted<?", (current - 86400,))

    def cleanup_unbound(self, app):
        """Retry cleanup from failed initial setup before accepting another candidate."""
        with connection(self.store.path) as db:
            rows = db.execute("SELECT c.source_id,c.credential_ref FROM insight_cleanup c LEFT JOIN insight_sources s ON s.app_id=c.app_id AND s.id=c.source_id WHERE c.app_id=? AND s.id IS NULL", (app,)).fetchall()
        for sid, reference in rows:
            Vault().delete(self.name(app, reference))
            with connection(self.store.path) as db:
                db.execute("DELETE FROM insight_cleanup WHERE app_id=? AND source_id=? AND credential_ref=?", (app, sid, reference))

    def discard_candidate(self, app, candidate):
        """Delete a non-active key or durably record its retryable cleanup reference."""
        if not candidate:
            return False
        try:
            Vault().delete(self.name(app, candidate["credential_ref"]))
            return False
        except Exception:
            with connection(self.store.path) as db:
                db.execute("INSERT OR IGNORE INTO insight_cleanup VALUES(?,?,?)", (app, candidate["id"], candidate["credential_ref"]))
            return True

    def check_stage(self, db, app, scope, old, version):
        """Prevent stale rotation and undeclared cross-app sharing of project totals."""
        if old and (type(version) is not int or version != old["version"]):
            raise Invalid("Connection changed; reload before replacing its key")
        if db.execute("SELECT 1 FROM insight_sources WHERE app_id<>? AND scope_key=?", (app, scope)).fetchone():
            raise Invalid("This provider project belongs to another app; choose a dedicated project")
        if not old and db.execute("SELECT COUNT(*) FROM insight_sources").fetchone()[0] >= 100:
            raise Invalid("Analytics source limit reached")

    def retire(self, app, old):
        """Retire only the prior local reference; preserve actionable cleanup state."""
        if not old:
            return "NO_PRIOR_KEY"
        try:
            Vault().delete(self.name(app, old["credential_ref"]))
            return "PRIOR_LOCAL_KEY_REMOVED"
        except Exception:
            with connection(self.store.path) as db:
                db.execute("INSERT OR IGNORE INTO insight_cleanup VALUES(?,?,?)", (app, old["id"], old["credential_ref"]))
            return "PRIOR_LOCAL_KEY_CLEANUP_REQUIRED"

    def row(self, db, app, sid):
        """Resolve only one app-owned source."""
        row = db.execute("SELECT * FROM insight_sources WHERE app_id=? AND id=?", (app, sid)).fetchone()
        if not row:
            raise KeyError("Analytics source not found in this app")
        return decoded(row)

    def reserve(self, app, sid, automatic):
        """Atomic single-read lease and rolling project cap includes failed attempts and rotations."""
        current = time.time()
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            row = self.row(db, app, sid)
            if row["status"] in ("DISCONNECTED", "CLEANUP_REQUIRED"):
                raise Invalid("Reconnect before reading this source")
            if row["lease"] > current:
                raise Invalid("A read is already running; refresh its result shortly")
            if automatic and (not row["data"]["automatic"] or row["next_due"] > current or row["status"] == "PERMISSION_REQUIRED"):
                return None
            count = db.execute("SELECT COUNT(*) FROM insight_requests WHERE scope_key=? AND attempted>?", (row["scope_key"], current - 86400)).fetchone()[0]
            if row["provider"] == "clarity" and count >= 10:
                raise ProviderFailure("LOCAL_RATE_LIMITED", "Clarity's ten daily requests are reserved; wait for the rolling quota to reset")
            db.execute("INSERT INTO insight_requests(scope_key,attempted) VALUES(?,?)", (row["scope_key"], current))
            db.execute("DELETE FROM insight_requests WHERE attempted<?", (current - 86400,))
            db.execute("UPDATE insight_sources SET lease=?,next_due=? WHERE app_id=? AND id=?", (current + 60, current + 21600, app, sid))
            row["lease"] = current + 60
        return row

    def refresh(self, app, sid, body, automatic=False):
        """Perform one permitted read; errors become visible states, never fabricated empty reports."""
        if body != {"confirm_read": True}:
            raise Invalid("Confirm the read-only analytics request")
        row = self.reserve(app, sid, automatic)
        if row is None:
            return {"status": "NOT_DUE"}
        try:
            secret = Vault().get(self.name(app, row["credential_ref"]))
            if not secret or secret.get("binding") != {"app_id": app, "id": sid, "hash": row["hash"]}:
                raise ProviderFailure("PERMISSION_REQUIRED", "Protected key is missing or bound elsewhere; reconnect")
            result = read(row["data"], secret["api_key"])
            status, error = "CONNECTED", None
        except ProviderFailure as exc:
            result, status, error = None, exc.code, str(exc)
        except (Invalid, ValueError, TypeError, KeyError):
            result, status, error = None, "READ_FAILED", "Provider data or configuration differs; check permissions and reconnect or retry"
        return self.complete(app, row, result, status, error)

    def complete(self, app, row, result, status, error):
        """Discard in-flight results after rotation/disconnect; retain prior successful observations."""
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            current = self.row(db, app, row["id"])
            if current["version"] != row["version"] or current["lease"] != row["lease"]:
                return {"status": "OBSOLETE_RESULT_DISCARDED"}
            db.execute("UPDATE insight_sources SET lease=0,status=?,last_error=?,updated=? WHERE app_id=? AND id=?", (status, error, now(), app, row["id"]))
            if result is not None:
                self.report(db, app, row, result)
            audit(db, app, "insights.read", {"id": row["id"], "status": status})
        return {"status": status, "error": error, "report": result}

    def report(self, db, app, row, result):
        """Persist sanitized provider evidence and keep a bounded per-source history."""
        result = dict(result, source_version=row["version"], configuration_hash=row["hash"])
        db.execute("INSERT INTO insight_reports VALUES(?,?,?,?,?,?,?)", (app, uid(), row["id"], row["provider"], canonical(result), digest(result), now()))
        db.execute("DELETE FROM insight_reports WHERE app_id=? AND source_id=? AND id NOT IN (SELECT id FROM insight_reports WHERE app_id=? AND source_id=? ORDER BY rowid DESC LIMIT 100)", (app, row["id"], app, row["id"]))

    def update_events(self, app, sid, body):
        """Reuse one app's existing protected key; explicit read consent tests the new version."""
        self.store.app(app)
        if not isinstance(body, dict) or set(body) != {"version", "event_map", "confirm_read"} or body["confirm_read"] is not True:
            raise Invalid("Confirm the read and provide the current version and six event roles")
        events = mapping(body["event_map"])
        with LOCK, connection(self.store.path) as db:
            row = self.row(db, app, sid)
            if type(body["version"]) is not int or row["version"] != body["version"]:
                raise Invalid("Connection changed; reload before editing event names")
            if not self.events_editable(row):
                raise Invalid("Connect PostHog before editing event names")
            secret = Vault().get(self.name(app, row["credential_ref"]))
            if not secret or secret.get("binding") != {"app_id": app, "id": sid, "hash": row["hash"]}:
                raise Invalid("Protected key is missing or bound elsewhere; reconnect")
            config_body = dict(row["data"], event_map=events, api_key=secret["api_key"],
                               dedicated_project=True, confirm_read=True, version=row["version"])
        return self.setup(app, config_body)

    def events_editable(self, row):
        """Allow event mapping changes only for an active PostHog source."""
        return row["provider"] == "posthog" and row["status"] not in ("DISCONNECTED", "CLEANUP_REQUIRED")

    def disconnect(self, app, sid, body):
        """Disable scheduling before secret deletion, including previously failed rotation cleanup."""
        if set(body) != {"version", "confirm_disconnect"} or body["confirm_disconnect"] is not True:
            raise Invalid("Confirm local disconnect")
        with LOCK, connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            row = self.row(db, app, sid)
            if type(body["version"]) is not int or row["version"] != body["version"]:
                raise Invalid("Connection changed; reload before disconnect")
            db.execute("UPDATE insight_sources SET status='CLEANUP_REQUIRED',version=version+1,lease=0 WHERE app_id=? AND id=?", (app, sid))
        refs = [row["credential_ref"]]
        with connection(self.store.path) as db:
            refs += [r[0] for r in db.execute("SELECT credential_ref FROM insight_cleanup WHERE app_id=? AND source_id=?", (app, sid))]
        for ref in refs:
            try:
                Vault().delete(self.name(app, ref))
            except Invalid:
                return {"status": "CLEANUP_REQUIRED", "error": "Reads are disabled; retry disconnect to remove remaining protected keys"}
        with connection(self.store.path) as db:
            db.execute("DELETE FROM insight_cleanup WHERE app_id=? AND source_id=?", (app, sid))
            db.execute("UPDATE insight_sources SET status='DISCONNECTED',last_error=NULL,updated=? WHERE app_id=? AND id=?", (now(), app, sid))
            audit(db, app, "insights.disconnected", {"id": sid})
        return {"status": "DISCONNECTED", "provider_revocation": "NOT_PERFORMED"}

    def tick(self):
        """Run at most one due permitted read per worker poll; no automatic external writes."""
        with connection(self.store.path) as db:
            candidates = db.execute("SELECT app_id,id FROM insight_sources WHERE next_due<=? AND lease<=? AND status NOT IN ('DISCONNECTED','CLEANUP_REQUIRED','PERMISSION_REQUIRED') ORDER BY next_due LIMIT 100", (time.time(), time.time())).fetchall()
        for app, sid in candidates:
            try:
                result = self.refresh(app, sid, {"confirm_read": True}, automatic=True)
                if result["status"] != "NOT_DUE":
                    return result
            except ProviderFailure as exc:
                with connection(self.store.path) as db:
                    db.execute("UPDATE insight_sources SET status=?,last_error=?,next_due=? WHERE app_id=? AND id=?", (exc.code, str(exc), time.time() + 21600, app, sid))
            except Invalid:
                continue
        return {"status": "IDLE"}
