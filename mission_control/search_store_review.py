"""Prepare owner-reviewed work from separately evidenced web and store signals."""

import json
from sqlite3 import Connection
from typing import Any, TypedDict

from .common import Invalid, canonical, now
from .growth_review_contract import context_of
from .growth_review_store import current_readout, decoded


class AgentAction(TypedDict):
    id: str
    title: str
    task: str
    metric: str
    guardrail: str
    follow_up: str
    depends_on: list[str]
    agent: str


def _verified_web(db: Connection, app: dict, stamp: str) -> tuple[dict, dict] | None:
    context = context_of(app)
    rows = db.execute(
        "SELECT * FROM growth_review_entries WHERE app_id=? AND kind='WEB_SEO_EVIDENCE' "
        "AND imported=0 AND context=? ORDER BY created DESC,id DESC",
        (app["id"], canonical(context)),
    )
    try:
        for record in rows:
            row = decoded(record)
            if not row["data"].get("native_source"):
                continue
            readout = current_readout(db, row, context, stamp)
            analysis = readout["analysis"]
            observed = analysis["recommendation"]
            if (
                readout["availability"] == "CURRENT_LOCAL_EVIDENCE"
                and analysis["native_connection_read"]
                and observed["tool"] == "get_search_console_performance"
                and observed["status"] != "RECHECK_SOURCE"
            ):
                return row, observed
            return None
    except (Invalid, ValueError, TypeError, KeyError, AttributeError):
        return None
    return None


def _mature_days(rows: list[dict], family: str, metric: str) -> int:
    return sum(
        item[family]["status"] == "APPLE_REPORTED" and item[family]["counts"][metric] is not None for item in rows
    )


def _apple_action(result: dict, connected: bool, complete: bool) -> AgentAction:
    return AgentAction(
        id="apple-baseline",
        title="Review the Apple baseline" if complete else "Complete the Apple baseline",
        task=_apple_task(result, connected, complete),
        metric="Mature Apple discovery and first-time download days in the selected window.",
        guardrail="Preserve missing days and keep file counts separate from App Store event counts.",
        follow_up="Check Apple processing dates and retain receipts before comparing windows.",
        depends_on=[],
        agent="Apple analytics agent",
    )


def _apple_task(result: dict, connected: bool, complete: bool) -> str:
    if not result["store_app_id"]:
        return "Confirm the app’s Apple ID before reading App Store Connect analytics."
    if not connected:
        return "Connect this app’s App Store Connect read source and check report availability."
    window = result["start"] + " through " + result["end"]
    if complete:
        return f"Review the saved Apple event counts for {window} by event date and report family."
    return f"Check Apple inventory and collect available discovery and download files for {window}."


def _web_action(website: str | None, reading: tuple[dict, dict] | None) -> AgentAction:
    title, task = _web_task(website, reading)
    return AgentAction(
        id="web-baseline",
        title=title,
        task=task,
        metric="Google organic clicks and impressions for the same page, market, device and dates.",
        guardrail="Use the selected app’s site and retain the reported coverage. Keep Google and Apple counts separate.",
        follow_up="Compare an equivalent complete Google reporting window before making a performance claim.",
        depends_on=[],
        agent="Web search agent",
    )


def _web_task(website: str | None, reading: tuple[dict, dict] | None) -> tuple[str, str]:
    if not website:
        return "Add the app website", "Set the app’s owned website before selecting its OpenSEO project."
    if reading is None:
        return "Read OpenSEO search evidence", f"Read and save the current Search Console evidence for {website}."
    _, row = reading
    if row["coverage"] != "COMPLETE":
        return (
            "Complete the web evidence",
            f"Review omitted rows and confirm complete Search Console data for {row['page_url']}.",
        )
    if row["status"] != "REVIEW_ACTION":
        return (
            "Complete the web evidence",
            f"Confirm clicks and impressions for {row['page_url']} before choosing a test.",
        )
    return (
        "Review the strongest observed web page",
        f"Assess the saved search performance for {row['page_url']} and prepare the next evidence-backed test.",
    )


def _link_check(page: str, store_app_id: str) -> AgentAction:
    return AgentAction(
        id="store-link-check",
        title="Verify the page’s App Store path",
        task=f"Inspect the iOS call to action on {page} and record whether it reaches Apple app {store_app_id}.",
        metric="Verified App Store destination and campaign tag status for this exact page.",
        guardrail="Keep the existing web start path intact. Inspect the link without publishing a change.",
        follow_up="If the page lacks a usable store path, draft one secondary iOS CTA for owner approval.",
        depends_on=["web-baseline"],
        agent="Acquisition measurement agent",
    )


