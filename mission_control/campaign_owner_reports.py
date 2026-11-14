"""Private source-bound owner reports; no provider reads or outbound delivery."""

import json
import re
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from .campaign_execution import saved_pause_receipt, scope_view
from .campaign_monitor import actor, last_observation, whole
from .common import Invalid, canonical, digest, identifier, iso_time, now, uid
from .db import connection
from .experiments import lookup as lookup_experiment
from .first_party_outcomes import normalized_batch
from .first_party_receipts import HASH, for_campaign, retain
from .ios_reports import snapshot
from .metrics import KPI_GAPS
from .operation_authority import bound_owner, protected, store_identity
from .operation_catalog import path_segment
from .review_access import member
from .social_contract import reference

SELECTION = ("scope_id", "monitor_id", "experiment_id", "measurement_window")
SCHEMA = """
CREATE TABLE IF NOT EXISTS campaign_report_plans (
 id TEXT PRIMARY KEY,app_id TEXT NOT NULL,owner TEXT NOT NULL,summary TEXT NOT NULL,
 summary_hash TEXT NOT NULL,status TEXT NOT NULL,version INTEGER NOT NULL,due REAL NOT NULL,
 runs INTEGER NOT NULL DEFAULT 0,last_job TEXT,created TEXT NOT NULL,updated TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS campaign_owner_reports (
 id TEXT PRIMARY KEY,app_id TEXT NOT NULL,owner TEXT NOT NULL,plan_id TEXT,
 capture_key TEXT NOT NULL,data TEXT NOT NULL,hash TEXT NOT NULL,comparison_key TEXT NOT NULL,
 created TEXT NOT NULL,UNIQUE(app_id,owner,capture_key));
"""


def initialize(store):
    with connection(store.path) as db:
        db.executescript(SCHEMA)


def selection(body):
    """Existing exact resources and an explicit review window, no implicit attribution."""
    if not isinstance(body, dict) or set(body) not in (set(SELECTION), set(SELECTION) | {"outcome_receipt_sha256"}):
        raise Invalid("Use the exact private owner report fields")
    if "outcome_receipt_sha256" in body and (
        not isinstance(body["outcome_receipt_sha256"], str) or not HASH.fullmatch(body["outcome_receipt_sha256"])
    ):
        raise Invalid("A valid outcome receipt fingerprint is required")
    reference(body["scope_id"])
    if body["monitor_id"] is not None:
        reference(body["monitor_id"])
    if body["experiment_id"] is not None:
        path_segment(body["experiment_id"])
    window = body["measurement_window"]
    exact(window, ("starts_at", "ends_at"))
    starts, ends = (iso_time(window[key]) for key in ("starts_at", "ends_at"))
    if not starts < ends <= starts + timedelta(days=366):
        raise Invalid("Choose a positive measurement window within 366 days")
    return dict(
        body,
        measurement_window=dict(starts_at=starts.isoformat(), ends_at=ends.isoformat()),
    )


def exact(body, fields):
    if not isinstance(body, dict) or set(body) != set(fields):
        raise Invalid("Use the exact private owner report fields")


def proposal(body):
    exact(body, ("selection", "cadence_seconds", "expires_at", "max_reports"))
    chosen = selection(body["selection"])
    whole(body["cadence_seconds"], 30, 86400)
    whole(body["max_reports"], 1, 100)
    expiry = iso_time(body["expires_at"])
    if not datetime.now(timezone.utc) < expiry <= datetime.now(timezone.utc) + timedelta(days=7):
        raise Invalid("Report plan expiry must be within the next 7 days")
    return dict(body, selection=chosen, expires_at=expiry.isoformat())


def object_data(raw):
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        raise Invalid("Saved owner report source needs repair") from None
    if not isinstance(value, dict):
        raise Invalid("Saved owner report source needs repair")
    return value


def owned_resource(db, table, app, owner, identity):
    if table not in (
        "campaign_scopes",
        "campaign_monitors",
        "campaign_report_plans",
        "campaign_owner_reports",
    ):
        raise Invalid("Unsupported owner report resource")
    row = db.execute(
        "SELECT * FROM " + table + " WHERE id=? AND app_id=? AND owner=?",  # noqa: S608 - table allowlist above
        (identity, app, owner),
    ).fetchone()
    if row is None:
        raise Invalid("Selected report source is unavailable for this owner")
    return row


