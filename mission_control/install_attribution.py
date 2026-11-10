"""Exact MMP install export tied to a campaign token; descriptive counts only."""
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from .common import Invalid, canonical, digest, iso_time, now, uid
from .db import connection
from .review_access import member

STATES = ("ATTRIBUTED", "UNATTRIBUTED", "SUPPRESSED", "UNKNOWN")
SOURCE = re.compile(r"[A-Z][A-Z0-9_]{1,31}")
OPAQUE = re.compile(r"[A-Za-z0-9_-]{1,128}")
SHA256 = re.compile(r"[a-f0-9]{64}")


def _exact(value, keys):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise Invalid("Use the exact install attribution fields")


def _uuid(value, name):
    try:
        if str(uuid.UUID(value)) != value:
            raise ValueError()
    except (ValueError, TypeError, AttributeError) as exc:
        raise Invalid(name + " must be a canonical UUID") from exc
    return value


def _time(value, name):
    try:
        return iso_time(value).astimezone(timezone.utc)
    except Exception as exc:
        raise Invalid(name + " must be an ISO timestamp with timezone") from exc


def _window(value):
    _exact(value, ("starts_at", "ends_at"))
    starts = _time(value["starts_at"], "Window start")
    ends = _time(value["ends_at"], "Window end")
    if not starts < ends:
        raise Invalid("Window start must be before its end")
    if (ends - starts).total_seconds() > 90 * 86400:
        raise Invalid("Window cannot exceed 90 days")
    return dict(starts_at=starts.isoformat(), ends_at=ends.isoformat())


def _install(row, observed, window):
    _exact(row, ("install_id", "state", "occurred_at"))
    identity = row["install_id"]
    if not isinstance(identity, str) or not OPAQUE.fullmatch(identity):
        raise Invalid("Install identity must be a bounded opaque token")
    raw_device_id = re.fullmatch(r"(?:[0-9a-fA-F]{16}|[0-9a-fA-F]{32}|[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12})", identity)
    if re.fullmatch(r"[0-9_-]{7,}", identity) or raw_device_id:
        raise Invalid("Use a pseudonymous install token without raw phone or device identifiers")
    if row["state"] not in STATES:
        raise Invalid("Install state must be ATTRIBUTED, UNATTRIBUTED, SUPPRESSED or UNKNOWN")
    occurred = _time(row["occurred_at"], "Occurred time")
    if occurred > observed:
        raise Invalid("Install time cannot be after the source observation")
    if not iso_time(window["starts_at"]) <= occurred <= iso_time(window["ends_at"]):
        raise Invalid("Install time must fall inside the declared window")
    return dict(install_id=identity, state=row["state"], occurred_at=occurred.isoformat())


