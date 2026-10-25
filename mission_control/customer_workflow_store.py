"""Immutable customer research in the app-owned store; portable records grant no authority."""
from datetime import datetime, timezone
import json
from .common import Invalid, canonical, digest, identifier, iso_time
from .db import connection
from .pmf_contract import exact
from .customer_workflow import workflow_data, workflow_readout


def history(db, app_id):
    """Export app-owned immutable rows without creating source verification claims."""
    rows = db.execute("SELECT * FROM customer_workflows WHERE app_id=? ORDER BY created,id", (app_id,)).fetchall()
    return [dict(dict(row), data=json.loads(row["data"])) for row in rows]


def app_scope(app, data):
    """Require the current release, locale and currency when creating a proposal."""
    if any(app["data"].get(key) != data[key] for key in ("release", "locale", "currency")):
        raise Invalid("Customer workflow does not match the app release, locale and currency")


def restored_entry(app_id, row, observed):
    """Reject forged scope, malformed source linkage, noncanonical data or future history."""
    exact(row, {"app_id", "id", "data", "hash", "created", "imported"})
    identifier(row["id"])
    if row["app_id"] != app_id or type(row["imported"]) is not int or row["imported"] not in (0, 1):
        raise Invalid("Customer workflow snapshot scope or provenance is invalid")
    created = iso_time(row["created"])
    if created > observed or workflow_data(row["data"], created) != row["data"] or digest(row["data"]) != row["hash"]:
        raise Invalid("Customer workflow snapshot content, dates or hash changed")


def restore(db, app_id, rows):
    """Restore inside the caller's transaction; old snapshots may omit this section."""
    if rows is None:
        return
    if not isinstance(rows, list) or len(rows) > 1000:
        raise Invalid("Customer workflow snapshot exceeds 1000 entries")
    observed = datetime.now(timezone.utc)
    identities = set()
    for row in rows:
        restored_entry(app_id, row, observed)
        if row["id"] in identities:
            raise Invalid("Customer workflow snapshot has duplicate identities")
        identities.add(row["id"])
        db.execute("INSERT INTO customer_workflows VALUES(?,?,?,?,?,?)", (app_id, row["id"], canonical(row["data"]), row["hash"], row["created"], 1))


class CustomerWorkflows:
    """Read and save proposals without modifying app authority or old research rows."""

    def __init__(self, store, clock=None):
        self.store = store
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def list(self, app_id):
        """Return source freshness and current manifest compatibility after restart."""
        app = self.store.app(app_id)
        observed = self.clock()
        with connection(self.store.path) as db:
            rows = history(db, app_id)
        results = []
        for row in rows:
            readout = workflow_readout(row["data"], observed)
            if any(app["data"].get(key) != row["data"][key] for key in ("release", "locale", "currency")):
                readout = dict(readout, status="STALE_APP_SCOPE")
            results.append(dict(row, readout=readout))
        return dict(app_id=app_id, history=results, source_hash=digest(rows), external_writes=False, demand_verified=False)

    def save(self, app_id, body):
        """Bind the optimistic manifest and immutable research identity atomically."""
        exact(body, {"id", "manifest_version", "data"})
        identity = identifier(body["id"])
        stamp = self.clock()
        value = workflow_data(body["data"], stamp)
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM apps WHERE id=?", (app_id,)).fetchone()
            if not row or type(body["manifest_version"]) is not int or row["version"] != body["manifest_version"]:
                raise Invalid("Customer workflow app setup changed; reload before saving")
            app_scope({"data": json.loads(row["data"])}, value)
            result = self.commit(db, app_id, identity, value, stamp)
        return result

    def commit(self, db, app_id, identity, value, stamp):
        """Idempotent replay never overwrites history; bounded history remains inspectable."""
        rows = history(db, app_id)
        hashed = digest(value)
        old = next((row for row in rows if row["id"] == identity), None)
        if old:
            if old["hash"] != hashed:
                raise Invalid("Customer workflow identity is immutable; create a new version ID")
            return old
        if len(rows) >= 1000:
            raise Invalid("Customer workflow history exceeds 1000 entries")
        created = stamp.isoformat()
        db.execute("INSERT INTO customer_workflows VALUES(?,?,?,?,?,?)", (app_id, identity, canonical(value), hashed, created, 0))
        return dict(app_id=app_id, id=identity, data=value, hash=hashed, created=created, imported=0)