def binding(db, store, app_id, owner, chosen) -> dict[str, Any]:
    """Current role/app and exact existing resource summaries bind local storage authority."""
    role = member(db, app_id, owner, "OWNER")
    app = db.execute("SELECT * FROM apps WHERE id=?", (app_id,)).fetchone()
    if app is None:
        raise Invalid("Report app is unavailable")
    scope = owned_resource(db, "campaign_scopes", app_id, owner, chosen["scope_id"])
    scope_data = object_data(scope["summary"])
    if digest(scope_data) != scope["summary_hash"]:
        raise Invalid("Report source summary integrity changed")
    if (scope_data["app_id"], scope_data["owner_principal"]) != (app_id, owner):
        raise Invalid("Report summary ownership changed")
    monitor_hash = None
    if chosen["monitor_id"] is not None:
        monitor = owned_resource(db, "campaign_monitors", app_id, owner, chosen["monitor_id"])
        monitor_data = object_data(monitor["summary"])
        monitor_hash = monitor["summary_hash"]
        if digest(monitor_data) != monitor_hash:
            raise Invalid("Report source summary integrity changed")
        if (monitor_data["app_id"], monitor_data["owner"]) != (app_id, owner):
            raise Invalid("Report summary ownership changed")
        if (monitor_data["source"]["scope_id"], monitor_data["source"]["scope_hash"]) != (
            scope["id"],
            scope["summary_hash"],
        ):
            raise Invalid("Monitor and campaign scope do not match")
    experiment = experiment_source(db, app_id, chosen["experiment_id"])
    return dict(
        app_id=app_id,
        app_version=app["version"],
        app_hash=digest(object_data(app["data"])),
        owner=owner,
        role_version=role["version"],
        scope_hash=scope["summary_hash"],
        monitor_hash=monitor_hash,
        experiment_hash=experiment["definition_hash"] if experiment else None,
        host_hash=digest(store_identity(store)),
    )


def experiment_source(db, app_id, identity, *, review_window=None, observed_at=None):
    """Read existing analysis only; never evaluate or select a winner during reporting."""
    if identity is None:
        return None
    row = lookup_experiment(db, app_id, identity)
    data = row["data"]
    if digest(data) != row["hash"]:
        raise Invalid("Experiment definition integrity changed")
    latest = db.execute(
        "SELECT * FROM experiment_assessments WHERE app_id=? AND experiment_id=? ORDER BY version DESC LIMIT 1",
        (app_id, identity),
    ).fetchone()
    analysis_at = iso_time(data["analysis_at"])
    observed = iso_time(observed_at or now())
    assessment = assessment_view(latest, row["hash"], data) if latest else None
    aligned = review_window is not None and experiment_window_matches(data, review_window)
    return dict(
        id=identity,
        definition_hash=row["hash"],
        primary_metric=data["primary_metric"],
        analysis_at=data["analysis_at"],
        state=row["state"],
        maturity="ANALYSIS_WINDOW_REACHED" if analysis_at <= observed else "AWAITING_ANALYSIS",
        review_window_alignment="MATCHED" if aligned else "NOT_MATCHED",
        assessment_in_window=bool(latest and analysis_at <= iso_time(latest["created"]) <= observed),
        assessment=assessment,
        analysis_method="EXISTING_SAVED_ASSESSMENT_NO_NEW_EVALUATION",
    )


def experiment_window_matches(definition, review_window):
    try:
        return all(
            iso_time(definition[arm]["cohort"][key]) == iso_time(review_window[key])
            for arm in ("control", "treatment")
            for key in ("starts_at", "ends_at")
        )
    except (KeyError, TypeError, Invalid):
        return False


def assessment_view(row, definition_hash, definition):
    data = object_data(row["data"])
    if digest(data) != row["hash"]:
        raise Invalid("Experiment assessment integrity changed")
    state = data.get("status")
    if state not in ("BLOCKED", "INCONCLUSIVE", "EVALUATED"):
        raise Invalid("Unsupported saved experiment assessment state")
    from .experiment_iteration import iteration_plan

    matches = data.get("definition_hash") == definition_hash
    return dict(
        hash=row["hash"],
        observed_at=row["created"],
        status=state,
        definition_matches=matches,
        effect=effect_view(data.get("effect")) if matches else None,
        iteration=iteration_plan(definition, data, row["hash"]) if matches else None,
        diagnostics_hash=digest(data.get("diagnostics")),
        guardrails_hash=digest(data.get("guardrail_findings")),
        limitations="Saved descriptive assessment only; no verified causal lift or automatic winner.",
    )


