"""Retain and complete an exact owner-authorized Apple report refresh."""

import json
from datetime import date
from pathlib import Path
from sqlite3 import Connection, Row
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import urlsplit

from .apple_analytics import CAMPAIGN_DOWNLOADS, DISCOVERY, DOWNLOADS, identity
from .common import Invalid, canonical, digest, iso_time, now
from .db import connection
from .operation_authority import PROTECTED, check
from .review_access import exact_role
from .worker import enqueue_db

if TYPE_CHECKING:
    from .store import Store


ACTIVE = {"QUEUED", "RUNNING"}
REASONS = {
    "NOT_REQUESTED": "Choose Fetch Apple analytics to check these event dates.",
    "INVENTORY": "Checking App Store Connect report availability for the selected dates.",
    "COLLECTING": "Reading available Apple daily discovery and download report files.",
    "READY": "Apple report files were processed. Review the saved event-day rows for actual coverage.",
    "FAILED": "The Apple refresh did not complete. Review the saved inventory job and check the connection before retrying.",
    "INCOMPLETE": "Some requested Apple evidence is missing. Review the saved files and event-day rows before retrying.",
    "SOURCE_CHANGED": "The app, Apple connection or owner authority changed. Confirm current setup before fetching again.",
    "WAITING_FOR_REPORTS": "Apple did not list daily files yet. Check report availability again when Apple has processed them.",
    "REPORT_SETUP_REQUIRED": "Check the ongoing analytics report request in App Store Connect, then fetch again.",
    "REQUEST_INVENTORY_PARTIAL": "Apple returned an incomplete report inventory. Refresh before selecting any files.",
    "NO_FILES_FOR_DATES": "Apple listed no supported daily files covering the selected event dates.",
}


def _record(db: Connection, app_id: str, refresh_id: str) -> Row | None:
    return db.execute(
        "SELECT * FROM apple_performance_refreshes WHERE app_id=? AND id=?", (app_id, refresh_id)
    ).fetchone()


def _latest(db: Connection, app_id: str, owner: str, start: date, end: date) -> Row | None:
    return db.execute(
        "SELECT * FROM apple_performance_refreshes WHERE app_id=? AND event_start=? AND event_end=? "
        "AND json_extract(scope,'$.owner')=? "
        "ORDER BY created DESC,id DESC LIMIT 1",
        (app_id, start.isoformat(), end.isoformat(), owner),
    ).fetchone()


def _verified_scope(db: Connection, row: Row) -> dict[str, Any]:
    from .apple_metrics_http import check_source

    scope = json.loads(row["scope"])
    if digest(scope) != row["scope_sha256"]:
        raise Invalid("The saved Apple refresh failed its integrity check")
    try:
        exact_role(db, row["app_id"], scope["owner"], scope["owner_version"], "OWNER")
        current = check_source(
            db, row["app_id"], scope["manifest_version"], scope["connection_id"], scope["connection_version"]
        )
        if "campaign_report_id" in scope:
            saved, _, _, _ = campaign_refresh_selection(
                db,
                row["app_id"],
                scope["owner"],
                scope["campaign_report_id"],
                date.fromisoformat(row["event_start"]),
                date.fromisoformat(row["event_end"]),
            )
            if saved["hash"] != scope["campaign_report_sha256"]:
                raise Invalid("Saved campaign report changed")
    except (Invalid, PermissionError) as exc:
        raise Invalid(REASONS["SOURCE_CHANGED"]) from exc
    if current.store_app_id != scope["store_app_id"] or current.connection_hash != scope["connection_hash"]:
        raise Invalid(REASONS["SOURCE_CHANGED"])
    return scope


