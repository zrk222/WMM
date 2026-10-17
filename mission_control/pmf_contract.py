"""Closed PMF research contracts; no raw contacts or conversations."""
import csv
import io
import re
from .common import Invalid, required, identifier, iso_time, digest

COLUMNS = "subject_id consent eligible invited responded first_value return_opportunity repeat_value disappointment barrier".split()
BARRIERS = {"none", "price", "missing_value", "friction", "trust", "alternative", "no_opportunity", "unknown"}
STUDY_TEXT = "segment problem alternative switching_cost value_event cadence".split()


def exact(data, keys):
    """Reject ambiguous or unrecognized fields."""
    if not isinstance(data, dict) or set(data) != set(keys):
        raise Invalid("Research fields must match the selected form exactly")


def one(value, choices, name):
    """Keep categorical facts closed, including explicit unknown."""
    if not isinstance(value, str) or value not in choices: raise Invalid(name + ": choose a listed value")
    return value


def count(value, low=0, high=1000):
    """Reject Boolean, fractional and excessive counts."""
    if type(value) is not int or not low <= value <= high:
        raise Invalid("Research count must be a whole number in the declared range")
    return value


def hashed(value, prefix=""):
    """Validate a SHA256 or native evidence reference."""
    if not isinstance(value, str) or not re.fullmatch(re.escape(prefix) + "[a-f0-9]{64}", value):
        raise Invalid("Evidence requires a full lowercase SHA256 identifier")
    return value


def study(value):
    """Normalize an immutable problem and observation window."""
    keys = STUDY_TEXT + ["release", "locale", "currency", "arm", "starts_at", "ends_at", "matures_at", "target_responses"]
    exact(value, keys)
    result = {k: required(value[k], k, 500) for k in STUDY_TEXT + ["release", "locale", "currency"]}
    if not re.fullmatch("[a-z]{2,3}(?:-[a-zA-Z0-9]{2,8}){0,3}",result["locale"]) or not re.fullmatch("[A-Z]{3}",result["currency"]):
        raise Invalid("Choose one language/region and a three-letter currency in app setup")
    result["arm"] = one(value["arm"], ("discovery", "holdout"), "Study arm")
    times = [iso_time(value[k]) for k in ("starts_at", "ends_at", "matures_at")]
    if not times[0] <= times[1] <= times[2]: raise Invalid("Study dates must be start <= end <= maturity")
    result.update(zip(("starts_at", "ends_at", "matures_at"), (v.isoformat() for v in times)))
    result["target_responses"] = count(value["target_responses"], 1)
    return result


def survey_row(row):
    """Validate coded facts without discarding nonresponders."""
    exact(row, COLUMNS)
    if not re.fullmatch("p_[a-f0-9]{32}", str(row["subject_id"])): raise Invalid("Use a pseudonymous p_ plus 32 hexadecimal subject ID")
    result = {"subject_id": row["subject_id"]}
    for key in ("consent", "eligible", "invited", "responded"):
        result[key] = one(row[key], ("true", "false"), key)
    survey_relations(result)
    for key in ("first_value", "return_opportunity", "repeat_value"): result[key] = one(row[key], ("yes", "no", "unknown"), key)
    result["disappointment"] = one(row["disappointment"], ("very", "somewhat", "not", "unknown"), "Disappointment")
    if result["responded"] != "true" and result["disappointment"] != "unknown": raise Invalid("Disappointment requires a response")
    if result["repeat_value"] == "yes" and (result["first_value"], result["return_opportunity"]) != ("yes", "yes"):
        raise Invalid("Repeat value requires verified first value and opportunity")
    result["barrier"] = one(row["barrier"], BARRIERS, "Barrier")
    return result


def survey_relations(value):
    """Consent and invitation/response denominators cannot contradict."""
    if value["consent"] != "true": raise Invalid("Explicit research consent is required")
    if value["invited"] == "true" and value["eligible"] != "true": raise Invalid("Invitation requires eligibility")
    if value["responded"] == "true" and value["invited"] != "true": raise Invalid("Response requires invitation")


def csv_rows(text):
    """Bound an exact CSV schema and unique pseudonymous subjects."""
    if not isinstance(text, str) or len(text.encode("utf-8")) > 1048576: raise Invalid("CSV exceeds 1 MiB")
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")), strict=True)
    if reader.fieldnames != COLUMNS: raise Invalid("CSV columns and order must exactly match the template")
    result = []; seen = set()
    try:
        for row in reader:
            value = survey_row(row)
            if value["subject_id"] in seen: raise Invalid("Duplicate subject in this snapshot")
            seen.add(value["subject_id"]); result.append(value)
            if len(result) > 1000: raise Invalid("Snapshot exceeds 1000 rows")
    except csv.Error as exc: raise Invalid("CSV syntax is invalid") from exc
    if not result: raise Invalid("CSV must contain observations")
    return result


def snapshot(value, observed):
    """Normalize a complete source snapshot, never additive deltas."""
    exact(value, ("study_id", "source_id", "observed_at", "expected_population", "csv"))
    at = iso_time(value["observed_at"])
    if at > observed: raise Invalid("Observation cannot be in the future")
    values = csv_rows(value["csv"]); population = value["expected_population"]
    if population is not None: count(population, len(values))
    return {"study_id": identifier(value["study_id"]), "source_id": identifier(value["source_id"]),
            "observed_at": at.isoformat(), "expected_population": population, "rows": values, "csv_hash": digest(value["csv"])}


def receipt(value, observed):
    """Supplied tool results never establish authenticated execution."""
    exact(value, ("engine", "source_hash", "observed_at", "evidence_ids", "artifact_hashes", "summary", "coverage", "unknowns", "rea_id"))
    at = iso_time(value["observed_at"])
    if at > observed: raise Invalid("Result cannot be in the future")
    result = dict(value); result["observed_at"] = at.isoformat()
    one(value["engine"], ("REA", "ECC"), "Engine"); hashed(value["source_hash"])
    for key, prefix in (("evidence_ids", "ev_"), ("artifact_hashes", "")):
        items = value[key]
        if not isinstance(items, list) or not 1 <= len(items) <= 20: raise Invalid("Supply between 1 and 20 evidence references")
        result[key] = sorted({hashed(v, prefix) for v in items})
    for key in ("summary", "coverage", "unknowns"): result[key] = required(value[key], key, 1000)
    if value["engine"] == "REA" and value["rea_id"] is not None: raise Invalid("REA cannot reference itself")
    if value["engine"] == "ECC": identifier(value["rea_id"])
    return result
