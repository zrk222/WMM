"""Private app-scoped observational campaign attribution records and reports."""
from collections import Counter
import json
import re
from datetime import timezone
from urllib.parse import urlsplit

from . import observational_campaign_contract as contract
from .common import Invalid, canonical, digest, iso_time, now
from .db import connection

OPS = {name: "observational-campaign." + name for name in contract.ACTION_NAMES}


def _tables(db):
    db.executescript("""
    CREATE TABLE IF NOT EXISTS observational_campaign_studies(
      app_id TEXT NOT NULL REFERENCES apps(id), study_id TEXT NOT NULL,
      request_id TEXT NOT NULL, request_hash TEXT NOT NULL, app_version INTEGER NOT NULL, data TEXT NOT NULL,
      hash TEXT NOT NULL, registered_at TEXT NOT NULL,
      PRIMARY KEY(app_id,study_id), UNIQUE(app_id,request_id));
    CREATE TABLE IF NOT EXISTS observational_campaign_batches(
      app_id TEXT NOT NULL, study_id TEXT NOT NULL, batch_id TEXT NOT NULL,
      source_id TEXT NOT NULL, hash TEXT NOT NULL, data TEXT NOT NULL,
      receipt TEXT NOT NULL, created TEXT NOT NULL,
      PRIMARY KEY(app_id,batch_id),
      FOREIGN KEY(app_id,study_id) REFERENCES observational_campaign_studies(app_id,study_id));
    CREATE TABLE IF NOT EXISTS observational_campaign_events(
      app_id TEXT NOT NULL, study_id TEXT NOT NULL, source_id TEXT NOT NULL,
      event_id TEXT NOT NULL, batch_id TEXT NOT NULL, data TEXT NOT NULL,
      hash TEXT NOT NULL, created TEXT NOT NULL,
      PRIMARY KEY(app_id,source_id,event_id),
      FOREIGN KEY(app_id,study_id) REFERENCES observational_campaign_studies(app_id,study_id));
    CREATE INDEX IF NOT EXISTS observational_campaign_event_study
      ON observational_campaign_events(app_id,study_id,source_id,event_id);
    CREATE TABLE IF NOT EXISTS observational_campaign_coverage(
      app_id TEXT NOT NULL, study_id TEXT NOT NULL, source_id TEXT NOT NULL,
      event_type TEXT NOT NULL, batch_id TEXT NOT NULL, complete INTEGER NOT NULL, source_event_count INTEGER,
      observed_at TEXT NOT NULL, receipt_hash TEXT NOT NULL, created TEXT NOT NULL,
      PRIMARY KEY(app_id,study_id,source_id,event_type,batch_id),
      FOREIGN KEY(app_id,study_id) REFERENCES observational_campaign_studies(app_id,study_id));
    CREATE TABLE IF NOT EXISTS observational_campaign_corrections(
      app_id TEXT NOT NULL, study_id TEXT NOT NULL, correction_id TEXT NOT NULL,
      source_id TEXT NOT NULL, event_id TEXT NOT NULL, original_hash TEXT NOT NULL,
      replacement TEXT NOT NULL, replacement_hash TEXT NOT NULL, reason TEXT NOT NULL,
      author TEXT NOT NULL, created TEXT NOT NULL, hash TEXT NOT NULL,
      PRIMARY KEY(app_id,correction_id), UNIQUE(app_id,source_id,event_id),
      FOREIGN KEY(app_id,study_id) REFERENCES observational_campaign_studies(app_id,study_id));
    CREATE TABLE IF NOT EXISTS observational_campaign_activity(
      app_id TEXT NOT NULL, study_id TEXT NOT NULL, kind TEXT NOT NULL,
      record_id TEXT NOT NULL, data TEXT NOT NULL, hash TEXT NOT NULL,
      created TEXT NOT NULL, PRIMARY KEY(app_id,kind,record_id),
      FOREIGN KEY(app_id,study_id) REFERENCES observational_campaign_studies(app_id,study_id));
    CREATE TRIGGER IF NOT EXISTS observational_campaign_studies_no_update
      BEFORE UPDATE ON observational_campaign_studies BEGIN SELECT RAISE(ABORT,'study records are immutable'); END;
    CREATE TRIGGER IF NOT EXISTS observational_campaign_studies_no_delete
      BEFORE DELETE ON observational_campaign_studies BEGIN SELECT RAISE(ABORT,'study records are immutable'); END;
    CREATE TRIGGER IF NOT EXISTS observational_campaign_batches_no_update
      BEFORE UPDATE ON observational_campaign_batches BEGIN SELECT RAISE(ABORT,'batch records are immutable'); END;
    CREATE TRIGGER IF NOT EXISTS observational_campaign_batches_no_delete
      BEFORE DELETE ON observational_campaign_batches BEGIN SELECT RAISE(ABORT,'batch records are immutable'); END;
    CREATE TRIGGER IF NOT EXISTS observational_campaign_events_no_update
      BEFORE UPDATE ON observational_campaign_events BEGIN SELECT RAISE(ABORT,'event records are immutable'); END;
    CREATE TRIGGER IF NOT EXISTS observational_campaign_events_no_delete
      BEFORE DELETE ON observational_campaign_events BEGIN SELECT RAISE(ABORT,'event records are immutable'); END;
    CREATE TRIGGER IF NOT EXISTS observational_campaign_coverage_no_update
      BEFORE UPDATE ON observational_campaign_coverage BEGIN SELECT RAISE(ABORT,'coverage records are immutable'); END;
    CREATE TRIGGER IF NOT EXISTS observational_campaign_coverage_no_delete
      BEFORE DELETE ON observational_campaign_coverage BEGIN SELECT RAISE(ABORT,'coverage records are immutable'); END;
    CREATE TRIGGER IF NOT EXISTS observational_campaign_corrections_no_update
      BEFORE UPDATE ON observational_campaign_corrections BEGIN SELECT RAISE(ABORT,'corrections are append-only'); END;
    CREATE TRIGGER IF NOT EXISTS observational_campaign_corrections_no_delete
      BEFORE DELETE ON observational_campaign_corrections BEGIN SELECT RAISE(ABORT,'corrections are append-only'); END;
    CREATE TRIGGER IF NOT EXISTS observational_campaign_activity_no_update
      BEFORE UPDATE ON observational_campaign_activity BEGIN SELECT RAISE(ABORT,'activity records are append-only'); END;
    CREATE TRIGGER IF NOT EXISTS observational_campaign_activity_no_delete
      BEFORE DELETE ON observational_campaign_activity BEGIN SELECT RAISE(ABORT,'activity records are append-only'); END;
    """)


