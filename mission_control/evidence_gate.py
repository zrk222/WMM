"""Compose an approved campaign scope into an evidence-complete launch preflight."""

import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from math import isfinite
from typing import Any
from urllib.parse import parse_qs, urlsplit

from .aeo_transport import ReadError, public_url
from .common import Invalid, digest, iso_time, required

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
ACQUISITION_SOURCES = {"posthog"}
OUTCOME_SOURCES = {"revenuecat"}


def measurement_plan(value: Any, *, retained: bool = False) -> dict[str, Any]:
    """Validate the owner-approved measurement inputs before they enter a scope."""
    fields = set(value) if isinstance(value, dict) else set()
    if fields != set(PLAN_FIELDS) and not (retained and fields == set(PLAN_FIELDS) | {"utm_campaign"}):
        raise Invalid("Use the exact measurement plan fields")
    for name in ("primary_metric", "denominator", "campaign_tag", "hypothesis", "decision_rule"):
        required(value[name], name, 2000)
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", value["campaign_tag"]):
        raise Invalid("Use a lowercase campaign tag with letters, numbers, hyphens or underscores")
    link = value["link"]
    if not isinstance(link, str) or len(link) > 2048:
        raise Invalid("Use a bounded HTTPS measurement link")
    try:
        public_url(link, allow_tracking=True)
        parts = urlsplit(link)
    except (ReadError, ValueError):
        raise Invalid("Use a valid public HTTPS measurement link") from None
    tags = parse_qs(parts.query, keep_blank_values=True).get("utm_campaign")
    tag = value["campaign_tag"]
    if tags != [tag] or ("utm_campaign" in value and value["utm_campaign"] != tag):
        raise Invalid("The measurement link must carry the approved utm_campaign tag")
    starts, ends = iso_time(value["starts_at"]), iso_time(value["ends_at"])
    if not starts < ends:
        raise Invalid("Measurement start must precede its end")
    return dict(value, starts_at=starts.isoformat(), ends_at=ends.isoformat(), utm_campaign=tag)


def provider_set(store: Any, app_id: str) -> set[str]:
    """Use saved successful reads for the current source revisions, never connection labels."""
    from .db import connection

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=7)
    with connection(store.path) as db:
        rows = db.execute(
            """SELECT s.provider,r.data FROM insight_sources s
            JOIN insight_reports r ON r.app_id=s.app_id AND r.source_id=s.id AND r.provider=s.provider
            WHERE s.app_id=? AND s.status='CONNECTED'
              AND r.created >= ?
              AND CASE WHEN json_valid(r.data)
              THEN json_extract(r.data,'$.source_version')=s.version
                   AND json_extract(r.data,'$.configuration_hash')=s.hash
                   AND json_type(r.data,'$.rows')='array'
                   AND json_array_length(r.data,'$.rows') > 0 ELSE 0 END""",
            (app_id, cutoff.isoformat()),
        )
        providers = set()
        for provider, raw in rows:
            data = json.loads(raw)
            try:
                observed = iso_time(data.get("observed_at"))
            except (Invalid, TypeError, ValueError):
                continue
            if cutoff <= observed <= now and any(usable_aggregate(item) for item in data["rows"]):
                providers.add(provider)
        return providers


def usable_aggregate(item: Any) -> bool:
    """Require a named finite aggregate with a declared unit and period."""
    return (
        isinstance(item, dict)
        and bool(item.get("id") or item.get("name"))
        and bool(item.get("unit"))
        and bool(item.get("period"))
        and type(item.get("value")) in (int, float)
        and isfinite(item["value"])
    )


def check_promotion_link(post: Any, plan: Any) -> None:
    """Bind a paid promotion to a verified post with the exact retained tagged link."""
    parsed = measurement_plan(plan, retained=True)
    try:
        result = json.loads(post["result"] or "{}")
        seen = result["destination_check"]["approved_link_sha256"]
    except (KeyError, TypeError, ValueError):
        seen = None
    if seen != digest(parsed["link"]):
        raise Invalid("The verified Page post does not have the approved tagged link receipt.")


def evaluate(
    scope: dict[str, Any],
    providers: set[str],
    request: Any = None,
    scope_status: str = "ACTIVE",
    observed: Any = None,
) -> dict[str, Any]:
    """Return explicit checks and blockers without inventing evidence or authority."""
    checks = []

    def check(name, status, detail):
        checks.append(dict(name=name, status=status, detail=detail))

    plan = scope.get("measurement_plan")
    if not isinstance(plan, dict):
        check("MEASUREMENT_PLAN", "MISSING", "Approve a measurement plan before launch.")
        plan = None
    else:
        try:
            plan = measurement_plan(plan, retained=True)
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
        paid = isinstance(request, dict) and "end_time" in request and "post_id" in request
        link = request.get("link") if isinstance(request, dict) else None
        check(
            "TAGGED_LINK",
            "PASS" if plan["link"] and (request is None or paid or link == plan["link"]) else "MISMATCH",
            "Approved tagged link is present." if link is None else "Request link must equal the approved tagged link.",
        )
        stamp = observed or datetime.now(timezone.utc)
        starts, ends = iso_time(plan["starts_at"]), iso_time(plan["ends_at"])
        check(
            "WINDOW",
            "NOT_STARTED" if stamp < starts else ("EXPIRED" if stamp >= ends else "PASS"),
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
        scope="Preflight only. READY confirms aggregate availability, not the selected metric, denominator, attribution or an outcome. It grants no publication or spending authority.",
    )


def assert_ready(store: Any, app_id: str, scope: dict[str, Any], request: Any = None) -> dict[str, Any]:
    """Enforce an explicitly approved measurement plan at the campaign effect boundary."""
    gate = evaluate(scope, provider_set(store, app_id), request=request, scope_status=scope.get("status", "ACTIVE"))
    plan = gate.get("measurement_plan")
    if (
        plan
        and isinstance(request, dict)
        and "end_time" in request
        and iso_time(request["end_time"]) > iso_time(plan["ends_at"])
    ):
        raise Invalid("Paid delivery must end inside the approved measurement window")
    if gate["status"] != "READY":
        details = "; ".join(f"{b['name']}: {b['status']}" for b in gate["blockers"])
        raise Invalid("Measurement evidence is incomplete: " + details)
    return gate


def latest(store: Any, app_id: str) -> dict[str, Any]:
    """Expose the gate for the newest saved scope without creating authority."""
    from .db import connection

    try:
        with connection(store.path) as db:
            row = db.execute(
                "SELECT summary,summary_hash,status FROM campaign_scopes WHERE app_id=? ORDER BY created DESC,id DESC LIMIT 1",
                (app_id,),
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
    try:
        scope = json.loads(row["summary"])
        if not isinstance(scope, dict) or digest(scope) != row["summary_hash"]:
            raise ValueError
        gate = evaluate(scope, provider_set(store, app_id), scope_status=row["status"])
        checks = [dict(name=item["name"], status=item["status"]) for item in gate["checks"]]
        return dict(
            status=gate["status"], checks=checks, blockers=[item for item in checks if item["status"] != "PASS"]
        )
    except (TypeError, ValueError):
        return dict(status="BLOCKED", checks=[], blockers=[dict(name="SAVED_MEASUREMENT_PLAN", status="INVALID")])
