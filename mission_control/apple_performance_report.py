"""Project saved Apple standard report counts without opening provider credentials."""

from datetime import date, timedelta
from sqlite3 import Connection
from typing import Any

from .apple_analytics import DISCOVERY, DOWNLOADS
from .apple_metrics_store import read_in_snapshot
from .common import digest

METRICS = {
    DISCOVERY: {"impression": "impressions", "page_view": "page_views"},
    DOWNLOADS: {"first_download": "first_time_downloads", "redownload": "redownloads"},
}
COMPLETENESS_DAYS = {DISCOVERY: 3, DOWNLOADS: 2}


def _saved_day(db, key, day, family, report):
    counts: dict[str, int | None] = dict.fromkeys(METRICS[family].values())
    saved = (
        read_in_snapshot(db, dict(key, report_id=report["id"], report_family=family, event_date=day.isoformat()))
        if report
        else None
    )
    if saved is None:
        return dict(counts=counts, status="NO_FILE", processing_date=None, source_sha256=None)
    instance = saved["instance"]
    for row in instance["rows"]:
        metric = METRICS[family].get(row["type"])
        if metric is not None:
            counts[metric] = (counts[metric] or 0) + row["count"]
    processing = instance["processing_date"]
    provisional = (date.fromisoformat(processing) - day).days < COMPLETENESS_DAYS[family]
    return dict(
        counts={metric: str(count) if count is not None else None for metric, count in counts.items()},
        status="PROVISIONAL" if provisional else "APPLE_REPORTED",
        processing_date=processing,
        source_sha256=digest(sorted(instance["sources"], key=lambda source: source["id"])),
    )


def saved_performance(
    db: Connection, key: dict[str, Any], reports: list[dict[str, Any]], start: date, end: date
) -> list[dict[str, Any]]:
    """Read exactly the selected app and current report source over event dates."""
    by_family = {report["name"]: report for report in reports if report["coverage"] == "COMPLETE"}
    rows = []
    for offset in range((end - start).days + 1):
        day = start + timedelta(days=offset)
        rows.append(
            dict(
                date=day.isoformat(),
                discovery=_saved_day(db, key, day, DISCOVERY, by_family.get(DISCOVERY)),
                downloads=_saved_day(db, key, day, DOWNLOADS, by_family.get(DOWNLOADS)),
            )
        )
    return rows
