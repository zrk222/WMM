"""Finite analytics setup and privacy-preserving aggregate observation shapes."""
import math
import re
from .common import Invalid
from .payment_signature import strict_json
from .event_mapping import mapping, DEFAULTS

PROVIDERS = {
    "posthog": {"name": "PostHog", "link": "https://posthog.com/docs/api",
                "guide": "Create a read-scoped Personal API key (project and query read access). Choose your cloud region and the numeric project ID from its URL. SDK public capture keys cannot read analytics."},
    "clarity": {"name": "Microsoft Clarity", "link": "https://learn.microsoft.com/en-us/clarity/setup-and-installation/clarity-data-export-api",
                "guide": "Project Settings → Data Export → Generate new API token. Paste that project token and its project ID. No recordings or personal browsing URLs are imported."},
    "revenuecat": {"name": "RevenueCat", "link": "https://www.revenuecat.com/docs/api-v2",
                   "guide": "Create a secret REST API v2 key with charts_metrics:overview:read. Paste the proj… project ID. Public SDK keys and v1 secret keys cannot read this API."},
}


def config(body):
    """Require explicit read consent and dedicated-project declaration before storing secrets."""
    fields = {"provider", "project_id", "region", "api_key", "automatic", "confirm_read", "dedicated_project"}
    if not isinstance(body, dict) or set(body) not in (fields, fields | {"event_map"}):
        raise Invalid("Provide the guided connection fields only")
    provider = body["provider"]
    if provider not in PROVIDERS or body["confirm_read"] is not True or body["dedicated_project"] is not True:
        raise Invalid("Choose a provider and confirm permitted reads from a dedicated app project")
    if type(body["automatic"]) is not bool:
        raise Invalid("Choose automatic or manual refresh")
    project_scope(body)
    key = body["api_key"]
    if not isinstance(key, str) or not re.fullmatch(r"[!-~]{16,1800}", key):
        raise Invalid("Paste the permitted API token without spaces")
    validate_key(provider, key)
    result = {key: body[key] for key in ("provider", "project_id", "region", "automatic")}
    if "event_map" in body:
        if provider != "posthog":
            raise Invalid("Event mapping is supported only for PostHog")
        result["event_map"] = mapping(body["event_map"])
    return result


def project_scope(body):
    """Bound project identity and region before building a documented provider path."""
    provider = body["provider"]
    project = body["project_id"]
    patterns = {"posthog": r"[0-9]{1,30}", "clarity": r"[A-Za-z0-9]{1,40}", "revenuecat": r"proj[A-Za-z0-9]{1,80}"}
    if not isinstance(project, str) or not re.fullmatch(patterns[provider], project):
        raise Invalid("Project ID format is invalid for this provider")
    regions = ("us", "eu") if provider == "posthog" else ("global",)
    if body["region"] not in regions:
        raise Invalid("Choose the documented provider cloud region")


def validate_key(provider, key):
    """Reject public SDK tokens before any remote request; scopes still require provider checks."""
    patterns = {"posthog": r"ph[xs]_[A-Za-z0-9_-]{16,}", "revenuecat": r"sk_[A-Za-z0-9_-]{16,}",
                "clarity": r"[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"}
    if not re.fullmatch(patterns[provider], key):
        raise Invalid("Use a project export token or server-side read key, not a public SDK key")


def finite(value):
    """Accept finite measured numbers without turning absence into zero."""
    return type(value) in (int, float) and math.isfinite(value)


def text(value, cap=200):
    """Retain bounded provider label metadata, never arbitrary structured content."""
    if not isinstance(value, str) or len(value) > cap or not value.isprintable():
        raise Invalid("Provider metric label shape is unsupported")
    return value


def shape_posthog(payload, events=None):
    """Retain only the requested event counts, never user IDs or event properties."""
    rows = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or len(rows) > 100 or payload.get("error"):
        raise Invalid("PostHog query is incomplete or unsupported; retry after checking query permission")
    query_status = payload.get("query_status")
    if query_status and (not isinstance(query_status, dict) or query_status.get("complete") is not True):
        raise Invalid("PostHog asynchronous query is incomplete; retry")
    allowed = set(mapping(DEFAULTS if events is None else events).values()) - {""}
    result, seen = [], set()
    for row in rows:
        validate_event_count(row, allowed)
        if row[0] in seen:
            raise Invalid("PostHog returned duplicate event counts")
        seen.add(row[0])
        result.append({"id": row[0], "value": row[1], "unit": "events", "period": "last_7_days"})
    return result


def validate_event_count(row, allowed=None):
    """Reject arbitrary event labels, negative counts and changed query columns."""
    allowed = set(DEFAULTS.values()) - {""} if allowed is None else allowed
    if not isinstance(row, list) or len(row) != 2:
        raise Invalid("PostHog aggregate response differs from the requested report")
    if not isinstance(row[0], str) or row[0] not in allowed or type(row[1]) is not int or not 0 <= row[1] <= 9007199254740991:
        raise Invalid("PostHog aggregate response differs from the requested report")


def shape_clarity(payload):
    """Keep aggregate numeric diagnostics only; URL and dimension labels are discarded."""
    if not isinstance(payload, list) or len(payload) > 1000:
        raise Invalid("Clarity response shape is unsupported")
    allowed = {"Traffic", "RageClickCount", "DeadClickCount", "ScriptErrorCount",
               "Rage Click Count", "Dead Click Count", "Script Error Count", "ScrollDepth", "EngagementTime"}
    result = []
    for metric in payload:
        if not isinstance(metric, dict) or metric.get("metricName") not in allowed:
            continue
        result.extend(clarity_rows(metric))
    return result


def clarity_rows(metric):
    """Discard every string dimension while preserving finite aggregate measurements."""
    info = metric.get("information")
    if not isinstance(info, list) or len(info) > 1000:
        raise Invalid("Clarity metric rows exceed the bounded response contract")
    result = []
    for index, row in enumerate(info):
        if not isinstance(row, dict):
            raise Invalid("Clarity numeric metric row is unsupported")
        numbers = {text(k, 80): v for k, v in row.items() if finite(v)}
        numbers.update(numeric_strings(row))
        if numbers:
            result.append({"id": metric["metricName"], "row": index, "values": numbers, "period": "last_72_hours"})
    return result


def numeric_strings(row):
    """Clarity returns some counts as decimal strings; do not parse URLs or IDs."""
    fields = {"totalSessionCount", "totalBotSessionCount", "distantUserCount", "sessionsCount",
              "pagesViews", "subTotal", "total", "sessionsWithMetricPercentage", "sessionsWithoutMetricPercentage"}
    return {k: float(v) for k, v in row.items() if k in fields and isinstance(v, str)
            and re.fullmatch(r"[0-9]{1,15}(?:\.[0-9]{1,6})?", v)}


def shape_revenuecat(payload):
    """Preserve provider unit/period/recency instead of relabeling project metrics as cash."""
    rows = payload.get("metrics") if isinstance(payload, dict) else None
    if not isinstance(payload, dict) or payload.get("object") != "overview_metrics" or not isinstance(rows, list) or len(rows) > 100:
        raise Invalid("RevenueCat overview response is unsupported")
    result = []
    for row in rows:
        if not isinstance(row, dict) or not finite(row.get("value")):
            raise Invalid("RevenueCat metric value is absent or nonfinite")
        result.append({**{key: text(row.get(key, "")) for key in ("id", "name", "unit", "period")},
                       "value": row["value"], "last_updated_at": row.get("last_updated_at") if finite(row.get("last_updated_at")) else None})
    return result
