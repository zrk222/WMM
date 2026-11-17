"""App-scoped, imported OpenSEO observations for web acquisition decisions."""

from datetime import date, timedelta
from hashlib import sha256
from math import isfinite
from typing import TypedDict
from urllib.parse import unquote, urlsplit

from .aeo_transport import public_url
from .common import Invalid, iso_time, required
from .pmf_contract import exact, hashed


class EvidenceGroup(TypedDict):
    family: str
    action: str
    metric: str
    fields: dict[str, str]


def _group(family: str, action: str, metric: str, **fields: str) -> EvidenceGroup:
    return {"family": family, "action": action, "metric": metric, "fields": fields}


# Order is repair first, owned measured opportunity second, external research third.
TOOLS = {
    "get_audit_issues": _group(
        "Owned website audit",
        "Repair one confirmed crawl or page error before testing acquisition copy.",
        "Open critical and major audit issues",
        critical_issues="count",
        major_issues="count",
        total_issues="count",
    ),
    "inspect_urls": _group(
        "Google index inspection",
        "Verify the preferred URL and repair indexing before testing copy.",
        "Indexed landing pages",
        indexing_state="text",
        canonical_match="boolean",
    ),
    "get_search_opportunities": _group(
        "Search Console + GA4 (page-level comparison)",
        "Test one page promise or call to action where search traffic already arrives.",
        "Store-bound sessions divided by eligible organic sessions",
        impressions="count",
        sessions="count",
        key_events="count",
        position="position",
        store_bound_sessions="count",
    ),
    "get_search_console_performance": _group(
        "Google Search Console",
        "Match one page's search title to an observed search query.",
        "Google clicks divided by impressions",
        clicks="count",
        impressions="count",
        ctr="fraction",
        position="position",
    ),
    "get_google_analytics_organic_landing_pages": _group(
        "Google Analytics organic landing pages",
        "Test one store call to action before evaluating native outcomes separately.",
        "Store-bound sessions divided by eligible organic sessions",
        sessions="count",
        key_events="count",
        store_bound_sessions="count",
    ),
    "get_serp_results": _group(
        "Google search results",
        "Compare the top pages' promises and draft one differentiated landing-page or creative angle.",
        "Store-bound clicks per qualified web session",
        best_position="position",
        seen_in="count",
    ),
    "get_rank_history": _group(
        "Google rank history",
        "Confirm the trend on the same device and market before changing the page.",
        "Google search position for the same query",
        position="position",
    ),
    "research_keywords": _group(
        "Estimated Google keyword demand",
        "Check one relevant long-tail idea against owned query evidence or a separate storefront search.",
        "Google clicks and store-bound clicks",
        volume="count",
        difficulty="score",
    ),
    "get_keyword_metrics": _group(
        "Estimated Google keyword metrics",
        "Compare one relevant long-tail idea with owned query evidence before choosing a web test.",
        "Google clicks and store-bound sessions",
        volume="count",
        difficulty="score",
    ),
    "get_domain_overview": _group(
        "Estimated web competitor visibility",
        "Inspect the competitor pages serving the same buyer problem; draft one differentiated page.",
        "Owned Google query clicks and store-bound sessions",
        ranked_keywords="count",
        estimated_traffic="count",
    ),
    "get_backlinks_overview": _group(
        "Web backlinks",
        "Inspect referring pages for relevant partnership or editorial angles.",
        "Qualified referral sessions and store-bound clicks",
        referring_domains="count",
        backlinks="count",
    ),
    "get_ai_visibility_results": _group(
        "Sampled AI visibility",
        "Check cited sources and improve one factual answer page.",
        "Brand citations in repeat samples; site referrals separately",
        mentions="count",
        citations="count",
        samples="count",
    ),
}


