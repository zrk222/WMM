"""Portable PMF history never confers execution or provider authority."""
from datetime import datetime, timezone
from .common import Invalid, canonical, digest, identifier, iso_time
from .pmf_contract import exact, study, receipt, survey_row, count, hashed
from .pmf_research import rows, snapshot_links, receipt_links


def export_research(db, app_id):
    """Export immutable app-owned entries without credentials."""
    return rows(db, app_id)


def validate_value(kind, value, observed):
    """Revalidate content instead of trusting a self-declared hash."""
    if kind == "study":
        if study(value) != value: raise Invalid("Noncanonical study")
    elif kind == "receipt":
        if receipt(value, observed) != value: raise Invalid("Noncanonical result")
    elif kind == "snapshot":
        validate_snapshot(value, observed)
    else: raise Invalid("Unknown research history kind")


def validate_snapshot(value, observed):
    """Portable snapshots retain exact privacy and denominator checks."""
    exact(value, ("study_id", "source_id", "observed_at", "expected_population", "rows", "csv_hash"))
    identifier(value["study_id"]); identifier(value["source_id"]); hashed(value["csv_hash"])
    if iso_time(value["observed_at"]) > observed: raise Invalid("Future snapshot")
    values = value["rows"]
    if not isinstance(values, list) or not 1 <= len(values) <= 1000: raise Invalid("Invalid observation count")
    if [survey_row(r) for r in values] != values: raise Invalid("Noncanonical observations")
    if len({r["subject_id"] for r in values}) != len(values): raise Invalid("Duplicate survey subject")
    if value["expected_population"] is not None: count(value["expected_population"], len(values))


def validate_entry(app_id, row, seen, observed):
    """Reject scope, hash, date, provenance and ID tampering."""
    exact(row, ("app_id", "id", "kind", "data", "hash", "imported", "created"))
    identity = identifier(row["id"]); created = iso_time(row["created"])
    if row["app_id"] != app_id or identity in seen or row["hash"] != digest(row["data"]): raise Invalid("Research history scope, hash or duplicate invalid")
    if type(row["imported"]) is not int or row["imported"] not in (0, 1) or created > observed: raise Invalid("Research provenance invalid")
    validate_value(row["kind"], row["data"], observed); seen.add(identity)


def restore_research(db, app_id, data):
    """Validate history references within the caller's atomic restore."""
    if data is None: return
    if not isinstance(data, list) or len(data) > 1000: raise Invalid("Invalid research history")
    seen = set(); observed = datetime.now(timezone.utc)
    for row in data: validate_entry(app_id, row, seen, observed)
    studies = [r for r in data if r["kind"] == "study"]
    snapshots=sorted((r for r in data if r["kind"]=="snapshot"),key=lambda r:iso_time(r["data"]["observed_at"]))
    prior=list(studies)
    for row in snapshots:
        snapshot_links(row["data"],prior);prior.append(row)
    for row in data:
        if row["kind"] == "receipt": receipt_links(row["data"], data, row["data"]["source_hash"])
    for row in data:
        db.execute("INSERT INTO pmf_research VALUES(?,?,?,?,?,?,?)", (app_id, row["id"], row["kind"], canonical(row["data"]), row["hash"], 1, row["created"]))
