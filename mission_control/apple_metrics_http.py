"""Fresh-owner Apple analytics inventory and schedule controls for one app."""

import json
import re
import secrets
from datetime import date, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

from .aeo_transport import public_url
from .apple_analytics import CAMPAIGN_DOWNLOADS, DISCOVERY, DOWNLOADS, REPORTS, identity
from .apple_campaign_links import campaign_parts
from .apple_metrics_schedule import AppleMetricsSchedules, public_row
from .apple_metrics_store import read_in_snapshot
from .common import Invalid, digest, identifier, uid
from .connection_setup import Connections
from .db import connection
from .discovery_http import json_body
from .managed_media_http import singleton
from .operation_authority import bound_owner, protected

FIELDS = {
    "view": set(),
    "inventory": {"manifest_version", "connection_id", "connection_version"},
    "impressions": {"manifest_version", "report_id"},
    "campaign-collect": {"manifest_version", "report_id", "link", "instance_id"},
    "campaign-results": {"manifest_version", "report_id", "link", "territory", "start", "end"},
}
INVENTORY_STATES = {
    "REPORT_SETUP_REQUIRED",
    "REQUEST_INVENTORY_PARTIAL",
    "METRIC_DOWNLOAD_REQUIRED",
    "WAITING_FOR_REPORTS",
}


def source(db, app_id):
    """Resolve a unique integrity-checked source without reading any credential."""
    app = db.execute("SELECT data,version FROM apps WHERE id=?", (app_id,)).fetchone()
    if app is None:
        raise Invalid("App workspace is unavailable")
    data = json.loads(app["data"])
    store_id = data.get("store_app_id")
    if not isinstance(store_id, str) or not store_id.isascii() or not store_id.isdigit() or len(store_id) > 30:
        return app["version"], None, None
    matches = []
    for row in db.execute(
        "SELECT id,version,data,hash,source FROM records WHERE app_id=? AND kind=?", (app_id, "connection")
    ):
        binding = json.loads(row["data"])
        if (
            binding.get("provider") == "app_store"
            and binding.get("store_app_id") == store_id
            and binding.get("auth_mode") != "disconnected"
        ):
            if identity(row["id"]) != row["id"]:
                raise Invalid("Invalid Apple connection identity")
            if digest({"kind": "connection", "data": binding, "source": row["source"]}) != row["hash"]:
                raise Invalid("Apple connection integrity check failed")
            matches.append(row)
    if len(matches) > 1:
        raise Invalid("Connect exactly one Apple account for this app")
    return app["version"], store_id, matches[0] if matches else None


def inventory(db, app_id, version, store_id, record):
    """Project the newest successful inventory proven bound to this source and app version."""
    if record is None:
        return None, []
    rows = db.execute(
        "SELECT id,data,result FROM jobs WHERE app_id=? AND action='sync' "
        "AND status='SUCCEEDED' ORDER BY updated DESC,id DESC LIMIT 1000",
        (app_id,),
    )
    for row in rows:
        try:
            data = json.loads(row["data"])
            if (
                data.get("connection_id") != record["id"]
                or data.get("connection_version") != record["version"]
                or data.get("manifest_version") != version
                or data.get("connection_hash") != record["hash"]
                or data.get("options") != {"operation": "analytics_reports"}
            ):
                continue
            result = json.loads(row["result"])
            if (
                result.get("operation") != "analytics_reports"
                or result.get("provider") != "app_store"
                or result.get("app_id") != app_id
                or result.get("store_app_id") != store_id
                or result.get("status") not in INVENTORY_STATES
                or result.get("coverage") not in ("COMPLETE", "PARTIAL")
            ):
                return None, []
            timestamp = result.get("observed_at")
            if (
                not isinstance(timestamp, str)
                or len(timestamp) > 40
                or datetime.fromisoformat(timestamp).tzinfo is None
            ):
                return None, []
            reports = result.get("reports")
            if not isinstance(reports, list) or len(reports) > len(REPORTS):
                return None, []
            projected, ids, names = [], set(), set()
            for report in reports:
                if not isinstance(report, dict) or report.get("name") not in REPORTS:
                    return None, []
                report_id = identity(report.get("id"))
                instances = report.get("instances")
                if (
                    report_id in ids
                    or report["name"] in names
                    or not isinstance(instances, list)
                    or len(instances) > 300
                    or report.get("coverage") not in ("COMPLETE", "PARTIAL")
                ):
                    return None, []
                ids.add(report_id)
                names.add(report["name"])
                item: dict[str, Any] = dict(
                    id=report_id, name=report["name"], instance_count=len(instances), coverage=report["coverage"]
                )
                if report["name"] == CAMPAIGN_DOWNLOADS:
                    item["daily"] = [
                        dict(id=identity(i["id"]), processing_date=date.fromisoformat(i["processing_date"]).isoformat())
                        for i in instances
                        if i.get("granularity") == "DAILY"
                    ]
                    if len({i["id"] for i in item["daily"]}) != len(item["daily"]):
                        return None, []
                projected.append(item)
            return dict(job_id=identity(row["id"]), status=result["status"], observed_at=timestamp), projected
        except (ValueError, TypeError, AttributeError, KeyError):
            return None, []
    return None, []


