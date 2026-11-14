"""Compose an approved campaign scope into an evidence-complete launch preflight."""

import json
import re
import sqlite3
from typing import Any
from urllib.parse import parse_qs, urlsplit

from .common import Invalid, iso_time, required

PLAN_FIELDS = (
    "primary_metric",
    "denominator",
    "link",
    "campaign_tag",
    "starts_at",
    "ends_at",
    "hypothesis",
    "decision_rule",
)
ACQUISITION_SOURCES = {"posthog", "app_store", "google_play", "apple_ads"}
OUTCOME_SOURCES = {"revenuecat", "storekit", "stripe_live", "stripe_test"}


def measurement_plan(value: Any) -> dict[str, Any]:
    """Validate the owner-approved measurement inputs before they enter a scope."""
    if not isinstance(value, dict) or set(value) != set(PLAN_FIELDS):
        raise Invalid("Use the exact measurement plan fields")
    for name in ("primary_metric", "denominator", "campaign_tag", "hypothesis", "decision_rule"):
        required(value[name], name, 2000)
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", value["campaign_tag"]):
        raise Invalid("Use a lowercase campaign tag with letters, numbers, hyphens or underscores")
    link = value["link"]
    if not isinstance(link, str) or len(link) > 2048:
        raise Invalid("Use a bounded HTTPS measurement link")
    parts = urlsplit(link)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        raise Invalid("Use a public HTTPS measurement link without credentials")
    tag = (parse_qs(parts.query).get("utm_campaign") or [None])[0]
    if tag != value["campaign_tag"]:
        raise Invalid("The measurement link must carry the approved utm_campaign tag")
    starts, ends = iso_time(value["starts_at"]), iso_time(value["ends_at"])
    if not starts < ends:
        raise Invalid("Measurement start must precede its end")
    return dict(value, starts_at=starts.isoformat(), ends_at=ends.isoformat(), utm_campaign=tag)


def provider_set(store: Any, app_id: str) -> set[str]:
    """Read only connection and payment-source provider names for gate coverage."""
    values = {r["data"].get("provider") for r in store.records(app_id) if r.get("kind") == "connection"}
    from .db import connection

    with connection(store.path) as db:
        table = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='payment_sources'").fetchone()
        if table:
            values.update(
                row[0]
                for row in db.execute(
                    "SELECT DISTINCT json_extract(data,'$.provider') FROM payment_sources WHERE app_id=?", (app_id,)
                )
            )
    return {value for value in values if isinstance(value, str) and value}


def evaluate(
    scope: dict[str, Any],
    providers: set[str],
    request: Any = None,
    scope_status: str = "ACTIVE",
    observed: Any = None,
) -> dict[str, Any]:
    """Return explicit checks and blockers without inventing evidence or authority."""
    del observed
    checks = []

    def check(name, status, detail):
        checks.append(dict(name=name, status=status, detail=detail))

    plan = scope.get("measurement_plan")
    if not isinstance(plan, dict):
        check("MEASUREMENT_PLAN", "MISSING", "Approve a measurement plan before launch.")
        plan = None
    else:
        try:
            plan = measurement_plan(plan)
            check("MEASUREMENT_PLAN", "PASS", "Approved measurement plan is present.")
        except Invalid as exc:
            check("MEASUREMENT_PLAN", "INVALID", str(exc))
            plan = None
    if plan:
        check(
            "DENOMINATOR",
            "PASS" if plan["primary_metric"] and plan["denominator"] else "MISSING",
            f"{plan['primary_metric']} / {plan['denominator']}.",
        )
        check(
            "PRE_REGISTRATION",
            "PASS" if plan["hypothesis"].strip() and plan["decision_rule"].strip() else "MISSING",
            "Hypothesis and decision rule are frozen in the approved scope.",
        )
        acquisition = sorted(providers & ACQUISITION_SOURCES)
        outcome = sorted(providers & OUTCOME_SOURCES)
        check(
            "ACQUISITION_SOURCE",
            "PASS" if acquisition else "MISSING",
            "Connected acquisition source: " + (", ".join(acquisition) or "none") + ".",
        )
        check(
            "OUTCOME_SOURCE",
            "PASS" if outcome else "MISSING",
            "Connected outcome or cash source: " + (", ".join(outcome) or "none") + ".",
        )
        link = request.get("link") if isinstance(request, dict) else None
        check(
            "TAGGED_LINK",
            "PASS" if plan["link"] and (link is None or link == plan["link"]) else "MISMATCH",
            "Approved tagged link is present." if link is None else "Request link must equal the approved tagged link.",
        )
        check(
            "WINDOW",
            "PASS" if iso_time(plan["starts_at"]) < iso_time(plan["ends_at"]) else "INVALID",
            f"{plan['starts_at']} to {plan['ends_at']}.",
        )
    check(
        "SCOPE_STATUS",
        "PASS" if scope_status == "ACTIVE" else "BLOCKED",
        "Campaign scope is " + str(scope_status) + ".",
    )
    blockers = [c for c in checks if c["status"] != "PASS"]
    return dict(
        schema="wmm.campaign-evidence-gate.v1",
        status="READY" if not blockers else ("NOT_CONFIGURED" if plan is None else "BLOCKED"),
        checks=checks,
        blockers=blockers,
        measurement_plan=plan,
        providers=sorted(providers),
        authority_issued=False,
        external_writes=False,
        scope="Preflight only. A READY gate does not publish, spend, approve provider terms or prove an outcome.",
    )


def assert_ready(store: Any, app_id: str, scope: dict[str, Any], request: Any = None) -> dict[str, Any]:
    """Enforce an explicitly approved measurement plan at the campaign effect boundary."""
    gate = evaluate(scope, provider_set(store, app_id), request=request, scope_status=scope.get("status", "ACTIVE"))
    if gate["status"] != "READY":
        details = "; ".join(f"{b['name']}: {b['detail']}" for b in gate["blockers"])
        raise Invalid("Measurement evidence is incomplete: " + details)
    return gate


def latest(store: Any, app_id: str) -> dict[str, Any]:
    """Expose the gate for the newest saved scope without creating authority."""
    from .db import connection

    try:
        with connection(store.path) as db:
            row = db.execute(
                "SELECT * FROM campaign_scopes WHERE app_id=? ORDER BY created DESC,id DESC LIMIT 1", (app_id,)
            ).fetchone()
    except (sqlite3.Error, OSError, ValueError):
        row = None
    if row is None:
        return dict(
            schema="wmm.campaign-evidence-gate.v1",
            status="NOT_CONFIGURED",
            scope_id=None,
            checks=[],
            blockers=[dict(name="SCOPE", status="MISSING", detail="No saved campaign scope.")],
            authority_issued=False,
            external_writes=False,
            scope="Preflight only.",
        )
    scope = json.loads(row["summary"])
    gate = evaluate(scope, provider_set(store, app_id), scope_status=row["status"])
    return dict(gate, scope_id=row["id"])
