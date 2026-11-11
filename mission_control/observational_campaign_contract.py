"""Closed validation contracts for observational campaign attribution."""
from datetime import timezone
import re
import uuid
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .common import Invalid, canonical, digest, iso_time, required

SOURCES = ("facebook", "instagram", "tiktok", "youtube")
EVENT_TYPES = ("LANDING", "REGISTRATION")
CHECKPOINT_STATES = ("COLLECTING", "SOURCE_NOT_DECLARED", "COVERAGE_INCOMPLETE",
                     "NO_ELIGIBLE_LANDINGS", "DESCRIPTIVE_READY")
OPTIONAL_DEFINITION_FIELDS = {"collector_source_id"}
ID_RE = re.compile(r"[A-Za-z0-9_-]{1,128}\Z", re.ASCII)
SOURCE_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,64}\Z", re.ASCII)
SHA256_RE = re.compile(r"[a-f0-9]{64}\Z", re.ASCII)
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z", re.ASCII)

DEFINITION_FIELDS = {
    "id", "name", "hypothesis", "source", "creative_id", "landing_path",
    "starts_at", "ends_at", "landing_event", "registration_event", "attribution_model",
}
EVENT_FIELDS = {
    "event_id", "subject_id", "type", "occurred_at", "campaign_token",
    "consent", "bot", "internal_test",
}
COVERAGE_FIELDS = {"complete", "source_event_count"}
BATCH_FIELDS = {
    "batch_id", "study_id", "study_hash", "app_version", "source_id",
    "source_receipt_sha256", "observed_at", "coverage", "events",
}
ACTION_FIELDS = {
    "register": {"required": ("request_id", "manifest_version", "definition"), "optional": ()},
    "link": {"required": ("study_id", "study_hash", "manifest_version"), "optional": ()},
    "ingest": {"required": ("study_id", "study_hash", "manifest_version", "batch"), "optional": ()},
    "report": {"required": ("study_id", "study_hash", "manifest_version"), "optional": ()},
    "history": {"required": (), "optional": ("offset",)},
    "correct": {"required": ("study_id", "study_hash", "manifest_version", "correction"), "optional": ()},
}
ACTION_NAMES = {"register", "link", "ingest", "report", "history", "correct"}


def exact(value, fields, label):
    if not isinstance(value, dict) or set(value) != set(fields):
        raise Invalid(f"{label} fields must match the registered schema")


def uuid_value(value, label):
    if not isinstance(value, str) or not UUID_RE.fullmatch(value):
        raise Invalid(f"{label} must be a canonical lowercase UUID")
    return value


def opaque(value, label, pattern=ID_RE):
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise Invalid(f"{label} must be an opaque ASCII identifier")
    return value


def aware_utc(value, label):
    parsed = iso_time(value)
    return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def definition_data(value, registered_at):
    if (not isinstance(value, dict) or not DEFINITION_FIELDS <= set(value)
            or set(value) - DEFINITION_FIELDS - OPTIONAL_DEFINITION_FIELDS):
        raise Invalid("Study definition fields must match the registered schema")
    result = dict(value)
    if "collector_source_id" in result:
        result["collector_source_id"] = opaque(result["collector_source_id"], "collector_source_id", SOURCE_ID_RE)
    result["id"] = uuid_value(result["id"], "study_id")
    result["name"] = required(result["name"], "name", 120)
    result["hypothesis"] = required(result["hypothesis"], "hypothesis", 1000)
    if result["source"] not in SOURCES:
        raise Invalid("source must be facebook, instagram, tiktok, or youtube")
    result["creative_id"] = opaque(result["creative_id"], "creative_id")
    result["landing_path"] = landing_path(result["landing_path"])
    result["starts_at"] = aware_utc(result["starts_at"], "starts_at")
    result["ends_at"] = aware_utc(result["ends_at"], "ends_at")
    start, end, created = (iso_time(result["starts_at"]), iso_time(result["ends_at"]), iso_time(registered_at))
    if (start - created).total_seconds() < 1:
        raise Invalid("starts_at must be at least one second after registration")
    if end <= start or (end - start).total_seconds() > 30 * 86400:
        raise Invalid("Study window must end after start and last no more than 30 days")
    for name in ("landing_event", "registration_event"):
        result[name] = opaque(result[name], name)
    if result["landing_event"] == result["registration_event"]:
        raise Invalid("Landing and registration event names must differ")
    if result["attribution_model"] != "FIRST_TOUCH":
        raise Invalid("attribution_model must be FIRST_TOUCH")
    return result