def effect_view(data):
    if data is None:
        return None
    exact(data, ("control_rate", "treatment_rate", "difference", "interval", "method"))
    result = {key: data[key] for key in ("control_rate", "treatment_rate", "difference", "interval")}
    canonical(result)
    if any(type(result[key]) not in (float, int) for key in ("control_rate", "treatment_rate", "difference")):
        raise Invalid("Invalid saved assessment numeric effect")
    if (
        not isinstance(result["interval"], list)
        or len(result["interval"]) != 2
        or any(type(n) not in (int, float) for n in result["interval"])
    ):
        raise Invalid("Invalid saved assessment interval")
    return dict(
        result,
        method="Descriptive difference; supplied assignment is not verified causal evidence",
    )


def campaign_view(db, app_id, owner, scope_id):
    """Preserve receipt identities, uncertainty and committed money without raw payloads."""
    scope = owned_resource(db, "campaign_scopes", app_id, owner, scope_id)
    summary = object_data(scope["summary"])
    permission = scope_view(db, scope)
    posts = [
        dict(row, kind="POST")
        for row in db.execute(
            "SELECT id,request_id,request_hash,status,remote_id,updated FROM campaign_intents WHERE app_id=? AND scope_id=? ORDER BY id",
            (app_id, scope_id),
        )
    ]
    ads = []
    for row in db.execute(
        "SELECT * FROM campaign_paid_intents WHERE app_id=? AND scope_id=? ORDER BY id",
        (app_id, scope_id),
    ):
        item = {
            key: row[key]
            for key in ("id", "request_id", "request_hash", "status", "ids", "commitment", "currency", "updated")
        }
        item["kind"] = "AD"
        receipt = saved_pause_receipt(db, row)
        if receipt is not None:
            item["pause_readback"] = {
                key: receipt[key] for key in ("configured_status", "effective_status", "observed_at", "sha256")
            }
        if item["currency"] != summary["currency"]:
            raise Invalid("Campaign receipt currency differs from approved scope")
        ids = object_data(item.pop("ids"))
        from .campaign_contract import numeric

        if set(ids) - {"campaign", "adset", "creative", "ad"}:
            raise Invalid("Saved campaign receipt identity needs repair")
        item["ids"] = {kind: numeric(value) for kind, value in ids.items()}
        ads.append(item)
    return dict(
        scope_id=scope_id,
        approval_hash=scope["summary_hash"],
        status=scope["status"],
        expires_at=summary["expires_at"],
        permission_expires_at=permission["permission_expires_at"],
        consent_revision=permission["consent_revision"],
        currency=summary["currency"],
        media_ceiling_minor=summary["max_total_minor"],
        retained_commitment_minor=sum(a["commitment"] for a in ads),
        receipts=posts + ads,
        provider_readback="NOT_PERFORMED",
        spend="UNKNOWN_PROVIDER_REPORTS_MAY_LAG",
        fees="EXCLUDED_FROM_MEDIA_CEILING",
        outcome_attribution="NOT_ESTABLISHED",
    )


def definitions(db, app_id, metrics):
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


def _cohort_definition(value):
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


def comparison(db, app_id, owner, key, current):
    previous = db.execute(
        "SELECT id,data,hash FROM campaign_owner_reports WHERE app_id=? AND owner=? AND comparison_key=? ORDER BY rowid DESC LIMIT 1",
        (app_id, owner, key),
    ).fetchone()
    if previous is None:
        return dict(status="NO_COMPATIBLE_PREVIOUS_SNAPSHOT", previous_id=None, changes=[])
    old = object_data(previous["data"])
    if digest(old) != previous["hash"]:
        raise Invalid("Previous private report integrity changed")
    before = {row["metric"]: row["observed"] for row in old["kpis"]["rows"]}
    changes = [
        dict(
            metric=row["metric"],
            previous=before.get(row["metric"]),
            current=row["observed"],
        )
        for row in current["rows"]
        if before.get(row["metric"]) != row["observed"]
    ]
    return dict(
        status="COMPATIBLE_SAVED_OBSERVATIONS",
        previous_id=previous["id"],
        previous_hash=previous["hash"],
        changes=changes,
        limitations="Same declared window and metric definitions; changes are descriptive, not causal growth.",
    )