def campaign_refresh_selection(
    db: Connection, app_id: str, owner: str, report_id: str, start: date, end: date
) -> tuple[dict, dict, dict, dict]:
    """Revalidate the retained private report and its approved Apple measurement plan."""
    from .apple_campaign_links import campaign_parts
    from .apple_metrics_http import source
    from .apple_owner_outcome import apple_window
    from .campaign_owner_reports import owned_resource, report_view, selection
    from .evidence_gate import is_apple_plan, measurement_plan
    from .review_access import member

    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='campaign_owner_reports'").fetchone():
        raise Invalid("Save a private report for this approved Apple campaign first")
    saved = report_view(owned_resource(db, "campaign_owner_reports", app_id, owner, identity(report_id)))
    report = saved["report"]
    chosen = selection(report["selection"])
    app = db.execute("SELECT version,data FROM apps WHERE id=?", (app_id,)).fetchone()
    if app is None:
        raise Invalid("Campaign report app is unavailable")
    scope = owned_resource(db, "campaign_scopes", app_id, owner, chosen["scope_id"])
    approved = json.loads(scope["summary"])
    source_binding = report.get("source") or {}
    role = member(db, app_id, owner, "OWNER")
    local_db = db.execute("PRAGMA database_list").fetchone()["file"]
    current = dict(
        app_version=app["version"],
        app_hash=digest(json.loads(app["data"])),
        role_version=role["version"],
        host_hash=digest(str(Path(local_db).resolve())),
        scope_hash=scope["summary_hash"],
    )
    if (
        (report.get("app_id"), report.get("owner")) != (app_id, owner)
        or (approved.get("app_id"), approved.get("owner_principal")) != (app_id, owner)
        or any(source_binding.get(key) != value for key, value in current.items())
        or digest(approved) != scope["summary_hash"]
    ):
        raise Invalid("Save a current private report for this approved campaign first")
    plan = approved.get("measurement_plan")
    if not is_apple_plan(plan) or not chosen.get("apple_storefront"):
        raise Invalid("Select an approved Apple measurement plan and its storefront")
    plan = measurement_plan(plan, retained=True)
    linked = campaign_parts(urlsplit(plan["link"]))
    _, store_id, _ = source(db, app_id)
    if linked is None or linked[0] != store_id or apple_window(plan, chosen["measurement_window"]) != (start, end):
        raise Invalid("Use the exact approved Apple app, campaign and event dates")
    return saved, approved, plan, chosen


def _job_data(scope: dict[str, Any], options: dict[str, Any], refresh: str) -> dict[str, Any]:
    return dict(
        manifest_version=scope["manifest_version"],
        connection_id=scope["connection_id"],
        connection_version=scope["connection_version"],
        connection_hash=scope["connection_hash"],
        options=options,
        apple_performance_refresh_id=refresh,
    )


def _files(row: Row) -> list[dict[str, Any]]:
    if row["files"] is None:
        return []
    files = json.loads(row["files"])
    if digest(files) != row["files_sha256"]:
        raise Invalid("The saved Apple report-file handoff failed its integrity check")
    return files


def _job(db: Connection, app_id: str, job_id: str) -> Row | None:
    return db.execute("SELECT status,result FROM jobs WHERE app_id=? AND id=?", (app_id, job_id)).fetchone()


def _inventory_metadata(job: Row | None) -> tuple[str | None, str | None, str | None]:
    from .apple_metrics_http import INVENTORY_STATES

    if job is None:
        return None, None, None
    if job["status"] != "SUCCEEDED" or not job["result"]:
        return job["status"], None, None
    result = json.loads(job["result"])
    provider_status = result.get("status")
    coverage = result.get("coverage")
    return (
        job["status"],
        provider_status if provider_status in INVENTORY_STATES else None,
        coverage if coverage in {"COMPLETE", "PARTIAL"} else None,
    )


def _observed_at(job: Row | None) -> str | None:
    if job is None or job["status"] != "SUCCEEDED" or not job["result"]:
        return None
    value = json.loads(job["result"]).get("observed_at")
    if not isinstance(value, str) or len(value) > 40:
        return None
    try:
        iso_time(value)
    except (Invalid, ValueError):
        return None
    return value


def _status(row: Row, inventory_status: str | None, files: list[dict[str, Any]]) -> str:
    handoff = row["handoff_status"]
    if handoff is None:
        return "INVENTORY" if inventory_status in ACTIVE else "FAILED"
    if handoff != "COLLECTING":
        return handoff
    if any(file["status"] in ACTIVE for file in files):
        return "COLLECTING"
    complete = {file["report_family"] for file in files if file["status"] == "SUCCEEDED"}
    required = (
        {CAMPAIGN_DOWNLOADS}
        if any(file["report_family"] == CAMPAIGN_DOWNLOADS for file in files)
        else {DOWNLOADS, DISCOVERY}
    )
    if required.issubset(complete) and all(file["status"] == "SUCCEEDED" for file in files):
        return "READY"
    return "INCOMPLETE"