OWNED_TOOLS = frozenset(
    (
        "get_audit_issues",
        "inspect_urls",
        "get_search_opportunities",
        "get_search_console_performance",
        "get_google_analytics_organic_landing_pages",
    )
)
WINDOWED_TOOLS = frozenset(tool for tool in OWNED_TOOLS if tool not in ("inspect_urls", "get_audit_issues"))


class SearchObservation(TypedDict):
    tool: str
    subject: str
    page_url: str | None
    period: dict[str, str] | None
    coverage: str
    retrieved_at: str
    reference_url: str
    sha256: str
    excerpt: str
    values: dict[str, object]


def _subject(value: object) -> str:
    return required(value, "Web search subject", 240)


def _metric(value: object, unit: str) -> object:
    if value is None:
        return None
    if unit == "text":
        return required(value, "Index inspection state", 100)
    if unit == "boolean" and type(value) is bool:
        return value
    if unit == "boolean" or not isinstance(value, (int, float)) or isinstance(value, bool):
        raise Invalid("Web metric must match its declared unit")
    if not 0 <= value <= 10**12 or not isfinite(value):
        raise Invalid("Web metric must be a finite number within its permitted range")
    if unit == "count" and value != int(value):
        raise Invalid("Web counts must be whole numbers")
    if (unit == "position" and value < 1) or (unit == "fraction" and value > 1) or (unit == "score" and value > 100):
        raise Invalid("Web metric does not match its unit")
    return value


def _source(row: dict, as_of: str) -> tuple[str, str, str]:
    retrieved = iso_time(row["retrieved_at"])
    if retrieved > iso_time(as_of):
        raise Invalid("Web observation cannot be in the future")
    url = public_url(row["reference_url"])
    required(row["excerpt"], "Source excerpt", 600)
    excerpt = row["excerpt"]
    hashed(row["sha256"])
    if sha256(excerpt.encode("utf-8")).hexdigest() != row["sha256"]:
        raise Invalid("Web source excerpt does not match its SHA-256")
    return retrieved.isoformat(), url, excerpt


def _validate_observation(row: dict, as_of: str, website: str) -> SearchObservation:
    exact(
        row,
        {
            "tool",
            "subject",
            "page_url",
            "period",
            "coverage",
            "retrieved_at",
            "reference_url",
            "sha256",
            "excerpt",
            "values",
        },
    )
    tool = row["tool"]
    if not isinstance(tool, str) or tool not in TOOLS:
        raise Invalid("Choose a supported OpenSEO tool")
    if row["coverage"] not in ("COMPLETE", "PARTIAL", "NO_RESULTS"):
        raise Invalid("Choose a valid OpenSEO coverage state")
    fields = TOOLS[tool]["fields"]
    exact(row["values"], fields)
    values = {name: _metric(row["values"][name], unit) for name, unit in fields.items()}
    if row["coverage"] == "NO_RESULTS" and any(value is not None for value in values.values()):
        raise Invalid("No-results evidence cannot supply web metrics")
    page = _page(row["page_url"], website, tool)
    _relationships(tool, values)
    retrieved, url, excerpt = _source(row, as_of)
    period = _period(row["period"], tool, retrieved)
    return {
        "tool": tool,
        "subject": _subject(row["subject"]),
        "page_url": page,
        "period": period,
        "coverage": row["coverage"],
        "retrieved_at": retrieved,
        "reference_url": url,
        "sha256": row["sha256"],
        "excerpt": excerpt,
        "values": values,
    }


def _page(value: object, website: str, tool: str) -> str | None:
    if tool not in OWNED_TOOLS:
        if value is not None:
            raise Invalid("External OpenSEO observations must not claim an owned page")
        return None
    page = public_url(value)
    site, target = urlsplit(website), urlsplit(page)
    root = unquote(site.path).rstrip("/")
    path = unquote(target.path)
    if site.netloc != target.netloc or not (path == root or path.startswith(root + "/")):
        raise Invalid("Owned web observations must point inside the app's configured website")
    if any(segment in (".", "..") for segment in path.split("/")):
        raise Invalid("Use the canonical page path without dot segments")
    return page


