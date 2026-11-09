"""Exact MMP install export tied to a campaign token; descriptive counts only."""
import json
import re
import uuid
from .common import Invalid, canonical, digest, iso_time, now
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
        return iso_time(value)
    except Exception as exc:
        raise Invalid(name + " must be an ISO timestamp with timezone") from exc


def _install(row, observed):
    _exact(row, ("install_id", "state", "occurred_at"))
    identity = row["install_id"]
    if not isinstance(identity, str) or not OPAQUE.fullmatch(identity):
        raise Invalid("Install identity must be a bounded opaque token")
    if identity.isdigit() and len(identity) >= 7:
        raise Invalid("Install identity cannot be a raw phone-like number")
    if row["state"] not in STATES:
        raise Invalid("Install state must be ATTRIBUTED, UNATTRIBUTED, SUPPRESSED or UNKNOWN")
    occurred = _time(row["occurred_at"], "Occurred time")
    if occurred > observed:
        raise Invalid("Install time cannot be after the source observation")
    return dict(install_id=identity, state=row["state"], occurred_at=occurred.isoformat())


def _coverage(value):
    _exact(value, ("complete", "source_event_count"))
    if type(value["complete"]) is not bool:
        raise Invalid("Coverage complete must be an explicit boolean")
    count = value["source_event_count"]
    if count is not None and (type(count) is not int or not 0 <= count <= 1000000):
        raise Invalid("Source event count must be null or a bounded whole number")
    if value["complete"] and count is None:
        raise Invalid("Complete coverage must state the source event count")
    return dict(complete=value["complete"], source_event_count=count)


def validate_batch(body):
    """Validate one exact batch without touching storage; used by imports and the mapper."""
    _exact(body, ("source", "campaign_token", "request_id", "source_receipt_sha256",
                  "observed_at", "coverage", "installs"))
    source = body["source"]
    if not isinstance(source, str) or not SOURCE.fullmatch(source):
        raise Invalid("Attribution source must be an uppercase token")
    campaign = _uuid(body["campaign_token"], "Campaign token")
    request = _uuid(body["request_id"], "Request identity")
    receipt = body["source_receipt_sha256"]
    if not isinstance(receipt, str) or not SHA256.fullmatch(receipt):
        raise Invalid("Source receipt must be a lowercase SHA-256")
    observed = _time(body["observed_at"], "Observed time")
    coverage = _coverage(body["coverage"])
    installs = body["installs"]
    if not isinstance(installs, list) or len(installs) > 1000:
        raise Invalid("Provide between 0 and 1000 install rows")
    rows = [_install(row, observed) for row in installs]
    if len({row["install_id"] for row in rows}) != len(rows):
        raise Invalid("Install identities must be unique within one batch")
    return dict(source=source, campaign_token=campaign, request_id=request,
                source_receipt_sha256=receipt, observed_at=observed.isoformat(),
                coverage=coverage, installs=rows)


def _study_link(db, app_id, campaign_token):
    """Link to the exact app-scoped observational study when one is registered."""
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='observational_campaign_studies'").fetchone():
        return None
    row = db.execute("SELECT study_id,hash,app_version,registered_at FROM observational_campaign_studies "
                     "WHERE app_id=? AND study_id=?", (app_id, campaign_token)).fetchone()
    if row is None:
        return None
    return dict(study_id=row["study_id"], study_hash=row["hash"],
                app_version=row["app_version"], registered_at=row["registered_at"])


def record_batch(store, app_id, user, body):
    """Retain one atomic, app-owner install export; never infer lift or rates."""
    store.app(app_id)
    data = validate_batch(body)
    source, campaign, request, rows = (data["source"], data["campaign_token"],
                                       data["request_id"], data["installs"])
    with connection(store.path) as db:
        db.execute("BEGIN IMMEDIATE")
        member(db, app_id, user["principal"], "OWNER")
        data["study_link"] = _study_link(db, app_id, campaign)
        hashed = digest(data)
        saved = db.execute("SELECT * FROM install_attribution_batches WHERE app_id=? AND id=?",
                           (app_id, request)).fetchone()
        if saved:
            if saved["hash"] != hashed:
                raise Invalid("Request identity was already used with a different batch")
            return dict(id=saved["id"], hash=saved["hash"], status="ALREADY_RECORDED",
                        inserted=0, duplicates=len(rows))
        conflicts = []
        duplicates = 0
        for row in rows:
            prior = db.execute("SELECT campaign_token,state,occurred_at FROM install_attribution_rows "
                               "WHERE app_id=? AND source=? AND install_id=?",
                               (app_id, source, row["install_id"])).fetchone()
            if prior is None:
                continue
            if (prior["campaign_token"], prior["state"], prior["occurred_at"]) != (
                    campaign, row["state"], row["occurred_at"]):
                conflicts.append(row["install_id"])
            else:
                duplicates += 1
        if conflicts:
            raise Invalid("Install identities conflict with retained attribution: " + ", ".join(conflicts[:5]))
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