def landing_path(value):
    value = required(value, "landing_path", 1024)
    parsed = urlsplit(value)
    if (not value.startswith("/") or value.startswith("//") or parsed.scheme or parsed.netloc
            or parsed.query or parsed.fragment or "\\" in value or "\x00" in value):
        raise Invalid("landing_path must be a path on the registered app origin")
    if any(part in (".", "..") for part in parsed.path.split("/")):
        raise Invalid("landing_path cannot contain traversal segments")
    return value


def app_origin(value):
    if not isinstance(value, str) or len(value) > 2048:
        raise Invalid("The app must have a registered HTTPS website")
    try:
        parsed = urlsplit(value)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise Invalid("The app must have a registered HTTPS website")
        if parsed.query or parsed.fragment:
            raise Invalid("The app website cannot contain query or fragment data")
        host = parsed.hostname.lower()
        port = parsed.port
    except ValueError as exc:
        raise Invalid("The app must have a registered HTTPS website") from exc
    return "https://" + host + ((f":{port}") if port and port != 443 else "")


def tagged_url(app_website, definition):
    origin = app_origin(app_website)
    query = urlencode([
        ("utm_source", definition["source"]),
        ("utm_medium", "organic"),
        ("utm_campaign", definition["id"]),
        ("utm_content", definition["creative_id"]),
    ])
    parsed = urlsplit(origin)
    return urlunsplit((parsed.scheme, parsed.netloc, definition["landing_path"], query, ""))


def validate_tagged_url(value, app_website, definition):
    expected = tagged_url(app_website, definition)
    if not isinstance(value, str) or len(value) > 4096:
        raise Invalid("Tagged URL is invalid")
    parsed = urlsplit(value)
    if app_origin(f"{parsed.scheme}://{parsed.netloc}") != app_origin(app_website):
        raise Invalid("Tagged URL origin differs from the registered app website")
    pairs = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
    if len(pairs) != 4 or len({key for key, _ in pairs}) != 4 or value != expected:
        raise Invalid("Tagged URL must exactly match the four registered UTM parameters")
    return expected


def event_data(value, study_id, starts_at, ends_at, observed_at):
    exact(value, EVENT_FIELDS, "Event")
    result = dict(value)
    result["event_id"] = opaque(result["event_id"], "event_id")
    result["subject_id"] = opaque(result["subject_id"], "subject_id")
    if result["type"] not in EVENT_TYPES:
        raise Invalid("type must be LANDING or REGISTRATION")
    result["occurred_at"] = aware_utc(result["occurred_at"], "occurred_at")
    occurred, observed = iso_time(result["occurred_at"]), iso_time(observed_at)
    if occurred > observed:
        raise Invalid("occurred_at cannot be after observed_at")
    if not iso_time(starts_at) <= occurred < iso_time(ends_at):
        raise Invalid("occurred_at must be within the registered study window")
    token = result["campaign_token"]
    if token is not None:
        result["campaign_token"] = uuid_value(token, "campaign_token")
    if result["consent"] not in ("GRANTED", "DENIED", "UNKNOWN"):
        raise Invalid("consent must be GRANTED, DENIED, or UNKNOWN")
    if result["bot"] is not None and type(result["bot"]) is not bool:
        raise Invalid("bot must be true, false, or null")
    if type(result["internal_test"]) is not bool:
        raise Invalid("internal_test must be boolean")
    return result


def batch_data(value, study, app_version, current_time):
    exact(value, BATCH_FIELDS, "Batch")
    result = dict(value)
    result["batch_id"] = uuid_value(result["batch_id"], "batch_id")
    if result["study_id"] != study["id"] or result["study_hash"] != study["hash"]:
        raise Invalid("Batch study identity or hash differs")
    if type(result["app_version"]) is not int or result["app_version"] != app_version:
        raise Invalid("Batch app version differs")
    result["source_id"] = opaque(result["source_id"], "source_id", SOURCE_ID_RE)
    collector = study["data"].get("collector_source_id")
    if collector is not None and result["source_id"] != collector:
        raise Invalid("The batch source differs from the collector declared for this study")
    if not isinstance(result["source_receipt_sha256"], str) or not SHA256_RE.fullmatch(result["source_receipt_sha256"]):
        raise Invalid("source_receipt_sha256 must be 64 lowercase hex characters")
    result["observed_at"] = aware_utc(result["observed_at"], "observed_at")
    if iso_time(result["observed_at"]) > iso_time(current_time):
        raise Invalid("observed_at cannot be in the future")
    if not isinstance(result["coverage"], dict) or set(result["coverage"]) != set(EVENT_TYPES):
        raise Invalid("coverage must declare LANDING and REGISTRATION")
    coverage = {}
    for name in EVENT_TYPES:
        entry = result["coverage"][name]
        exact(entry, COVERAGE_FIELDS, "Coverage")
        if type(entry["complete"]) is not bool:
            raise Invalid("coverage.complete must be boolean")
        count = entry["source_event_count"]
        if count is not None and (type(count) is not int or count < 0):
            raise Invalid("coverage.source_event_count must be a nonnegative integer or null")
        if entry["complete"] and count is None:
            raise Invalid("Complete coverage requires a source event count")
        coverage[name] = dict(complete=entry["complete"], source_event_count=count)
    events = result["events"]
    if not isinstance(events, list) or len(events) > 500:
        raise Invalid("events must contain between 0 and 500 rows")
    normalized = [event_data(row, study["id"], study["data"]["starts_at"], study["data"]["ends_at"], result["observed_at"]) for row in events]
    return dict(result, coverage=coverage, events=normalized)