def _context(app_id, action, body, store):
    from .operation_authority import PROTECTED, store_identity
    context = PROTECTED.get()
    if context is None or context.get("store") != store_identity(store):
        raise PermissionError("Current exact observational-campaign operation authority is required")
    try:
        envelope = json.loads(context["envelope"])
    except (KeyError, TypeError, ValueError):
        raise PermissionError("Current exact observational-campaign operation authority is required")
    if (not isinstance(envelope, dict) or envelope.get("app_id") != app_id
            or envelope.get("operation") != OPS.get(action) or envelope.get("input") != body
            or set(envelope) - {"app_id", "operation", "input", "resource_id"}):
        raise PermissionError("Current exact observational-campaign operation authority is required")
    definition = body.get("definition") if isinstance(body, dict) else None
    definition_id = definition.get("id") if isinstance(definition, dict) else None
    if "resource_id" in envelope and envelope["resource_id"] not in (None, body.get("study_id"), definition_id):
        raise PermissionError("Current exact observational-campaign operation authority is required")
    return context


def _app(db, app_id):
    row = db.execute("SELECT data,version FROM apps WHERE id=?", (app_id,)).fetchone()
    if row is None:
        raise Invalid("Selected app is unavailable")
    return {"id": app_id, "data": json.loads(row["data"]), "version": row["version"]}