def connection_status(store, app_id, record):
    """Expose only whether this host can access the saved local credential."""
    status = Connections(store).credential_status(app_id, record["id"], json.loads(record["data"]))
    if status in ("PROTECTED_KEY_PRESENT", "ENVIRONMENT_REFERENCE"):
        return "CONFIGURED_UNVERIFIED"
    if status == "RECONNECT_REQUIRED":
        return status
    return "PROTECTED_STORAGE_UNAVAILABLE"


def require_connection_ready(store, app_id, record):
    if record is None:
        raise Invalid("Set up App Store Connect before starting an analytics read")
    status = connection_status(store, app_id, record)
    if status == "RECONNECT_REQUIRED":
        raise Invalid("Reconnect App Store Connect before starting an analytics read")
    if status == "PROTECTED_STORAGE_UNAVAILABLE":
        raise Invalid("Unlock protected storage on this host for App Store Connect, then refresh")


def check_source(
    db,
    app_id,
    manifest_version,
    connection_id=None,
    connection_version=None,
    report_id=None,
    report_family=DOWNLOADS,
    *,
    readiness_store=None,
):
    """Revalidate all inputs inside the scheduler or queue write transaction."""
    version, store_id, record = source(db, app_id)
    if type(manifest_version) is not int or version != manifest_version:
        raise Invalid("App changed; reload Apple analytics")
    if connection_id is not None and (
        record is None
        or record["id"] != connection_id
        or type(connection_version) is not int
        or record["version"] != connection_version
    ):
        raise Invalid("Apple connection changed; reload Apple analytics")
    if readiness_store is not None:
        require_connection_ready(readiness_store, app_id, record)
    inventory_id = None
    if report_id is not None:
        current, reports = inventory(db, app_id, version, store_id, record)
        if current is None or not any(
            r["id"] == report_id
            and r["name"] == report_family
            and (report_family == DOWNLOADS or r["coverage"] == "COMPLETE")
            for r in reports
        ):
            raise Invalid("Select the current Apple report from this app inventory")
        inventory_id = current["job_id"]
    return (
        version,
        store_id,
        record["id"] if record else None,
        record["version"] if record else None,
        record["hash"] if record else None,
        inventory_id,
    )


def view(store, app_id):
    with connection(store.path) as db:
        db.execute("BEGIN")
        version, store_id, record = source(db, app_id)
        current, reports = inventory(db, app_id, version, store_id, record)
        row = db.execute("SELECT * FROM apple_metrics_schedules WHERE app_id=?", (app_id,)).fetchone()
        schedule = public_row(db, row)
        if schedule is not None:
            schedule["last_error"] = None
        return dict(
            app_id=app_id,
            manifest_version=version,
            store_app_id=store_id,
            connection=dict(id=record["id"], version=record["version"], status=connection_status(store, app_id, record))
            if record
            else None,
            reports=reports,
            inventory=current,
            schedule=schedule,
        )