def _coverage(value):
    if (not isinstance(value, dict) or not {"complete", "source_event_count"} <= set(value)
            or set(value) - {"complete", "source_event_count", "excluded"}):
        raise Invalid("Use the exact coverage fields")
    if type(value["complete"]) is not bool:
        raise Invalid("Coverage complete must be an explicit boolean")
    count = value["source_event_count"]
    if count is not None and (type(count) is not int or not 0 <= count <= 1000000):
        raise Invalid("Source event count must be null or a bounded whole number")
    if value["complete"] and count is None:
        raise Invalid("Complete coverage must state the source event count")
    excluded = value.get("excluded", {})
    if not isinstance(excluded, dict) or len(excluded) > 20:
        raise Invalid("Excluded counts must be a bounded object")
    for reason, number in excluded.items():
        if not isinstance(reason, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", reason):
            raise Invalid("Exclusion reasons must be uppercase tokens")
        if type(number) is not int or not 0 <= number <= 1000000:
            raise Invalid("Excluded counts must be bounded whole numbers")
    return dict(complete=value["complete"], source_event_count=count, excluded=dict(excluded))


def validate_batch(body):
    """Validate one exact batch without touching storage; used by imports and the mapper."""
    _exact(body, ("source", "campaign_token", "request_id", "source_receipt_sha256",
                  "observed_at", "window", "coverage", "installs"))
    source = body["source"]
    if not isinstance(source, str) or not SOURCE.fullmatch(source):
        raise Invalid("Attribution source must be an uppercase token")
    campaign = _uuid(body["campaign_token"], "Campaign token")
    request = _uuid(body["request_id"], "Request identity")
    receipt = body["source_receipt_sha256"]
    if not isinstance(receipt, str) or not SHA256.fullmatch(receipt):
        raise Invalid("Source receipt must be a lowercase SHA-256")
    observed = _time(body["observed_at"], "Observed time")
    window = _window(body["window"])
    if observed < iso_time(window["starts_at"]) or observed > iso_time(now()):
        raise Invalid("Source observation must be between the window start and the current time")
    coverage = _coverage(body["coverage"])
    if coverage["complete"] and observed < iso_time(window["ends_at"]):
        raise Invalid("Complete coverage requires an observation at or after the window ends")
    installs = body["installs"]
    if not isinstance(installs, list) or len(installs) > 1000:
        raise Invalid("Provide between 0 and 1000 install rows")
    rows = [_install(row, observed, window) for row in installs]
    if len({row["install_id"] for row in rows}) != len(rows):
        raise Invalid("Install identities must be unique within one batch")
    accounted = len(rows) + sum(coverage["excluded"].values())
    if coverage["source_event_count"] is not None and coverage["source_event_count"] < accounted:
        raise Invalid("Source event count cannot be below imported plus excluded records")
    if coverage["complete"] and coverage["source_event_count"] != accounted:
        raise Invalid("Complete coverage must equal imported plus excluded records")
    return dict(source=source, campaign_token=campaign, request_id=request,
                source_receipt_sha256=receipt, observed_at=observed.isoformat(), window=window,
                coverage=coverage, installs=rows)


def _study_link(db, app_id, campaign_token):
    """Resolve an exact registered study and its immutable observation window."""
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='observational_campaign_studies'").fetchone():
        return None
    row = db.execute("SELECT study_id,hash,app_version,registered_at,data FROM observational_campaign_studies "
                     "WHERE app_id=? AND study_id=?", (app_id, campaign_token)).fetchone()
    if row is None:
        return None
    data = json.loads(row["data"])
    if digest(data) != row["hash"]:
        raise Invalid("Registered study integrity changed")
    return dict(study_id=row["study_id"], study_hash=row["hash"],
                app_version=row["app_version"], registered_at=row["registered_at"],
                window=_window({key: data[key] for key in ("starts_at", "ends_at")}))


def _owner_context(db, app_id, user):
    owner = member(db, app_id, user["principal"], "OWNER")
    app = db.execute("SELECT version FROM apps WHERE id=?", (app_id,)).fetchone()
    if app is None:
        raise Invalid("Select an existing app")
    return owner, app["version"]


def _import_binding(db, app_id, data):
    study = _study_link(db, app_id, data["campaign_token"])
    if study is not None and data["window"] != study["window"]:
        raise Invalid("Use the exact registered study window")
    return study


def _normalize_stored_times(data):
    """Read old offset representations without changing their saved receipt hash."""
    return dict(data, window=_window(data["window"]),
                observed_at=_time(data["observed_at"], "Observed time").isoformat(),
                installs=[dict(row, occurred_at=_time(row["occurred_at"], "Occurred time").isoformat())
                          for row in data["installs"]])


def _saved_input(saved, data):
    stored = json.loads(saved["data"])
    if digest(stored) != saved["hash"]:
        raise Invalid("Saved install batch integrity changed")
    study = stored.pop("study_link", None)
    if _normalize_stored_times(stored) != data:
        raise Invalid("Request identity was already used with a different batch")
    return study


def _check_retained_rows(db, app_id, data):
    duplicates = 0
    for row in data["installs"]:
        prior = db.execute("SELECT campaign_token,state,occurred_at FROM install_attribution_rows "
                           "WHERE app_id=? AND source=? AND install_id=?",
                           (app_id, data["source"], row["install_id"])).fetchone()
        if prior is None:
            continue
        if (prior["campaign_token"], prior["state"], iso_time(prior["occurred_at"])) != (
                data["campaign_token"], row["state"], iso_time(row["occurred_at"])):
            raise Invalid("One or more install identities conflict with retained attribution")
        duplicates += 1
    return duplicates


def preview_batch(store, app_id, user, data):
    """Keep a bounded durable digest of the owner's exact normalized preview."""
    with connection(store.path) as db:
        db.execute("BEGIN IMMEDIATE")
        owner, app_version = _owner_context(db, app_id, user)
        saved = db.execute("SELECT * FROM install_attribution_batches WHERE app_id=? AND id=?",
                           (app_id, data["request_id"])).fetchone()
        study = _saved_input(saved, data) if saved else _import_binding(db, app_id, data)
        if not saved:
            _check_retained_rows(db, app_id, data)
        preview = uid()
        expires = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()
        db.execute("INSERT OR REPLACE INTO install_import_previews VALUES(?,?,?,?,?,?,?)",
                   (app_id, owner["principal"], preview, owner["version"], app_version,
                    digest(dict(batch=data, study=study)), expires))
        return preview


def _require_preview(db, app_id, owner, app_version, identity, data, study):
    _uuid(identity, "Preview identity")
    row = db.execute("SELECT * FROM install_import_previews WHERE app_id=? AND owner=? AND id=?",
                     (app_id, owner["principal"], identity)).fetchone()
    if (row is None or iso_time(row["expires"]) <= datetime.now(timezone.utc)
            or row["role_version"] != owner["version"] or row["app_version"] != app_version
            or row["request_hash"] != digest(dict(batch=data, study=study))):
        raise Invalid("Preview this exact install export again before confirming")


def record_batch(store, app_id, user, body, *, preview_id=None):
    """Retain one atomic, app-owner install export; never infer lift or rates."""
    store.app(app_id)
    data = validate_batch(body)
    source, campaign, request, rows = (data["source"], data["campaign_token"],
                                       data["request_id"], data["installs"])
    with connection(store.path) as db:
        db.execute("BEGIN IMMEDIATE")
        owner, app_version = _owner_context(db, app_id, user)
        saved = db.execute("SELECT * FROM install_attribution_batches WHERE app_id=? AND id=?",
                           (app_id, request)).fetchone()
        study = _saved_input(saved, data) if saved else _import_binding(db, app_id, data)
        if preview_id is not None:
            _require_preview(db, app_id, owner, app_version, preview_id, data, study)
        if saved:
            return dict(id=saved["id"], hash=saved["hash"], status="ALREADY_RECORDED",
                        inserted=0, duplicates=len(rows))
        data["study_link"] = study
        hashed = digest(data)
        duplicates = _check_retained_rows(db, app_id, data)
        stamp = now()
        db.execute("INSERT INTO install_attribution_batches VALUES(?,?,?,?,?,?,?)",
                   (app_id, request, campaign, source, canonical(data), hashed, stamp))
        inserted = 0
        for row in rows:
            changed = db.execute("INSERT OR IGNORE INTO install_attribution_rows VALUES(?,?,?,?,?,?,?,?)",
                                 (app_id, request, campaign, source, row["install_id"], row["state"],
                                  row["occurred_at"], stamp)).rowcount
            inserted += changed
        return dict(id=request, hash=hashed, status="RECORDED", inserted=inserted, duplicates=duplicates)


def _batch_coverage(row, *, include_rows=False):
    data = json.loads(row["data"])
    if digest(data) != row["hash"]:
        raise Invalid("Saved install batch integrity changed")
    data = _normalize_stored_times(data)
    declared = data["coverage"]["source_event_count"]
    imported = len(data["installs"])
    excluded = sum(data["coverage"].get("excluded", {}).values())
    result = dict(batch_id=row["id"], source=data["source"], complete=data["coverage"]["complete"],
                source_event_count=declared, imported=imported, excluded=excluded,
                reconciled=not data["coverage"]["complete"] or declared == imported + excluded,
                observed_at=data["observed_at"], window=data["window"],
                source_receipt_sha256=data["source_receipt_sha256"], batch_hash=row["hash"],
                study_link=data.get("study_link"))
    result["declaration_hash"] = digest({key: value for key, value in data.items() if key != "request_id"})
    if include_rows:
        result["installs"] = data["installs"]
    return result


def _coverage_result(batches, study, cutoff=None):
    reasons = []
    if len({item["declaration_hash"] for item in batches}) > 1:
        reasons.append("MULTIPLE_BATCH_DECLARATIONS")
    if any(not item["complete"] for item in batches):
        reasons.append("INCOMPLETE_COVERAGE")
    if any(not item["reconciled"] for item in batches):
        reasons.append("UNRECONCILED_COUNTS")
    if any(study and item["window"] != study["window"] for item in batches):
        reasons.append("STUDY_WINDOW_MISMATCH")
    if any((cutoff and iso_time(item["window"]["ends_at"]) < cutoff)
           or iso_time(item["observed_at"]) < (cutoff or iso_time(item["window"]["ends_at"]))
           for item in batches):
        reasons.append("WINDOW_NOT_FULLY_OBSERVED")
    links = [item["study_link"] for item in batches]
    linked = bool(study and links and all(link and link["study_hash"] == study["study_hash"] and item["window"] == study["window"]
                                         for link, item in zip(links, batches)))
    study_status = "LINKED" if linked else "MIXED" if any(links) else "UNLINKED"
    status = "NO_IMPORT" if not batches else "PARTIAL" if reasons else "COMPLETE"
    return status, reasons, study_status


def report(store, app_id, user, campaign_token, day=None):
    """Return descriptive install counts and exact coverage, with unknowns kept null."""
    store.app(app_id)
    campaign = _uuid(campaign_token, "Campaign token")
    if day is not None and (type(day) is not int or day not in (1, 3, 7)):
        raise Invalid("Day aggregation must be 1, 3, 7 or omitted")
    with connection(store.path) as db:
        db.execute("BEGIN")
        member(db, app_id, user["principal"], "OWNER")
        study = _study_link(db, app_id, campaign)
        batches = [_batch_coverage(row, include_rows=True) for row in db.execute(
            "SELECT id,source,data,hash FROM install_attribution_batches "
            "WHERE app_id=? AND campaign_token=? ORDER BY created,id", (app_id, campaign))]
    installs = {}
    starts = {iso_time(item["window"]["starts_at"]) for item in batches}
    if study:
        starts = {iso_time(study["window"]["starts_at"])}
    for item in batches:
        rows = item.pop("installs")
        if not study or item["window"] == study["window"]:
            for row in rows:
                installs.setdefault((item["source"], row["install_id"]), row)
    if day is not None and len(starts) > 1:
        raise Invalid("Day views require one frozen campaign window; batches declare different starts")
    campaign_start = next(iter(starts)) if len(starts) == 1 else None
    cutoff = campaign_start + timedelta(days=day) if campaign_start is not None and day is not None else None
    rows = [row for row in installs.values()
            if cutoff is None or iso_time(row["occurred_at"]) <= cutoff]
    status, reasons, study_status = _coverage_result(batches, study, cutoff)
    counts = {state: 0 for state in STATES}
    for row in rows:
        counts[row["state"]] += 1
    if status != "COMPLETE":
        counts = {state: count or None for state, count in counts.items()}
    public = [dict({k: v for k, v in item.items() if k not in ("study_link", "declaration_hash")},
                   study_linked=bool(item["study_link"])) for item in batches]
    return dict(schema="growth.install-attribution-report.v1", app_id=app_id,
                campaign_token=campaign, counts=counts, recorded=len(rows) if batches else None,
                coverage_status=status, coverage_reasons=reasons, batches=public,
                campaign_start=campaign_start.isoformat() if campaign_start else None,
                study=study if study_status == "LINKED" else None, study_status=study_status, day=day,
                aggregation=(dict(day=day, rule="INSTALL_OCCURRED_AT_OR_BEFORE_CAMPAIGN_START_PLUS_DAY")
                             if day is not None else None),
                scope="Descriptive linked installs from supplied exports only; no rate, lift, revenue or causal claim.",
                external_writes=False)


def summary(store, app_id):
    """Workspace-safe metadata using the same coverage rules as the owner report."""
    store.app(app_id)
    with connection(store.path) as db:
        db.execute("BEGIN")
        campaigns = {}
        for row in db.execute("SELECT campaign_token,id,source,data,hash FROM install_attribution_batches "
                              "WHERE app_id=? ORDER BY created,id", (app_id,)):
            campaigns.setdefault(row["campaign_token"], []).append(_batch_coverage(row))
        result = []
        for token, batches in sorted(campaigns.items()):
            coverage, _, study_status = _coverage_result(batches, _study_link(db, app_id, token))
            result.append(dict(campaign_token=token, batches=len(batches), coverage_status=coverage,
                               study_status=study_status,
                               last_observed_at=max(item["observed_at"] for item in batches)))
    return dict(schema="growth.install-attribution-summary.v1", app_id=app_id, campaigns=result,
                scope="Export coverage and study link metadata only; install counts are in the owner report.")