def correction_data(value, study, app_version, current_time):
    exact(value, {"correction_id", "source_id", "event_id", "original_hash", "replacement", "reason"}, "Correction")
    result = dict(value)
    result["correction_id"] = uuid_value(result["correction_id"], "correction_id")
    result["source_id"] = opaque(result["source_id"], "source_id", SOURCE_ID_RE)
    result["event_id"] = opaque(result["event_id"], "event_id")
    if not isinstance(result["original_hash"], str) or not SHA256_RE.fullmatch(result["original_hash"]):
        raise Invalid("original_hash must be 64 lowercase hex characters")
    result["reason"] = required(result["reason"], "reason", 500)
    result["replacement"] = event_data(result["replacement"], study["id"], study["data"]["starts_at"], study["data"]["ends_at"], current_time)
    if result["replacement"]["event_id"] != result["event_id"]:
        raise Invalid("Replacement must retain the original event_id")
    return result


def schema_contract():
    """Return the closed JSON-safe domain contract for transport catalogs."""
    return {"schema": "growth.observational-campaign-operations.v1",
            "actions": {name: {"required": list(fields["required"]), "optional": list(fields["optional"]), "effect": "PRIVATE_APP_LOCAL_EVIDENCE"}
                        for name, fields in ACTION_FIELDS.items()},
            "study_fields": sorted(DEFINITION_FIELDS),
            "optional_study_fields": sorted(OPTIONAL_DEFINITION_FIELDS),
            "study_constraints": {"starts_at": "at least 1 second after registered_at", "window_max_seconds": 2592000,
                                  "source_allowlist": list(SOURCES), "attribution_model": "FIRST_TOUCH",
                                  "origin": "registered app HTTPS origin", "query_parameter_count": 4},
            "batch_fields": sorted(BATCH_FIELDS),
            "event_fields": sorted(EVENT_FIELDS), "event_types": list(EVENT_TYPES),
            "event_constraints": {"opaque_ascii_pattern": "[A-Za-z0-9_-]{1,128}", "timestamp": "timezone-aware ISO-8601 normalized to UTC",
                                  "consent": ["GRANTED", "DENIED", "UNKNOWN"], "bot": [True, False, None],
                                  "internal_test": "boolean", "raw_personal_identifiers": "rejected"},
            "coverage_fields": sorted(COVERAGE_FIELDS),
            "coverage_semantics": {"source_event_count": "nonnegative integer or null", "unknown": "null", "complete_empty": 0,
                                   "mismatch": "incomplete and explicit"},
            "correction_fields": ["correction_id", "source_id", "event_id", "original_hash", "replacement", "reason"],
            "max_batch_events": 500, "history_limit": 100,
            "report_schema": "growth.observational-campaign-report.v1",
            "measurement_checkpoint": {"states": list(CHECKPOINT_STATES),
                "fields": ["state", "collector_source_id", "coverage_issues", "ratio_counts"],
                "ratio_counts": "null or linked_registrations and eligible_landings; positive denominator and reconciled declared collector receipts at or after close",
                "legacy": "undeclared collector is never descriptive-ready"},
            "report_scope": "ATTRIBUTED_DESCRIPTIVE_ONLY; no installs, activation, paid conversion, revenue, lift, or causal decision",
            "exclusions": ["consent_denied", "consent_unknown", "bot_true", "bot_unknown", "internal_test",
                           "token_missing", "token_invalid", "unmatched_registration", "duplicate", "source_coverage_unknown"]}


catalog_contract = schema_contract


def payload_hash(value):
    return digest(value)
