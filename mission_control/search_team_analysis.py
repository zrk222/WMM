"""Build evidence-backed deliverables from one current, owner-reviewed local snapshot."""

from typing import Any

from .common import Invalid


def _apple(snapshot: dict) -> tuple[str, dict]:
    rows = snapshot["rows"]
    metrics = {}
    for family, metric in (
        ("discovery", "impressions"),
        ("discovery", "page_views"),
        ("downloads", "first_time_downloads"),
        ("downloads", "redownloads"),
    ):
        observed = {}
        missing = []
        for row in rows:
            source = row[family]
            value = source["counts"][metric]
            if source["status"] == "APPLE_REPORTED" and value is not None and source["source_sha256"]:
                observed[row["date"]] = {"count": int(value), "source_sha256": source["source_sha256"]}
            else:
                missing.append(row["date"])
        metrics[metric] = dict(
            mature_observed_total=sum(r["count"] for r in observed.values()) if observed else None,
            observed=observed,
            missing_or_provisional_dates=missing,
        )
    complete = all(not metrics[k]["missing_or_provisional_dates"] for k in ("impressions", "first_time_downloads"))
    summary = (
        "Reviewed mature Apple discovery and first-time download counts for each selected date."
        if complete
        else "Apple baseline needs additional mature provider rows. See the missing dates by metric."
    )
    return ("COMPLETED" if complete else "NEEDS_EXTERNAL_VERIFICATION"), dict(summary=summary, details=metrics)


def _web(review: dict) -> tuple[str, dict]:
    reading = review.get("web_observation")
    if not reading or reading["coverage"] != "COMPLETE" or reading["status"] != "REVIEW_ACTION":
        return "NEEDS_EXTERNAL_VERIFICATION", dict(
            summary="Collect and save a complete Search Console reading for this page.",
            details={"available_reading": reading},
        )
    values = reading["values"]
    clicks, impressions = values["clicks"], values["impressions"]
    if clicks is None or impressions is None:
        return "NEEDS_EXTERNAL_VERIFICATION", dict(
            summary="The saved web reading lacks clicks or impressions.", details={"available_reading": reading}
        )
    rate = clicks / impressions if impressions else None
    summary = f"{reading['page_url']} received {clicks} organic clicks from {impressions} impressions."
    if rate is not None:
        summary += f" The observed click-through rate was {rate:.1%}."
    summary += " " + reading["next_action"]
    return "COMPLETED", dict(
        summary=summary,
        details=dict(
            page_url=reading["page_url"],
            territory=reading["territory"],
            period=reading["period"],
            counts=values,
            click_through_rate=rate,
            source_sha256=reading["sha256"],
            proposed_test=reading["next_action"],
        ),
    )


def produce(snapshot: dict[str, Any], task: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    action = task["action_id"]
    if action == "apple-baseline":
        return _apple(snapshot)
    if action == "web-baseline":
        return _web(snapshot["search_review"])
    if action == "store-link-check":
        reading = snapshot["search_review"]["web_observation"]
        return "NEEDS_EXTERNAL_VERIFICATION", dict(
            summary="The exact page's iOS link requires a verified destination readback.",
            details=dict(
                page_url=reading["page_url"],
                expected_apple_id=snapshot["store_app_id"],
                required_evidence="Record the rendered CTA, final App Store destination and campaign tag.",
            ),
        )
    if action == "measure-tag":
        return "NEEDS_EXTERNAL_VERIFICATION", dict(
            summary="Campaign link setup requires owner-approved market, dates and sample floor.",
            details=dict(task=task["action"]["task"]),
        )
    raise Invalid("This step has no tested execution adapter")
