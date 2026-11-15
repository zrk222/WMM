"""Side-by-side source reconciliation with explicit deltas and no averaging."""

from typing import Any

from .common import digest


def row(
    source,
    metric,
    period,
    value,
    unit,
    *,
    denominator=None,
    definition=None,
    coverage="UNKNOWN",
    source_hash=None,
    observed_at=None,
):
    """Keep one source observation addressable without normalizing away its meaning."""
    return dict(
        source=source,
        metric=metric,
        period=period,
        value=value,
        unit=unit,
        denominator=denominator,
        definition=definition or source,
        coverage=coverage,
        source_hash=source_hash,
        observed_at=observed_at,
    )


def matrix(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Group compatible observations by metric and period; never compute an average."""
    groups = {}
    for item in rows:
        groups.setdefault((item["metric"], item["period"]), []).append(item)
    result = []
    for (metric, period), items in sorted(groups.items()):
        items = sorted(items, key=lambda item: (item["source"], item["source_hash"] or ""))
        values = [item for item in items if item["value"] is not None]
        units = sorted({item["unit"] for item in values})
        definitions = sorted({item["definition"] for item in values})
        sources = sorted({item["source"] for item in items})
        observed_sources = {item["source"] for item in values}
        missing_sources = sorted({item["source"] for item in items if item["value"] is None})
        compatible = (
            len(units) == 1
            and len(definitions) == 1
            and all(item["denominator"] == values[0]["denominator"] for item in values)
            and period not in {"UNSPECIFIED", "CURRENT"}
            and not period.lower().startswith("last_")
            and len(observed_sources) == len(values)
        )
        numeric = values and all(type(item["value"]) in (int, float) for item in values)
        if not values:
            status = "NO_DATA"
        elif missing_sources:
            status = "INCOMPLETE"
        elif len(observed_sources) == 1:
            status = "SINGLE_SOURCE"
        elif not compatible:
            status = "INCOMPATIBLE"
        elif not numeric:
            status = "NON_NUMERIC"
        elif all(item["value"] == values[0]["value"] for item in values):
            status = "MATCH"
        else:
            status = "CONFLICT"
        deltas = []
        if compatible and numeric and not missing_sources:
            for index, first in enumerate(values):
                for second in values[index + 1 :]:
                    difference = second["value"] - first["value"]
                    deltas.append(
                        dict(
                            from_source=first["source"],
                            to_source=second["source"],
                            difference=difference,
                            percent=difference / abs(first["value"]) if first["value"] else None,
                        )
                    )
        result.append(
            dict(
                metric=metric,
                period=period,
                status=status,
                sources=sources,
                observed_sources=sorted(observed_sources),
                missing_sources=missing_sources,
                units=units,
                definitions=definitions,
                values=items,
                deltas=deltas,
            )
        )
    return dict(
        schema="wmm.cross-source-reconciliation.v1",
        groups=result,
        source_count=len({item["source"] for item in rows}),
        observed_input_sha256=digest(rows),
        scope="Exact supplied source observations; no averaging, source join, causal claim or revenue inference.",
    )


def summary(workspace: Any) -> dict[str, Any]:
    """Project existing saved sources into the reconciliation matrix."""
    rows = []
    for report in workspace.get("ledger") or []:
        cohort = report.get("cohort") or {}
        period = cohort.get("cohort_id") or "UNSPECIFIED"
        coverage = "COMPLETE" if report.get("status") == "SUPPLIED_RECONCILED" else "PARTIAL"
        source = "ledger:" + str(period)
        source_hash = report.get("source_hash")
        for metric in ("installs", "activated", "paid", "retained"):
            if metric in report:
                rows.append(
                    row(
                        source,
                        metric,
                        period,
                        report[metric],
                        "count",
                        denominator=report.get("installs") if metric != "installs" else None,
                        definition="imported event ledger funnel",
                        coverage=coverage,
                        source_hash=source_hash,
                    )
                )
        for metric, unit in (
            ("net_proceeds_minor", cohort.get("currency") or "minor"),
            ("paid_cac_minor", cohort.get("currency") or "minor"),
        ):
            if metric in report:
                rows.append(
                    row(
                        source,
                        metric,
                        period,
                        report[metric],
                        unit,
                        denominator=report.get("paid") if metric == "paid_cac_minor" else None,
                        definition="imported event ledger money",
                        coverage=coverage,
                        source_hash=source_hash,
                    )
                )
    insights = workspace.get("insights") or {}
    for report in insights.get("reports") or []:
        data = report.get("data") or {}
        source = "insights:" + str(report.get("provider")) + ":" + str(report.get("source_id") or report.get("id"))
        for item in list(data.get("rows") or []) + list(data.get("metrics") or []):
            if not isinstance(item, dict):
                continue
            metric = item.get("id") or item.get("metric") or item.get("name")
            value = item.get("value")
            if not metric:
                continue
            rows.append(
                row(
                    source,
                    str(metric),
                    str(item.get("period") or "UNSPECIFIED"),
                    value,
                    str(item.get("unit") or "unknown"),
                    denominator=item.get("denominator"),
                    definition=item.get("definition") or (str(report.get("provider") or "provider") + " aggregate"),
                    coverage=item.get("coverage") or data.get("coverage") or "PARTIAL",
                    source_hash=item.get("source_hash") or report.get("hash"),
                    observed_at=item.get("observed_at") or data.get("observed_at"),
                )
            )
    storekit = (workspace.get("storekit") or {}).get("report") or {}
    if storekit.get("status") != "NO_DATA" and storekit.get("transactions") is not None:
        rows.append(
            row(
                "storekit",
                "storekit_transactions",
                "CURRENT",
                len(storekit["transactions"]),
                "transactions",
                definition="verified native notifications",
                coverage="PARTIAL",
            )
        )
    for item in storekit.get("configured_price_observations") or []:
        rows.append(
            row(
                "storekit",
                "configured_price_milliunits",
                "CURRENT",
                item.get("observed_configured_price_milliunits"),
                str(item.get("currency") or "unknown"),
                denominator=item.get("unique_priced_transactions"),
                definition="configured store price, not realized cash",
                coverage="PARTIAL",
            )
        )
    return matrix(rows)
