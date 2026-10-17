"""Descriptive PMF research with visible missingness and denominators."""
import math
from datetime import datetime, timezone
from .common import iso_time


def interval(yes, total):
    """Wilson 95 percent interval, never a causal or PMF threshold."""
    if not total: return None
    z = 1.959963984540054; p = yes / total; divisor = 1 + z*z/total
    center = (p + z*z/(2*total))/divisor
    width = z*math.sqrt((p*(1-p)+z*z/(4*total))/total)/divisor
    return [max(0, center-width), min(1, center+width)]


def counts(rows, key, values):
    """Unknown facts stay separate from observed negative outcomes."""
    return {v: sum(r[key] == v for r in rows) for v in values}


def pending_reasons(facts, data, observed):
    """Coverage, maturity and declared sampling target remain distinct."""
    pending = []
    if observed < iso_time(facts["matures_at"]) or iso_time(data["observed_at"]) < iso_time(facts["matures_at"]): pending.append("Observation window has not matured")
    if data["expected_population"] != len(data["rows"]): pending.append("Population coverage is partial or unknown")
    if sum(r["responded"] == "true" for r in data["rows"]) < facts["target_responses"]: pending.append("Declared response target not reached")
    return pending


def analyze(study, snapshot, observed=None):
    """Do not pool studies/arms or assert fit from a survey percentage."""
    observed = observed or datetime.now(timezone.utc)
    if snapshot is None: return {"status": "MISSING_SNAPSHOT", "pending": ["Import observations"], "pmf": "UNPROVEN"}
    d = snapshot["data"]; values = d["rows"]; facts = study["data"]
    invited = sum(r["invited"] == "true" for r in values); responded = sum(r["responded"] == "true" for r in values)
    repeat_rows = [r for r in values if r["first_value"] == "yes" and r["return_opportunity"] == "yes"]
    repeat = counts(repeat_rows, "repeat_value", ("yes", "no", "unknown"))
    survey = counts([r for r in values if r["responded"] == "true"], "disappointment", ("very", "somewhat", "not", "unknown"))
    answered = sum(survey[k] for k in ("very", "somewhat", "not")); pending = pending_reasons(facts, d, observed)
    return {"status": "PENDING_EVIDENCE" if pending else "DESCRIPTIVE_COMPLETE_SUPPLIED", "pending": pending,
            "pmf": "UNPROVEN", "population": len(values), "expected_population": d["expected_population"],
            "eligible": sum(r["eligible"] == "true" for r in values), "invited": invited, "responded": responded, "nonresponse": invited-responded,
            "first_value": counts(values, "first_value", ("yes", "no", "unknown")),
            "opportunity": counts(values, "return_opportunity", ("yes", "no", "unknown")), "repeat": repeat, "repeat_denominator": len(repeat_rows),
            "repeat_rate": repeat["yes"]/len(repeat_rows) if repeat_rows else None,
            "all_acquired_repeat_lower_bound": sum(r["repeat_value"] == "yes" for r in values)/d["expected_population"] if d["expected_population"] else None,
            "survey": survey, "survey_answered": answered, "very_disappointed_rate": survey["very"]/answered if answered else None,
            "survey_wilson95": interval(survey["very"], answered), "barriers": counts(values, "barrier", sorted({r["barrier"] for r in values})),
            "provenance": "IMPORTED_ASSERTION" if snapshot["imported"] else "SUPPLIED_UNVERIFIED",
            "registration": "DECLARED_BEFORE_WINDOW" if iso_time(study["created"]) < iso_time(facts["starts_at"]) else "RETROSPECTIVE"}
