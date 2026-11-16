"""Project saved Apple campaign rows into one private owner report."""

from collections.abc import Callable
from datetime import date, timedelta, timezone
from sqlite3 import Connection
from typing import Any
from urllib.parse import urlsplit

from .apple_analytics import CAMPAIGN_DOWNLOADS
from .apple_campaign_links import campaign_parts
from .apple_metrics_http import apple_campaign_results, inventory, source
from .common import digest, iso_time


def apple_window(plan: dict[str, Any], selected: dict[str, Any]) -> tuple[date, date] | None:
    """Return inclusive UTC day bounds only for the exact approved interval."""
    start, end = (iso_time(plan[key]).astimezone(timezone.utc) for key in ("starts_at", "ends_at"))
    if any(
        iso_time(selected[key]).astimezone(timezone.utc) != value
        for key, value in (("starts_at", start), ("ends_at", end))
    ):
        return None
    if any(value.hour or value.minute or value.second or value.microsecond for value in (start, end)):
        return None
    if not 1 <= (end.date() - start.date()).days <= 31:
        return None
    return start.date(), end.date() - timedelta(days=1)


def saved_downloads(
    db: Connection, app_id: str, store_id: str, token: str, territory: str, window: tuple[date, date]
) -> dict[str, Any] | None:
    """Use the same current app/source partition contract as Apple Analytics."""
    version, current_store, record = source(db, app_id)
    if current_store != store_id or record is None:
        return None
    current, reports = inventory(db, app_id, version, store_id, record)
    if current is None or current["coverage"] != "COMPLETE":
        return None
    report = next((r for r in reports if r["name"] == CAMPAIGN_DOWNLOADS and r["coverage"] == "COMPLETE"), None)
    if report is None:
        return None
    key = dict(
        app_id=app_id,
        store_app_id=store_id,
        connection_id=record["id"],
        connection_version=record["version"],
        report_id=report["id"],
        report_family=CAMPAIGN_DOWNLOADS,
        granularity="DAILY",
    )
    return apple_campaign_results(
        db, key, token, dict(territory=territory, start=window[0].isoformat(), end=window[1].isoformat())
    )


def apple_owner_outcome(
    db: Connection,
    app_id: str,
    plan: dict[str, Any],
    chosen: dict[str, Any],
    match_delivery: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    """Return dated coverage and a total only with one exact verified post."""
    territory = chosen.get("apple_storefront")
    result: dict[str, Any] = dict(territory=territory, first_time_downloads=None, rows=[], delivery=None)
    window = apple_window(plan, chosen["measurement_window"])
    if window is None:
        return dict(result, status="WINDOW_MISMATCH", next_action="Use the approved window of up to 31 whole UTC days.")
    if territory is None:
        return dict(
            result, status="STOREFRONT_REQUIRED", next_action="Choose the App Store storefront for these results."
        )
    linked = campaign_parts(urlsplit(plan["link"]))
    if linked is None:
        return dict(
            result, status="SOURCE_UNAVAILABLE", next_action="Check the approved Apple campaign link for this app."
        )
    evidence = saved_downloads(db, app_id, linked[0], linked[1], territory, window)
    if evidence is None:
        return dict(
            result, status="SOURCE_UNAVAILABLE", next_action="Read this app’s App Downloads Detailed inventory."
        )
    result["delivery"] = match_delivery(
        dict(
            report=dict(starts_at=plan["starts_at"], ends_at=plan["ends_at"], campaign=plan["campaign_tag"]),
            receipt_sha256=digest(evidence),
        )
    )
    if result["delivery"]["status"] != "EXACT_TAGGED_POST_READBACK":
        return dict(
            result,
            status="DELIVERY_UNVERIFIED",
            next_action="Verify one saved post for this exact link before interpreting downloads.",
        )
    result["rows"] = evidence["rows"]
    if any(row["evidence_status"] != "READY_TO_REVIEW" for row in evidence["rows"]):
        return dict(result, status="INCOMPLETE", next_action=evidence["next_action"])
    return dict(
        result,
        status="REPORTED",
        next_action=evidence["next_action"],
        first_time_downloads=sum(row["first_time_downloads"] for row in evidence["rows"]),
    )
