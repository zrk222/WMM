"""Derive campaign-grain acquisition cost from the same Apple Ads provider report."""

import re
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, localcontext
from typing import TypedDict

from .common import Invalid, digest, iso_time
from .currency_units import minor_units

AMOUNT = re.compile(r"[0-9]{1,30}(?:\.[0-9]{1,30})?")


class CampaignCost(TypedDict):
    campaign_id: str
    status: str
    billing_currency: str | None
    spend_minor_exact: str | None
    first_time_downloads: int | None
    cost_per_new_download_minor: str | None


def spend_minor(money: object) -> tuple[str | None, Decimal | None]:
    if not isinstance(money, dict):
        return None, None
    unit, amount = money.get("currency"), money.get("amount")
    if not isinstance(unit, str) or type(amount) not in (str, int) or not AMOUNT.fullmatch(str(amount)):
        return None, None
    try:
        digits = minor_units(unit)
    except Invalid:
        return None, None
    with localcontext() as ctx:
        ctx.prec = 96
        return unit, Decimal(str(amount)).scaleb(digits)


def download_count(count: object) -> int | None:
    if isinstance(count, str) and re.fullmatch(r"[0-9]{1,30}", count):
        return int(count)
    if type(count) is int and 0 <= count < 10**30:
        return count
    return None


def cost_state(spend: Decimal | None, downloads: int | None) -> str:
    if spend is None:
        return "MISSING_SPEND"
    if downloads is None:
        return "MISSING_FIRST_DOWNLOADS"
    if not spend:
        return "NO_REPORTED_SPEND"
    if not downloads:
        return "NO_FIRST_DOWNLOADS"
    return "AVAILABLE"


def row_cost(campaign: str, metrics: dict[str, object] | None, report_state: str) -> CampaignCost:
    unit, spend = spend_minor(metrics.get("localSpend")) if metrics is not None else (None, None)
    downloads = download_count(metrics.get("totalNewDownloads")) if metrics is not None else None
    status = report_state or ("NO_CAMPAIGN_ROW" if metrics is None else cost_state(spend, downloads))
    cost = None
    if status == "AVAILABLE" and spend is not None and downloads:
        with localcontext() as ctx:
            ctx.prec = 96
            cost = format((spend / downloads).quantize(Decimal("0.0001")), "f")
    return {
        "campaign_id": campaign,
        "status": status,
        "billing_currency": unit,
        "spend_minor_exact": format(spend, "f") if spend is not None else None,
        "first_time_downloads": downloads,
        "cost_per_new_download_minor": cost,
    }


def campaign_costs(
    report: dict,
    app_id: str,
    store_app_id: str,
    account_id: str,
    options: dict,
    observed_at: str,
    source_hash: str,
) -> dict[str, object]:
    """Bind each calculation to the successful read, exact account, app and UTC window."""
    start = datetime.combine(date.fromisoformat(options["start"]), time.min, timezone.utc)
    end = datetime.combine(date.fromisoformat(options["end"]) + timedelta(days=1), time.min, timezone.utc)
    indexed = {}
    for row in report["rows"]:
        identity = str(row["metadata"]["id"])
        if identity in indexed:
            raise Invalid("Campaign report repeats an entity; no metrics were combined")
        indexed[identity] = row["totalMetrics"]
    status = ""
    if report["coverage"] != "COMPLETE":
        status = "INCOMPLETE_REPORT"
    elif iso_time(observed_at) < end:
        status = "OPEN_REPORT_WINDOW"
    receipt = {
        "schema": "wmm.apple-ads.campaign-acquisition.v1",
        "provider": "apple_ads",
        "app_id": app_id,
        "store_app_id": store_app_id,
        "ad_account_id": account_id,
        "starts_at": start.isoformat(),
        "ends_at_exclusive": end.isoformat(),
        "reporting_timezone": "UTC",
        "observed_at": observed_at,
        "provider_source_sha256": source_hash,
        "coverage": report["coverage"],
        "counts_basis": "APPLE_ADS_REPORTED_NEW_DOWNLOADS",
        "revenue_source_joined": False,
        "rows": [row_cost(identity, indexed.get(identity), status) for identity in options["campaign_ids"]],
    }
    return {**receipt, "receipt_sha256": digest(receipt)}
