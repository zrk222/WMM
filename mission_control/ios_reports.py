"""Allowlisted native analytics projection; no raw account, subject or connection data."""

from .common import Invalid, digest

COHORT_FIELDS = (
    "activation_rate",
    "paid_conversion",
    "paid_cac_minor",
    "contribution_minor",
    "contribution_after_acquisition_minor",
)
COUNT_FIELDS = (
    "installs",
    "activated",
    "paid",
    "acquisition_cost_minor",
    "net_proceeds_minor",
    "delivery_cost_minor",
    "refunds_minor",
)
LEDGER_FIELDS = (
    "installs",
    "activated",
    "paid",
    "retained",
    "activation_rate",
    "paid_conversion",
    "retention_rate",
    "net_proceeds_minor",
    "refunds_minor",
    "acquisition_cost_minor",
    "delivery_cost_minor",
    "paid_cac_minor",
    "contribution_after_acquisition_minor",
)


def snapshot(db, store, app_id, observed, *, include_handoffs=True, include_workflows=True):
    """One report projection for both admitted agents and the native owner host.

    The caller owns the consistent transaction and current authorization context.
    This helper neither authenticates nor promotes its caller to owner.
    """
    import json
    from .common import iso_time
    from .store import decode
    from .ledger import report
    from .insights import decoded as insight_decode
    from .apple_metrics_store import KEY_FIELDS, read_partition
    from .agent_handoffs import report_summary
    from .apple_readiness_report import summary as apple_readiness

    app = db.execute("SELECT * FROM apps WHERE id=?", (app_id,)).fetchone()
    if app is None:
        raise Invalid("Report app is unavailable")
    app = decode(app)
    records = [decode(r) for r in db.execute("SELECT * FROM records WHERE app_id=? ORDER BY updated,id", (app_id,))]
    cohorts = [
        json.loads(r["data"])
        for r in db.execute("SELECT data FROM growth_cohorts WHERE app_id=? ORDER BY id", (app_id,))
    ]
    events = [
        dict(cohort_id=r["cohort_id"], data=json.loads(r["data"]))
        for r in db.execute(
            "SELECT cohort_id,data FROM growth_events WHERE app_id=? ORDER BY provider,external_id", (app_id,)
        )
    ]
    reports = [
        report(c, [r["data"] for r in events if r["cohort_id"] == c["cohort_id"]], iso_time(observed)) for c in cohorts
    ]
    insights = [
        insight_decode(r)
        for r in db.execute("SELECT * FROM insight_reports WHERE app_id=? ORDER BY rowid DESC LIMIT 300", (app_id,))
    ]
    keys = [
        {field: r[field] for field in KEY_FIELDS}
        for r in db.execute(
            "SELECT * FROM apple_metric_partitions WHERE app_id=? AND store_app_id=? ORDER BY event_date,report_id",
            (app_id, app["data"].get("store_app_id", "")),
        )
    ]
    monitoring = monitoring_summary(db, app_id) if include_workflows else None
    batches = batch_summary(db, app_id) if include_workflows else None
    handoffs = report_summary(db, app_id, iso_time(observed)) if include_workflows and include_handoffs else None
    apple_health = apple_readiness(db, app_id, app["data"].get("store_app_id"), observed) if include_workflows else None
    return projection(
        app,
        records,
        reports,
        observed,
        insights,
        [read_partition(store.path, key) for key in keys],
        monitoring,
        batches,
        handoffs,
        apple_health,
    )