def _view(db: Connection, app_id: str, store_id: str | None, start: date, end: date, row: Row | None) -> dict:
    scope = dict(app_id=app_id, store_app_id=store_id, start=start.isoformat(), end=end.isoformat())
    inventory_status = provider_status = coverage = None
    inventory_observed_at = None
    campaign_report_id = None
    files = []
    if row is None:
        status = "NOT_REQUESTED"
    else:
        try:
            verified = _verified_scope(db, row)
        except Invalid:
            status = "SOURCE_CHANGED"
        else:
            inventory_job = _job(db, app_id, row["inventory_job_id"])
            inventory_status, provider_status, coverage = _inventory_metadata(inventory_job)
            inventory_observed_at = _observed_at(inventory_job)
            campaign_report_id = verified.get("campaign_report_id")
            for file in _files(row):
                selected = _job(db, app_id, file["job_id"])
                files.append(
                    dict(
                        job_id=file["job_id"],
                        processing_date=file["processing_date"],
                        report_family=file["report_family"],
                        status=selected["status"] if selected is not None else "MISSING",
                        observed_at=_observed_at(selected),
                    )
                )
            status = _status(row, inventory_status, files)
    return dict(
        scope,
        refresh_id=row["id"] if row is not None else None,
        requested_at=row["created"] if row is not None else None,
        campaign_report_id=campaign_report_id,
        inventory_job_id=row["inventory_job_id"] if row is not None else None,
        inventory_observed_at=inventory_observed_at,
        inventory_status=inventory_status,
        provider_status=provider_status,
        coverage=coverage,
        status=status,
        reason=REASONS[status],
        files=files,
        external_writes=False,
    )


def _owner(db: Connection, app_id: str, action: str) -> tuple[str, int]:
    context = PROTECTED.get()
    if context is None or "grant_id" in context:
        raise PermissionError("The Apple refresh requires the current owner")
    envelope = json.loads(cast(str, context["envelope"]))
    if envelope.get("app_id") != app_id or envelope.get("operation") != "apple.analytics.owner." + action:
        raise PermissionError("Use the owner Apple refresh action for this app")
    return check(db, context), cast(int, context["role_version"])


def _admit(
    db: Connection, store: "Store", app_id: str, action: str, body: dict, start: date, end: date
) -> tuple[str | None, Row | None]:
    from .apple_metrics_http import check_source

    if not isinstance(body["connection_id"], str):
        raise Invalid("Select this app’s Apple connection")
    refresh_id = identity(body["request_id"])
    owner, owner_version = _owner(db, app_id, action)
    expected = check_source(db, app_id, body["manifest_version"], body["connection_id"], body["connection_version"])
    scope = dict(
        manifest_version=expected.manifest_version,
        store_app_id=expected.store_app_id,
        connection_id=expected.connection_id,
        connection_version=expected.connection_version,
        connection_hash=expected.connection_hash,
        owner=owner,
        owner_version=owner_version,
    )
    if "campaign_report_id" in body:
        saved, _, _, _ = campaign_refresh_selection(db, app_id, owner, body["campaign_report_id"], start, end)
        scope.update(campaign_report_id=saved["id"], campaign_report_sha256=saved["hash"])
    previous = _record(db, app_id, refresh_id)
    if previous is not None:
        if (previous["event_start"], previous["event_end"], previous["scope"]) != (
            start.isoformat(),
            end.isoformat(),
            canonical(scope),
        ):
            raise Invalid("Apple refresh request ID is already bound to another date or connection")
        return expected.store_app_id, previous
    pending = _latest(db, app_id, owner, start, end)
    if pending is not None and _view(db, app_id, expected.store_app_id, start, end, pending)["status"] in {
        "INVENTORY",
        "COLLECTING",
    }:
        raise Invalid("An Apple refresh is already running for these dates. Read its saved status.")
    check_source(
        db, app_id, body["manifest_version"], body["connection_id"], body["connection_version"], readiness_store=store
    )
    data = _job_data(scope, {"operation": "analytics_reports"}, refresh_id)
    job = enqueue_db(db, store, app_id, "sync", data, "apple-performance-refresh:" + digest([app_id, refresh_id]))
    db.execute(
        "INSERT INTO apple_performance_refreshes(app_id,id,event_start,event_end,scope,scope_sha256,inventory_job_id,created) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (app_id, refresh_id, start.isoformat(), end.isoformat(), canonical(scope), digest(scope), job["id"], now()),
    )
    return expected.store_app_id, _record(db, app_id, refresh_id)


