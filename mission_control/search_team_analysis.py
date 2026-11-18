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


def _brief(snapshot: dict, baselines: dict) -> dict:
    apple = baselines["apple-baseline"]["deliverable"]["details"]
    web = baselines["web-baseline"]["deliverable"]["details"]
    counts = {key: value["mature_observed_total"] for key, value in apple.items()}
    period = web["period"]
    page = web["page_url"]
    if web["counts"]["clicks"] > 0:
        hypothesis = "A clearer secondary iOS call to action on this page may increase first-time downloads among eligible visitors."
        control = "After verifying the current App Store link, compare its current label with one new label. Split eligible iOS visits equally and use a separate verified Apple campaign tag for each arm."
        metric = "Mature tagged first-time Apple downloads per eligible iOS visit in each arm and territory."
        guardrail = "Track existing web starts per eligible visit and preserve the web start path in both arms."
        stop = "Hold launch until both tags, visit denominators, web starts and sample floor are verified. Pause on broken links or missing tracking. Withhold a winner if Apple suppresses either arm or the approved guardrail is breached."
    else:
        hypothesis = "A title that answers the measured search intent may earn more qualified clicks for this page."
        control = "Collect the page's qualifying search queries, then compare one crawl-visible title change against the prior title and an unchanged comparable page."
        metric = "Google organic clicks per impression across the same queries, market and device."
        guardrail = (
            "Review impressions and web starts alongside click-through rate. Monitor app-wide downloads separately."
        )
        stop = "Hold launch until the target queries and control page are evidenced. Pause if the page loses indexability. Withhold a conclusion when coverage, control or exposure is insufficient."
    baseline = (
        f"Google recorded {web['counts']['clicks']} clicks and {web['counts']['impressions']} impressions for {page} "
        f"from {period['start']} through {period['end']}. Apple recorded {counts['impressions']} app-wide impressions "
        f"and {counts['first_time_downloads']} first-time downloads from {snapshot['start']} through {snapshot['end']}."
    )
    observation = "Propose two full weeks after verified launch. Freeze the audience, minimum sample and decision thresholds with the owner before starting. Wait for mature source rows before comparing."
    return dict(
        summary=f"{baseline} {hypothesis} {control} {metric} {guardrail} {observation} {stop}",
        details=dict(
            page_url=page,
            territory=web["territory"],
            device=period["device"],
            baseline=baseline,
            apple_app_wide_counts=counts,
            apple_window=[snapshot["start"], snapshot["end"]],
            google_counts=web["counts"],
            google_period=period,
            hypothesis=hypothesis,
            control=control,
            primary_metric=metric,
            guardrail=guardrail,
            observation_window=observation,
            stop_rules=stop,
            interpretation="The observed app-wide Apple totals cannot attribute downloads to this Google page.",
            baseline_receipts={name: result["receipt_sha256"] for name, result in baselines.items()},
        ),
    )


def produce(
    snapshot: dict[str, Any], task: dict[str, Any], prerequisites: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    action = task["action_id"]
    if action == "apple-baseline":
        return _apple(snapshot)
    if action == "web-baseline":
        return _web(snapshot["search_review"])
    if action == "test-brief":
        return "COMPLETED", _brief(snapshot, prerequisites)
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
