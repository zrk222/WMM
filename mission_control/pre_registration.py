"""Draft a tagged, frozen measurement plan from existing app and evidence facts."""

import re
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .common import digest

ACQUISITION_SOURCES = {"posthog", "app_store", "google_play", "apple_ads"}
OUTCOME_SOURCES = {"revenuecat", "storekit", "stripe_live", "stripe_test"}
GOAL_METRICS = (
    (("retain", "retention", "return"), ("retention_rate", "installs")),
    (("paid", "revenue", "subscri", "purchase", "convert"), ("paid_conversion", "installs")),
    (("activat", "onboard", "first"), ("activation_rate", "installs")),
)


def slug(value: Any) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-")
    return text or "app"


def metric_for(goal: str) -> tuple[str, str]:
    lowered = goal.casefold()
    for words, metric in GOAL_METRICS:
        if any(word in lowered for word in words):
            return metric
    return "activation_rate", "installs"


def tagged_link(link: Any, tag: str) -> str | None:
    """Preserve the owner's URL and add only explicit public campaign parameters."""
    if not isinstance(link, str) or len(link) > 2048:
        return None
    parts = urlsplit(link)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        return None
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key not in ("utm_campaign", "utm_source", "utm_medium")
    ]
    query += [("utm_campaign", tag), ("utm_source", "wmm"), ("utm_medium", "launch")]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def providers(records: list[dict[str, Any]]) -> set[str]:
    return {
        record["data"].get("provider")
        for record in records
        if record.get("kind") == "connection" and isinstance(record.get("data"), dict)
    }


def draft(
    app: dict[str, Any],
    records: list[dict[str, Any]],
    goal: str | None = None,
    link: str | None = None,
    observed: Any = None,
) -> dict[str, Any]:
    """Compose a measurement plan and experiment draft without creating authority."""
    data = app.get("data") if isinstance(app, dict) else {}
    data = data if isinstance(data, dict) else {}
    goal = goal or data.get("goal") or data.get("activation") or data.get("job") or ""
    link = link or data.get("website") or data.get("store_url")
    tag = ("launch-" + slug(app.get("id")) + "-" + slug(goal))[:64].rstrip("-")
    tagged = tagged_link(link, tag)
    metric, denominator = metric_for(goal)
    start = observed or datetime.now(timezone.utc)
    if isinstance(start, str):
        start = datetime.fromisoformat(start.replace("Z", "+00:00"))
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    start = start.replace(microsecond=0)
    starts_at = (start + timedelta(days=1)).isoformat()
    ends_at = (start + timedelta(days=8)).isoformat()
    connected = providers(records)
    missing = []
    if not goal:
        missing.append("Set the app's first useful action or goal")
    if not tagged:
        missing.append("Add a bounded HTTPS landing link that can carry utm_campaign")
    if not connected & ACQUISITION_SOURCES:
        missing.append("Connect an acquisition source such as PostHog, App Store or Google Play")
    if not connected & OUTCOME_SOURCES:
        missing.append("Connect an outcome or cash source such as RevenueCat, StoreKit or Stripe")
    if not data.get("release"):
        missing.append("Set the current app release")
    plan = None
    if tagged:
        plan = dict(
            primary_metric=metric,
            denominator=denominator,
            link=tagged,
            campaign_tag=tag,
            starts_at=starts_at,
            ends_at=ends_at,
            hypothesis=f"A truthful {goal or 'product'} change for {data.get('name') or app.get('id')} improves {metric}.",
            decision_rule="Continue only if the pre-registered interval excludes zero and no guardrail regresses; otherwise stop or revise.",
        )
    experiment = dict(
        name="Pre-registration: " + (goal or "first useful action"),
        hypothesis=plan["hypothesis"] if plan else "Describe the expected useful outcome.",
        primary_metric=metric,
        analysis_at=ends_at,
        treatment_allocation=0.5,
        missing=[
            "Owner-supplied baseline rate",
            "Minimum detectable effect",
            "Two comparable cohorts",
            "Authentic and rights-cleared creative assets",
        ],
    )
    result = dict(
        schema="wmm.pre-registration-draft.v1",
        status="READY_FOR_OWNER_REVIEW" if plan and not missing else "DRAFT",
        goal=goal,
        measurement_plan=plan,
        experiment_draft=experiment,
        tagged_link=tagged,
        providers=sorted(value for value in connected if isinstance(value, str)),
        missing=missing,
        source_hash=digest(dict(app=app.get("data"), records=records, goal=goal, link=link)),
        authority_issued=False,
        external_writes=False,
        limits="Draft only. Review the tagged link, claims, release, baseline, cohorts and sample plan; no scope, experiment, publication or spend authority is created.",
    )
    return result
