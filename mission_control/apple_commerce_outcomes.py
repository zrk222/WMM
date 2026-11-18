"""Read verified Apple commerce partitions for their independent reporting windows."""

from datetime import date
from decimal import Decimal, localcontext
from sqlite3 import Connection
from typing import Any

from .apple_analytics import PURCHASES, SUBSCRIPTION_STATE
from .apple_metrics_store import read_in_snapshot
from .apple_performance_report import COMPLETENESS_DAYS
from .common import digest


def _snapshot(db: Connection, key: dict, reports: list[dict], day: str, family: str) -> dict | None:
    matches = [r for r in reports if r["name"] == family and r["coverage"] == "COMPLETE"]
    if len(matches) != 1:
        return None
    return read_in_snapshot(db, dict(key, report_id=matches[0]["id"], report_family=family, event_date=day))


def outcome_row(label: str, value: str | None, scope: str, repair: str | None, receipt: str | None = None) -> dict:
    return dict(label=label, value=value, scope=scope, repair=repair, source_sha256=receipt)


def _evidence(saved: dict) -> dict:
    instance = saved["instance"]
    return dict(
        partition=saved["partition"],
        processing_date=instance["processing_date"],
        source_sha256=digest(sorted(instance["sources"], key=lambda entry: entry["id"])),
    )


def _mature(saved: dict, family: str) -> bool:
    processing = date.fromisoformat(saved["instance"]["processing_date"])
    event = date.fromisoformat(saved["partition"]["event_date"])
    return (processing - event).days >= COMPLETENESS_DAYS[family]


def _proceeds(db: Connection, key: dict, reports: list[dict], days: list[str]) -> list[dict]:
    observations = []
    receipts = []
    mature = 0
    # The validated parser bounds source precision. This also leaves room for all rows and up to 31 days.
    with localcontext() as context:
        context.prec = 256
        total = Decimal(0)
        for day in days:
            saved = _snapshot(db, key, reports, day, PURCHASES)
            if saved is None:
                continue
            rows = saved["instance"]["rows"]
            if not rows or any(r["type"] != "purchase" or r.get("proceeds_usd") is None for r in rows):
                continue
            amount = sum((Decimal(r["proceeds_usd"]) for r in rows), Decimal(0))
            proof = _evidence(saved)
            receipts.append(proof)
            settled = _mature(saved, PURCHASES)
            if settled:
                mature += 1
                total += amount
            label = "Reported" if settled else "Provisional"
            observations.append(
                outcome_row(
                    f"Apple estimated proceeds · {day}",
                    f"{amount:f} USD",
                    f"{label} App Store Purchases Standard rows · processing date {proof['processing_date']}.",
                    None if settled else "Refresh after Apple’s two-day reporting lag.",
                    proof["source_sha256"],
                )
            )
    complete = bool(days) and mature == len(days)
    summary = outcome_row(
        "Apple estimated proceeds",
        f"{total:f} USD" if complete else None,
        f"App Store Purchases Standard · estimated USD proceeds including refunds · mature coverage {mature}/{len(days)} days.",
        None
        if complete
        else "Refresh App Store Purchases Standard for each event date. Check Analytics → Sales → Proceeds in USD for a matching range. Final settlement is available in Payments and Financial Reports.",
        digest(receipts) if receipts else None,
    )
    return [summary, *observations]


def _paid(db: Connection, key: dict, reports: list[dict], day: str) -> list[dict]:
    saved = _snapshot(db, key, reports, day, SUBSCRIPTION_STATE)
    scope = (
        f"App Store Subscription State Standard · {day} end-date snapshot · paid subscriptions, including paid offers."
    )
    repair = "Refresh the end-date subscription-state report. Check Active Paid Subscriptions in App Store Connect Sales and Trends for this app and date."
    if saved is None:
        return [outcome_row("Active paid subscriptions", None, scope, repair)]
    proof = _evidence(saved)
    rows = saved["instance"]["rows"]
    counts = [r["count"] for r in rows if r["type"] == "active_paid"]
    scope += f" Processing date {proof['processing_date']}."
    if any(r["type"] == "unknown" for r in rows):
        return [
            outcome_row(
                "Active paid subscriptions",
                None,
                scope,
                "Review the unrecognized state or state grouping before comparing paid subscriptions.",
                proof["source_sha256"],
            )
        ]
    if not counts:
        return [
            outcome_row(
                "Active paid subscriptions",
                None,
                scope,
                "Apple supplied no paid-state count in this snapshot. Confirm the end date in Sales and Trends.",
                proof["source_sha256"],
            )
        ]
    if not _mature(saved, SUBSCRIPTION_STATE):
        return [
            outcome_row(
                "Active paid subscriptions",
                None,
                scope,
                "Refresh after Apple’s three-day subscription-state reporting lag.",
                proof["source_sha256"],
            ),
            outcome_row(
                "Provisional paid subscription count",
                str(sum(counts)),
                scope,
                "Confirm the mature snapshot before acting.",
                proof["source_sha256"],
            ),
        ]
    return [outcome_row("Active paid subscriptions", str(sum(counts)), scope, None, proof["source_sha256"])]


def commerce_outcomes(
    db: Connection, result: dict[str, Any], expected: Any = None, reports: list[dict] | None = None
) -> list[dict]:
    from .apple_metrics_http import inventory, source

    app_id = result["app_id"]
    if reports is None or expected is None:
        version, store_id, record = source(db, app_id)
        _, reports = inventory(db, app_id, version, store_id, record)
        connection_id, connection_version = (record["id"], record["version"]) if record else (None, None)
    else:
        store_id = expected.store_app_id
        connection_id, connection_version = expected.connection_id, expected.connection_version
    key = dict(
        app_id=app_id,
        store_app_id=store_id,
        connection_id=connection_id,
        connection_version=connection_version,
        granularity="DAILY",
    )
    return [
        *_paid(db, key, reports or [], result["end"]),
        *_proceeds(db, key, reports or [], [d["date"] for d in result["rows"]]),
    ]
