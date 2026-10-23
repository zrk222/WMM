"""Frozen operator-tested paywall/offer variants; no provider mutation authority."""
import json
import re
from datetime import timedelta
from .common import Invalid, amount, digest, iso_time, required, safe_data
from .ledger import opaque, cohort_data, currency, eligible_events
from .subscription_journey import binding_data, JOURNEY_TYPES, stage_times

CONFIG_FIELDS = {"version", "experiment_type", "access_method", "placement", "product_id",
                 "offer_id", "storefront", "variant_id", "price_minor", "renewal_price_minor",
                 "currency", "trial_days", "intro_days", "billing_period_days", "renewal_terms"}
INPUT_FIELDS = {"variant_type", "cohort_id", "source_record_id", "configuration"}
FROZEN_FIELDS = INPUT_FIELDS | {"cohort", "cohort_hash", "source_hash", "configuration_hash"}
MONEY_FIELDS = {"product_id", "offer_id", "price_minor", "renewal_price_minor", "trial_days", "intro_days",
                "billing_period_days", "renewal_terms"}


def event_binding(configuration) -> dict:
    """Derive the exact event envelope from the frozen configuration bytes."""
    fields = ("version", "product_id", "offer_id", "storefront", "variant_id", "trial_days", "billing_period_days")
    return binding_data(dict({key: configuration[key] for key in fields}, configuration_sha256=digest(configuration)))

def validate_configuration(value) -> dict:
    """Validate explicit terms without inventing prices, products or trial eligibility."""
    safe_data(value)
    if not isinstance(value, dict) or set(value) != CONFIG_FIELDS:
        raise Invalid("Complete the exact subscription configuration fields")
    result = dict(value)
    event_binding(result)
    choices = {"experiment_type": {"PAYWALL", "OFFER"},
               "access_method": {"FREEMIUM", "HARD", "SOFT", "METERED"},
               "placement": {"AFTER_ONBOARDING", "AFTER_VALUE", "METERED_LIMIT"}}
    for key, allowed in choices.items():
        if not isinstance(result[key], str) or result[key] not in allowed:
            raise Invalid("Choose a supported subscription " + key)
    for key in ("price_minor", "renewal_price_minor"):
        result[key] = amount(result[key], key)
    result["currency"] = currency(result["currency"])
    if type(result["intro_days"]) is not int or not 0 <= result["intro_days"] <= 3660:
        raise Invalid("Introductory duration needs whole days from zero through 3660")
    result["renewal_terms"] = required(result["renewal_terms"], "Exact renewal terms", 2000)
    return result


def source_data(row, configuration, cohort, at):
    """Require exact billing observations from this release, locale and platform."""
    data = json.loads(row["data"])
    if not isinstance(data, dict) or data.get("subscription_configuration") != configuration:
        raise Invalid("Billing evidence configuration changed or does not match")
    identity = (cohort["release"], cohort["platform"], cohort["locale"], configuration["product_id"], configuration["currency"], configuration["price_minor"])
    if tuple(data.get(k) for k in ("release", "platform", "locale", "sku", "currency", "price_minor")) != identity:
        raise Invalid("Billing evidence belongs to a different release, platform, locale or product")
    if data.get("result") != "PASS" or data.get("eligibility_status") != "ELIGIBLE":
        raise Invalid("Subscription eligibility is untested, failed or ineligible")
    if data.get("restore_tested") is not True or data.get("trial_eligibility_tested") is not True:
        raise Invalid("Billing evidence needs restore and offer eligibility test observations")
    checked, expires = iso_time(data.get("checked_at")), iso_time(data.get("expires_at"))
    if not checked <= iso_time(at) < expires:
        raise Invalid("Subscription eligibility evidence is future or expired")
    expected = digest({"kind": "billing", "data": data, "source": row["source"]})
    if row["hash"] != expected:
        raise Invalid("Billing source hash is corrupt")
    return data


def source_row(db, app_id, record_id):
    """Resolve billing proof only inside the selected app's evidence namespace."""
    row = db.execute("SELECT * FROM records WHERE app_id=? AND id=? AND kind='billing'", (app_id, record_id)).fetchone()
    if not row:
        raise Invalid("Choose billing evidence from this app")
    return row

def bind_subscription(db, app_id, variant, at) -> dict:
    """Freeze a typed subscription arm without requiring a creative image."""
    if set(variant) != INPUT_FIELDS or variant["variant_type"] != "SUBSCRIPTION":
        raise Invalid("Subscription variant needs type, cohort, billing source and configuration")
    configuration = validate_configuration(variant["configuration"])
    cohort_id = opaque(variant["cohort_id"], "Cohort ID")
    source_id = opaque(variant["source_record_id"], "Billing evidence ID")
    cohort = db.execute("SELECT * FROM growth_cohorts WHERE app_id=? AND id=?", (app_id, cohort_id)).fetchone()
    if not cohort:
        raise Invalid("Choose a subscription cohort from this app")
    data = cohort_data(json.loads(cohort["data"]))
    if data["currency"] != configuration["currency"]:
        raise Invalid("Subscription and cohort currencies differ")
    row = source_row(db, app_id, source_id)
    source_data(row, configuration, data, at)
    return dict(variant_type="SUBSCRIPTION", cohort_id=cohort_id, cohort_hash=cohort["hash"], cohort=data,
                source_record_id=source_id, source_hash=row["hash"], configuration=configuration, configuration_hash=digest(configuration))

