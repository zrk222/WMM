"""Owner-only outcome coverage for the selected Apple event dates."""

import json
from datetime import date, datetime, time, timedelta, timezone
from functools import partial
from sqlite3 import Connection
from typing import Any

from .apple_commerce_outcomes import commerce_outcomes, outcome_row
from .common import Invalid, digest, iso_time
from .ledger import eligible_events
from .ledger import report as ledger_report
from .operation_authority import PROTECTED, check


def _downloads(result: dict) -> dict:
    observed = [
        day
        for day in result["rows"]
        if day["downloads"]["status"] == "APPLE_REPORTED"
        and day["downloads"]["source_sha256"]
        and all(day["downloads"]["counts"].get(field) is not None for field in ("first_time_downloads", "redownloads"))
    ]
    scope = "App Downloads Standard · first-time downloads plus redownloads · selected event dates."
    if len(observed) != len(result["rows"]) or not observed:
        return outcome_row(
            "Total downloads",
            None,
            scope,
            "Collect the App Downloads Standard files for these dates. Each day needs mature counts for both download types.",
        )
    total = sum(
        int(day["downloads"]["counts"][field]) for day in observed for field in ("first_time_downloads", "redownloads")
    )
    evidence = [dict(date=day["date"], **day["downloads"]) for day in observed]
    return outcome_row("Total downloads", str(total), scope, None, digest(evidence))


def _owner(db: Connection, app_id: str) -> str | None:
    context = PROTECTED.get()
    if context is None or "grant_id" in context:
        return None
    envelope = json.loads(str(context["envelope"]))
    if envelope["app_id"] != app_id or envelope["operation"] not in {
        "apple.analytics.owner.performance",
        "apple.analytics.owner.search-review",
    }:
        return None
    return check(db, context)


def _campaigns(db: Connection, app_id: str, owner: str, starts: datetime, ends: datetime) -> list[dict]:
    from .apple_owner_outcome import apple_owner_outcome
    from .apple_performance_refresh import campaign_refresh_selection
    from .campaign_report_delivery import matched_post

    if (
        db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='campaign_owner_reports'").fetchone()
        is None
    ):
        return []
    rows = db.execute(
        "SELECT id FROM campaign_owner_reports WHERE app_id=? AND owner=? "
        "AND json_type(data,'$.apple_downloads')='object' "
        "AND julianday(json_extract(data,'$.selection.measurement_window.starts_at'))=julianday(?) "
        "AND julianday(json_extract(data,'$.selection.measurement_window.ends_at'))=julianday(?) ORDER BY created DESC,rowid DESC",
        (app_id, owner, starts.isoformat(), ends.isoformat()),
    )
    seen = set()
    result = []
    for row in rows:
        try:
            saved, approved, plan, chosen = campaign_refresh_selection(
                db, app_id, owner, row["id"], starts.date(), (ends - timedelta(days=1)).date()
            )
        except (Invalid, PermissionError):
            continue
        key = (chosen["scope_id"], chosen["apple_storefront"])
        if key in seen:
            continue
        seen.add(key)
        live = apple_owner_outcome(
            db, app_id, plan, chosen, partial(matched_post, db, app_id, chosen["scope_id"], approved)
        )
        count = live["first_time_downloads"] if live["status"] == "REPORTED" else None
        value = outcome_row(
            "Campaign-attributed first-time downloads",
            str(count) if count is not None else None,
            f"Campaign {key[0]} · {key[1]} storefront · selection saved {saved['created']} · current local Apple rows.",
            None if count is not None else live["next_action"],
            digest(dict(selection_sha256=saved["hash"], evidence=live)),
        )
        result.append(dict(value, campaign_report_id=saved["id"]))
    return result


