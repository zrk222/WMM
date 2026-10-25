"""Immutable local review inputs; notes and source hashes grant no execution authority."""
from .common import Invalid, digest, identifier, iso_time, required, safe_data
from .pmf_contract import exact, hashed
from .aso_validation import validate_listing
from .benchmark_context import benchmark_record, compare_benchmark, METRICS

MAX_ENTRIES = 1000
MAX_TEXT = 2000
KINDS = ("ASO_LISTING", "BENCHMARK_REFERENCE", "BENCHMARK_COMPARISON", "EDITORIAL_NOTE")


def context_of(app):
    """Bind public app scope and its exact manifest content without exposing secrets."""
    data = app["data"]
    return dict(app_id=app["id"], manifest_version=app["version"], app_hash=digest(data),
                release=data.get("release"), locale=data.get("locale"), currency=data.get("currency"))


def entry_hash(kind, data, context):
    """Cover type, original data and app context with a single immutable content hash."""
    return digest(dict(kind=kind, data=data, context=context))


def entry_data(kind, value, context, observed_at):
    """Validate each closed input kind before any persistent change."""
    safe_data(value)
    if kind not in KINDS:
        raise Invalid("Choose a supported growth-review entry type")
    if kind == "EDITORIAL_NOTE":
        return note_data(value)
    if kind == "BENCHMARK_COMPARISON":
        return comparison_data(value)
    exact(value, {"release", "listing" if kind == "ASO_LISTING" else "reference"})
    if not context["release"] or value["release"] != context["release"]:
        raise Invalid("Review release must match the configured app release")
    return scoped_source_data(kind, value, context, observed_at)


def scoped_source_data(kind, value, context, observed_at):
    """Normalize a listing or reference against the already validated app release."""
    if kind == "ASO_LISTING":
        result = validate_listing(value["listing"], observed_at)
        if not context["locale"] or result["locale"] != context["locale"]:
            raise Invalid("Listing locale must match this app")
        return dict(release=value["release"], listing=result["original"])
    reference = benchmark_record(value["reference"], observed_at)
    if not context["currency"] or reference["currency"] != context["currency"]:
        raise Invalid("Benchmark currency must match the explicitly configured app currency")
    return dict(release=value["release"], reference=reference)


def note_data(value):
    """An exact-source editorial choice is bookkeeping, never authenticated approval."""
    exact(value, {"target_id", "target_hash", "decision", "rationale"})
    identifier(value["target_id"])
    hashed(value["target_hash"])
    if value["decision"] not in ("KEEP", "REVISE", "DEFER"):
        raise Invalid("Choose keep, revise or defer for this local review note")
    return dict(value, rationale=required(value["rationale"], "Review rationale", MAX_TEXT))


def comparison_data(value):
    """Accept source selectors and declared classification, never supplied account totals."""
    exact(value, {"reference_id", "reference_hash", "job_id", "report_hash", "metric", "segment"})
    identifier(value["reference_id"])
    identifier(value["job_id"])
    hashed(value["reference_hash"])
    hashed(value["report_hash"])
    if not isinstance(value["metric"], str) or value["metric"] not in METRICS:
        raise Invalid("Choose a supported benchmark metric")
    exact(value["segment"], {"category", "territory", "placement", "campaign_type"})
    segment = {key: required(text, key, 300) for key, text in value["segment"].items()}
    return dict(value, segment=segment)


def comparison_readout(data, observed_at):
    """Compare frozen source values only; absent provider metrics stay unavailable."""
    projection = data["projection"]
    if projection["observed"] is None:
        return dict(status="SOURCE_METRICS_UNAVAILABLE", reasons=projection["reasons"], difference=None)
    compared = compare_benchmark(data["reference"], projection["observed"], observed_at)
    return dict(compared, classification_provenance="OPERATOR_DECLARED", classification_provider_verified=False)


def entry_readout(row, app_context, observed_at):
    """Recalculate current freshness while retaining original source and provenance."""
    if entry_hash(row["kind"], row["data"], row["context"]) != row["hash"]:
        raise Invalid("Growth-review content hash changed")
    kind, data = row["kind"], row["data"]
    if kind == "ASO_LISTING":
        analysis = validate_listing(data["listing"], observed_at)
    elif kind == "BENCHMARK_REFERENCE":
        reference = benchmark_record(data["reference"], observed_at)
        analysis = dict(status="REFERENCE_EXPIRED" if iso_time(reference["expires_at"]) <= iso_time(observed_at) else "REFERENCE_AVAILABLE", reference=reference)
    elif kind == "BENCHMARK_COMPARISON":
        analysis = comparison_readout(data, observed_at)
    else:
        analysis = dict(status="EDITORIAL_NOTE_ONLY", decision=data["decision"], target_id=data["target_id"])
    availability = "CURRENT_LOCAL_EVIDENCE"
    if row["context"] != app_context:
        availability = "STALE_APP_SCOPE"
    if row["imported"]:
        availability = "IMPORTED_ASSERTION"
    if kind == "BENCHMARK_COMPARISON" and availability != "CURRENT_LOCAL_EVIDENCE":
        analysis = dict(status=availability, difference=None, reasons=["Rebind the saved reference and account source to the current app before relying on this comparison"])
    return dict(analysis=analysis, availability=availability, provider_verified=False, outcomes_verified=False,
                execution_authority=False, external_writes=False, spend_minor=0)
