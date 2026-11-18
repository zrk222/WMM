"""Native app-website Search Console retrieval through OpenSEO's bounded MCP."""

import json
import re
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from sqlite3 import Connection
from typing import TYPE_CHECKING
from urllib.parse import urlsplit, urlunsplit

from .aeo_transport import public_url
from .common import Invalid, canonical, digest, identifier, now
from .db import connection
from .pmf_contract import exact
from .web_search_evidence import validate_web_binding, validate_web_evidence

COUNTRIES = {"US": "USA", "CA": "CAN", "GB": "GBR", "AU": "AUS", "NZ": "NZL", "IE": "IRL", "ZA": "ZAF"}
SOURCE = "https://openseo.so/docs/mcp-tools"

if TYPE_CHECKING:
    from .service import Service
    from .store import Store


def assert_app_scope(data: dict, app_data: dict) -> None:
    """Stop native reads when the app's configured website changes."""
    validate_web_binding(data["website"], app_data.get("website"))
    if data["release"] != app_data.get("release") or data["locale"] != app_data.get("locale"):
        raise Invalid("App release or locale changed; review the OpenSEO connection again")


def _property(site: object, website: str) -> None:
    if isinstance(site, str) and site.startswith("sc-domain:") and site[10:].casefold() == urlsplit(website).hostname:
        return
    if isinstance(site, str) and not site.startswith("sc-domain:"):
        root = public_url(site)
        site_parts, app_parts = urlsplit(root), urlsplit(website)
        path = site_parts.path.rstrip("/")
        if site_parts.netloc == app_parts.netloc and (
            app_parts.path.rstrip("/") == path or app_parts.path.startswith(path + "/")
        ):
            return
    raise Invalid("OpenSEO Search Console property does not cover this app website")


def _row(row: object, data: dict, start: str, end: str, stamp: str) -> dict:
    size = 2 if data["report_mode"] == "queries" else 1
    if not isinstance(row, dict) or not isinstance(row.get("keys"), list) or len(row["keys"]) != size:
        raise Invalid("OpenSEO page report returned an unsupported row")
    page = public_url(row["keys"][0])
    subject = row["keys"][1] if size == 2 else page
    if not isinstance(subject, str) or not subject.strip() or len(subject) > 240:
        raise Invalid("OpenSEO search query is unsupported")
    if size == 2 and (re.search(r"[@<>]|\d{7,}", subject) or not subject.isprintable()):
        raise Invalid("OpenSEO query contains a contact-like or unsupported identifier")
    values = {key: row.get(key) for key in ("clicks", "impressions", "ctr", "position")}
    if values["impressions"] == 0 and values["position"] == 0:
        values["position"] = None
    excerpt = canonical(
        {
            "page": page,
            "subject": subject,
            "territory": data["territory"],
            "device": "ALL",
            "reporting_timezone": "America/Los_Angeles",
            "start": start,
            "end": end,
            "values": values,
        }
    )
    if len(excerpt) > 600:
        raise Invalid("OpenSEO page evidence exceeds the selected observation bound")
    return dict(
        tool="get_search_console_performance",
        subject=subject,
        page_url=page,
        period=dict(start=start, end=end, device="ALL"),
        coverage="COMPLETE",
        retrieved_at=stamp,
        reference_url=SOURCE,
        sha256=sha256(excerpt.encode()).hexdigest(),
        excerpt=excerpt,
        values=values,
    )


def _validated_rows(payload: dict, config: dict, dimensions: list[str], start: str, end: str) -> list:
    if payload.get("ok") is not True:
        raise Invalid("Connect Search Console to the selected OpenSEO project, then retry")
    _property(payload.get("siteUrl"), config["website"])
    if payload.get("dimensions") != dimensions or payload.get("startDate") != start or payload.get("endDate") != end:
        raise Invalid("OpenSEO returned a different reporting window or dimensions")
    rows = payload.get("rows")
    if (
        not isinstance(rows, list)
        or len(rows) > 20
        or payload.get("rowCount") != len(rows)
        or type(payload.get("hasMore")) is not bool
    ):
        raise Invalid("OpenSEO page report is incomplete or unsupported")
    return rows


def _selected_rows(rows: list, config: dict) -> tuple[list[dict], dict[str, int]]:
    """Omit unsupported full URLs without retaining parameters or merging pages."""
    selected: list[dict] = []
    omitted = {"outside_app": 0, "parameter_or_fragment": 0}
    for row in rows:
        page = _row_page(row, config)
        if not _inside_app(page, config["website"]):
            omitted["outside_app"] += 1
        elif "?" in row["keys"][0] or "#" in row["keys"][0]:
            omitted["parameter_or_fragment"] += 1
        else:
            selected.append(row)
    return selected, omitted