def _period(value: object, tool: str, retrieved_at: str) -> dict[str, str] | None:
    if value is None and tool not in WINDOWED_TOOLS:
        return None
    if not isinstance(value, dict):
        raise Invalid("Supply the exact reporting window and device")
    exact(value, {"start", "end", "device"})
    if value["device"] not in ("ALL", "DESKTOP", "MOBILE", "TABLET"):
        raise Invalid("Use the device from the evidence")
    try:
        start, end = (date.fromisoformat(value[key]) for key in ("start", "end"))
    except (TypeError, ValueError) as exc:
        raise Invalid("Use ISO dates for the exact provider reporting window") from exc
    if start > end or end > iso_time(retrieved_at).date():
        raise Invalid("Invalid web reporting dates")
    return dict(start=start.isoformat(), end=end.isoformat(), device=value["device"])


def _audit_relationship(values: dict[str, object]) -> None:
    critical, major, total = (values[key] for key in ("critical_issues", "major_issues", "total_issues"))
    if (
        isinstance(critical, (int, float))
        and isinstance(major, (int, float))
        and isinstance(total, (int, float))
        and critical + major > total
    ):
        raise Invalid("Audit issue categories cannot exceed the total")


def _relationships(tool: str, values: dict[str, object]) -> None:
    if tool == "get_audit_issues":
        _audit_relationship(values)
    if tool == "get_search_console_performance":
        clicks, impressions, ctr = (values[k] for k in ("clicks", "impressions", "ctr"))
        if isinstance(clicks, (int, float)) and isinstance(impressions, (int, float)):
            if clicks > impressions:
                raise Invalid("Search Console clicks cannot exceed impressions")
            if isinstance(ctr, (int, float)) and impressions > 0 and abs(ctr - clicks / impressions) > 0.001:
                raise Invalid("Search Console CTR does not match clicks divided by impressions")
    if tool == "get_ai_visibility_results":
        samples = values["samples"]
        mentions = values["mentions"]
        if isinstance(samples, (int, float)) and isinstance(mentions, (int, float)) and mentions > samples:
            raise Invalid("AI answer mentions cannot exceed the answer sample")
    if "store_bound_sessions" in values:
        store_bound, sessions = values["store_bound_sessions"], values["sessions"]
        if isinstance(store_bound, (int, float)) and isinstance(sessions, (int, float)) and store_bound > sessions:
            raise Invalid("Store-bound sessions cannot exceed eligible organic sessions")


def validate_web_binding(website: str, approved_website: object) -> None:
    """Match the app's configured site before saving locally recorded evidence."""
    if not isinstance(approved_website, str) or not approved_website:
        raise Invalid("Add the owned website to this app before saving web research")
    bound = urlsplit(approved_website)
    supplied = urlsplit(website)
    if (bound.scheme, bound.hostname, bound.path.rstrip("/")) != (
        supplied.scheme,
        supplied.hostname,
        supplied.path.rstrip("/"),
    ):
        raise Invalid("OpenSEO's website must match the website configured for the selected app")


def _evidence_scope(data: dict, context: dict) -> None:
    fields = {"release", "locale", "territory", "website", "provider", "observations"}
    if isinstance(data, dict) and "native_source" in data:
        fields.add("native_source")
        exact(data["native_source"], {"source_id", "report_id", "report_hash"})
        hashed(data["native_source"]["report_hash"])
    exact(data, fields)
    if data["locale"] != context.get("locale") or not context.get("locale"):
        raise Invalid("Web evidence locale must match the configured app locale")
    if data["provider"] != "openseo":
        raise Invalid("Choose OpenSEO as the web evidence provider")
    territory = required(data["territory"], "Territory", 2)
    if len(territory) != 2 or not territory.isascii() or not territory.isalpha() or not territory.isupper():
        raise Invalid("Territory must be a two-letter uppercase country code")


