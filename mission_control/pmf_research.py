"""Immutable app-owned research with source checks inside the commit."""
from datetime import datetime, timezone
from .common import Invalid, canonical, digest, identifier, iso_time
from .db import connection
from .store import decode
from .pmf_contract import exact, study, snapshot, receipt
from .pmf_analysis import analyze

KINDS = ("study", "snapshot", "receipt")


def rows(db, app_id):
    """Read bounded app-owned history without changing evidence."""
    return [decode(r) for r in db.execute("SELECT * FROM pmf_research WHERE app_id=? ORDER BY created,id", (app_id,))]


def latest(items):
    """Choose the latest timestamp, not string offset or import order."""
    return max(items, key=lambda r: (iso_time(r["data"]["observed_at"]), r["id"])) if items else None


def view(items, observed=None):
    """Show each study and its own latest snapshot; receipts are passive."""
    studies = [r for r in items if r["kind"] == "study"]
    snapshots = [r for r in items if r["kind"] == "snapshot"]
    return {"history": items, "studies": [{"study": s, "snapshot": latest([r for r in snapshots if r["data"]["study_id"] == s["id"]]),
              "readout": analyze(s, latest([r for r in snapshots if r["data"]["study_id"] == s["id"]]), observed)} for s in studies],
            "inputs_hash": digest(sorted((r["id"], r["hash"]) for r in items if r["kind"] != "receipt")),
            "provenance": "SUPPLIED_RESEARCH_NOT_AUTHENTICATED", "automatic_external_writes": False}


def app_snapshot(db, app_id):
    """Read the manifest in the mutation's write transaction."""
    row = db.execute("SELECT * FROM apps WHERE id=?", (app_id,)).fetchone()
    if row is None: raise Invalid("App workspace not found")
    return decode(row)


def scope(app, value):
    """A study belongs to an exact release, locale and currency."""
    if any(value[k] != app["data"].get(k) for k in ("release", "locale", "currency")):
        raise Invalid("Study does not match this app release, locale and currency")


def snapshot_links(value, items):
    """Require an owned study and monotonic, non-conflicting observations."""
    target = next((r for r in items if r["id"] == value["study_id"] and r["kind"] == "study"), None)
    if target is None: raise Invalid("Study is missing in this app")
    if iso_time(value["observed_at"]) < iso_time(target["data"]["starts_at"]): raise Invalid("Snapshot predates the study")
    peers = [r for r in items if r["kind"] == "snapshot" and r["data"]["study_id"] == value["study_id"]]
    snapshot_order(value,peers)


def snapshot_order(value,peers):
    """Enforce source identity separately from study ownership."""
    if any(r["data"]==value for r in peers):return
    if any(r["data"]["source_id"] == value["source_id"] and r["data"] != value for r in peers):
        raise Invalid("Source ID already names different observations")
    newest = latest(peers)
    if newest and iso_time(newest["data"]["observed_at"]) >= iso_time(value["observed_at"]) and newest["data"] != value:
        raise Invalid("Observation is older than or conflicts with the latest snapshot")


def task_source(store, db, app, items):
    """Writer lock freezes inputs; receipts never hash themselves."""
    from .ledger import Ledger
    from .pmf_workflow import prepare
    records = [decode(r) for r in db.execute("SELECT * FROM records WHERE app_id=? ORDER BY updated DESC,id", (app["id"],))]
    return prepare(app, records, Ledger(store.path).reports(app["id"]), research=view(items))["tasks"][0]["source_hash"]


def receipt_links(value, items, source_hash):
    """ECC cites the exact current supplied REA predecessor."""
    if value["source_hash"] != source_hash: raise Invalid("Task source changed; reopen the current PMF workflow")
    if value["engine"] == "ECC":
        parent = next((r for r in items if r["id"] == value["rea_id"] and r["kind"] == "receipt"), None)
        if not parent or parent["data"]["engine"] != "REA" or parent["data"]["source_hash"] != source_hash:
            raise Invalid("ECC requires a current app-owned REA receipt")
        if iso_time(value["observed_at"]) < iso_time(parent["data"]["observed_at"]):
            raise Invalid("ECC result cannot predate its REA predecessor")


class Research:
    def __init__(self, store, clock=None):
        self.store = store; self.clock = clock or (lambda: datetime.now(timezone.utc))

    def list(self, app_id):
        """Read research without implying current release compatibility."""
        self.store.app(app_id)
        with connection(self.store.path) as db: return view(rows(db, app_id), self.clock())

    def validate(self, app, kind, value, items, db):
        """Dispatch finite typed contracts and owned references."""
        if kind == "study":
            value = study(value); scope(app, value); return value
        if kind == "snapshot":
            value = snapshot(value, self.clock()); snapshot_links(value, items)
            target = next(r for r in items if r["id"] == value["study_id"]); scope(app, target["data"])
            return value
        if kind == "receipt":
            value = receipt(value, self.clock()); receipt_links(value, items, task_source(self.store, db, app, items)); return value
        raise Invalid("Unknown research kind")

    def save(self, app_id, kind, body, preview=False):
        """Validate and commit atomically, or return a write-free preview."""
        identity=self.request(kind,body,preview)
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            app = app_snapshot(db, app_id)
            if type(body["manifest_version"]) is not int or body["manifest_version"] != app["version"]: raise Invalid("App setup changed; reopen the research form")
            items = rows(db, app_id); value = self.validate(app, kind, body["data"], items, db); hashed = digest(value)
            if preview:return self.preview(value,hashed,items)
            if kind == "snapshot" and body["preview_hash"] != hashed: raise Invalid("Preview changed; preview this file again")
            return self.commit(db, app_id, identity, kind, value, hashed, items)

    def request(self,kind,body,preview):
        """Validate the exact action envelope before opening a transaction."""
        keys=["id","manifest_version","data"]+(["preview_hash"] if kind=="snapshot" and not preview else [])
        exact(body,keys)
        if preview and kind!="snapshot":raise Invalid("Only snapshots can be previewed")
        return identifier(body["id"])

    def preview(self,value,hashed,items):
        """Return computed observations without reserving any persistent identity."""
        target=next(r for r in items if r["id"]==value["study_id"])
        return {"preview_hash":hashed,"readout":analyze(target,{"data":value,"imported":0},self.clock()),"rows":len(value["rows"])}

    def commit(self, db, app_id, identity, kind, value, hashed, items):
        """Idempotent immutable identity plus source deduplication."""
        existing = next((r for r in items if r["id"] == identity), None)
        if existing:
            if existing["kind"] == kind and existing["hash"] == hashed: return existing
            raise Invalid("Research identity is immutable; use a new ID")
        duplicate = next((r for r in items if r["kind"] == kind and r["hash"] == hashed), None)
        if duplicate: return duplicate
        if len(items) >= 1000: raise Invalid("Research history exceeds 1000 items; archive the workspace")
        created = self.clock().isoformat()
        db.execute("INSERT INTO pmf_research VALUES(?,?,?,?,?,?,?)", (app_id, identity, kind, canonical(value), hashed, 0, created))
        return {"app_id": app_id, "id": identity, "kind": kind, "data": value, "hash": hashed, "imported": 0, "created": created}