def _cohort_rows(cohort: dict, events: list[dict], cutoff: datetime) -> list[dict]:
    result = ledger_report(cohort, events, cutoff)
    scope = f"Owner-supplied iOS cohort {cohort['cohort_id']} · {cohort['locale']} · {cohort['release']} · through {cutoff.isoformat()}."
    economics = cohort.get("economics", {})
    coverage = economics.get("coverage_through")
    complete = (
        result["observability"] == "OBSERVED"
        and result["mature"]
        and result["events"]
        and not result["issues"]
        and coverage
        and iso_time(coverage) >= cutoff
    )
    observed = [row for row in events if iso_time(row["occurred_at"]) <= cutoff]
    _, eligible = eligible_events(observed, iso_time(cohort["starts_at"]), iso_time(cohort["ends_at"]))
    charges = [row for row in observed if row["type"] in ("PURCHASE", "RENEWAL")]
    eligible_ids = {(row["provider"], row["event_id"]) for row in eligible}
    supported = (
        charges
        and all((row["provider"], row["event_id"]) in eligible_ids for row in charges)
        and complete
        and economics.get("revenue_basis") == "NET_PROCEEDS"
        and economics.get("currency") == cohort["currency"]
    )
    amount = result["net_proceeds_minor"] if supported else None
    rows = [
        outcome_row(
            "Imported cohort net proceeds",
            f"{amount} {cohort['currency']} minor units" if amount is not None else None,
            scope,
            None
            if amount is not None
            else "In the event cohort, import reconciled purchases and refunds, declare net proceeds and currency, and confirm coverage through maturity.",
            result["source_hash"],
        )
    ]
    for group in result["subscription_journey"]["groups"]:
        binding = group["binding"]
        paid = group["counts"]["PURCHASE"] if complete else None
        rows.append(
            outcome_row(
                "Imported subscription purchasers",
                str(paid) if paid is not None else None,
                scope
                + f" Product {binding['product_id']} · offer {binding['offer_id']} · {binding['storefront']} · variant {binding['variant_id']}. Distinct purchasers for this binding.",
                None
                if paid is not None
                else "Import subscription-bound first purchases and eligible installs, then confirm complete coverage.",
                result["source_hash"],
            )
        )
    return rows


def _cohorts(db: Connection, app_id: str, starts: datetime, ends: datetime) -> list[dict]:
    rows = []
    for record in db.execute("SELECT id,data,hash FROM growth_cohorts WHERE app_id=? ORDER BY id", (app_id,)):
        cohort = json.loads(record["data"])
        if digest(cohort) != record["hash"] or cohort["cohort_id"] != record["id"]:
            raise Invalid("Cohort definition failed its integrity check")
        if cohort["platform"].casefold() != "ios" or (iso_time(cohort["starts_at"]), iso_time(cohort["ends_at"])) != (
            starts,
            ends,
        ):
            continue
        events = []
        for row in db.execute(
            "SELECT provider,external_id,data,hash FROM growth_events WHERE app_id=? AND cohort_id=? ORDER BY provider,external_id",
            (app_id, record["id"]),
        ):
            data = json.loads(row["data"])
            if (data["provider"], data["event_id"]) != (row["provider"], row["external_id"]) or digest(
                {"cohort_id": record["id"], "event": data}
            ) != row["hash"]:
                raise Invalid("Imported cohort event failed its integrity check")
            events.append(data)
        # A cohort may mature after the acquisition window. Label that horizon explicitly.
        rows.extend(_cohort_rows(cohort, events, min(datetime.now(timezone.utc), iso_time(cohort["matures_at"]))))
    return rows


def outcome_coverage(
    db: Connection, result: dict[str, Any], *, expected: Any = None, reports: list[dict] | None = None
) -> dict:
    app_id = result["app_id"]
    owner = _owner(db, app_id)
    starts = datetime.combine(date.fromisoformat(result["start"]), time.min, timezone.utc)
    ends = datetime.combine(date.fromisoformat(result["end"]) + timedelta(days=1), time.min, timezone.utc)
    campaigns = _campaigns(db, app_id, owner, starts, ends) if owner else []
    return dict(
        metrics=[
            _downloads(result),
            outcome_row(
                "App Store conversion rate",
                None,
                "Apple’s download and pre-order conversion metric uses unique-device impressions and counts a pre-order once.",
                "In App Store Connect Analytics, open Acquisition, select Conversion Rate, and match this app, dates and filters. WMM’s standard rows do not contain the deduplicated denominator.",
            ),
            *(
                campaigns
                or [
                    outcome_row(
                        "Campaign-attributed first-time downloads",
                        None,
                        "Exact Apple campaign link, storefront and event dates.",
                        "Open Apple campaign results. Select the saved campaign link and storefront, collect App Downloads Detailed for these dates, and capture the matching campaign owner report after verifying delivery.",
                    )
                ]
            ),
            *commerce_outcomes(db, result, expected, reports),
        ],
        cohorts=_cohorts(db, app_id, starts, ends) if owner else [],
    )