def validate_web_evidence(data: dict, context: dict, as_of: str) -> list[SearchObservation]:
    """Validate evidence before either a local write or a historical read."""
    _evidence_scope(data, context)
    website = public_url(data["website"])
    rows = data["observations"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= 20:
        raise Invalid("Import one to twenty selected web observations")
    observations = [_validate_observation(row, as_of, website) for row in rows]
    keys = {_evidence_key(row) for row in observations}
    if len(keys) != len(observations):
        raise Invalid("OpenSEO observations must be distinct")
    return observations


def _window_key(row: SearchObservation) -> tuple[str, ...]:
    period = row["period"]
    return (period["start"], period["end"], period["device"]) if period else ()


def _evidence_key(row: SearchObservation) -> tuple:
    window = _window_key(row) or (row["retrieved_at"],)
    return row["tool"], " ".join(row["subject"].split()).casefold(), row["page_url"], window


def _status(row: SearchObservation, as_of: str, current: bool) -> str:
    if not current or iso_time(as_of) - iso_time(row["retrieved_at"]) > timedelta(days=30):
        return "RECHECK_SOURCE"
    if row["period"] and (iso_time(as_of).date() - date.fromisoformat(row["period"]["end"])).days > 30:
        return "RECHECK_SOURCE"
    if row["coverage"] == "COMPLETE" and _healthy(row):
        return "NO_ACTION"
    if row["coverage"] != "COMPLETE" or not _decisive(row):
        return "COLLECT_EVIDENCE"
    return "REVIEW_ACTION"


def _healthy(row: SearchObservation) -> bool:
    values = row["values"]
    if row["tool"] == "inspect_urls":
        return values["canonical_match"] is True and values["indexing_state"] == "INDEXED"
    if row["tool"] == "get_audit_issues":
        return all(values[key] == 0 for key in ("critical_issues", "major_issues", "total_issues"))
    return False


def _decisive(row: SearchObservation) -> bool:
    values = row["values"]
    tool = row["tool"]
    if tool == "inspect_urls":
        return values["canonical_match"] is False or values["indexing_state"] in {
            "NOT_INDEXED",
            "BLOCKED",
            "EXCLUDED",
        }
    if tool == "get_audit_issues":
        total = values["total_issues"]
        return isinstance(total, (int, float)) and total > 0
    if tool == "get_search_console_performance" and values["clicks"] is None:
        return False
    if "store_bound_sessions" in values and values["store_bound_sessions"] is None:
        return False
    positive = {
        "get_search_console_performance": ("impressions",),
        "get_search_opportunities": ("impressions", "sessions"),
        "get_google_analytics_organic_landing_pages": ("sessions",),
        "get_serp_results": ("best_position", "seen_in"),
        "get_rank_history": ("position",),
        "research_keywords": ("volume",),
        "get_keyword_metrics": ("volume",),
        "get_domain_overview": ("ranked_keywords",),
        "get_backlinks_overview": ("referring_domains",),
        "get_ai_visibility_results": ("samples",),
    }[tool]
    return all(isinstance(value, (int, float)) and value > 0 for value in (values[key] for key in positive))


def _priority(row: dict) -> int:
    if row["tool"] == "inspect_urls":
        return 0
    return tuple(TOOLS).index(row["tool"])


def _exposure_key(row: dict) -> int | float:
    """Use exposure only within the same source family and reporting scope."""
    field = {
        "get_search_opportunities": "impressions",
        "get_search_console_performance": "impressions",
        "get_google_analytics_organic_landing_pages": "sessions",
    }.get(row["tool"])
    value = row["values"].get(field) if field else None
    return -value if isinstance(value, (int, float)) else 0


def _action(row: SearchObservation, status: str) -> str:
    tool = row["tool"]
    if status == "NO_ACTION":
        return "No repair is indicated by this saved check; investigate the next measured funnel step."
    if status == "REVIEW_ACTION":
        if tool == "get_search_console_performance" and row["subject"] == row["page_url"]:
            return "Read the queries bringing impressions to this page before choosing a headline test."
        return TOOLS[tool]["action"]
    if status == "COLLECT_EVIDENCE" and row["coverage"] == "COMPLETE":
        if tool == "get_search_console_performance" and row["values"]["clicks"] is None:
            return "Read exact Google clicks and impressions for the same query, page, device, and dates."
        if "store_bound_sessions" in row["values"] and row["values"]["store_bound_sessions"] is None:
            return "Track and count sessions with a store-link click on this page. Generic GA4 key events cannot supply this."
    return "Refresh the exact market and source before choosing a test."


def _observed_rate(row: SearchObservation) -> dict | None:
    pairs = {
        "get_search_console_performance": ("clicks", "impressions", "Google organic CTR"),
        "get_search_opportunities": ("store_bound_sessions", "sessions", "Web store-link conversion"),
        "get_google_analytics_organic_landing_pages": (
            "store_bound_sessions",
            "sessions",
            "Web store-link conversion",
        ),
    }
    if row["tool"] not in pairs:
        return None
    top, base, label = pairs[row["tool"]]
    n, d = row["values"][top], row["values"][base]
    if not isinstance(n, (int, float)) or not isinstance(d, (int, float)) or d <= 0:
        return None
    return dict(label=label, numerator=n, denominator=d, value=n / d)


def _action_window(row: dict) -> tuple[int, int, str]:
    period = row["period"]
    if not period:
        return (0, 0, "")
    return (
        -date.fromisoformat(period["end"]).toordinal(),
        -date.fromisoformat(period["start"]).toordinal(),
        period["device"],
    )


def _page_repairs(items: list[dict]) -> None:
    """Keep uncertain indexing visible before suggesting a test on the same page."""
    pending = {
        row["page_url"]
        for row in items
        if row["tool"] in ("inspect_urls", "get_audit_issues")
        and row["status"] in ("RECHECK_SOURCE", "COLLECT_EVIDENCE")
    }
    for row in items:
        if row["tool"] not in ("inspect_urls", "get_audit_issues") and row["page_url"] in pending:
            row.update(
                status="COLLECT_EVIDENCE",
                next_action="Refresh this page's indexing and canonical check before testing copy.",
                measure=None,
                observed_rate=None,
            )


def _test_brief(row: dict, territory: str) -> dict[str, object] | None:
    """Draft one measurable web change from the same record as the retained baseline."""
    window, baseline, page = row["period"], row["observed_rate"], row["page_url"]
    if row["status"] != "REVIEW_ACTION" or not window or not baseline or not page:
        return None
    if row["tool"] == "get_search_console_performance":
        if row["subject"] == page:
            return None
        change = "Change only the search title for this page, aligned with the observed query."
        hypothesis = "A title that answers this search intent may earn more qualified clicks."
        guardrail = "Keep the existing canonical URL, body and store CTA. Verify indexing and the observed title."
    else:
        change = "Change only the text of the main store call to action."
        hypothesis = "A clearer reason to try the app may increase the share of visitors opening its store listing."
        guardrail = "Keep the store destination, placement and click-event definition fixed."
    days = (date.fromisoformat(window["end"]) - date.fromisoformat(window["start"])).days + 1
    return dict(
        state="DRAFT_FOR_REVIEW",
        page=page,
        subject=row["subject"],
        territory=territory,
        device=window["device"],
        source_sha256=row["sha256"],
        baseline=baseline,
        baseline_window=window,
        comparison_days=days,
        change=change,
        hypothesis=hypothesis,
        comparison="Use the same source, page, market and device in the next comparable complete window. "
        "Keep the query fixed for a title test. Record other changes; this comparison cannot establish causal lift.",
        guardrail=guardrail,
        decision="Before changing the page, confirm the source and set minimum sample and useful improvement. "
        "Collect if the sample is too small; stop on a guardrail breach; otherwise continue or revise against the frozen rule.",
    )


def web_evidence_readout(data: dict, context: dict, as_of: str, current: bool) -> dict:
    """Select a reproducible next step without creating any measured outcome."""
    items = []
    for row in validate_web_evidence(data, context, as_of):
        tool = TOOLS[row["tool"]]
        status = _status(row, as_of, current)
        action = _action(row, status)
        items.append(
            dict(
                row,
                family=tool["family"],
                units=tool["fields"],
                status=status,
                next_action=action,
                measure=tool["metric"] if status == "REVIEW_ACTION" else None,
                observed_rate=_observed_rate(row) if status == "REVIEW_ACTION" else None,
            )
        )
    _page_repairs(items)
    items.sort(
        key=lambda item: (
            {"REVIEW_ACTION": 0, "RECHECK_SOURCE": 1, "COLLECT_EVIDENCE": 1, "NO_ACTION": 2}[item["status"]],
            _priority(item),
            _action_window(item),
            _exposure_key(item),
            item["subject"].casefold(),
            item["retrieved_at"],
        )
    )
    return dict(
        status=items[0]["status"],
        next_action=items[0]["next_action"],
        recommendation=items[0],
        test_brief=_test_brief(items[0], data["territory"]),
        observations=items,
        repairs=[row for row in items if row["status"] in ("RECHECK_SOURCE", "COLLECT_EVIDENCE")],
        scope="WEB_SEARCH_ONLY",
        provenance="IMPORTED_OPERATOR_ASSERTION",
        provider_verified=False,
        store_rank_verified=False,
        outcomes_verified=False,
    )


def agent_contract() -> dict:
    """Print the existing growth.save contract extension without granting network access."""
    return {
        "kind": "WEB_SEO_EVIDENCE",
        "entry_fields": {
            "release": "current app release",
            "locale": "current app locale",
            "territory": "US",
            "website": "public HTTPS app website",
            "provider": "openseo",
            "observations": [
                {
                    "tool": "one declared tool",
                    "subject": "exact query or page label",
                    "page_url": "canonical owned page for Google property tools; null otherwise",
                    "coverage": "COMPLETE|PARTIAL|NO_RESULTS",
                    "period": {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD", "device": "ALL|DESKTOP|MOBILE|TABLET"},
                    "retrieved_at": "timezone-bearing ISO date",
                    "reference_url": "clean public HTTPS source reference",
                    "sha256": "SHA-256 of exact UTF-8 excerpt",
                    "excerpt": "permitted proof up to 600 characters",
                    "values": "exact metric fields for selected tool; use null when missing",
                },
            ],
        },
        "tools": TOOLS,
        "windowed_tools": sorted(WINDOWED_TOOLS),
        "built_in_retrieval": {
            "connect": "Owner connects OpenSEO in Connections using an app-dedicated project API key.",
            "read_operation": "web.research.read",
            "source": "resource_id is the selected app's connected OpenSEO source ID, from workspace.read.",
            "input": {"confirm_read": True},
            "save_operation": "web.research.save",
            "save_input": {
                "id": "new immutable request ID",
                "manifest_version": "current app version",
                "report_id": "retained native reading ID",
            },
            "effect": "Final Google Search Console page aggregates only; no SEO-credit purchase or external mutation.",
            "unknowns": "NO_RESULTS is not zero traffic. PARTIAL is not complete site coverage. Read each exact window on its own.",
        },
        "limits": {"observations": 20, "freshness_days": 30},
        "instructions": "Use your separately authorized OpenSEO connection. Import only selected structured result fields. Do not send private WMM data or use paid tools without an owner-approved cap. Keep Google web evidence separate from App Store rank and native outcomes.",
        "local_import_network_calls": False,
        "native_retrieval_network_calls": True,
    }
