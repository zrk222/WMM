"""Fingerprint the definitions behind a private report comparison."""

import json
import re
from collections.abc import Mapping
from itertools import pairwise
from sqlite3 import Connection

from .common import Invalid, digest


def object_data(raw: str) -> dict:
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        raise Invalid("Saved owner report source needs repair") from None
    if not isinstance(value, dict):
        raise Invalid("Saved owner report source needs repair")
    return value


def definitions(db: Connection, app_id: str, metrics: Mapping[str, list[dict[str, str]]]) -> str:
    """Compare metric identities and units, never just similarly named totals."""
    cohorts = [
        _cohort_definition(object_data(row["data"]))
        for row in db.execute("SELECT data FROM growth_cohorts WHERE app_id=? ORDER BY id", (app_id,))
    ]
    records = []
    for row in db.execute(
        "SELECT data,kind FROM records WHERE app_id=? AND kind IN ('cohort','retention','acquisition') ORDER BY id",
        (app_id,),
    ):
        value = object_data(row["data"])
        records.append(
            dict(
                kind=row["kind"],
                scope={
                    k: value.get(k)
                    for k in (
                        "cohort_id",
                        "currency",
                        "horizon",
                        "window",
                        "release",
                        "platform",
                        "locale",
                        "starts_at",
                        "ends_at",
                        "matures_at",
                    )
                },
            )
        )
    sources = [
        dict(row)
        for row in db.execute(
            "SELECT id,provider,version,hash FROM insight_sources WHERE app_id=? ORDER BY id",
            (app_id,),
        )
    ]
    return digest(
        dict(
            projection_schema="ios_reports.v1",
            metric_names=[r["metric"] for r in metrics["rows"]],
            metric_units_and_dimensions=[
                re.findall(
                    r"(?:currency|horizon|period|unit|type|source_type|dimensions|subscription binding)=([^;]+)",
                    r["evidence"],
                )
                for r in metrics["rows"]
            ],
            cohorts=cohorts,
            record_scopes=records,
            sources=sources,
        )
    )


def _cohort_definition(value: dict[str, object]) -> dict[str, object]:
    fields = (
        "cohort_id",
        "release",
        "platform",
        "locale",
        "currency",
        "starts_at",
        "ends_at",
        "matures_at",
        "attribution_method",
        "observability",
        "source",
        "subscription_map",
    )
    return {key: value.get(key) for key in fields}


def joined_outcome_advice(delivery: object, report: object) -> dict[str, object]:
    """One test or repair based on an exact delivery and a compatible retained outcome join."""
    evidence = {"inputs": ["Facebook delivery readback", "PostHog product events", "RevenueCat billing events"]}
    if not isinstance(delivery, dict) or delivery.get("status") != "EXACT_TAGGED_POST_READBACK":
        return dict(
            evidence,
            status="REPAIR_DELIVERY",
            reason="This outcome receipt cannot be tied to one verified post.",
            next_action="Verify a single post and use a unique campaign tag before judging its creative.",
        )
    if not isinstance(report, dict) or report.get("coverage") != "DECLARED_COMPLETE":
        return dict(
            evidence,
            status="COLLECT_MATCHED_WINDOW",
            reason="The product and billing inputs do not both cover the full campaign window.",
            next_action="Collect both sources through the declared maturity date in the same app identity namespace.",
        )
    counts = report.get("counts")
    stages: list[int] = []
    if isinstance(counts, dict):
        for key in ("INSTALL", "ACTIVATION", "TRIAL_START", "PURCHASE"):
            n = counts.get(key)
            if type(n) is int and n >= 0:
                stages.append(n)
    if len(stages) != 4 or stages[0] < 20:
        return dict(
            evidence,
            status="COLLECT_MORE",
            reason="This review uses a descriptive floor of 20 eligible first opens and needs all ordered stage counts.",
            next_action="Verify the tagged store-to-first-open handoff, then collect a larger sample before changing the offer.",
        )
    steps = (
        ("ACTIVATION", "first opens", "activated", "Test one shorter route to the app's first useful action."),
        ("TRIAL", "activated", "started a trial", "Test one clearer description of what the trial unlocks."),
        ("PAID", "trial starters", "paid", "Review trial-to-paid and test one change to the upgrade prompt."),
    )
    if any(later > earlier for earlier, later in pairwise(stages)):
        raise Invalid("Joined campaign stage counts do not reconcile")
    losses = [earlier - later for earlier, later in pairwise(stages)]
    index = max(range(len(losses)), key=losses.__getitem__)
    if losses[index] == 0:
        return dict(
            evidence,
            status="COMPARE_CONTROL",
            reason="The retained funnel has no observed drop between these stages.",
            next_action="Compare against a matched, preregistered control before crediting the campaign.",
        )
    stage, denominator, outcome, action = steps[index]
    return dict(
        evidence,
        status="REVIEW_" + stage,
        reason=(
            f"The largest observed drop by people was {stages[index + 1]} {outcome} out of {stages[index]} {denominator}. "
            "These counts require each prior stage in order. Coverage is source-declared; this is not verified lift."
        ),
        next_action=action + " Keep the rest fixed and require a fresh approval before launch.",
    )


def historical_measurement(campaign: Mapping[str, object], delivery: object, outcome: object) -> str:
    """Separate receipt quality and measurement maturity from publishing permission."""
    if isinstance(delivery, dict) and delivery.get("status") == "MULTIPLE_POSTS_SHARE_TAG":
        return "Use a distinct tag per approved post in the next study. This tag cannot identify one delivery."
    if isinstance(delivery, dict) and delivery.get("status") == "EXACT_TAGGED_POST_READBACK":
        state = outcome.get("status") if isinstance(outcome, dict) else None
        if state == "OBSERVED_DESCRIPTIVE":
            return "Review the matched outcome and sample size. A descriptive rate does not establish lift."
        if state == "NO_ELIGIBLE_FIRST_OPENS":
            return "Record the empty eligible cohort; leave the conversion rate unknown and check the acquisition path."
        if state == "UNSUPPORTED_DEFINITION":
            return "Choose a supported metric and denominator for the next study. This outcome cannot be interpreted."
        if state == "DEFINITION_UNVERIFIED":
            return "Verify that the source counts first opens before interpreting conversion."
        if state == "COUNTS_UNVERIFIED":
            return "Reconcile the source counts before interpreting conversion."
        return "Complete evidence for the approved measurement window before interpreting the outcome."
    receipts = campaign.get("receipts")
    if isinstance(receipts, list) and any(
        isinstance(receipt, dict) and receipt.get("status") == "VERIFIED" for receipt in receipts
    ):
        return "Delivery was verified. Match the approved tag and measurement window to an outcome receipt before attributing results."
    return "Review saved campaign receipts."
