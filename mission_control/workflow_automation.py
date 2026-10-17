"""Explainable app-specific local choices, refreshed from authoritative saved inputs."""
from datetime import datetime, timezone
import math
from .common import Invalid, digest, iso_time
from .automation_policy import preferences, METRICS
from .automatic_preparation import check_scope


def baseline(app, reports, metric, observed_at):
    """Use the latest exact release/locale/currency cohort, never an older success."""
    facts = app["data"]
    scoped = [r for r in reports if all(facts.get(k) and r["cohort"].get(k) == facts[k]
                                      for k in ("release", "locale", "currency"))]
    if not scoped:
        return {"value": None, "status": "UNAVAILABLE", "reason": "No matching release, locale and currency cohort"}
    latest = max(scoped, key=lambda r: iso_time(r["cohort"]["ends_at"]))
    value = latest.get(metric)
    valid = usable_baseline(latest, value, observed_at)
    return {"value": value if valid else None, "status": "SUPPLIED_OBSERVATION" if valid else "UNAVAILABLE",
            "reason": "Latest reconciled same-scope cohort; descriptive, not independently verified or causal" if valid
                      else "Latest cohort is incomplete, immature, stale or has an unavailable outcome",
            "cohort_id": latest["cohort"]["cohort_id"], "source_hash": latest["source_hash"],
            "window": {k: latest["cohort"].get(k) for k in ("starts_at", "ends_at", "matures_at")}}


def usable_baseline(report, value, observed_at):
    """Unavailable and invalid values never become zero or a statistical assumption."""
    age = (observed_at - iso_time(report["as_of"])).total_seconds()
    flags = report.get("mature") is True and report.get("costs_complete") is True
    status = report.get("status") == "SUPPLIED_RECONCILED" and report.get("observability") == "OBSERVED"
    numeric = type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1
    return flags and status and numeric and report.get("installs", 0) > 0 and 0 <= age <= 30 * 86400


def selected_channel(policy):
    """Select a transparent pilot priority, with no unsupported optimality claim."""
    preferred = policy["preferred_channel"]
    value = preferred or next(iter(policy["channels"]), None)
    return {"value": value, "status": "UNTESTED_PILOT" if value else "NEEDS_INPUT",
            "basis": "Explicit operator preference" if preferred else "First declared app hypothesis; ordering is a test priority, not proven ROI",
            "alternatives": [c for c in policy["channels"] if c != value],
            "next_test": "Compare mature activation, contribution and retained value before calling a channel better"}


def destination(app, records):
    """Only current public store evidence is a verified destination; website stays a draft."""
    from .pipeline import current
    matching = [r for r in records if r["kind"] == "store" and
                r["data"].get("release") == app["data"].get("release") and
                r["data"].get("locale") == app["data"].get("locale")]
    latest = max(matching, key=lambda r: r["updated"]) if matching else None
    if latest and current(latest, app):
        return {"value": latest["data"].get("destination"), "status": "OPERATOR_PUBLIC_READBACK", "record_id": latest["id"]}
    return {"value": app["data"].get("website") or None, "status": "UNVERIFIED_DRAFT"}


def drafts(app, policy, channel, target, measured, workflow):
    """Draft only planning fields; every proof, count, credential and effect stays unset."""
    facts = app["data"]; activation = facts.get("activation") or "the app's declared useful outcome"
    hypothesis = f"Show {facts.get('job') or 'the declared user job'} to {facts.get('audience') or 'the declared audience'}; measure {activation}."
    stop = "Stop and repair if core journey, privacy, billing or current claim checks fail; no spending or publication without exact approval."
    rollback = f"Retain the previous reviewed packet and app manifest v{app['version']} for {facts.get('release') or 'the declared build'}."
    experiment = {"hypothesis": hypothesis, "primary_metric": policy["metric"], "audience": facts.get("audience", ""),
                  "currency": facts.get("currency", ""), "budget_minor": 0, "stop_rule": stop}
    registered = {"hypothesis": hypothesis, "primary_metric": policy["metric"], "rollback_plan": rollback, "stop_rule": stop}
    if measured["value"] is not None:
        registered["baseline_rate"] = measured["value"]
    return {"experiment": experiment, "registered_experiment": registered,
            "distribution": {"channel": channel["value"] or "", "intent": facts.get("job", ""),
                             "destination": target["value"] or "", "currency": facts.get("currency", ""),
                             "budget_minor": 0, "daily_cap_minor": 0, "mode": "MANUAL_HANDOFF"},
            "retention": {"window": policy["cadence"]},
            "learning": {"change": workflow["next_action"]["title"],
                         "heldout_test": "Reserve untouched examples and predeclare a mature analysis window before adoption.",
                         "rollback": rollback}}


def stage_choices(app, policy, channel, target, measured, workflow):
    """A choice in every stage remains subordinate to the existing readiness checks."""
    facts = app["data"]
    values = [facts.get("job") or "Supply one user job", "Prove the declared activation journey",
              "Map useful activation, payment and consent; use only app-owned provider projects",
              measured["reason"], "Use authentic proof for this release and locale",
              "Real-screen demonstration of " + (facts.get("activation") or "the declared activation"),
              channel["value"] or "Supply pilot channel candidates", target["value"] or "Supply a destination",
              "Verify the actual localized SKU, price and restore", policy["cadence"] or "Declare a useful-value cadence",
              "Use " + METRICS[policy["metric"]] + "; collect missing mature evidence",
              "Propose one source-bound change with a holdout and rollback"]
    return [{"stage": s["id"], "choice": values[s["id"] - 1], "local_status": s["local_status"],
             "tool": s["primary"]["id"], "missing": s["direct_needs"]} for s in workflow["steps"]]


def recommend(app, records, reports, workflow, observed_at=None):
    """Recompute local recommendations without writes, jobs, model calls or network."""
    check_scope(app, records, reports)
    if workflow.get("app_id") != app["id"] or workflow.get("app_version") != app["version"]:
        raise Invalid("Automation received a stale or foreign workflow; reload this app")
    policy = preferences(app["data"])
    measured = baseline(app, reports, policy["metric"], observed_at or datetime.now(timezone.utc))
    channel = selected_channel(policy); target = destination(app, records)
    choices = stage_choices(app, policy, channel, target, measured, workflow)
    result = {"schema": "growth.workflow-automation.v1", "app_id": app["id"], "app_version": app["version"],
              "mode": policy["mode"], "metric": {"value": policy["metric"], "label": METRICS[policy["metric"]],
              "activation": app["data"].get("activation"), "basis": "App preference or useful-activation default; not a measured winner"},
              "channel": channel, "cadence": policy["cadence"] or None, "baseline": measured, "destination": target,
              "choices": choices, "drafts": drafts(app, policy, channel, target, measured, workflow),
              "next_action": workflow["next_action"], "classification": "LOCAL_EDITABLE_PLANNING_CHOICES",
              "automatic_external_writes": False, "authorized_spend_minor": 0}
    result["source_hash"] = digest({"app": app, "records": sorted((r["id"], r["version"], r["hash"]) for r in records),
                                    "reports": sorted(r["source_hash"] for r in reports), "workflow": workflow["source_hash"],
                                    "recommendations": result})
    return result
