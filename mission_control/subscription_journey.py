"""Versioned, supplied subscription observations; no entitlement or causal claims."""
import re
from datetime import timedelta
from statistics import median
from .common import Invalid, digest, iso_time

JOURNEY_TYPES = {"ONBOARDING_COMPLETE", "PAYWALL_EXPOSURE", "TRIAL_START", "RENEWAL",
                 "CANCEL_REQUEST", "SUBSCRIPTION_END", "BILLING_FAILURE"}
BINDING_FIELDS = {"version", "product_id", "offer_id", "storefront", "variant_id", "configuration_sha256", "trial_days", "billing_period_days"}
IDENTITY_FIELDS = ("product_id", "offer_id", "variant_id")


def matches(value, pattern):
    """Reject non-string values before checking a complete bounded identity."""
    return isinstance(value, str) and re.fullmatch(pattern, value) is not None


def duration_data(value):
    """Require supplied observation horizons; do not guess eligibility from prices."""
    for key, lower, upper in (("trial_days", 0, 366), ("billing_period_days", 1, 3660)):
        number = value[key]
        if type(number) is not int or not lower <= number <= upper:
            raise Invalid("Subscription " + key + " is outside its supported whole-day bounds")


def binding_data(value) -> dict:
    """Require explicit identities; use offer_id STANDARD when no offer applies."""
    if not isinstance(value, dict) or set(value) != BINDING_FIELDS:
        raise Invalid("Subscription binding needs the version, product, offer, storefront, variant and configuration hash")
    if type(value["version"]) is not int or value["version"] != 1:
        raise Invalid("Unsupported subscription binding version")
    for field in IDENTITY_FIELDS:
        if not matches(value[field], r"[A-Za-z0-9_.-]{1,120}"):
            raise Invalid("Subscription " + field + " must be an opaque product or configuration identity")
    if not matches(value["storefront"], r"[A-Z]{2}"):
        raise Invalid("Subscription storefront needs a two-letter uppercase country code")
    if not matches(value["configuration_sha256"], r"[a-f0-9]{64}"):
        raise Invalid("Subscription configuration hash must be SHA256")
    duration_data(value)
    return dict(value)

def validate_event(event) -> dict:
    """Keep legacy bytes intact; new journey types always require a binding."""
    result = dict(event)
    if "subscription" not in event and event["type"] not in JOURNEY_TYPES:
        return result
    if event["type"] not in JOURNEY_TYPES | {"PURCHASE"}:
        raise Invalid("Subscription bindings only belong on journey or purchase events")
    result["subscription"] = binding_data(event.get("subscription"))
    financial = event["type"] in {"PURCHASE", "RENEWAL"}
    if financial and not event["amount_minor"] > 0:
        raise Invalid("Subscription charges must have positive supplied proceeds")
    if not financial and event["amount_minor"] != 0:
        raise Invalid("Subscription behavioral events cannot carry payment proceeds")
    return result


def chain_issues(events):
    """Require renewal transaction lineage, including out-of-order imports."""
    charges = {(e["provider"], e["event_id"]): e for e in events if e["type"] in {"PURCHASE", "RENEWAL"}}
    issues = []
    for event in events:
        if event["type"] != "RENEWAL":
            continue
        parent = charges.get((event["provider"], event["related_event_id"]))
        if not parent or not same_charge_scope(parent, event):
            issues.append("Unresolved subscription renewal: " + event["event_id"])
    return issues


def same_charge_scope(parent, event):
    """Strict temporal lineage prevents cycles and cross-product renewals."""
    return (parent.get("subscription") == event["subscription"]
            and parent["subject_id"] == event["subject_id"]
            and parent["currency"] == event["currency"]
            and iso_time(parent["occurred_at"]) < iso_time(event["occurred_at"]))


