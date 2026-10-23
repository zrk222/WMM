"""Comparable advisory reference data, never spend, causal lift or return forecasts."""
import math
from .common import Invalid, required, iso_time, digest, safe_data
from .pmf_contract import exact, hashed
from .creative_library import source_url
from .ledger import currency

SCOPE_FIELDS = {"metric", "denominator", "category", "territory", "platform", "placement",
                "campaign_type", "currency", "period_start", "period_end"}
REFERENCE_FIELDS = SCOPE_FIELDS | {"dataset_id", "source_url", "source_sha256", "published_at", "retrieved_at",
                                  "expires_at", "percentile", "value", "coverage", "limitations"}
OBSERVED_FIELDS = SCOPE_FIELDS | {"numerator", "denominator_count", "source_sha256", "coverage"}
METRICS = {"CPT_MINOR": "TAPS", "CPI_MINOR": "INSTALLS", "CR": "TAPS", "TTR": "IMPRESSIONS"}


def numeric(value, label):
    """Reject ambiguous or nonfinite supplied aggregate values."""
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise Invalid(label + " must be a finite nonnegative number")
    return value


def scope_data(value):
    """Normalize exact segment and denominator definitions without currency conversion."""
    result = {key: required(value[key], key, 300) for key in SCOPE_FIELDS}
    if result["metric"] not in METRICS or result["denominator"] != METRICS[result["metric"]]:
        raise Invalid("Metric denominator does not match CPT, CPI, CR or TTR")
    if result["platform"] not in ("iOS", "Android"):
        raise Invalid("Benchmark platform must be iOS or Android")
    currency(result["currency"])
    if iso_time(result["period_start"]) >= iso_time(result["period_end"]):
        raise Invalid("Benchmark period start must precede end")
    for key in ("period_start", "period_end"):
        result[key] = iso_time(result[key]).isoformat()
    return result


def benchmark_record(value, as_of) -> dict:
    """Retain dataset provenance, observation period and explicit expiry separately."""
    safe_data(value)
    exact(value, REFERENCE_FIELDS)
    result = dict(value, **scope_data(value))
    result["source_url"] = source_url(value["source_url"])
    hashed(value["source_sha256"])
    for key in ("dataset_id", "coverage", "limitations"):
        result[key] = required(value[key], key, 2000)
    result["value"] = numeric(value["value"], "Benchmark value")
    percentile = numeric(value["percentile"], "Percentile")
    if percentile > 100:
        raise Invalid("Percentile must be between zero and 100")
    if value["metric"] in ("CR", "TTR") and result["value"] > 1:
        raise Invalid("Rate benchmarks must be fractions")
    published, retrieved, expires = [iso_time(value[key]) for key in ("published_at", "retrieved_at", "expires_at")]
    if not iso_time(result["period_end"]) <= published <= retrieved <= iso_time(as_of) or expires <= retrieved:
        raise Invalid("Benchmark source dates are future, reversed or precede the data period")
    return result


def observed_record(value) -> dict:
    """Compute the supplied account metric from explicit nonzero denominators."""
    safe_data(value)
    exact(value, OBSERVED_FIELDS)
    result = dict(value, **scope_data(value))
    hashed(value["source_sha256"])
    result["coverage"] = required(value["coverage"], "Observed coverage", 2000)
    numerator = numeric(value["numerator"], "Observed numerator")
    denominator = value["denominator_count"]
    if type(denominator) is not int or denominator < 0:
        raise Invalid("Observed denominator must be a nonnegative whole count")
    if value["metric"] in ("CR", "TTR") and (type(numerator) is not int or numerator > denominator):
        raise Invalid("Observed rate numerator must be a count no larger than its denominator")
    result["value"] = numerator / denominator if denominator else None
    return result


def compare_benchmark(reference, observed, as_of) -> dict:
    """Compare only compatible slices; differences do not authorize bidding or scaling."""
    ref, actual = benchmark_record(reference, as_of), observed_record(observed)
    mismatches = sorted(key for key in SCOPE_FIELDS if ref[key] != actual[key])
    reasons = ["Incompatible " + key for key in mismatches]
    if iso_time(ref["expires_at"]) <= iso_time(as_of):
        reasons.append("Benchmark source has expired")
    if ref["coverage"] != "COMPLETE" or actual["coverage"] != "COMPLETE":
        reasons.append("Source coverage is partial or unknown")
    if actual["value"] is None:
        reasons.append("Observed denominator is unavailable")
    if iso_time(actual["period_end"]) > iso_time(as_of):
        reasons.append("Observed measurement period has not ended")
    return {"status": "INCOMPATIBLE" if reasons else "COMPARABLE_ADVISORY", "reasons": reasons,
            "difference": actual["value"] - ref["value"] if not reasons else None,
            "reference": ref, "observed": actual, "source_hash": digest({"reference": ref, "observed": actual}),
            "post_install_revenue": None, "roas": None, "lifetime_value": None, "spend_authority": False,
            "scope": "Supplied aggregate references and observations; source URL and hash do not authenticate the dataset. No causal lift, bid, budget, forecast or scale approval."}