def validate_frozen_subscription(db, app_id, variant) -> None:
    """Restore historical definitions without silently refreshing their billing proof."""
    if set(variant) != FROZEN_FIELDS or variant["variant_type"] != "SUBSCRIPTION":
        raise Invalid("Invalid frozen subscription variant")
    configuration = validate_configuration(variant["configuration"])
    cohort = cohort_data(variant["cohort"])
    stored = db.execute("SELECT hash FROM growth_cohorts WHERE app_id=? AND id=?", (app_id, variant["cohort_id"])).fetchone()
    if not stored or stored[0] != digest(cohort) or stored[0] != variant["cohort_hash"] or cohort["cohort_id"] != variant["cohort_id"]:
        raise Invalid("Frozen subscription cohort does not match restored source")
    source_row(db, app_id, variant["source_record_id"])
    if not re.fullmatch(r"[a-f0-9]{64}", str(variant["source_hash"])) or digest(configuration) != variant["configuration_hash"]:
        raise Invalid("Invalid frozen subscription source hash")
    if configuration["currency"] != cohort["currency"]:
        raise Invalid("Frozen subscription currency differs from cohort")

def variant_findings(db, app_id, variant, at) -> list:
    """Changed, expired, deleted or corrupt billing proof blocks interpretation."""
    try:
        row = source_row(db, app_id, variant["source_record_id"])
        if row["hash"] != variant["source_hash"] or digest(variant["configuration"]) != variant["configuration_hash"]:
            raise Invalid("Subscription configuration or billing evidence changed after registration")
        source_data(row, variant["configuration"], variant["cohort"], at)
    except (Invalid, ValueError, TypeError, KeyError) as error:
        return [str(error)]
    return []


def exposure_findings(eligible):
    """Every acquired subject needs exposure before any trial or charge counts."""
    walls = stage_times(eligible, "PAYWALL_EXPOSURE")
    installs = {e["subject_id"] for e in eligible if e["type"] == "INSTALL"}
    issues = ["Subscription exposure denominator is incomplete"] if installs - set(walls) else []
    for event in eligible:
        if event["type"] in {"TRIAL_START", "PURCHASE", "RENEWAL"}:
            if event["subject_id"] not in walls or iso_time(event["occurred_at"]) < walls[event["subject_id"]]:
                issues.append("Subscription outcome precedes its observed paywall exposure")
                break
    return issues

def event_findings(events, variant) -> list:
    """Reject unbound payments and config drift instead of borrowing cohort totals."""
    expected = event_binding(variant["configuration"])
    relevant = [e for e in events if e["type"] in JOURNEY_TYPES | {"PURCHASE"}]
    if any(e.get("subscription") != expected for e in relevant):
        return ["Subscription events do not match the frozen product, offer and configuration"]
    cohort = variant["cohort"]
    _, eligible = eligible_events(events, iso_time(cohort["starts_at"]), iso_time(cohort["ends_at"]))
    return exposure_findings(eligible)

def comparable_variants(control, treatment) -> None:
    """Keep experiment surfaces comparable and reject identical test configurations."""
    if control.get("variant_type") != treatment.get("variant_type"):
        raise Invalid("Creative and subscription variants cannot be mixed")
    if control.get("variant_type") != "SUBSCRIPTION":
        return
    c, t = control["configuration"], treatment["configuration"]
    if c["variant_id"] == t["variant_id"]:
        raise Invalid("Subscription variants need different identities")
    fixed = {"currency", "storefront", "experiment_type"}
    fixed |= MONEY_FIELDS if c["experiment_type"] == "PAYWALL" else {"access_method", "placement"}
    if any(c[k] != t[k] for k in fixed):
        raise Invalid("Subscription arms change incompatible pricing or paywall dimensions")
    changes = {k for k in CONFIG_FIELDS - {"variant_id"} if c[k] != t[k]}
    if not changes:
        raise Invalid("Subscription configurations are identical apart from variant identity")

def validate_horizons(variant, analysis_at) -> None:
    """Observe the last acquired user's trial and first renewal before analysis."""
    if variant.get("variant_type") != "SUBSCRIPTION":
        return
    config = variant["configuration"]
    minimum = iso_time(variant["cohort"]["ends_at"]) + timedelta(days=config["trial_days"] + config["intro_days"] + config["billing_period_days"])
    if iso_time(variant["cohort"]["matures_at"]) < minimum or iso_time(analysis_at) < minimum:
        raise Invalid("Subscription cohort and analysis need the complete trial and first-renewal horizon")

def variant_input(variant) -> dict:
    """Reconstruct exactly the historical registration input for hash validation."""
    if variant.get("variant_type") == "SUBSCRIPTION":
        return {key: variant[key] for key in INPUT_FIELDS}
    return {"cohort_id": variant["cohort_id"], "asset_id": variant["asset_id"]}