def report(store, app_id, user, campaign_token):
    """Return descriptive install counts and explicit coverage, never a rate or lift."""
    store.app(app_id)
    campaign = _uuid(campaign_token, "Campaign token")
    with connection(store.path) as db:
        member(db, app_id, user["principal"], "OWNER")
        rows = [dict(row) for row in db.execute(
            "SELECT state,occurred_at FROM install_attribution_rows WHERE app_id=? AND campaign_token=?",
            (app_id, campaign))]
        batches = [dict(row) for row in db.execute(
            "SELECT id,source,data,hash,created FROM install_attribution_batches "
            "WHERE app_id=? AND campaign_token=? ORDER BY created,id", (app_id, campaign))]
    counts = {state: 0 for state in STATES}
    for row in rows:
        counts[row["state"]] += 1
    coverage = []
    linked = []
    for batch in batches:
        data = json.loads(batch["data"])
        if data.get("study_link"):
            linked.append(data["study_link"])
        coverage.append(dict(batch_id=batch["id"], source=data["source"],
                             complete=data["coverage"]["complete"],
                             source_event_count=data["coverage"]["source_event_count"],
                             observed_at=data["observed_at"], receipt_sha256=batch["hash"],
                             study_linked=bool(data.get("study_link"))))
    if not coverage:
        status = "NO_IMPORT"
    elif all(item["complete"] for item in coverage):
        status = "COMPLETE"
    else:
        status = "PARTIAL"
    study = linked[0] if linked and all(item == linked[0] for item in linked) else None
    study_status = "LINKED" if study else ("MIXED" if linked else "UNLINKED")
    return dict(schema="growth.install-attribution-report.v1", app_id=app_id,
                campaign_token=campaign, counts=counts, recorded=len(rows),
                coverage_status=status, batches=coverage, study=study,
                study_status=study_status,
                scope="Descriptive linked installs from supplied exports only; no rate, lift, revenue or causal claim.",
                external_writes=False)



def summary(store, app_id):
    """Workspace-safe metadata: campaign tokens, coverage and study linkage only."""
    store.app(app_id)
    with connection(store.path) as db:
        rows = [dict(row) for row in db.execute(
            "SELECT campaign_token,data,created FROM install_attribution_batches WHERE app_id=? "
            "ORDER BY created,id", (app_id,))]
    campaigns = {}
    for row in rows:
        data = json.loads(row["data"])
        item = campaigns.setdefault(row["campaign_token"], dict(campaign_token=row["campaign_token"],
                                                                 batches=0, complete=True, linked=[],
                                                                 last_observed_at=None))
        item["batches"] += 1
        item["complete"] = item["complete"] and data["coverage"]["complete"]
        if data.get("study_link"):
            item["linked"].append(data["study_link"])
        observed = data["observed_at"]
        if item["last_observed_at"] is None or observed > item["last_observed_at"]:
            item["last_observed_at"] = observed
    result = []
    for token in sorted(campaigns):
        item = campaigns[token]
        linked = item.pop("linked")
        item["coverage_status"] = "COMPLETE" if item.pop("complete") else "PARTIAL"
        item["study_status"] = "LINKED" if linked and all(link == linked[0] for link in linked) else (
            "MIXED" if linked else "UNLINKED")
        result.append(item)
    return dict(schema="growth.install-attribution-summary.v1", app_id=app_id, campaigns=result,
                scope="Export coverage and study link metadata only; install counts are in the owner report.")