def build(db, store, app_id, owner, chosen):
    observed = now()
    source = binding(db, store, app_id, owner, chosen)
    monitor_view = dict(id=None, status="NOT_SELECTED", summary_hash=None, last_observation=None)
    if chosen["monitor_id"] is not None:
        monitor = owned_resource(db, "campaign_monitors", app_id, owner, chosen["monitor_id"])
        monitor_view = dict(
            id=monitor["id"],
            status=monitor["status"],
            summary_hash=monitor["summary_hash"],
            last_observation=last_observation(db, monitor, object_data(monitor["summary"])),
        )
    metrics: dict[str, Any] = snapshot(db, store, app_id, observed, include_workflows=False)
    campaign = campaign_view(db, app_id, owner, chosen["scope_id"])
    experiment = experiment_source(
        db,
        app_id,
        chosen["experiment_id"],
        review_window=chosen["measurement_window"],
        observed_at=observed,
    )
    metric_hash = definitions(db, app_id, metrics)
    key = digest(
        dict(
            app_id=app_id,
            app_hash=source["app_hash"],
            scope_hash=source["scope_hash"],
            experiment_hash=source["experiment_hash"],
            metric_definitions=metric_hash,
            window=chosen["measurement_window"],
        )
    )
    business = [
        row
        for row in metrics["rows"]
        if row["metric"] not in ("Report scope", "Units") and not row["metric"].startswith("KPI gap:")
    ]
    gaps = [dict(gap) for gap in KPI_GAPS]
    coverage = dict(
        available_rows=sum(row["observed"] is not None for row in business),
        unknown_rows=sum(row["observed"] is None for row in business),
        missing_metrics=[gap["metric"] for gap in gaps],
        window_alignment="SOURCE_WINDOWS_RETAINED_REQUESTED_WINDOW_NOT_FILTERED",
        attribution="NOT_ESTABLISHED",
        metric_definitions_hash=metric_hash,
    )
    value: dict[str, Any] = dict(
        schema="wmm.private-campaign-owner-report.v1",
        visibility="PRIVATE_OWNER_ONLY",
        app_id=app_id,
        owner=owner,
        selection=chosen,
        observed_at=observed,
        source=source,
        campaign=campaign,
        monitor=monitor_view,
        kpis=metrics,
        kpi_coverage=coverage,
        kpi_gaps=gaps,
        experiment=experiment,
        comparison=comparison(db, app_id, owner, key, metrics),
        next_action=next_action(campaign, monitor_view, experiment),
        authority_issued=False,
        limits="Saved local evidence only; no fresh provider reads, messages, publication or verified business lift.",
    )
    if "outcome_receipt_sha256" in chosen:
        scope = owned_resource(db, "campaign_scopes", app_id, owner, chosen["scope_id"])
        value["first_party_outcomes"] = for_campaign(
            db,
            app_id,
            source["app_version"],
            object_data(scope["summary"]).get("measurement_plan"),
            chosen["measurement_window"],
            chosen["outcome_receipt_sha256"],
        )
    value["source_hash"] = digest(
        dict(
            binding=source,
            campaign=campaign,
            monitor=value["monitor"],
            kpis=metrics["sourceHash"],
            experiment=experiment,
            **({"outcome_receipt_sha256": chosen["outcome_receipt_sha256"]} if "first_party_outcomes" in value else {}),
        )
    )
    return value, key