def _manifest(body, app):
    if type(body.get("manifest_version")) is not int or body["manifest_version"] != app["version"]:
        raise Invalid("manifest_version differs from the current app version")


def _study(db, app_id, study_id, study_hash, app):
    contract.uuid_value(study_id, "study_id")
    row = db.execute("SELECT * FROM observational_campaign_studies WHERE app_id=? AND study_id=?", (app_id, study_id)).fetchone()
    if row is None:
        raise Invalid("Study is unavailable in this app")
    data = json.loads(row["data"])
    if digest(data) != row["hash"] or row["hash"] != study_hash:
        raise Invalid("Study hash differs from its saved definition")
    if row["app_version"] != app["version"] or data["release"] != app["data"].get("release"):
        raise Invalid("App version or release changed; register a new study")
    if contract.app_origin(app["data"].get("website")) != data["origin"]:
        raise Invalid("App website changed; register a new study")
    return {"id": study_id, "hash": row["hash"], "app_version": row["app_version"], "data": data}


def _activity(db, app_id, study_id, kind, record_id, value, created):
    value_hash = digest(value)
    db.execute("INSERT INTO observational_campaign_activity VALUES(?,?,?,?,?,?,?)",
               (app_id, study_id, kind, record_id, canonical(value), value_hash, created))
    return value_hash


def _effective_events(db, app_id, study_id):
    rows = db.execute("""SELECT e.source_id,e.event_id,e.data,e.hash,c.replacement,c.replacement_hash
        FROM observational_campaign_events e LEFT JOIN observational_campaign_corrections c
        ON c.app_id=e.app_id AND c.source_id=e.source_id AND c.event_id=e.event_id
        WHERE e.app_id=? AND e.study_id=? ORDER BY e.source_id,e.event_id""", (app_id, study_id)).fetchall()
    result = []
    for row in rows:
        data = json.loads(row["data"])
        if digest(data) != row["hash"]:
            raise Invalid("Stored event integrity differs")
        if row["replacement"] is not None:
            data = json.loads(row["replacement"])
            if digest(data) != row["replacement_hash"]:
                raise Invalid("Stored correction integrity differs")
        result.append((row["source_id"], row["event_id"], data))
    return result


def _measurement_checkpoint(study, coverage, as_of):
    """A rate is usable only after exact, source-reported post-close reconciliation."""
    collector = study.get("collector_source_id")
    closed = iso_time(as_of) >= iso_time(study["ends_at"])
    issues = {}
    if collector:
        for kind in contract.EVENT_TYPES:
            rows = coverage[kind]["sources"]
            source = next((row for row in rows if row["source_id"] == collector), None)
            if source is None:
                issues[kind] = "MISSING_RECEIPT"
            elif iso_time(source["observed_at"]) < iso_time(study["ends_at"]):
                issues[kind] = "BEFORE_CLOSE"
            elif not source["complete"]:
                issues[kind] = "COUNT_MISMATCH" if coverage[kind]["mismatch"] else "INCOMPLETE"
    landing = coverage["LANDING"]["observed_count"]
    registration = coverage["REGISTRATION"]["observed_count"]
    if not collector:
        state = "SOURCE_NOT_DECLARED"
    elif not closed:
        state = "COLLECTING"
    elif issues:
        state = "COVERAGE_INCOMPLETE"
    elif not landing:
        state = "NO_ELIGIBLE_LANDINGS"
    else:
        state = "DESCRIPTIVE_READY"
    ratio_counts = {"linked_registrations": registration, "eligible_landings": landing} if state == "DESCRIPTIVE_READY" else None
    return {"state": state, "collector_source_id": collector, "coverage_issues": issues,
            "ratio_counts": ratio_counts}


