"""Pure supplied-evidence economics; no provider verification or causal inference."""

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timedelta
from typing import Literal, NotRequired, TypedDict, cast

from .common import Invalid, digest, iso_time, required
from .subscription_journey import journey_report, validate_event


class EconomicsContract(TypedDict):
    cost_basis: Literal["MEDIA_SPEND", "TOTAL_ACQUISITION_COST"]
    revenue_basis: Literal["NET_PROCEEDS", "GROSS_REVENUE"]
    attribution_status: Literal["DECLARED_MATCHED", "PARTIAL", "UNAVAILABLE"]
    spend_source: str
    currency: str
    coverage_through: str


class Event(TypedDict):
    provider: str
    event_id: str
    type: str
    subject_id: str
    occurred_at: str
    amount_minor: int
    currency: str
    related_event_id: str
    source: str
    subscription: NotRequired[dict[str, object]]


class Gap(TypedDict):
    code: str
    action: str


class Metric(TypedDict):
    value: float | None
    status: str
    numerator_minor: int | None
    denominator: int | None
    numerator_basis: str
    denominator_basis: str
    currency: str
    window: dict[str, str]
    sample_counts: dict[str, int]
    source_hash: str
    unavailable_data: list[Gap]
    evidence: str


Finance = Callable[[Sequence[Event], str], Mapping[str, object]]


def validate_contract(value: object) -> EconomicsContract:
    """Normalize only the closed optional economics declaration."""
    fields = {"cost_basis", "revenue_basis", "attribution_status", "spend_source", "currency", "coverage_through"}
    if not isinstance(value, dict) or set(value) != fields:
        raise Invalid("Economics needs exactly: " + ", ".join(sorted(fields)))
    if value["cost_basis"] not in ("MEDIA_SPEND", "TOTAL_ACQUISITION_COST"):
        raise Invalid("Choose MEDIA_SPEND or TOTAL_ACQUISITION_COST")
    if value["revenue_basis"] not in ("NET_PROCEEDS", "GROSS_REVENUE"):
        raise Invalid("Choose NET_PROCEEDS or GROSS_REVENUE")
    if value["attribution_status"] not in ("DECLARED_MATCHED", "PARTIAL", "UNAVAILABLE"):
        raise Invalid("Declare matched, partial or unavailable attribution")
    result = dict(value)
    result["spend_source"] = required(value["spend_source"], "Spend source", 2000)
    unit = value["currency"]
    if not isinstance(unit, str) or len(unit) != 3 or not unit.isascii() or not unit.isupper() or not unit.isalpha():
        raise Invalid("Economics currency must be an uppercase three-letter code")
    result["coverage_through"] = iso_time(value["coverage_through"]).isoformat()
    return cast(EconomicsContract, result)


def gap(code: str, action: str) -> Gap:
    """Each unavailable condition carries its concrete repair action."""
    return {"code": code, "action": action}


def unique_events(events: Sequence[Event]) -> tuple[list[Event], list[Gap]]:
    """Exact replays count once; conflicting immutable identities block economics."""
    unique: dict[tuple[str, str], Event] = {}
    issues: list[Gap] = []
    for event in events:
        key = event["provider"], event["event_id"]
        if key in unique and unique[key] != event:
            issues.append(
                gap(
                    "EVENT_ID_CONFLICT", "Reconcile conflicting provider/event IDs before importing a corrected cohort."
                )
            )
        unique.setdefault(key, event)
    return sorted(
        unique.values(), key=lambda item: (iso_time(item["occurred_at"]), item["provider"], item["event_id"])
    ), issues


def subscription_gaps(cohort: Mapping[str, object], events: Sequence[Event], as_of: datetime) -> list[Gap]:
    """Reuse ingestion binding rules and cohort journey/renewal lineage checks."""
    validated: list[Event] = []
    issues: list[Gap] = []
    for event in events:
        try:
            validated.append(cast(Event, validate_event(event)))
        except Invalid:
            issues.append(
                gap(
                    "SUBSCRIPTION_EVENT_INVALID",
                    "Correct subscription binding and positive charge amounts for the supplied subscription event.",
                )
            )
    journey = journey_report(cohort, validated, as_of)
    if journey["issues"]:
        issues.append(
            gap(
                "SUBSCRIPTION_LINEAGE_UNRECONCILED",
                "Reconcile each renewal with an earlier same-provider purchase/renewal, identical subject, currency and subscription binding, and an eligible cohort install.",
            )
        )
    return issues