def next_action(campaign, monitor, experiment):
    uncertain = ("UNKNOWN", "DISPATCHING", "ACKNOWLEDGED", "VERIFYING")
    if any(r["status"] in uncertain or r["status"].startswith("PENDING_") for r in campaign["receipts"]):
        return "Inspect and reconcile the exact uncertain campaign receipts; do not replay mutations."
    if _historical(campaign):
        return "Review historical campaign receipts; this report does not renew expired or OFF execution authority."
    observation = monitor["last_observation"]
    if monitor["id"] and not observation:
        return "Inspect the selected monitor; no saved monitor observation is available."
    if observation and observation.get("status") == "BLOCKED":
        return "Inspect the blocked monitor and reconcile its saved campaign receipts; do not replay mutations."
    if not experiment:
        return "Choose a primary outcome and a measured study for this campaign. App-wide KPI totals do not show what this campaign did."
    if experiment["review_window_alignment"] != "MATCHED":
        return (
            "Use the selected experiment’s exact acquisition dates as the report window before interpreting its result."
        )
    if experiment["maturity"] == "AWAITING_ANALYSIS":
        return "Wait for the declared experiment analysis window and mature evidence."
    assessment = experiment["assessment"]
    if not assessment or not experiment["assessment_in_window"] or not assessment["definition_matches"]:
        return "Review current evidence and explicitly evaluate the existing experiment."
    iteration = assessment["iteration"]
    draft = iteration["draft"]
    change = " Draft for review. " + draft["proposed_change"] if draft else ""
    return iteration["reason"] + change + " Re-evaluate current evidence before using this saved recommendation."


def _historical(campaign):
    permission_expiry = campaign.get("permission_expires_at", campaign["expires_at"])
    return campaign["status"] != "ACTIVE" or iso_time(permission_expiry) <= iso_time(now())


def report_view(row):
    data = object_data(row["data"])
    if digest(data) != row["hash"]:
        raise Invalid("Private report integrity changed")
    return dict(
        id=row["id"],
        hash=row["hash"],
        created=row["created"],
        plan_id=row["plan_id"],
        report=data,
    )


def save_report(db, store, app_id, owner, chosen, key, plan_id=None):
    old = db.execute(
        "SELECT * FROM campaign_owner_reports WHERE app_id=? AND owner=? AND capture_key=?",
        (app_id, owner, key),
    ).fetchone()
    if old is not None:
        value = report_view(old)
        if value["report"]["selection"] != chosen:
            raise Invalid("Report request identity was reused with different sources")
        return value
    value, comparison_key = build(db, store, app_id, owner, chosen)
    if binding(db, store, app_id, owner, chosen) != value["source"]:
        raise PermissionError("Report source authority changed before storage")
    identity = uid()
    stamp = now()
    db.execute(
        "INSERT INTO campaign_owner_reports VALUES(?,?,?,?,?,?,?,?,?)",
        (
            identity,
            app_id,
            owner,
            plan_id,
            key,
            canonical(value),
            digest(value),
            comparison_key,
            stamp,
        ),
    )
    return report_view(db.execute("SELECT * FROM campaign_owner_reports WHERE id=?", (identity,)).fetchone())