def apple_campaign_read(service: Any, app_id: str, action: str, body: dict[str, Any]) -> dict[str, Any]:
    """Queue only the selected app's Detailed instance, or read its retained dated rows."""
    report_id = identity(body["report_id"])
    if report_id != body["report_id"]:
        raise Invalid("Select the exact Apple campaign report identity")
    apple = campaign_parts(urlsplit(public_url(body["link"], allow_tracking=True)))
    collecting = action == "campaign-collect"

    def snapshot(db: Any, readiness: Any = None) -> tuple:
        current = check_source(
            db,
            app_id,
            body["manifest_version"],
            report_id=report_id,
            report_family=CAMPAIGN_DOWNLOADS,
            readiness_store=readiness,
        )
        if apple is None or apple[0] != current[1]:
            raise Invalid("Paste the Apple campaign link for this app's App Store listing")
        return current

    with connection(service.store.path) as db:
        db.execute("BEGIN")
        expected = snapshot(db, service.store if collecting else None)
        key = dict(
            app_id=app_id,
            store_app_id=expected[1],
            connection_id=expected[2],
            connection_version=expected[3],
            report_id=report_id,
            report_family=CAMPAIGN_DOWNLOADS,
            granularity="DAILY",
        )
        if not collecting:
            assert apple is not None
            return apple_campaign_results(db, key, apple[1], body)
        instance = identity(body["instance_id"])
        if instance != body["instance_id"]:
            raise Invalid("Select the exact Apple report instance")
        version, store_id, record = source(db, app_id)
        _, reports = inventory(db, app_id, version, store_id, record)
        if not any(r["id"] == report_id and any(i["id"] == instance for i in r.get("daily", [])) for r in reports):
            raise Invalid("Select an available daily Apple campaign report file")

    def check(db: Any) -> None:
        if snapshot(db) != expected:
            raise Invalid("Apple analytics source changed; reload before collecting")

    data = dict(
        manifest_version=expected[0],
        connection_id=expected[2],
        connection_version=expected[3],
        connection_hash=expected[4],
        options=dict(
            operation="analytics_metrics", report_id=report_id, report_family=CAMPAIGN_DOWNLOADS, instance_id=instance
        ),
    )
    job = service.queue(app_id, dict(action="sync", data=data, request_key=uid()), commit_check=check)
    return dict(job_id=job["id"], status=job["status"])


def apple_campaign_results(db: Any, key: dict, token: str, body: dict[str, Any]) -> dict[str, Any]:
    """Do not sum incomplete days into a campaign total or join to first opens."""
    territory = body["territory"]
    try:
        start, end = (date.fromisoformat(body[name]) for name in ("start", "end"))
    except (TypeError, ValueError):
        raise Invalid("Use start and end dates for the Apple campaign") from None
    if (
        not isinstance(territory, str)
        or not re.fullmatch("[A-Z]{2}", territory)
        or not 0 <= (end - start).days < 31
        or body["start"] != start.isoformat()
        or body["end"] != end.isoformat()
    ):
        raise Invalid("Choose a storefront and up to 31 calendar days")
    token_hash = digest(token)
    observations = []
    for offset in range((end - start).days + 1):
        day = (start + timedelta(days=offset)).isoformat()
        saved = read_in_snapshot(db, dict(key, event_date=day))
        matches = (
            [
                row["count"]
                for row in saved["instance"]["rows"]
                if row["type"] == "first_download"
                and row["dimensions"].get("campaign_sha256") == token_hash
                and row["dimensions"].get("territory") == territory
            ]
            if saved
            else []
        )
        observations.append(
            dict(
                date=day,
                first_time_downloads=sum(matches) if matches else None,
                source_sha256=digest(saved["instance"]["sources"]) if saved else None,
            )
        )
    return dict(
        app_id=key["app_id"],
        territory=territory,
        campaign_sha256=token_hash,
        rows=observations,
        status="APPLE_REPORTED_ROWS"
        if any(row["first_time_downloads"] is not None for row in observations)
        else "UNAVAILABLE_OR_SUPPRESSED",
        next_action="Collect the Detailed files for missing dates or extend the window if Apple suppresses low-volume rows.",
        external_writes=False,
    )


