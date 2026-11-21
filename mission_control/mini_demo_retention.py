"""Source-bound return events join the existing tagged landing/registration lane."""

from datetime import timedelta
from sqlite3 import Connection

from .common import Invalid, digest, iso_time, now
from .observational_campaign import _app, _effective_events, _study, report_in_snapshot
from .observational_campaign_contract import opaque
from .pmf_contract import exact, hashed


def assess(db: Connection, app: str, demo: dict, body: dict) -> dict:
    """Count mature registered subjects only, never infer unknown coverage or identity."""
    data = demo["data"]
    context = _app(db, app)
    study = _study(db, app, data["study_id"], data["study_hash"], context)
    source = opaque(body["source_id"], "Retention source")
    collector = study["data"].get("collector_source_id")
    if collector is None or source != collector:
        raise Invalid("Retention needs the study's declared collector and same subject namespace")
    days = body["days"]
    if type(days) is not int or not 1 <= days <= 30:
        raise Invalid("Choose a retention checkpoint from 1 through 30 days")
    observed = iso_time(body["observed_at"])
    through = iso_time(body["coverage_through"])
    since = iso_time(body["coverage_from"])
    if not since <= through <= observed <= iso_time(now()):
        raise Invalid("Retention coverage must be ordered, observed and not in the future")
    if (
        type(body["complete"]) is not bool
        or type(body["source_event_count"]) is not int
        or body["source_event_count"] < 0
    ):
        raise Invalid("Retention needs explicit coverage and a nonnegative source count")
    events = body["events"]
    if not isinstance(events, list) or len(events) > 500:
        raise Invalid("Retention accepts at most 500 source events")
    seen = {}
    normalized = []
    for row in events:
        exact(row, {"event_id", "subject_id", "campaign_token", "occurred_at", "consent", "bot", "internal_test"})
        identity = opaque(row["event_id"], "Retention event")
        opaque(row["subject_id"], "Retention subject")
        if row["campaign_token"] != data["study_id"]:
            raise Invalid("Retention event must preserve this exact post's campaign tag")
        if (
            row["consent"] not in ("GRANTED", "DENIED", "UNKNOWN")
            or row["bot"] is not None
            and type(row["bot"]) is not bool
            or type(row["internal_test"]) is not bool
        ):
            raise Invalid("Retention needs explicit consent, bot and internal-test status")
        if not since <= iso_time(row["occurred_at"]) <= through:
            raise Invalid("Retention event is outside declared coverage")
        fingerprint = digest(row)
        if identity in seen and seen[identity] != fingerprint:
            raise Invalid("Retention event identity has conflicting content")
        if identity not in seen:
            normalized.append(row)
        seen[identity] = fingerprint
    if body["complete"] and body["source_event_count"] != len(normalized):
        raise Invalid("Complete retention coverage count differs from retained events")
    original = _effective_events(db, app, study["id"])
    landings = {}
    registrations = {}
    for source_id, _, row in original:
        if (
            source_id != source
            or row["consent"] != "GRANTED"
            or row["bot"] is not False
            or row["internal_test"]
            or row["campaign_token"] != study["id"]
        ):
            continue
        stamp = iso_time(row["occurred_at"])
        target = landings if row["type"] == "LANDING" else registrations
        key = row["subject_id"]
        target[key] = min(stamp, target.get(key, stamp))
    cohort = {
        subject: stamp for subject, stamp in registrations.items() if subject in landings and landings[subject] < stamp
    }
    checkpoint = timedelta(days=days)
    maturity = iso_time(study["data"]["ends_at"]) + checkpoint
    measurement = report_in_snapshot(db, app, study, context, body["observed_at"])
    complete = (
        body["complete"]
        and since <= iso_time(study["data"]["starts_at"])
        and through >= maturity
        and measurement["checkpoint"]["state"] == "DESCRIPTIVE_READY"
    )
    returned = {
        row["subject_id"]
        for row in normalized
        if row["consent"] == "GRANTED"
        and row["bot"] is False
        and not row["internal_test"]
        and row["subject_id"] in cohort
        and cohort[row["subject_id"]] + checkpoint
        <= iso_time(row["occurred_at"])
        < cohort[row["subject_id"]] + checkpoint + timedelta(days=1)
    }
    # The full Dn day must have closed for every acquired registration.
    complete = complete and through >= maturity + timedelta(days=1)
    return dict(
        schema="wmm.mini-demo-retention.v1",
        status="DESCRIPTIVE_READY" if complete else "PARTIAL_OR_IMMATURE",
        study_id=study["id"],
        study_hash=study["hash"],
        channel=data["channel"],
        days=days,
        registered_subjects=len(cohort) if complete else None,
        retained_subjects=len(returned) if complete else None,
        rate=len(returned) / len(cohort) if complete and cohort else None,
        observed_retained_subjects=len(returned),
        source_receipt_sha256=hashed(body["source_receipt_sha256"]),
        registration_source_sha256=measurement["source_hash"],
        event_sha256=digest(normalized),
        definition="Return during [registration + N days, registration + N + 1 days), same collector and tagged subject.",
        provenance="SOURCE_REPORTED_NOT_PROVIDER_VERIFIED",
        causal_lift=False,
    )