class Reports:
    def __init__(self, store):
        self.store = store
        initialize(store)

    def capture(self, app_id, body):
        exact(body, ("selection", "request_key"))
        reference(body["request_key"])
        chosen = selection(body["selection"])
        owner = actor(self.store, app_id)
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            binding(db, self.store, app_id, owner, chosen)
            return save_report(db, self.store, app_id, owner, chosen, "owner:" + body["request_key"])

    def import_outcomes(self, app_id, body):
        """Use the approved campaign window to retain supplied, consented outcome evidence."""
        exact(body, HTTP_FIELDS["import-outcomes"])
        owner = actor(self.store, app_id)
        reference(body["scope_id"])
        with connection(self.store.path) as db:
            scope = owned_resource(db, "campaign_scopes", app_id, owner, body["scope_id"])
            summary = object_data(scope["summary"])
            if digest(summary) != scope["summary_hash"]:
                raise Invalid("Report source summary integrity changed")
            if (summary.get("app_id"), summary.get("owner_principal")) != (app_id, owner):
                raise Invalid("Report summary ownership changed")
            if scope["status"] != "ACTIVE":
                raise Invalid("Approve a measurement plan before importing campaign outcomes")
            plan = summary.get("measurement_plan")
            if not isinstance(plan, dict):
                raise Invalid("Approve a measurement plan before importing campaign outcomes")
        return retain(
            self.store.path,
            app_id=app_id,
            app_version=summary["app_version"],
            environment="production",
            campaign=plan["campaign_tag"],
            starts_at=plan["starts_at"],
            ends_at=body["acquisition_ends_at"],
            matures_at=plan["ends_at"],
            as_of=body["as_of"],
            product=normalized_batch(body["product"]),
            billing=normalized_batch(body["billing"]),
        )

    def prepare(self, app_id, body):
        owner = actor(self.store, app_id)
        value = proposal(body)
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            bound = binding(db, self.store, app_id, owner, value["selection"])
            summary = dict(
                schema="wmm.private-owner-report-plan.v1",
                proposal=value,
                source=bound,
                effects="PRIVATE_LOCAL_REPORT_STORAGE_ONLY",
            )
            identity = uid()
            stamp = now()
            db.execute(
                "INSERT INTO campaign_report_plans VALUES(?,?,?,?,?,?,1,?,0,NULL,?,?)",
                (
                    identity,
                    app_id,
                    owner,
                    canonical(summary),
                    digest(summary),
                    "DRAFT",
                    time.time(),
                    stamp,
                    stamp,
                ),
            )
            return plan_view(db.execute("SELECT * FROM campaign_report_plans WHERE id=?", (identity,)).fetchone())

    def activate(self, app_id, identity, summary_hash):
        owner = actor(self.store, app_id)
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            row = owned_resource(db, "campaign_report_plans", app_id, owner, identity)
            if row["status"] != "DRAFT" or row["summary_hash"] != summary_hash:
                raise Invalid("Review the exact current private report plan")
            checked_plan(db, self.store, dict(row, status="ACTIVE"))
            db.execute(
                "UPDATE campaign_report_plans SET status='ACTIVE',version=version+1,updated=? WHERE id=?",
                (now(), identity),
            )
        return self.status(app_id, identity)

    def status(self, app_id, identity):
        owner = actor(self.store, app_id)
        with connection(self.store.path) as db:
            return _current_plan_view(
                db,
                self.store,
                owned_resource(db, "campaign_report_plans", app_id, owner, identity),
            )

    def off(self, app_id, identity, version):
        owner = actor(self.store, app_id)
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            row = owned_resource(db, "campaign_report_plans", app_id, owner, identity)
            if type(version) is not int or row["version"] != version:
                raise Invalid("Private report plan revision changed")
            db.execute(
                "UPDATE campaign_report_plans SET status='OFF',version=version+1,updated=? WHERE id=?",
                (now(), identity),
            )
            db.execute(
                "UPDATE jobs SET status='CANCELLED',updated=? WHERE id=? AND status='QUEUED'",
                (now(), row["last_job"]),
            )
        return self.status(app_id, identity)

    def read(self, app_id, identity):
        owner = actor(self.store, app_id)
        with connection(self.store.path) as db:
            member(db, app_id, owner, "OWNER")
            return report_view(owned_resource(db, "campaign_owner_reports", app_id, owner, identity))

    def history(self, app_id):
        owner = actor(self.store, app_id)
        with connection(self.store.path) as db:
            member(db, app_id, owner, "OWNER")
            return dict(
                plans=[
                    _current_plan_view(db, self.store, r)
                    for r in db.execute(
                        "SELECT * FROM campaign_report_plans WHERE app_id=? AND owner=? ORDER BY created DESC,id LIMIT 50",
                        (app_id, owner),
                    )
                ],
                reports=[
                    report_view(r)
                    for r in db.execute(
                        "SELECT * FROM campaign_owner_reports WHERE app_id=? AND owner=? ORDER BY rowid DESC LIMIT 50",
                        (app_id, owner),
                    )
                ],
            )


def plan_view(row) -> dict[str, Any]:
    return dict(
        id=row["id"],
        version=row["version"],
        status=row["status"],
        summary=object_data(row["summary"]),
        summary_hash=row["summary_hash"],
        next_due=row["due"],
        reports_dispatched=row["runs"],
        last_job=row["last_job"],
    )