def dispatch(service, app_id, action, body):
    if not isinstance(body, dict):
        raise Invalid("Use the exact Apple analytics fields")
    if action in FIELDS and set(body) != FIELDS[action]:
        raise Invalid("Use the exact Apple analytics fields")
    if action in {"campaign-collect", "campaign-results"}:
        return apple_campaign_read(service, app_id, action, body)
    if action == "view":
        return view(service.store, app_id)
    if action == "inventory":
        if not isinstance(body["connection_id"], str):
            raise Invalid("Select this app Apple connection")
        with connection(service.store.path) as db:
            expected = check_source(
                db,
                app_id,
                body["manifest_version"],
                body["connection_id"],
                body["connection_version"],
                readiness_store=service.store,
            )

        def check(db):
            actual = check_source(
                db, app_id, body["manifest_version"], body["connection_id"], body["connection_version"]
            )
            if actual != expected:
                raise Invalid("Apple connection changed; reload Apple analytics")

        data = dict(
            manifest_version=body["manifest_version"],
            connection_id=body["connection_id"],
            connection_version=body["connection_version"],
            connection_hash=expected[4],
            options={"operation": "analytics_reports"},
        )
        job = service.queue(app_id, dict(action="sync", data=data, request_key=uid()), commit_check=check)
        return dict(job_id=job["id"], status=job["status"])
    if action == "impressions":
        report_id = identity(body["report_id"])
        if report_id != body["report_id"]:
            raise Invalid("Select the exact Apple analytics report identity")

        def impression_source(db, readiness_store=None):
            return check_source(
                db,
                app_id,
                body["manifest_version"],
                report_id=report_id,
                report_family=DISCOVERY,
                readiness_store=readiness_store,
            )

        with connection(service.store.path) as db:
            snapshot = impression_source(db, service.store)

        def check(db):
            if impression_source(db) != snapshot:
                raise Invalid("Apple analytics source changed; reload before collecting impressions")

        data = dict(
            manifest_version=snapshot[0],
            connection_id=snapshot[2],
            connection_version=snapshot[3],
            connection_hash=snapshot[4],
            options={"operation": "analytics_metrics_latest", "report_id": report_id, "report_family": DISCOVERY},
        )
        job = service.queue(app_id, dict(action="sync", data=data, request_key=uid()), commit_check=check)
        return dict(job_id=job["id"], status=job["status"])
    if action == "schedule":
        if type(body.get("enabled")) is not bool:
            raise Invalid("Choose whether Apple analytics refresh is enabled")
        expected = (
            {"manifest_version", "enabled", "interval_hours", "report_id", "version"}
            if body["enabled"]
            else {"manifest_version", "enabled", "version"}
        )
        if set(body) != expected:
            raise Invalid("Use the exact Apple analytics schedule fields")
        report_id = identity(body["report_id"]) if body["enabled"] else None
        if report_id is not None and report_id != body["report_id"]:
            raise Invalid("Select the exact Apple analytics report identity")
        with connection(service.store.path) as db:
            snapshot = check_source(
                db,
                app_id,
                body["manifest_version"],
                report_id=report_id,
                readiness_store=service.store if body["enabled"] else None,
            )

        def check(db):
            if check_source(db, app_id, body["manifest_version"], report_id=report_id) != snapshot:
                raise Invalid("Apple analytics source changed; reload before saving")

        value = AppleMetricsSchedules(service.store).save(
            app_id, {key: value for key, value in body.items() if key != "manifest_version"}, commit_check=check
        )
        if value is not None:
            value["last_error"] = None
        return value
    raise Invalid("Unknown Apple analytics operation")


def post(handler, parts):
    if (
        len(parts) != 5
        or parts[:2] != ["api", "apps"]
        or parts[3] != "apple-analytics"
        or parts[4] not in {"view", "inventory", "impressions", "schedule", "campaign-collect", "campaign-results"}
    ):
        raise Invalid("Use the exact Apple analytics address")
    identifier(parts[2])
    if handler.command != "POST" or handler.path != "/" + "/".join(parts):
        raise Invalid("Use an exact Apple analytics POST without query")
    origin = "http://127.0.0.1:" + str(handler.server.server_port)
    if handler.headers.get_all("Host") != [origin[7:]] or handler.headers.get_all("Origin") != [origin]:
        raise PermissionError("Use the exact local Apple analytics origin")
    session = handler.session()
    if not secrets.compare_digest(singleton(handler, "X-CSRF-Token"), session):
        raise PermissionError("Reload the current Apple analytics session")
    user = handler.server.identities.fresh(session)
    service = handler.server.service
    envelope = dict(app_id=parts[2], operation="apple.analytics.owner." + parts[4], input={})
    with (
        bound_owner(service.store, envelope, handler.server.identities, session, user),
        protected(service.store, envelope),
    ):
        return handler.send(200, dispatch(service, parts[2], parts[4], json_body(handler, "Apple analytics")))