def adjusted_selection(events: Sequence[Event], purchases: Sequence[Event]) -> list[Event]:
    """Retain selected purchases and late linked adjustments exactly once as of report."""
    purchase_ids = {(item["provider"], item["event_id"]) for item in purchases}
    refunds = [
        item
        for item in events
        if item["type"] == "REFUND" and (item["provider"], item["related_event_id"]) in purchase_ids
    ]
    refund_ids = {(item["provider"], item["event_id"]) for item in refunds}
    reversals = [
        item
        for item in events
        if item["type"] == "REFUND_REVERSED" and (item["provider"], item["related_event_id"]) in refund_ids
    ]
    return [*purchases, *refunds, *reversals]


def metric(
    numerator: int | None,
    denominator: int | None,
    basis: str,
    denominator_basis: str,
    unit: str,
    window: dict[str, str],
    counts: dict[str, int],
    source_hash: str,
    issues: list[Gap],
) -> Metric:
    """Expose evidence and both operands even when a ratio is unavailable."""
    return {
        "value": numerator / denominator if not issues and numerator is not None and denominator else None,
        "status": "UNAVAILABLE" if issues else "SUPPLIED",
        "numerator_minor": numerator,
        "denominator": denominator,
        "numerator_basis": basis,
        "denominator_basis": denominator_basis,
        "currency": unit,
        "window": window,
        "sample_counts": counts,
        "source_hash": source_hash,
        "unavailable_data": issues,
        "evidence": "SUPPLIED_NOT_PROVIDER_VERIFIED",
    }