def _row_page(row: object, config: dict) -> str:
    size = 2 if config["report_mode"] == "queries" else 1
    if not isinstance(row, dict) or not isinstance(row.get("keys"), list) or len(row["keys"]) != size:
        raise Invalid("OpenSEO page report returned an unsupported row")
    raw = row["keys"][0]
    if not isinstance(raw, str) or len(raw) > 2400 or re.search(r"[\x00-\x20\x7f\\]", raw):
        raise Invalid("OpenSEO page URL is malformed")
    parts = urlsplit(raw)
    # This validates authority/path only. The reconstructed URL is never saved.
    return public_url(urlunsplit((parts.scheme, parts.netloc, parts.path, "", "")))


def _inside_app(page: str, website: str) -> bool:
    app = urlsplit(website)
    target = urlsplit(page)
    prefix = app.path.rstrip("/")
    return target.netloc == app.netloc and (target.path == prefix or target.path.startswith(prefix + "/"))


def read(config: dict, token: str) -> dict:
    """Fetch only final page aggregates in the configured app market; no SEO credits."""
    from .openseo_transport import call_tool

    end = (datetime.now(timezone.utc) - timedelta(days=4)).date()
    start = end - timedelta(days=27)
    dimensions = ["page", "query"] if config["report_mode"] == "queries" else ["page"]
    payload = call_tool(
        token,
        "get_search_console_performance",
        dict(
            projectId=config["project_id"],
            dimensions=dimensions,
            startDate=start.isoformat(),
            endDate=end.isoformat(),
            filters=[dict(dimension="country", operator="equals", expression=COUNTRIES[config["territory"]].lower())],
            rowLimit=20,
            startRow=0,
            type="web",
            dataState="final",
        ),
    )
    rows = _validated_rows(payload, config, dimensions, start.isoformat(), end.isoformat())
    rows, omitted = _selected_rows(rows, config)
    stamp = now()
    observations = [_row(row, config, start.isoformat(), end.isoformat(), stamp) for row in rows]
    evidence = dict(
        release=config["release"],
        locale=config["locale"],
        territory=config["territory"],
        website=config["website"],
        provider="openseo",
        observations=observations,
    )
    if observations:
        validate_web_evidence(evidence, {"locale": config["locale"]}, stamp)
    coverage = (
        "PARTIAL" if payload["hasMore"] or any(omitted.values()) else "COMPLETE" if observations else "NO_RESULTS"
    )
    if coverage == "PARTIAL":
        for row in observations:
            row["coverage"] = "PARTIAL"
    return dict(
        provider="openseo",
        project_id=config["project_id"],
        observed_at=stamp,
        scope="APP_WEBSITE_GOOGLE_SEARCH",
        coverage=coverage,
        omitted_rows=omitted,
        rows=[
            dict(
                id=row["page_url"],
                values=row["values"],
                period=start.isoformat() + " to " + end.isoformat(),
                unit="Google web metrics",
            )
            for row in observations
        ],
        web_evidence=evidence if observations else None,
        provider_response_sha256=digest(payload),
        interpretation="Native OpenSEO response from the configured project and market. Google observations only, not App Store rank or native installs. A property-level top-20 slice may omit this app's pages; no rows does not mean zero traffic. "
        + f"Omitted {omitted['outside_app']} rows outside this app and {omitted['parameter_or_fragment']} app-page rows with URL parameters or fragments. Such URLs are not retained or merged; review a clean-page provider export to investigate omitted evidence.",
    )


def native_reading(db: Connection, app: str, source_id: str, report_id: str) -> tuple[dict, dict]:
    """Select a same-app immutable report and check the current source binding."""
    from .insights import decoded

    source = db.execute("SELECT * FROM insight_sources WHERE app_id=? AND id=?", (app, source_id)).fetchone()
    report = db.execute(
        "SELECT * FROM insight_reports WHERE app_id=? AND source_id=? AND id=?",
        (app, source_id, report_id),
    ).fetchone()
    if not source or not report:
        raise Invalid("Select a saved OpenSEO reading in this app")
    source, report = decoded(source), decoded(report)
    if source["provider"] != "openseo" or source["status"] in ("DISCONNECTED", "CLEANUP_REQUIRED"):
        raise Invalid("Reconnect the selected OpenSEO source before saving current evidence")
    if (
        report["data"].get("source_version") != source["version"]
        or report["data"].get("configuration_hash") != source["hash"]
    ):
        raise Invalid("OpenSEO setup changed; read the current source first")
    return source, report


def verify_native_source(db: Connection, app: str, data: dict) -> None:
    """Prevent a caller from asserting a native read without its retained provider report."""
    ref = data.get("native_source")
    if ref is None:
        return
    exact(ref, {"source_id", "report_id", "report_hash"})
    source, report = native_reading(db, app, ref["source_id"], ref["report_id"])
    if report["hash"] != ref["report_hash"]:
        raise Invalid("Native OpenSEO report hash changed")
    supplied = {key: value for key, value in data.items() if key != "native_source"}
    if supplied != report["data"].get("web_evidence"):
        raise Invalid("Native OpenSEO evidence differs from its saved provider reading")
    app_row = db.execute("SELECT data FROM apps WHERE id=?", (app,)).fetchone()
    assert_app_scope(source["data"], json.loads(app_row[0]))


