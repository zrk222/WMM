"""Trace narrow customer workflows to supplied public source observations."""
import re
from .common import Invalid, required, identifier, iso_time, safe_data, digest
from .pmf_contract import exact, hashed
from .creative_library import source_url

FIELDS = {"release", "locale", "currency", "buyer", "micro_behavior", "desired_outcome",
          "sources", "features", "excluded_features", "prototype_test"}
SOURCE_FIELDS = {"id", "url", "content_sha256", "observed_at", "expires_at", "availability", "excerpt",
                 "evidence_type", "frequency", "impact"}


def bounded_rows(value, maximum, label):
    """Reject oversized, empty or malformed evidence and feature collections."""
    if not isinstance(value, list) or not 1 <= len(value) <= maximum or any(not isinstance(r, dict) for r in value):
        raise Invalid(label + " needs between one and " + str(maximum) + " objects")
    return value


def public_excerpt(value):
    """Retain a bounded excerpt without contact identifiers or private transcripts."""
    text = required(value, "Public evidence excerpt", 500)
    if re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", text):
        raise Invalid("Remove personal contact information from evidence excerpts")
    return text


def observation_data(value, observed):
    """Accept source metadata as supplied research, never authenticated customer demand."""
    exact(value, SOURCE_FIELDS)
    result = dict(value, id=identifier(value["id"]), url=source_url(value["url"]),
                  content_sha256=hashed(value["content_sha256"]), excerpt=public_excerpt(value["excerpt"]))
    for key in ("frequency", "impact"):
        result[key] = required(value[key], key, 500)
    if value["availability"] not in ("AVAILABLE", "REMOVED", "UNKNOWN"):
        raise Invalid("Choose available, removed or unknown source availability")
    if value["evidence_type"] not in ("FIRSTHAND_COMPLAINT", "OBSERVED_WORKFLOW", "STATED_WILLINGNESS_TO_PAY", "OBSERVED_PAID_BEHAVIOR"):
        raise Invalid("Generated ideas and secondhand claims are not firsthand evidence")
    start, expires = iso_time(value["observed_at"]), iso_time(value["expires_at"])
    if start > observed or expires <= start:
        raise Invalid("Customer evidence has future or reversed observation dates")
    return result


def feature_data(value, sources):
    """Each proposed feature needs at least one distinct existing source observation."""
    exact(value, {"id", "description", "source_ids", "validation"})
    references = value["source_ids"]
    if not isinstance(references, list) or not references or len(references) > 100:
        raise Invalid("Feature needs one through 100 source references")
    if any(not isinstance(r, str) or r not in sources for r in references) or len(set(references)) != len(references):
        raise Invalid("Feature references an unknown or duplicate customer source")
    return dict(id=identifier(value["id"]), description=required(value["description"], "Feature", 500),
                source_ids=list(references), validation=required(value["validation"], "Falsifiable feature test", 500))


def exclusion_data(value):
    """Make excluded scope and its evidence rationale explicit."""
    exact(value, {"feature", "reason"})
    return {key: required(value[key], key, 500) for key in ("feature", "reason")}

def workflow_data(value, observed) -> dict:
    """Normalize a bounded source-to-feature proposal while preserving explicit unknowns."""
    safe_data(value)
    exact(value, FIELDS)
    result = {key: required(value[key], key, 500) for key in FIELDS - {"sources", "features", "excluded_features"}}
    result["sources"] = [observation_data(row, observed) for row in bounded_rows(value["sources"], 100, "Customer observations")]
    ids = [s["id"] for s in result["sources"]]
    urls = [s["url"] for s in result["sources"]]
    if len(set(ids)) != len(ids) or len(set(urls)) != len(urls):
        raise Invalid("Customer sources must have unique identities and original URLs")
    result["features"] = [feature_data(row, ids) for row in bounded_rows(value["features"], 20, "Proposed features")]
    feature_ids = [row["id"] for row in result["features"]]
    if len(set(feature_ids)) != len(feature_ids):
        raise Invalid("Proposed feature identities cannot repeat")
    result["excluded_features"] = [exclusion_data(row) for row in bounded_rows(value["excluded_features"], 20, "Excluded features")]
    return result

def workflow_readout(value, observed) -> dict:
    """Current expiry and availability affect every linked action; no willingness-to-pay inference."""
    data = workflow_data(value, observed)
    unavailable = {s["id"] for s in data["sources"] if s["availability"] != "AVAILABLE" or iso_time(s["expires_at"]) <= observed}
    features = [dict(row, state="SOURCE_REVIEW_NEEDED" if set(row["source_ids"]) & unavailable else "HYPOTHESIS_READY_FOR_REVIEW") for row in data["features"]]
    return {"source_hash": digest(data), "features": features, "unavailable_source_ids": sorted(unavailable),
            "excluded_features": data["excluded_features"], "prototype_test": data["prototype_test"],
            "status": "SOURCE_REVIEW_NEEDED" if unavailable else "HYPOTHESIS_READY_FOR_REVIEW",
            "demand_verified": False, "paid_behavior_verified": False, "external_writes": False,
            "scope": "Supplied public research and operator-coded observations. A quote, hash, willingness-to-pay statement or generated proposal does not prove demand or paid behavior."}