def monitoring_summary(db, app_id):
    """Summarize current local observation limits without exposing owner identities."""
    from .common import iso_time
    from .experiment_schedules import STATUSES

    rows = db.execute(
        "SELECT s.experiment_id,s.status,s.enabled,l.expires,l.max_observations,l.reserved FROM experiment_schedules s LEFT JOIN experiment_schedule_limits l ON l.app_id=s.app_id AND l.experiment_id=s.experiment_id AND l.schedule_version=s.version WHERE s.app_id=? ORDER BY s.updated DESC,s.experiment_id LIMIT 20",
        (app_id,),
    ).fetchall()
    total = db.execute("SELECT count(*) FROM experiment_schedules WHERE app_id=?", (app_id,)).fetchone()[0]
    items = []
    for row in rows:
        try:
            expiry = iso_time(row["expires"]).isoformat() if row["expires"] else None
        except (Invalid, ValueError, TypeError):
            expiry = None
        maximum, reserved = row["max_observations"], row["reserved"]
        valid = type(maximum) is int and 1 <= maximum <= 30 and type(reserved) is int and 0 <= reserved <= maximum
        items.append(
            dict(
                status=row["status"] if row["status"] in STATUSES else "UNKNOWN",
                expires=expiry,
                remaining=maximum - reserved if valid else None,
            )
        )
    return dict(total=total, items=items, truncated=total > len(rows))


def batch_summary(db, app_id):
    """Summarize local production states without exporting plans, authority or inputs."""
    rows = db.execute(
        "SELECT id,state,reserved_frames,created FROM creative_batches WHERE app_id=? ORDER BY created DESC,id LIMIT 20",
        (app_id,),
    ).fetchall()
    total = db.execute("SELECT count(*) FROM creative_batches WHERE app_id=?", (app_id,)).fetchone()[0]
    states = {"ACTIVE", "COMPLETED", "CANCELLED", "CANCEL_PENDING_HOLD", "BLOCKED_HOLD", "FAILED", "RECONCILE_REQUIRED"}
    items = [
        dict(
            state=r["state"] if r["state"] in states else "UNKNOWN",
            reserved_frames=r["reserved_frames"]
            if type(r["reserved_frames"]) is int and 0 <= r["reserved_frames"] <= 11520
            else None,
        )
        for r in rows
    ]
    return dict(total=total, items=items, truncated=total > len(rows))


def read(store, app_id, *, include_handoffs=True):
    from .db import connection
    from .common import now

    with connection(store.path) as db:
        db.execute("BEGIN IMMEDIATE")
        return snapshot(db, store, app_id, now(), include_handoffs=include_handoffs)