def _current_plan_view(db, store, row):
    value = plan_view(row)
    value["effective_status"] = row["status"]
    value["next_action"] = "Inspect the saved private report plan and current source evidence."
    if row["status"] == "ACTIVE":
        try:
            checked_plan(db, store, row)
        except (Invalid, PermissionError, ValueError, KeyError):
            value["effective_status"] = "BLOCKED"
            value["next_action"] = (
                "Review changed app, owner, source hashes or expiry before approving a new report plan."
            )
    elif row["status"] == "BLOCKED":
        summary = object_data(row["summary"])
        if digest(summary) != row["summary_hash"]:
            value["summary"] = None
            value["next_action"] = (
                "The saved report plan could not be verified. Review current access and sources, then prepare a new plan."
            )
            return value
        proposal = summary.get("proposal")
        if not isinstance(proposal, dict):
            value["summary"] = None
            value["next_action"] = (
                "The saved report plan could not be verified. Review current access and sources, then prepare a new plan."
            )
            return value
        expiry = proposal.get("expires_at")
        if expiry:
            try:
                if iso_time(expiry).timestamp() <= time.time():
                    value["next_action"] = (
                        "This report plan expired. Review current sources and limits, then prepare a new plan if needed."
                    )
                    return value
            except (Invalid, ValueError, TypeError):
                pass
        try:
            current = binding(db, store, row["app_id"], row["owner"], proposal["selection"])
            if current != summary["source"]:
                value["next_action"] = (
                    "The report plan source or owner binding changed. Review current sources and prepare a new plan."
                )
                return value
        except (Invalid, PermissionError, ValueError, KeyError, TypeError):
            value["next_action"] = (
                "The report plan source or owner binding could not be confirmed. Review current access and sources, then prepare a new plan."
            )
            return value

        job = (
            db.execute(
                "SELECT status FROM jobs WHERE id=? AND app_id=?",
                (row["last_job"], row["app_id"]),
            ).fetchone()
            if row["last_job"]
            else None
        )
        if row["last_job"] and (job is None or job["status"] != "SUCCEEDED"):
            value["next_action"] = (
                "The previous report snapshot is missing or did not complete. Inspect its status and saved reports, then prepare a new plan if needed."
            )
        elif row["runs"] >= proposal.get("max_reports", 0):
            value["next_action"] = (
                "This finite report plan reached its report limit. Review saved reports and prepare a new plan if another review is needed."
            )
        else:
            value["next_action"] = (
                "The report plan is blocked. Review its current status and sources, then prepare a new plan if needed."
            )
    return value


def checked_plan(db, store, row):
    if row is None:
        raise PermissionError("Private report plan is unavailable")
    summary = object_data(row["summary"])
    if digest(summary) != row["summary_hash"] or row["status"] != "ACTIVE":
        raise PermissionError("Private report plan is OFF or changed")
    if iso_time(summary["proposal"]["expires_at"]).timestamp() <= time.time():
        raise PermissionError("Private report plan expired")
    current = binding(db, store, row["app_id"], row["owner"], summary["proposal"]["selection"])
    if current != summary["source"]:
        raise PermissionError("Private report authority source changed")
    return summary


def tick(store):
    initialize(store)
    count = 0
    with connection(store.path) as db:
        db.execute("BEGIN IMMEDIATE")
        for row in db.execute(
            "SELECT * FROM campaign_report_plans WHERE status='ACTIVE' AND due<=? ORDER BY due,id LIMIT 20",
            (time.time(),),
        ).fetchall():
            if report_due(db, store, row):
                count += enqueue(db, row)
    return count


def report_due(db, store, row):
    try:
        summary = checked_plan(db, store, row)
    except (Invalid, PermissionError, ValueError, KeyError):
        block(db, row["id"])
        return False
    job = db.execute("SELECT status FROM jobs WHERE id=?", (row["last_job"],)).fetchone() if row["last_job"] else None
    if job and job["status"] in ("QUEUED", "RUNNING"):
        return False
    if row["last_job"] and (job is None or job["status"] != "SUCCEEDED"):
        block(db, row["id"])
        return False
    if row["runs"] >= summary["proposal"]["max_reports"]:
        block(db, row["id"])
        return False
    return True


def block(db, identity):
    db.execute(
        "UPDATE campaign_report_plans SET status='BLOCKED',updated=? WHERE id=? AND status='ACTIVE'",
        (now(), identity),
    )


def enqueue(db, row):
    summary = object_data(row["summary"])
    identity = uid()
    body = dict(
        plan_id=row["id"],
        plan_version=row["version"],
        summary_hash=row["summary_hash"],
        run=row["runs"] + 1,
    )
    stamp = now()
    db.execute(
        "INSERT INTO jobs(id,app_id,action,data,status,created,updated,request_key) VALUES(?,?,?,?,?,?,?,?)",
        (
            identity,
            row["app_id"],
            "campaign_owner_report",
            canonical(body),
            "QUEUED",
            stamp,
            stamp,
            "campaign-owner-report-" + row["id"] + "-" + str(body["run"]),
        ),
    )
    db.execute(
        "UPDATE campaign_report_plans SET last_job=?,runs=runs+1,due=?,updated=? WHERE id=?",
        (
            identity,
            time.time() + summary["proposal"]["cadence_seconds"],
            stamp,
            row["id"],
        ),
    )
    return 1


