"""Documented fixed-destination read-only analytics API adapters."""
import json
from urllib.request import Request, build_opener
from urllib.error import HTTPError, URLError
from .common import Invalid, now
from .providers import NoRedirect
from .insights_contract import shape_posthog, shape_clarity, shape_revenuecat
from .payment_signature import unique_pairs, bounded_tree
from .event_mapping import mapping, query, DEFAULTS


class ProviderFailure(Invalid):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def request(url, token, body=None):
    """Fixed callers only; never follow redirects or persist a raw error body."""
    data = json.dumps(body, allow_nan=False).encode() if body is not None else None
    req = Request(url, data=data, headers={"Authorization": "Bearer " + token,
                  "Accept": "application/json", "Content-Type": "application/json"},
                  method="POST" if data is not None else "GET")
    try:
        with build_opener(NoRedirect()).open(req, timeout=15) as response:
            raw = response.read(2097153)
    except HTTPError as exc:
        code = "PERMISSION_REQUIRED" if exc.code in (401, 403) else "RATE_LIMITED" if exc.code == 429 else "PROVIDER_ERROR"
        raise ProviderFailure(code, "Provider HTTP " + str(exc.code) + "; check token, project permissions and rate limits") from None
    except (URLError, TimeoutError, OSError):
        raise ProviderFailure("NETWORK_ERROR", "Provider read failed; saved configuration remains available") from None
    if len(raw) > 2097152:
        raise ProviderFailure("RESPONSE_TOO_LARGE", "Provider response exceeds 2 MB")
    try:
        payload = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_pairs)
        bounded_tree(payload)
        return payload
    except (ValueError, UnicodeError, RecursionError, Invalid):
        raise ProviderFailure("INVALID_RESPONSE", "Provider returned invalid or ambiguous JSON") from None


def read(config, token):
    """Fetch only documented project aggregate endpoints; user input cannot become a host."""
    provider, project = config["provider"], config["project_id"]
    metadata = {}
    if provider == "posthog":
        events = mapping(config.get("event_map", DEFAULTS))
        base = "https://" + config["region"] + ".posthog.com/api/projects/" + project + "/"
        identity = request(base, token)
        if not isinstance(identity, dict) or str(identity.get("id")) != project:
            raise Invalid("PostHog returned another project identity")
        sql = query(events)
        payload = request(base + "query/", token, {"query": {"kind": "HogQLQuery", "query": sql}})
        rows, scope = shape_posthog(payload, events), "PROJECT_ID_CHECKED"
        metadata = {"event_map": events}
    elif provider == "clarity":
        payload = request("https://www.clarity.ms/export-data/api/v1/project-live-insights?numOfDays=3", token)
        rows, scope = shape_clarity(payload), "DECLARED_PROJECT_TOKEN_SCOPE"
    else:
        payload = request("https://api.revenuecat.com/v2/projects/" + project + "/metrics/overview", token)
        rows, scope = shape_revenuecat(payload), "PROJECT_PATH_CHECKED_PROJECT_WIDE_METRICS"
    return {"provider": provider, "project_id": project, "observed_at": now(), "scope": scope, **metadata,
            "rows": rows, "coverage": "SELECTED_AGGREGATES_ONLY",
            "interpretation": "Provider aggregate observation; not transaction evidence, SDK installation proof or causal attribution. Never add these totals to Stripe or StoreKit."}
