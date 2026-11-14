"""Fingerprint the definitions behind a private report comparison."""

import json
import re
from collections.abc import Mapping
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