def report_in_snapshot(db, app_id, study, app, as_of):
    """Project the selected study without opening another transaction or writing."""
    events = _effective_events(db, app_id, study["id"])
    counts = {name: {} for name in contract.EVENT_TYPES}
    observed_counts = Counter((source_id, event["type"]) for source_id, _, event in events)
    collector = study["data"].get("collector_source_id")
    if collector and any(source_id != collector for source_id, _ in observed_counts):
        raise Invalid("Stored events do not match the declared study collector")
    exclusions = {name: 0 for name in ("CONSENT_DENIED", "CONSENT_UNKNOWN", "BOT", "BOT_UNKNOWN", "INTERNAL_TEST", "TOKEN_MISSING", "TOKEN_INVALID", "UNMATCHED_REGISTRATION")}
    eligible_landings = {}
    observed_by_type = {name: False for name in contract.EVENT_TYPES}
    eligible = []
    for source_id, _event_id, event in events:
        kind = event["type"]
        observed_by_type[kind] = True
        if event["consent"] != "GRANTED":
            exclusions["CONSENT_" + event["consent"]] += 1
            continue
        if event["bot"] is not False:
            exclusions["BOT_UNKNOWN" if event["bot"] is None else "BOT"] += 1
            continue
        if event["internal_test"]:
            exclusions["INTERNAL_TEST"] += 1
            continue
        if event["campaign_token"] is None:
            exclusions["TOKEN_MISSING"] += 1
            continue
        if event["campaign_token"] != study["id"]:
            exclusions["TOKEN_INVALID"] += 1
            continue
        key = (source_id, event["subject_id"])
        time = iso_time(event["occurred_at"])
        if kind == "LANDING":
            eligible_landings[key] = min(time, eligible_landings.get(key, time))
        eligible.append((kind, key, time))
    for kind, key, time in eligible:
        if kind == "LANDING":
            counts[kind][key] = min(time, counts[kind].get(key, time))
        elif key in eligible_landings and eligible_landings[key] < time:
            counts[kind][key] = min(time, counts[kind].get(key, time))
        else:
            exclusions["UNMATCHED_REGISTRATION"] += 1
    coverage = {}
    for event_type in contract.EVENT_TYPES:
        sources = db.execute("SELECT source_id,complete,source_event_count,observed_at,receipt_hash FROM observational_campaign_coverage WHERE app_id=? AND study_id=? AND event_type=? ORDER BY observed_at DESC,created DESC,batch_id DESC", (app_id, study["id"], event_type))
        latest = {}
        for row in sources:
            latest.setdefault(row["source_id"], row)
        complete_sources = 0
        expected_sources = 1 if collector else len(latest)
        source_rows = []
        mismatch = False
        for source_id, row in latest.items():
            if collector and source_id != collector:
                raise Invalid("Stored coverage does not match the declared study collector")
            actual = observed_counts[source_id, event_type]
            valid_complete = bool(row["complete"] and row["source_event_count"] == actual)
            complete_sources += int(valid_complete)
            mismatch = mismatch or bool(row["complete"] and not valid_complete)
            source_rows.append({"source_id": source_id, "complete": valid_complete, "reported_count": row["source_event_count"], "stored_count": actual, "source_receipt_sha256": row["receipt_hash"], "observed_at": row["observed_at"]})
        complete = expected_sources > 0 and complete_sources == expected_sources and not mismatch
        if collector:
            complete = complete and all(iso_time(row["observed_at"]) >= iso_time(study["data"]["ends_at"])
                                        for row in source_rows)
        n = len(counts[event_type])
        value = n if observed_by_type[event_type] or complete else None
        coverage[event_type] = {"coverage_complete": complete, "source_count": expected_sources, "complete_source_count": complete_sources, "mismatch": mismatch, "sources": source_rows}
        coverage[event_type]["observed_count"] = value
    checkpoint = _measurement_checkpoint(study["data"], coverage, as_of)
    return {"schema": "growth.observational-campaign-report.v1", "checkpoint": checkpoint, "study_id": study["id"], "study_hash": study["hash"], "app_id": app_id, "app_version": app["version"], "release": study["data"]["release"], "starts_at": study["data"]["starts_at"], "ends_at": study["data"]["ends_at"], "as_of": as_of, "landing_subjects": coverage["LANDING"]["observed_count"], "linked_registration_subjects": coverage["REGISTRATION"]["observed_count"], "coverage": coverage, "exclusions": exclusions, "status": "ATTRIBUTED_DESCRIPTIVE_ONLY", "provenance": "SOURCE_REPORTED_NOT_PROVIDER_VERIFIED", "source_hash": digest({"study_hash": study["hash"], "events": [(s, i, digest(e)) for s, i, e in events], "coverage": coverage}), "limits": ["No install, activation, revenue, lift, or causal decision is reported.", "bot=false is not proof of a human.", "First-touch attribution may reflect an earlier campaign."]}