def _tagged_test(page: str) -> AgentAction:
    return AgentAction(
        id="measure-tag",
        title="Design one tagged web-to-store test",
        task=f"Propose one owner-approved Apple campaign link for {page} and freeze its market, dates and sample floor.",
        metric="Mature Apple first-time downloads attributed to the exact campaign and territory.",
        guardrail="Keep web starts as a separate guardrail. Treat missing or suppressed Apple rows as unknown.",
        follow_up="Review delivery receipts and mature campaign rows before making a keep, revise or collect decision.",
        depends_on=["apple-baseline", "web-baseline", "store-link-check"],
        agent="Acquisition measurement agent",
    )


def _web_facts(reading: tuple[dict, dict] | None) -> tuple[str, list[str]]:
    if reading is None:
        return "No current verified OpenSEO reading", []
    entry, row = reading
    data = entry["data"]
    period = row["period"]
    counts = row["values"]
    facts = [
        f"{row['page_url']} · {data['territory']} · {period['device'].lower()} devices",
        f"{period['start']} through {period['end']} · {row['coverage'].lower()} coverage",
        "Google organic impressions " + _display_count(counts["impressions"]),
        "Google organic clicks " + _display_count(counts["clicks"]),
    ]
    if counts["impressions"] and counts["clicks"] is not None:
        facts.append(f"Google organic click-through rate {counts['clicks'] / counts['impressions']:.1%}")
    if counts["position"] is not None:
        facts.append(f"Google average position {counts['position']:.1f}")
    facts.append(f"Source receipt SHA-256 {row['sha256']}")
    return "Saved OpenSEO Search Console reading", facts


def _display_count(value: Any) -> str:
    return "unknown" if value is None else f"{int(value):,}"


def _web_observation(reading: tuple[dict, dict] | None) -> dict | None:
    if reading is None:
        return None
    entry, row = reading
    return dict(
        page_url=row["page_url"],
        territory=entry["data"]["territory"],
        period=row["period"],
        coverage=row["coverage"],
        status=row["status"],
        values=row["values"],
        sha256=row["sha256"],
        next_action=row["next_action"],
    )


def _can_check_link(row: dict) -> bool:
    return row["coverage"] == "COMPLETE" and (row["values"]["clicks"] or 0) > 0


def _web_insight(reading: tuple[dict, dict] | None) -> str:
    if reading is None:
        return "A current verified Google reading is needed to choose a measured web opportunity."
    _, row = reading
    if row["coverage"] != "COMPLETE":
        return "OpenSEO returned partial coverage. Confirm the page’s search evidence before selecting a test."
    if _can_check_link(row):
        clicks = _display_count(row["values"]["clicks"])
        return (
            f"Google reported {clicks} organic clicks for the selected search row on {row['page_url']}. "
            "Verify the page’s App Store path before testing it. Tagged Apple outcomes can then be reviewed separately."
        )
    if row["values"]["impressions"] and row["values"]["clicks"] == 0:
        return "Google reported impressions and zero clicks for the selected row. Review search intent before changing the store listing."
    return "Confirm Google clicks and impressions for the selected page before choosing an acquisition change."


def _window_note(reading: tuple[dict, dict] | None, result: dict) -> str:
    if reading is None:
        return ""
    period = reading[1]["period"]
    if (period["start"], period["end"]) == (result["start"], result["end"]):
        return ""
    return " The saved Google and selected Apple reporting windows differ."


def search_store_review(db: Connection, result: dict, connected: bool) -> dict:
    """Build a plan from one current app snapshot without provider or execution access."""
    record = db.execute("SELECT id,version,data FROM apps WHERE id=?", (result["app_id"],)).fetchone()
    if record is None:
        raise Invalid("App workspace is unavailable")
    app = dict(dict(record), data=json.loads(record["data"]))
    reading = _verified_web(db, app, now())
    web_source, web_facts = _web_facts(reading)
    rows = result["rows"]
    days = len(rows)
    discovery_days = _mature_days(rows, "discovery", "impressions")
    download_days = _mature_days(rows, "downloads", "first_time_downloads")
    complete = discovery_days == download_days == days
    apple = _apple_action(result, connected, complete)
    web = _web_action(app["data"].get("website"), reading)
    actions = [apple, web]
    primary = web if complete else apple
    store_id = result["store_app_id"]
    if reading is not None and store_id and _can_check_link(reading[1]):
        page = reading[1]["page_url"]
        link_check = _link_check(page, store_id)
        actions.append(link_check)
        if complete:
            actions.append(_tagged_test(page))
            primary = link_check
    return dict(
        insight=f"Apple’s app-wide reports have mature discovery counts for {discovery_days}/{days} days and mature first-time download counts for {download_days}/{days} days. "
        + _web_insight(reading)
        + _window_note(reading, result),
        next_action=primary["task"],
        success_metric=primary["metric"],
        guardrail=primary["guardrail"],
        follow_up=primary["follow_up"],
        web_source=web_source,
        web_facts=web_facts,
        web_evidence_sha256=reading[0]["hash"] if reading is not None else None,
        web_observation=_web_observation(reading),
        evidence_status=("Complete Apple baseline" if complete else "Incomplete Apple baseline") + " · " + web_source,
        actions=actions,
    )