def refresh(service: Any, app_id: str, action: str, body: dict[str, Any]) -> dict:
    """Admit an exact refresh or project its durable progress for the requested dates."""
    from .apple_metrics_http import campaign_dates, check_source

    start, end = campaign_dates(body, "Choose up to 31 Apple event dates")
    starting = action in {"performance-refresh", "campaign-refresh"}
    with connection(service.store.path) as db:
        db.execute("BEGIN IMMEDIATE" if starting else "BEGIN")
        if starting:
            store_id, row = _admit(db, service.store, app_id, action, body, start, end)
        else:
            owner, _ = _owner(db, app_id, action)
            store_id = check_source(db, app_id, body["manifest_version"]).store_app_id
            row = _latest(db, app_id, owner, start, end)
        return _view(db, app_id, store_id, start, end, row)


def guard_job(db: Connection, job: dict[str, Any]) -> Row:
    """Check persisted admission, exact job membership and current authority."""
    refresh_id = job["data"].get("apple_performance_refresh_id")
    row = _record(db, job["app_id"], identity(refresh_id))
    if row is None or job["action"] != "sync":
        raise Invalid("Apple refresh job has no verified owner admission")
    scope = _verified_scope(db, row)
    if row["inventory_job_id"] == job["id"]:
        options = {"operation": "analytics_reports"}
    else:
        file = next((entry for entry in _files(row) if entry["job_id"] == job["id"]), None)
        if file is None or row["handoff_status"] != "COLLECTING":
            raise Invalid("Apple refresh file job has no verified inventory handoff")
        options = file["options"]
    if _job_data(scope, options, refresh_id) != job["data"]:
        raise Invalid("Apple refresh job changed after owner admission")
    return row


def guard_worker(store: "Store", job: dict[str, Any]) -> None:
    """Guard the provider read on both sides of the network boundary."""
    if "apple_performance_refresh_id" not in job["data"]:
        return
    with connection(store.path) as db:
        db.execute("BEGIN")
        guard_job(db, job)


def _plan(db: Connection, store: "Store", row: Row, scope: dict[str, Any]) -> tuple[str, list[dict]]:
    from .apple_metrics_http import (
        AnalyticsSource,
        _bounded_performance_files,
        _file_options,
        _queue_apple_file,
        inventory,
        source,
    )

    app_id = row["app_id"]
    version, store_id, record = source(db, app_id)
    observed, reports = inventory(db, app_id, version, store_id, record, job_id=row["inventory_job_id"])
    if observed is None:
        return "FAILED", []
    if observed["coverage"] != "COMPLETE":
        return "REQUEST_INVENTORY_PARTIAL", []
    if observed["status"] != "METRIC_DOWNLOAD_REQUIRED":
        return observed["status"], []
    date_start, date_end = (date.fromisoformat(row[field]) for field in ("event_start", "event_end"))
    campaign = "campaign_report_id" in scope
    try:
        candidates = _bounded_performance_files(
            reports, date_start, date_end, completeness={CAMPAIGN_DOWNLOADS: 2} if campaign else None
        )
    except Invalid:
        return "REQUEST_INVENTORY_PARTIAL", []
    if not candidates:
        return "NO_FILES_FOR_DATES", []
    expected = AnalyticsSource(
        version,
        store_id,
        scope["connection_id"],
        scope["connection_version"],
        scope["connection_hash"],
        observed["job_id"],
        None,
    )
    files = []
    for report, file in candidates:
        window = (date_start, date_end)
        selected = _queue_apple_file(
            store,
            db,
            app_id,
            expected,
            file,
            report,
            "apple-campaign-file" if campaign else "apple-performance-file",
            refresh_id=row["id"],
            window=window,
        )
        options = _file_options(report, file, window)
        files.append(
            dict(
                job_id=selected["job_id"],
                processing_date=file["processing_date"],
                report_family=report["name"],
                options=options,
            )
        )
    return "COLLECTING", files


def complete_inventory(db: Connection, store: "Store", job: dict[str, Any]) -> None:
    """Publish the inventory and enqueue its bounded follow-on reads in one transaction."""
    row = guard_job(db, job)
    scope = _verified_scope(db, row)
    status, files = _plan(db, store, row, scope)
    db.execute(
        "UPDATE apple_performance_refreshes SET handoff_status=?,files=?,files_sha256=? WHERE app_id=? AND id=?",
        (status, canonical(files), digest(files), row["app_id"], row["id"]),
    )
