"""Validate complete portable growth history before insertion; imports are assertions."""
from datetime import datetime, timezone
from .common import Invalid, canonical, identifier, iso_time, safe_data
from .pmf_contract import exact, hashed
from .growth_review_contract import entry_data, entry_hash, comparison_data, MAX_ENTRIES
from .benchmark_context import benchmark_record, observed_record, METRICS


def context_data(value, app_id):
    """Historical app scope is retained, never adopted as current access or approval."""
    exact(value, {"app_id", "manifest_version", "app_hash", "release", "locale", "currency"})
    if value["app_id"] != app_id or type(value["manifest_version"]) is not int or value["manifest_version"] < 1:
        raise Invalid("Growth review snapshot app scope is invalid")
    hashed(value["app_hash"])
    for name in ("release", "locale", "currency"):
        if value[name] is not None and not isinstance(value[name], str):
            raise Invalid("Growth review snapshot scope fields are malformed")


def projection_data(value, request, created):
    """Validate frozen observations and lineage without authenticating an imported job."""
    exact(value, {"status", "observed", "numerator_exact", "reasons", "binding", "row_count", "unit_source_sha256", "classification_provenance", "classification_provider_verified", "provider_observed_at", "external_writes", "spend_authority", "scope"})
    exact(value["binding"], {"job_id", "report_hash", "result_hash", "connection_id", "connection_version", "connection_hash", "request_hash"})
    binding = value["binding"]
    if binding["job_id"] != request["job_id"] or binding["report_hash"] != request["report_hash"]:
        raise Invalid("Comparison snapshot source selector changed")
    identifier(binding["connection_id"])
    if type(binding["connection_version"]) is not int or binding["connection_version"] < 1:
        raise Invalid("Comparison snapshot connection version is invalid")
    for name in ("report_hash", "result_hash", "connection_hash", "request_hash"):
        hashed(binding[name])
    hashed(value["unit_source_sha256"])
    if type(value["row_count"]) is not int or not 0 <= value["row_count"] <= 300:
        raise Invalid("Comparison snapshot row coverage is invalid")
    if iso_time(value["provider_observed_at"]) > iso_time(created):
        raise Invalid("Comparison snapshot source observation is in the future")
    projection_truth(value)
    projection_observation(value, request)


def projection_truth(value):
    """Reject fabricated authority, unbounded reasons and contradictory missing metrics."""
    if value["classification_provenance"] != "OPERATOR_DECLARED" or value["classification_provider_verified"] is not False:
        raise Invalid("Comparison classification cannot become provider verification")
    if value["external_writes"] is not False or value["spend_authority"] is not False:
        raise Invalid("Comparison snapshot cannot import execution authority")
    projection_state(value)


def projection_state(value):
    """Validate bounded descriptive state independently of authority assertions."""
    reasons = value["reasons"]
    if not isinstance(reasons, list) or len(reasons) > 100 or any(not isinstance(item, str) or len(item) > 2000 for item in reasons):
        raise Invalid("Comparison snapshot reasons are malformed")
    if not isinstance(value["scope"], str) or len(value["scope"]) > 2000:
        raise Invalid("Comparison snapshot scope is malformed")
    expected = "SOURCE_METRICS_UNAVAILABLE" if reasons else "SAVED_ACCOUNT_OBSERVATION"
    if value["status"] != expected or (value["observed"] is None) != bool(reasons):
        raise Invalid("Comparison snapshot source state is contradictory")
    projection_numerator(value)


def projection_numerator(value):
    """Keep retained decimal source text bounded without inventing missing totals."""
    if value["numerator_exact"] is not None and (not isinstance(value["numerator_exact"], str) or len(value["numerator_exact"]) > 100):
        raise Invalid("Comparison snapshot exact numerator is malformed")


def projection_observation(value, request):
    """Retain exact metric and declared segment binding on a portable observation."""
    observed = value["observed"]
    if observed is None:
        return
    normalized = observed_record(observed)
    normalized.pop("value")
    if normalized != observed or observed["source_sha256"] != value["binding"]["result_hash"]:
        raise Invalid("Comparison snapshot observation changed or is not canonical")
    expected = dict(request["segment"], metric=request["metric"], denominator=METRICS[request["metric"]], platform="iOS")
    if any(observed[key] != item for key, item in expected.items()):
        raise Invalid("Comparison snapshot metric or classification changed")


def stored_data(row):
    """Distinguish a creation request from its server-frozen comparison projection."""
    value, kind, created = row["data"], row["kind"], row["created"]
    if kind != "BENCHMARK_COMPARISON":
        if entry_data(kind, value, row["context"], created) != value:
            raise Invalid("Growth review snapshot is not canonical")
        return
    exact(value, {"reference_id", "reference_hash", "job_id", "report_hash", "metric", "segment", "reference", "projection"})
    selected = {key: item for key, item in value.items() if key not in ("reference", "projection")}
    if comparison_data(selected) != selected or benchmark_record(value["reference"], created) != value["reference"]:
        raise Invalid("Comparison snapshot data is not canonical")
    projection_data(value["projection"], selected, created)


def row_data(app_id, row, observed):
    """Reject tampering before any imported assertion is written."""
    exact(row, {"app_id", "id", "kind", "data", "hash", "context", "created", "imported"})
    identifier(row["id"])
    safe_data(row)
    if row["app_id"] != app_id or type(row["imported"]) is not int or row["imported"] not in (0, 1):
        raise Invalid("Growth review snapshot scope or provenance is invalid")
    if iso_time(row["created"]) > observed:
        raise Invalid("Growth review snapshot creation is in the future")
    context_data(row["context"], app_id)
    stored_data(row)
    if entry_hash(row["kind"], row["data"], row["context"]) != row["hash"]:
        raise Invalid("Growth review snapshot content hash changed")


def linked_data(row, entries):
    """Resolve every note and comparison against the complete same-app archive."""
    value = row["data"]
    if row["kind"] == "EDITORIAL_NOTE":
        target = entries.get(value["target_id"])
        if not target or target["hash"] != value["target_hash"] or target["kind"] == "EDITORIAL_NOTE":
            raise Invalid("Growth review snapshot note target is missing or changed")
    if row["kind"] == "BENCHMARK_COMPARISON":
        linked_reference(row, entries)


def linked_reference(row, entries):
    """Resolve a frozen comparison to its exact same-scope reference packet."""
    value = row["data"]
    reference = entries.get(value["reference_id"])
    if not reference or reference["kind"] != "BENCHMARK_REFERENCE" or reference["hash"] != value["reference_hash"]:
        raise Invalid("Growth review snapshot reference is missing or changed")
    if reference["data"]["reference"] != value["reference"] or reference["context"] != row["context"]:
        raise Invalid("Growth review snapshot frozen reference or app scope changed")


def restore(db, app_id, rows):
    """Validate all rows and dependencies before inserting under the caller transaction."""
    if rows is None:
        return
    if not isinstance(rows, list) or len(rows) > MAX_ENTRIES:
        raise Invalid("Growth review snapshot exceeds its 1000 entry bound")
    observed = datetime.now(timezone.utc)
    entries = {}
    for row in rows:
        row_data(app_id, row, observed)
        if row["id"] in entries:
            raise Invalid("Growth review snapshot identities repeat")
        entries[row["id"]] = row
    for row in rows:
        linked_data(row, entries)
    for row in rows:
        db.execute("INSERT INTO growth_review_entries VALUES(?,?,?,?,?,?,?,?)", (app_id, row["id"], row["kind"], canonical(row["data"]), row["hash"], canonical(row["context"]), row["created"], 1))
