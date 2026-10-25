"""App-owned listing/reference/editorial history with atomic immutable identity replay."""
from datetime import datetime, timezone
import json
from .common import Invalid, canonical, digest, identifier
from .db import connection
from .pmf_contract import exact
from .growth_review_contract import context_of, entry_data, entry_hash, entry_readout, MAX_ENTRIES
from .benchmark_ads import project_saved_ads


def decoded(row):
    """Decode only public evidence and scope; no stored credential fields exist."""
    return dict(dict(row), data=json.loads(row["data"]), context=json.loads(row["context"]))


def history(db, app_id):
    """Return deterministic immutable records for review and portable export."""
    return [decoded(row) for row in db.execute("SELECT * FROM growth_review_entries WHERE app_id=? ORDER BY created,id", (app_id,))]


def target_entry(db, app_id, value):
    """Bind notes to an exact same-app non-note source without granting approval."""
    row = db.execute("SELECT * FROM growth_review_entries WHERE app_id=? AND id=?", (app_id, value["target_id"])).fetchone()
    if not row or row["hash"] != value["target_hash"] or row["kind"] == "EDITORIAL_NOTE":
        raise Invalid("Review note target must be this app's exact saved source entry")
    return decoded(row)


def freeze_comparison(db, app_id, value, context, stamp):
    """Freeze an exact same-app reference and derive actual saved account metrics."""
    row = db.execute("SELECT * FROM growth_review_entries WHERE app_id=? AND id=?", (app_id, value["reference_id"])).fetchone()
    if not row or row["kind"] != "BENCHMARK_REFERENCE" or row["hash"] != value["reference_hash"]:
        raise Invalid("Choose this app's exact benchmark reference")
    reference = decoded(row)
    if reference["context"] != context or reference["imported"]:
        raise Invalid("Benchmark reference needs a new current-app version before comparison")
    projection = project_saved_ads(db, app_id, value["job_id"], value["report_hash"], value["metric"], value["segment"], stamp)
    return dict(value, reference=reference["data"]["reference"], projection=projection)


def current_readout(db, row, context, stamp):
    """Withhold a current difference if the exact report or connection has changed."""
    result = entry_readout(row, context, stamp)
    if row["kind"] != "BENCHMARK_COMPARISON" or result["availability"] != "CURRENT_LOCAL_EVIDENCE":
        return result
    data = row["data"]
    try:
        current = project_saved_ads(db, row["app_id"], data["job_id"], data["report_hash"], data["metric"], data["segment"], stamp)
        frozen = data["projection"]
        if any(current[key] != frozen[key] for key in ("binding", "observed", "unit_source_sha256", "numerator_exact")):
            raise Invalid("Saved account source or unit profile changed")
    except Invalid as exc:
        result.update(availability="SOURCE_REVIEW_NEEDED", analysis=dict(status="SOURCE_REVIEW_NEEDED", difference=None, reasons=[str(exc)]))
    return result


def replay_comparison(db, app_id, identity, kind, value, context):
    """Idempotent comparison replay reads the original packet without rearming anything."""
    if kind != "BENCHMARK_COMPARISON":
        return None
    previous = db.execute("SELECT * FROM growth_review_entries WHERE app_id=? AND id=?", (app_id, identity)).fetchone()
    if not previous:
        return None
    row = decoded(previous)
    selected = {key: row["data"].get(key) for key in value}
    if row["kind"] != kind or selected != value or row["context"] != context:
        raise Invalid("Review identity is immutable; save a new version ID")
    if row["hash"] != entry_hash(row["kind"], row["data"], row["context"]):
        raise Invalid("Saved review hash changed")
    return row


class GrowthReviews:
    """Persist local decision memory; all provider and outcome verification is separate."""

    def __init__(self, store, clock=None):
        self.store = store
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def list(self, app_id):
        """Derive freshness, current scope and explicit imported-assertion boundaries."""
        observed = self.clock().isoformat()
        with connection(self.store.path) as db:
            db.execute("BEGIN")
            app = db.execute("SELECT * FROM apps WHERE id=?", (app_id,)).fetchone()
            if not app:
                raise KeyError("App workspace not found")
            context = context_of(dict(dict(app), data=json.loads(app["data"])))
            rows = history(db, app_id)
            result = [dict(row, readout=current_readout(db, row, context, observed)) for row in rows]
        return dict(app_id=app_id, history=result,
                    source_hash=digest(rows), observed_at=observed, external_writes=False, execution_authority=False)

    def save(self, app_id, body):
        """Freeze exact kind/data/context in the current manifest transaction."""
        exact(body, {"id", "manifest_version", "kind", "data"})
        identity = identifier(body["id"])
        stamp = self.clock().isoformat()
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            app = db.execute("SELECT * FROM apps WHERE id=?", (app_id,)).fetchone()
            if not app or type(body["manifest_version"]) is not int or body["manifest_version"] != app["version"]:
                raise Invalid("Review app setup changed; reload before saving")
            context = context_of(dict(dict(app), data=json.loads(app["data"])))
            value = entry_data(body["kind"], body["data"], context, stamp)
            replay = replay_comparison(db, app_id, identity, body["kind"], value, context)
            if replay:
                return replay
            if body["kind"] == "BENCHMARK_COMPARISON":
                value = freeze_comparison(db, app_id, value, context, stamp)
            if body["kind"] == "EDITORIAL_NOTE":
                target_entry(db, app_id, value)
            return self.commit(db, app_id, identity, body["kind"], value, context, stamp)

    def commit(self, db, app_id, identity, kind, value, context, stamp):
        """Never overwrite evidence or reinterpret a repeated identity as new authority."""
        hashed = entry_hash(kind, value, context)
        previous = db.execute("SELECT * FROM growth_review_entries WHERE app_id=? AND id=?", (app_id, identity)).fetchone()
        if previous:
            if previous["hash"] != hashed:
                raise Invalid("Review identity is immutable; save a new version ID")
            return decoded(previous)
        count = db.execute("SELECT count(*) FROM growth_review_entries WHERE app_id=?", (app_id,)).fetchone()[0]
        if count >= MAX_ENTRIES:
            raise Invalid("Growth review history has reached its 1000 entry bound")
        row = dict(app_id=app_id, id=identity, kind=kind, data=value, hash=hashed, context=context, created=stamp, imported=0)
        db.execute("INSERT INTO growth_review_entries VALUES(?,?,?,?,?,?,?,?)", (app_id, identity, kind, canonical(value), hashed, canonical(context), stamp, 0))
        return row