class ObservationalCampaign:
    """Append-only one-study attribution with current exact operation authority."""
    def __init__(self, store):
        self.store = store

    def dispatch(self, app_id, action, body):
        if action not in contract.ACTION_NAMES:
            raise Invalid("Unknown observational campaign action")
        schema = contract.ACTION_FIELDS[action]
        required, optional = set(schema["required"]), set(schema["optional"])
        if not isinstance(body, dict) or set(body) - required - optional or required - set(body):
            raise Invalid("Operation fields must match the declared schema")
        method = self.tagged_url if action == "link" else getattr(self, action)
        return method(app_id, body)

    def register(self, app_id, body):
        context = _context(app_id, "register", body, self.store)
        schema = contract.ACTION_FIELDS["register"]
        contract.exact(body, set(schema["required"]) | set(schema["optional"]), "Registration")
        request_id = contract.uuid_value(body["request_id"], "request_id")
        if type(body["manifest_version"]) is not int:
            raise Invalid("manifest_version must be an integer")
        request_hash = digest({"manifest_version": body["manifest_version"], "definition": body["definition"]})
        with connection(self.store.path) as db:
            _tables(db)
            db.execute("BEGIN IMMEDIATE")
            from .operation_authority import check
            actor = check(db, context)
            app = _app(db, app_id)
            _manifest(body, app)
            old = db.execute("SELECT * FROM observational_campaign_studies WHERE app_id=? AND request_id=?", (app_id, request_id)).fetchone()
            if old:
                if old["request_hash"] != request_hash:
                    raise Invalid("request_id already identifies different registration content")
                return {"study_id": old["study_id"], "study_hash": old["hash"], "app_version": old["app_version"], "status": "REGISTERED", "idempotent": True}
            created = now()
            definition = contract.definition_data(body["definition"], created)
            origin = contract.app_origin(app["data"].get("website"))
            data = dict(definition, app_id=app_id, app_version=app["version"], release=app["data"].get("release", ""), origin=origin, registered_at=created)
            value_hash = digest(data)
            if db.execute("SELECT 1 FROM observational_campaign_studies WHERE app_id=? AND study_id=?", (app_id, definition["id"])).fetchone():
                raise Invalid("Study ID is already registered")
            db.execute("INSERT INTO observational_campaign_studies VALUES(?,?,?,?,?,?,?,?)", (app_id, definition["id"], request_id, request_hash, app["version"], canonical(data), value_hash, created))
            receipt = {"study_id": definition["id"], "study_hash": value_hash, "app_version": app["version"], "status": "REGISTERED", "actor_scope": "CURRENT_AUTHORITY", "actor": actor}
            _activity(db, app_id, definition["id"], "REGISTERED", request_id, receipt, created)
        return receipt

    def tagged_url(self, app_id, body):
        context = _context(app_id, "link", body, self.store)
        schema = contract.ACTION_FIELDS["link"]
        contract.exact(body, set(schema["required"]) | set(schema["optional"]), "Tagged URL")
        with connection(self.store.path) as db:
            _tables(db)
            from .operation_authority import check
            check(db, context)
            app = _app(db, app_id)
            _manifest(body, app)
            study = _study(db, app_id, body["study_id"], body["study_hash"], app)
            url = contract.tagged_url(app["data"].get("website"), study["data"])
            return {"study_id": study["id"], "study_hash": study["hash"], "url": url, "url_sha256": __import__("hashlib").sha256(url.encode()).hexdigest(), "status": "LOCAL_LINK_PREPARED",
                    "study": {key: study["data"][key] for key in
                              ("name", "hypothesis", "source", "creative_id", "starts_at", "ends_at")}
                              | {"collector_source_id": study["data"].get("collector_source_id")}}

    def ingest(self, app_id, body):
        context = _context(app_id, "ingest", body, self.store)
        schema = contract.ACTION_FIELDS["ingest"]
        contract.exact(body, set(schema["required"]) | set(schema["optional"]), "Ingest")
        created = now()
        with connection(self.store.path) as db:
            _tables(db)
            db.execute("BEGIN IMMEDIATE")
            from .operation_authority import check
            actor = check(db, context)
            app = _app(db, app_id)
            _manifest(body, app)
            study = _study(db, app_id, body["study_id"], body["study_hash"], app)
            batch = contract.batch_data(body["batch"], study, app["version"], created)
            batch_hash = digest(batch)
            old = db.execute("SELECT * FROM observational_campaign_batches WHERE app_id=? AND batch_id=?", (app_id, batch["batch_id"])).fetchone()
            if old:
                if old["hash"] != batch_hash or old["study_id"] != study["id"]:
                    raise Invalid("Batch ID already exists with conflicting content")
                return json.loads(old["receipt"])
            inserted = duplicates = 0
            staged = []
            seen = {}
            for event in batch["events"]:
                event_hash = digest(event)
                prior = seen.get(event["event_id"])
                if prior:
                    if prior != event_hash:
                        raise Invalid("Event ID collision in batch")
                    duplicates += 1
                    continue
                seen[event["event_id"]] = event_hash
                existing = db.execute("SELECT study_id,data,hash FROM observational_campaign_events WHERE app_id=? AND source_id=? AND event_id=?", (app_id, batch["source_id"], event["event_id"])).fetchone()
                if existing:
                    if existing["study_id"] != study["id"] or existing["hash"] != event_hash:
                        raise Invalid("Event ID conflicts with saved source evidence")
                    duplicates += 1
                    continue
                staged.append((event, event_hash))
            for event, event_hash in staged:
                db.execute("INSERT INTO observational_campaign_events VALUES(?,?,?,?,?,?,?,?)", (app_id, study["id"], batch["source_id"], event["event_id"], batch["batch_id"], canonical(event), event_hash, created))
                inserted += 1
            for event_type in contract.EVENT_TYPES:
                cov = batch["coverage"][event_type]
                complete = int(cov["complete"])
                db.execute("INSERT INTO observational_campaign_coverage VALUES(?,?,?,?,?,?,?,?,?,?)", (app_id, study["id"], batch["source_id"], event_type, batch["batch_id"], complete, cov["source_event_count"], batch["observed_at"], batch["source_receipt_sha256"], created))
            receipt = {"schema": "growth.observational-campaign-batch-receipt.v1", "study_id": study["id"], "study_hash": study["hash"], "batch_id": batch["batch_id"], "source_id": batch["source_id"], "batch_hash": batch_hash, "source_receipt_sha256": batch["source_receipt_sha256"], "inserted": inserted, "duplicates": duplicates, "coverage": {key: {"reported_complete": val["complete"], "source_event_count": val["source_event_count"]} for key, val in batch["coverage"].items()}, "status": "SOURCE_REPORTED", "received_at": created}
            db.execute("INSERT INTO observational_campaign_batches VALUES(?,?,?,?,?,?,?,?)", (app_id, study["id"], batch["batch_id"], batch["source_id"], batch_hash, canonical(batch), canonical(receipt), created))
            _activity(db, app_id, study["id"], "INGESTED", batch["batch_id"], dict(receipt, actor=actor), created)
        return receipt

    def report(self, app_id, body):
        context = _context(app_id, "report", body, self.store)
        schema = contract.ACTION_FIELDS["report"]
        contract.exact(body, set(schema["required"]) | set(schema["optional"]), "Report")
        as_of = now()
        with connection(self.store.path) as db:
            _tables(db)
            db.execute("BEGIN")
            from .operation_authority import check
            check(db, context)
            app = _app(db, app_id)
            _manifest(body, app)
            study = _study(db, app_id, body["study_id"], body["study_hash"], app)
            return report_in_snapshot(db, app_id, study, app, as_of)

    def history(self, app_id, body):
        context = _context(app_id, "history", body, self.store)
        if not isinstance(body, dict) or set(body) - {"offset"}:
            raise Invalid("History accepts only optional offset")
        offset = body.get("offset", 0)
        if type(offset) is not int or not 0 <= offset <= 10000:
            raise Invalid("offset must be an integer from 0 through 10000")
        with connection(self.store.path) as db:
            _tables(db)
            from .operation_authority import check
            check(db, context)
            rows = db.execute("SELECT kind,record_id,data,hash,created FROM observational_campaign_activity WHERE app_id=? ORDER BY created DESC,kind,record_id LIMIT 100 OFFSET ?", (app_id, offset)).fetchall()
            return {"schema": "growth.observational-campaign-history.v1", "records": [{"kind": r["kind"], "record_id": r["record_id"], "data": json.loads(r["data"]), "hash": r["hash"], "created_at": r["created"]} for r in rows], "limit": 100, "offset": offset}

    def correct(self, app_id, body):
        context = _context(app_id, "correct", body, self.store)
        schema = contract.ACTION_FIELDS["correct"]
        contract.exact(body, set(schema["required"]) | set(schema["optional"]), "Correction")
        correction = body["correction"]
        if not isinstance(correction, dict):
            raise Invalid("correction must be an object")
        created = now()
        with connection(self.store.path) as db:
            _tables(db)
            db.execute("BEGIN IMMEDIATE")
            from .operation_authority import check
            actor = check(db, context)
            app = _app(db, app_id)
            _manifest(body, app)
            study = _study(db, app_id, body["study_id"], body["study_hash"], app)
            value = contract.correction_data(correction, study, app["version"], created)
            row = db.execute("SELECT data,hash,study_id FROM observational_campaign_events WHERE app_id=? AND source_id=? AND event_id=?", (app_id, value["source_id"], value["event_id"])).fetchone()
            if row is None or row["study_id"] != study["id"] or row["hash"] != value["original_hash"] or digest(json.loads(row["data"])) != row["hash"]:
                raise Invalid("Correction original event identity or hash differs")
            if db.execute("SELECT 1 FROM observational_campaign_corrections WHERE app_id=? AND source_id=? AND event_id=?", (app_id, value["source_id"], value["event_id"])).fetchone():
                raise Invalid("An event can have only one correction record")
            replacement_hash = digest(value["replacement"])
            correction_hash = digest(value)
            db.execute("INSERT INTO observational_campaign_corrections VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (app_id, study["id"], value["correction_id"], value["source_id"], value["event_id"], value["original_hash"], canonical(value["replacement"]), replacement_hash, value["reason"], actor, created, correction_hash))
            receipt = {"schema": "growth.observational-campaign-correction-receipt.v1", "study_id": study["id"], "correction_id": value["correction_id"], "event_id": value["event_id"], "original_hash": value["original_hash"], "replacement_hash": replacement_hash, "correction_hash": correction_hash, "created_at": created}
            _activity(db, app_id, study["id"], "CORRECTED", value["correction_id"], dict(receipt, actor=actor), created)
        return receipt