def save_reading(store: "Store", app: str, source_id: str, body: dict) -> dict:
    """Save an exact retained native reading through the existing immutable local review."""
    from .growth_review_store import GrowthReviews

    exact(body, {"id", "manifest_version", "report_id"})
    with connection(store.path) as db:
        _, report = native_reading(db, app, source_id, body["report_id"])
        evidence = report["data"].get("web_evidence")
        if not evidence:
            raise Invalid("This reading contains no app-page rows; refine the source and read again")
        evidence = dict(
            evidence, native_source=dict(source_id=source_id, report_id=body["report_id"], report_hash=report["hash"])
        )
    return GrowthReviews(store).save(
        app,
        dict(
            id=body["id"],
            manifest_version=body["manifest_version"],
            kind="WEB_SEO_EVIDENCE",
            data=evidence,
        ),
    )


def fetch_for_owner(service: "Service", app: str, action: str, body: dict) -> dict:
    """Fetch and retain the exact OpenSEO reading from the signed-in acquisition report."""
    from .growth_review_contract import context_of, entry_hash
    from .growth_review_store import decoded
    from .insights import Insights
    from .operation_authority import PROTECTED, check

    context = PROTECTED.get()
    if context is None or "grant_id" in context:
        raise PermissionError("Open the owner's search report to fetch its connected source")
    envelope = json.loads(str(context["envelope"]))
    if (
        envelope["app_id"] != app
        or envelope["operation"] != "apple.analytics.owner.search-web-fetch"
        or action != "search-web-fetch"
    ):
        raise PermissionError("Use the current app's owner report")
    sid, request_id = identifier(body["source_id"]), identifier(body["request_id"])
    response = dict(app_id=app, source_id=sid, request_id=request_id)
    with connection(service.store.path) as db:
        db.execute("BEGIN")
        check(db, context)
        row = db.execute("SELECT id,version,data FROM apps WHERE id=?", (app,)).fetchone()
        if row is None or type(body["manifest_version"]) is not int or row["version"] != body["manifest_version"]:
            raise Invalid("App setup changed. Reopen the owner report before fetching.")
        existing = db.execute(
            "SELECT * FROM growth_review_entries WHERE app_id=? AND id=?", (app, request_id)
        ).fetchone()
        if existing:
            entry = decoded(existing)
            binding = entry["data"].get("native_source", {})
            if (
                entry["kind"] != "WEB_SEO_EVIDENCE"
                or binding.get("source_id") != sid
                or entry["context"] != context_of(dict(row, data=json.loads(row["data"])))
                or entry["hash"] != entry_hash(entry["kind"], entry["data"], entry["context"])
            ):
                raise Invalid("This request ID belongs to another review")
            _, report = native_reading(db, app, sid, binding["report_id"])
            if report["hash"] != binding["report_hash"]:
                raise Invalid("The previous reading changed. Fetch a fresh report.")
            return dict(
                response,
                status="SAVED",
                report_id=report["id"],
                source_sha256=report["hash"],
                review_sha256=entry["hash"],
            )
    require_web_source(service.store, app, sid)
    read = Insights(service.store).refresh(app, sid, {"confirm_read": True})
    if read.get("status") != "CONNECTED" or not read.get("report_id"):
        raise Invalid(read.get("error") or "OpenSEO could not finish the read. Check the source connection.")
    saved = save_reading(
        service.store,
        app,
        sid,
        dict(id=request_id, manifest_version=body["manifest_version"], report_id=read["report_id"]),
    )
    binding = saved["data"]["native_source"]
    return dict(
        response,
        status="SAVED",
        report_id=binding["report_id"],
        source_sha256=binding["report_hash"],
        review_sha256=saved["hash"],
    )


def require_web_source(store: "Store", app: str, source_id: str) -> None:
    """Validate one exact app-owned OpenSEO source before scoped dispatch."""
    from .insights import Insights

    with connection(store.path) as db:
        source = Insights(store).row(db, app, source_id)
        if source["provider"] != "openseo":
            raise Invalid("Choose this app's OpenSEO source")


def dispatch(service: "Service", envelope: dict) -> dict:
    """Reuse existing read and save services under the admitted agent scope."""
    from .insights import Insights
    from .operation_authority import protected

    app, source = envelope["app_id"], envelope["resource_id"]
    with protected(service.store, envelope):
        require_web_source(service.store, app, source)
        if envelope["operation"] == "web.research.read":
            return Insights(service.store).refresh(app, source, envelope["input"])
        return save_reading(service.store, app, source, envelope["input"])