def execute(store, job):
    """Validate same-host exact leased local job without impersonating its owner."""
    with connection(store.path) as db:
        db.execute("BEGIN IMMEDIATE")
        row, summary = job_authority(db, store, job)
        return save_report(
            db,
            store,
            row["app_id"],
            row["owner"],
            summary["proposal"]["selection"],
            "job:" + job["id"],
            row["id"],
        )


def job_authority(db, store, job):
    current = db.execute("SELECT * FROM jobs WHERE id=?", (job["id"],)).fetchone()
    if current is None or (
        current["app_id"],
        current["action"],
        current["status"],
        current["attempts"],
    ) != (job["app_id"], "campaign_owner_report", "RUNNING", job["attempts"]):
        raise PermissionError("Private report worker identity changed")
    if current["lease"] <= time.time() or object_data(current["data"]) != job["data"]:
        raise PermissionError("Private report worker lease or inputs changed")
    data = job["data"]
    exact(data, ("plan_id", "plan_version", "summary_hash", "run"))
    row = db.execute(
        "SELECT * FROM campaign_report_plans WHERE id=? AND app_id=?",
        (data["plan_id"], job["app_id"]),
    ).fetchone()
    summary = checked_plan(db, store, row)
    if (row["version"], row["summary_hash"], row["runs"], row["last_job"]) != (
        data["plan_version"],
        data["summary_hash"],
        data["run"],
        job["id"],
    ):
        raise PermissionError("Private report plan revision changed")
    return row, summary


HTTP_FIELDS = {
    "import-outcomes": {"scope_id", "acquisition_ends_at", "as_of", "product", "billing"},
    "capture": {"selection", "request_key"},
    "prepare": {"proposal"},
    "activate": {"plan_id", "summary_hash"},
    "status": {"plan_id"},
    "off": {"plan_id", "version"},
    "read": {"report_id"},
    "history": set(),
}


def dispatch(store, app, action, body):
    if action not in HTTP_FIELDS:
        raise Invalid("Unsupported private owner report action")
    exact(body, HTTP_FIELDS[action])
    service = Reports(store)
    routes = {
        "import-outcomes": lambda: service.import_outcomes(app, body),
        "capture": lambda: service.capture(app, body),
        "prepare": lambda: service.prepare(app, body["proposal"]),
        "activate": lambda: service.activate(app, body["plan_id"], body["summary_hash"]),
        "status": lambda: service.status(app, body["plan_id"]),
        "off": lambda: service.off(app, body["plan_id"], body["version"]),
        "read": lambda: service.read(app, body["report_id"]),
        "history": lambda: service.history(app),
    }
    return routes[action]()


def post(handler, parts):
    """Root route hook /api/apps/{app}/campaign-owner-reports/{action}."""
    _http_request(handler, parts)
    session = handler.session()
    from .managed_media_http import singleton

    if not secrets.compare_digest(singleton(handler, "X-CSRF-Token"), session):
        raise PermissionError("Reload the private report session")
    owner = handler.server.identities.fresh(session)
    store = handler.server.service.store
    envelope = dict(app_id=parts[2], operation="campaign.owner-report." + parts[4], input={})
    from .discovery_http import json_body

    with (
        bound_owner(store, envelope, handler.server.identities, session, owner),
        protected(store, envelope),
    ):
        return handler.send(
            200,
            dispatch(store, parts[2], parts[4], json_body(handler, "Private owner report")),
        )


def _http_request(handler, parts):
    if (
        len(parts) != 5
        or parts[:2] != ["api", "apps"]
        or parts[3] != "campaign-owner-reports"
        or parts[4] not in HTTP_FIELDS
    ):
        raise Invalid("Use an exact private owner report address")
    identifier(parts[2])
    origin = "http://127.0.0.1:" + str(handler.server.server_port)
    if handler.command != "POST" or handler.path != "/" + "/".join(parts):
        raise Invalid("Use an exact private report POST")
    if handler.headers.get_all("Host") != [origin[7:]] or handler.headers.get_all("Origin") != [origin]:
        raise PermissionError("Use the exact private report origin")