def projection(
    app,
    records,
    ledger_reports,
    observed_at,
    insight_reports=(),
    apple_partitions=(),
    monitoring=None,
    batches=None,
    handoffs=None,
    apple_health=None,
):
    from .metrics import summarize

    metrics = summarize(records, app["id"], ledger_reports)
    source = {
        "app": app,
        "records": records,
        "ledger": ledger_reports,
        "insights": insight_reports,
        "apple": apple_partitions,
    }
    for name, value in (
        ("monitoring", monitoring),
        ("batches", batches),
        ("handoffs", handoffs),
        ("apple_health", apple_health),
    ):
        if value is not None:
            source[name] = value
    source_hash = digest(source)
    rows = []

    def add(label, value, evidence):
        if len(rows) >= 1000:
            raise Invalid("Native report exceeds 1000 rows; narrow the source evidence before exporting")
        rows.append(dict(metric=label, observed=None if value is None else str(value), evidence=evidence))

    add("Report scope", "Supplied observations; no causal lift established", source_hash)
    add(
        "Units",
        "Rates are fractions from 0 to 1; money fields marked minor use the stated currency minor unit.",
        source_hash,
    )
    if apple_health is not None:
        add(
            "Apple schedule",
            apple_health["schedule"],
            "Local scheduled-read configuration; this does not establish app performance.",
        )
        add(
            "Apple scheduled read",
            apple_health["read"],
            "Latest current-source scheduled read; an empty report is not a zero metric.",
        )
        add(
            "Apple read observed",
            apple_health["observed_at"],
            "Time of the verified read or terminal job state, if available.",
        )
        add("Apple next due", apple_health["next_due"], "Next local scheduled-read time, if enabled.")
        add(
            "Apple next action",
            apple_health["next_action"],
            "No provider write or campaign action is authorized by this report.",
        )
        add(
            "Apple numeric outcome",
            None,
            "Schedule readiness is not a numeric metric; saved download observations are listed separately.",
        )
    if monitoring is not None:
        add(
            "Experiment monitoring",
            monitoring["total"],
            "Local finite schedules; observations do not authorize external actions. Truncated="
            + str(monitoring["truncated"]),
        )
        for index, item in enumerate(monitoring["items"], 1):
            add(
                "Experiment schedule " + str(index),
                item["status"],
                "Remaining="
                + str(item["remaining"])
                + "; expiry="
                + str(item["expires"])
                + "; unknown metrics are not zero.",
            )
    if batches is not None:
        add(
            "Creative batches",
            batches["total"],
            "Local production only; publication NOT_RUN; human visual review remains required. Truncated="
            + str(batches["truncated"]),
        )
        for index, item in enumerate(batches["items"], 1):
            add(
                "Creative batch " + str(index),
                item["state"],
                "Reserved frames=" + str(item["reserved_frames"]) + "; publication NOT_RUN.",
            )
    if handoffs is not None:
        add(
            "Agent handoffs",
            handoffs["total"],
            handoffs["scope"] + "; truncated=" + str(handoffs["truncated"]) + "; " + handoffs["next_action"],
        )
        add(
            "Handoff lifecycle counts",
            None,
            "All saved handoffs: "
            + str(handoffs["status_counts"])
            + "; recent effective states: "
            + str(handoffs["recent_effective_counts"]),
        )
        for index, item in enumerate(handoffs["items"], 1):
            details = "; ".join(
                field + "=" + str(item[field])
                for field in (
                    "id",
                    "job_id",
                    "job_action",
                    "job_status",
                    "source_kind",
                    "created",
                    "expires",
                    "context_status",
                    "context_changes",
                )
                if field in item
            )
            add("Agent handoff " + str(index), item.get("status"), "Saved metadata only; " + details)
    if not any(metrics[key] for key in ("cohorts", "retention", "event_ledger", "acquisition")):
        add("App performance", None, "No app-scoped cohort, retention, acquisition or event observations are saved.")
    for index, cohort in enumerate(metrics["cohorts"], 1):
        evidence = "Supplied cohort; " + cohort.get("scope", cohort.get("reason", ""))
        evidence += (
            "; currency="
            + str(cohort.get("currency") or "unknown")
            + "; horizon="
            + str(cohort.get("horizon") or "unknown")
        )
        add(f"Cohort {index}: status", cohort["status"], evidence)
        for field in COHORT_FIELDS:
            add(f"Cohort {index}: {field}", cohort.get(field), evidence)
        for field in COUNT_FIELDS:
            add(f"Cohort {index}: {field}", cohort.get("counts", {}).get(field), evidence)
    for index, retention in enumerate(metrics["retention"], 1):
        evidence = "Supplied retention; window=" + str(retention["window"]) + "; mature=" + str(retention["mature"])
        for field in ("eligible", "retained", "rate"):
            add(f"Retention {index}: {field}", retention[field], evidence)
    for index, ledger in enumerate(ledger_reports, 1):
        cohort = ledger["cohort"]
        evidence = "Imported events; source=" + ledger["source_hash"] + "; as_of=" + ledger["as_of"]
        evidence += (
            "; currency=" + cohort["currency"] + "; starts=" + cohort["starts_at"] + "; ends=" + cohort["ends_at"]
        )
        evidence += (
            "; matures="
            + cohort["matures_at"]
            + "; status="
            + ledger["status"]
            + "; observability="
            + ledger["observability"]
        )
        add(f"Event cohort {index}: scope", ledger["scope"], evidence)
        for field in LEDGER_FIELDS:
            add(f"Event cohort {index}: {field}", ledger.get(field), evidence)
        journey = ledger["subscription_journey"]
        for group_index, group in enumerate(journey["groups"], 1):
            binding = group["binding"]
            proof = evidence + "; subscription binding=" + digest(binding) + "; coverage=" + journey["coverage"]
            proof += (
                "; trial_days="
                + str(binding["trial_days"])
                + "; billing_period_days="
                + str(binding["billing_period_days"])
            )
            prefix = f"Event cohort {index}, offer {group_index}"
            add(prefix + ": rate status", group["rate_status"], proof)
            for field in (
                "trial_to_paid_rate",
                "first_renewal_rate",
                "mature_trial_subjects",
                "mature_paid_subjects",
                "trial_to_paid_subjects",
                "renewed_subjects",
                "median_seconds_to_first_payment",
            ):
                add(prefix + ": " + field, group.get(field), proof)
            for field, count in sorted(group["counts"].items()):
                add(prefix + ": " + field, count, proof)
    # Detailed ASA/AEO worksheets retain their own typed result contract. Do not
    # flatten public attention counts into installs or revenue.
    if metrics["acquisition"]:
        add(
            "Acquisition worksheets",
            len(metrics["acquisition"]),
            "App-scoped ASA/AEO worksheets are saved; detailed worksheet export is not included in this projection.",
        )
    # Export the latest observation per source separately from transaction totals.
    # Public projections omit project/account identifiers and protected bindings.
    seen = set()
    for item in insight_reports:
        if item["app_id"] != app["id"]:
            raise Invalid("Analytics report belongs to another app")
        if item["source_id"] in seen:
            continue
        seen.add(item["source_id"])
        data = item["data"]
        proof = (
            "Provider aggregate; provider="
            + item["provider"]
            + "; observed="
            + data["observed_at"]
            + "; source="
            + item["hash"]
            + "; not transaction evidence or causal attribution"
        )
        add("Provider " + item["provider"] + ": coverage", data["coverage"], proof)
        for metric in data["rows"]:
            label = "Provider " + item["provider"] + ": " + metric["id"]
            if item["provider"] == "clarity":
                for field, value in metric["values"].items():
                    add(
                        label + ": row " + str(metric["row"]) + ": " + field,
                        value,
                        proof + "; period=" + metric["period"] + "; provider numeric aggregate",
                    )
            else:
                add(label, metric["value"], proof + "; period=" + metric["period"] + "; unit=" + metric["unit"])
    from .apple_analytics import DISCOVERY

    for index, item in enumerate(apple_partitions, 1):
        key = item["partition"]
        instance = item["instance"]
        if key["app_id"] != app["id"] or key["store_app_id"] != app["data"].get("store_app_id"):
            raise Invalid("Apple metrics partition belongs to another selected app")
        discovery = key["report_family"] == DISCOVERY
        evidence_type = "Apple discovery report row" if discovery else "Apple download events"
        proof = evidence_type + "; source=" + digest(item) + "; event_date=" + key["event_date"]
        proof += (
            "; processing_date="
            + instance["processing_date"]
            + "; finality=UNKNOWN; not installs, sales, revenue or causal lift"
        )
        for offset, metric in enumerate(instance["rows"], 1):
            label = f"Apple partition {index}, observation {offset}: "
            row_proof = (
                proof
                + "; type="
                + metric["type"]
                + "; source_type="
                + metric["source_type"]
                + "; dimensions="
                + digest(metric["dimensions"])
            )
            if discovery:
                if metric["type"] == "impression":
                    add(label + "store_impressions", metric["count"], row_proof)
                    add(
                        label + "store_impressions_unique_row",
                        metric["unique_count"],
                        row_proof + "; row-level unique count only",
                    )
            else:
                add(label + "download_events", metric["count"], row_proof)
    if any(
        len(row["metric"]) > 200 or len(row["evidence"]) > 4000 or len(row["observed"] or "") > 4000 for row in rows
    ):
        raise Invalid("Native report field exceeds the reviewed export bounds")
    return dict(appID=app["id"], appName=app["data"]["name"], sourceHash=source_hash, observedAt=observed_at, rows=rows)