def build_economics(
    cohort: Mapping[str, object], events: Sequence[Event], as_of: datetime, finance: Finance
) -> dict[str, object]:
    """Calculate app/cohort-scoped CAC and install-relative D7/D30 supplied ROAS."""
    observed, issues = unique_events([item for item in events if iso_time(item["occurred_at"]) <= as_of])
    unit = cast(str, cohort["currency"])
    starts, ends, maturity = [iso_time(cohort[key]) for key in ("starts_at", "ends_at", "matures_at")]
    contract = validate_contract(cohort["economics"]) if "economics" in cohort else None
    source_hash = digest({"cohort": cohort, "events": observed})
    if contract is None:
        issues.append(
            gap(
                "ECONOMICS_DECLARATION_MISSING",
                "Declare cost/revenue bases, attribution, spend source, currency and coverage_through on a new cohort.",
            )
        )
    if cohort["observability"] != "OBSERVED":
        issues.append(
            gap("OBSERVABILITY_INCOMPLETE", "Import complete observed install and purchase coverage for this cohort.")
        )
    if contract and contract["attribution_status"] != "DECLARED_MATCHED":
        issues.append(
            gap(
                "ATTRIBUTION_INCOMPLETE",
                "Reconcile install, purchase and spend attribution, then declare the exact match.",
            )
        )
    if contract and contract["currency"] != unit:
        issues.append(
            gap(
                "DECLARED_CURRENCY_MISMATCH",
                "Use the cohort currency for the economics declaration; no FX is inferred.",
            )
        )
    issues.extend(subscription_gaps(cohort, observed, as_of))
    money = finance(observed, unit)
    if money["issues"]:
        issues.append(
            gap(
                "FINANCE_UNRECONCILED",
                "Resolve ledger currency and purchase/refund/reversal references before calculating economics.",
            )
        )
    installers: dict[str, datetime] = {}
    for item in observed:
        stamp = iso_time(item["occurred_at"])
        if item["type"] == "INSTALL" and starts <= stamp < ends:
            installers.setdefault(item["subject_id"], stamp)
    acquisitions = [
        item
        for item in observed
        if item["type"] == "COST_ACQUISITION" and starts <= iso_time(item["occurred_at"]) < ends
    ]
    costs = [
        item
        for item in acquisitions
        if contract and item["source"] == contract["spend_source"] and item["currency"] == unit
    ]
    if not costs:
        issues.append(
            gap(
                "MATCHED_SPEND_MISSING",
                "Import a matching COST_ACQUISITION receipt in the acquisition window, including an explicit zero receipt when applicable.",
            )
        )
    if contract and any(item["source"] != contract["spend_source"] for item in acquisitions):
        issues.append(
            gap("SPEND_SOURCE_MISMATCH", "Reconcile acquisition-cost receipts to the exact declared spend source.")
        )
    spend = sum(item["amount_minor"] for item in costs) if costs else None
    base_counts = {"installs": len(installers), "spend_receipts": len(costs), "events": len(observed)}
    coverage = iso_time(contract["coverage_through"]) if contract else None
    metrics: dict[str, Metric] = {}
    eligible = [
        item
        for item in observed
        if item["type"] in ("PURCHASE", "RENEWAL")
        and item["subject_id"] in installers
        and iso_time(item["occurred_at"]) >= installers[item["subject_id"]]
    ]
    cac_purchases = [
        item
        for item in eligible
        if item["type"] == "PURCHASE" and iso_time(item["occurred_at"]) <= maturity and item["amount_minor"] > 0
    ]
    payers = {item["subject_id"] for item in cac_purchases}
    cac_issues = list(issues)
    if as_of < maturity or coverage is None or coverage < maturity:
        cac_issues.append(
            gap("CAC_WINDOW_INCOMPLETE", "Wait through cohort maturity and import evidence covered through matures_at.")
        )
    if not payers:
        cac_issues.append(
            gap(
                "NO_ACQUIRED_PAYERS",
                "Import an eligible positive purchase for an acquired subject; zero payers cannot form a CAC denominator.",
            )
        )
    metrics["cac_minor"] = metric(
        spend,
        len(payers),
        contract["cost_basis"] if contract else "UNDECLARED",
        "UNIQUE_ACQUIRED_PAYERS",
        unit,
        {"starts_at": starts.isoformat(), "ends_at": ends.isoformat(), "observed_through": maturity.isoformat()},
        {**base_counts, "acquired_payers": len(payers)},
        source_hash,
        cac_issues,
    )
    for days in (7, 30):
        cutoff = ends + timedelta(days=days)
        selected = [
            item
            for item in eligible
            if iso_time(item["occurred_at"]) < installers[item["subject_id"]] + timedelta(days=days)
        ]
        horizon_issues = list(issues)
        if as_of < cutoff or coverage is None or coverage < cutoff:
            horizon_issues.append(
                gap(
                    "HORIZON_INCOMPLETE",
                    f"Wait through acquisition end plus {days} days and import complete coverage through that cutoff.",
                )
            )
        if coverage is not None and coverage < as_of:
            horizon_issues.append(
                gap(
                    "ADJUSTMENT_COVERAGE_INCOMPLETE",
                    "Import complete purchase/refund/reversal evidence through the report as_of timestamp.",
                )
            )
        if not installers:
            horizon_issues.append(
                gap("NO_ACQUIRED_INSTALLS", "Import install evidence within the cohort acquisition window.")
            )
        if not spend:
            horizon_issues.append(
                gap(
                    "ZERO_SPEND_DENOMINATOR",
                    "ROAS requires a positive matched media-spend denominator; do not substitute zero for missing spend.",
                )
            )
        if contract and contract["cost_basis"] != "MEDIA_SPEND":
            horizon_issues.append(
                gap(
                    "ROAS_REQUIRES_MEDIA_SPEND",
                    "Declare and import media spend separately from total acquisition cost on a new cohort.",
                )
            )
        selected_money = finance(adjusted_selection(observed, selected), unit)
        if selected_money["issues"]:
            horizon_issues.append(
                gap(
                    "HORIZON_FINANCE_UNRECONCILED",
                    "Reconcile adjustments linked to purchases in this install-relative horizon.",
                )
            )
        basis = contract["revenue_basis"] if contract else "UNDECLARED"
        net = cast(int | None, selected_money["net_proceeds_minor"])
        gross = sum(item["amount_minor"] for item in selected)
        for revenue_basis, numerator in (("NET_PROCEEDS", net), ("GROSS_REVENUE", gross)):
            local_issues = list(horizon_issues)
            if basis != revenue_basis:
                local_issues.append(
                    gap(
                        "REVENUE_BASIS_UNDECLARED",
                        f"Declare {revenue_basis} for the imported purchase amounts; gross revenue and net proceeds are distinct.",
                    )
                )
            name = ("net_proceeds" if revenue_basis == "NET_PROCEEDS" else "gross_revenue") + f"_roas_d{days}"
            metrics[name] = metric(
                numerator if basis == revenue_basis else None,
                spend,
                revenue_basis,
                "MEDIA_SPEND",
                unit,
                {
                    "starts_at": starts.isoformat(),
                    "acquisition_ends_at": ends.isoformat(),
                    "observed_through": cutoff.isoformat(),
                    "rule": f"install <= purchase < install + {days} days; adjustments through as_of",
                },
                {
                    **base_counts,
                    "purchases": len(selected),
                    "acquired_payers": len({item["subject_id"] for item in selected if item["amount_minor"] > 0}),
                },
                source_hash,
                local_issues,
            )
    all_gaps = {item["code"] + item["action"]: item for value in metrics.values() for item in value["unavailable_data"]}
    return {
        "schema": "wmm.measurement-economics.v1",
        "evidence": "SUPPLIED_NOT_PROVIDER_VERIFIED",
        "attribution_status": contract["attribution_status"] if contract else "UNAVAILABLE",
        "metrics": metrics,
        "unavailable_data": list(all_gaps.values()),
        "source_hash": source_hash,
    }