def group_counts(events):
    """Count distinct subjects and sequence trial-to-paid within the same binding."""
    stages = {kind: {} for kind in JOURNEY_TYPES | {"PURCHASE"}}
    for event in events:
        stage = stages[event["type"]]
        subject = event["subject_id"]
        stamp = iso_time(event["occurred_at"])
        stage[subject] = min(stamp, stage.get(subject, stamp))
    trials, paid = stages["TRIAL_START"], stages["PURCHASE"]
    converted = {s for s, stamp in trials.items() if s in paid and paid[s] >= stamp}
    renewed = set(paid) & set(stages["RENEWAL"])
    return {"counts": {kind: len(subjects) for kind, subjects in stages.items()},
            "trial_to_paid_subjects": len(converted), "renewed_subjects": len(renewed)}


def stage_times(events, kind):
    """Use first occurrence per subject, independent of supplied row order."""
    result = {}
    for event in events:
        if event["type"] == kind:
            stamp = iso_time(event["occurred_at"])
            result[event["subject_id"]] = min(stamp, result.get(event["subject_id"], stamp))
    return result


def mature_conversion(events, origin, outcome, days, as_of):
    """Keep recent starters out of both numerator and eligible denominator."""
    starts, outcomes = stage_times(events, origin), stage_times(events, outcome)
    eligible = {s for s, stamp in starts.items() if stamp + timedelta(days=days) <= as_of}
    converted = {s for s in eligible if s in outcomes and outcomes[s] >= starts[s]}
    return len(converted), len(eligible)


def payment_timing(events, installers):
    """Return aggregate observed install-to-first-payment time, never lifetime value."""
    paid = stage_times(events, "PURCHASE")
    delays = [(stamp - installers[s]).total_seconds() for s, stamp in paid.items() if s in installers]
    return median(delays) if delays else None


def group_report(binding, events, cohort, as_of, issues):
    """Maturity gates rates; supplied observability never verifies delivery coverage."""
    data = group_counts(events)
    available = cohort["observability"] == "OBSERVED" and as_of >= iso_time(cohort["matures_at"]) and not issues
    converted, trials = mature_conversion(events, "TRIAL_START", "PURCHASE", binding["trial_days"], as_of)
    renewed, paid = mature_conversion(events, "PURCHASE", "RENEWAL", binding["billing_period_days"], as_of)
    data.update(binding=binding, mature_trial_subjects=trials, mature_paid_subjects=paid,
                trial_to_paid_rate=converted / trials if available and trials else None,
                first_renewal_rate=renewed / paid if available and paid else None,
                rate_status="SUPPLIED_MATURE" if available else "INCONCLUSIVE")
    return data

def journey_report(cohort, events, as_of) -> dict:
    """Report one cohort's supplied journeys without pooling incompatible variants."""
    starts, ends = (iso_time(cohort[k]) for k in ("starts_at", "ends_at"))
    observed = [e for e in events if iso_time(e["occurred_at"]) <= as_of]
    installers = {}
    for event in observed:
        stamp = iso_time(event["occurred_at"])
        if event["type"] == "INSTALL" and starts <= stamp < ends:
            installers[event["subject_id"]] = min(stamp, installers.get(event["subject_id"], stamp))
    supplied = [e for e in observed if "subscription" in e]
    issues = chain_issues(supplied)
    groups = {}
    for event in supplied:
        if event["subject_id"] not in installers or iso_time(event["occurred_at"]) < installers[event["subject_id"]]:
            issues.append("Subscription event lacks an eligible install: " + event["event_id"])
            continue
        groups.setdefault(digest(event["subscription"]), []).append(event)
    return {"groups": [dict(group_report(rows[0]["subscription"], rows, cohort, as_of, issues), median_seconds_to_first_payment=payment_timing(rows, installers)) for _, rows in sorted(groups.items())],
            "issues": issues, "coverage": "SUPPLIED_NOT_VERIFIED", "entitlement_verified": False,
            "scope": "Operator-supplied events and whole-day offer horizons; provider eligibility and delivery completeness are unverified. Cancellation intent does not end access. No causal lift."}
