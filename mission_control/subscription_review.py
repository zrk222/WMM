"""Unified founder evidence review; all effects and independent acceptance stay separate."""
from datetime import datetime, timezone
from .common import Invalid, digest
from .db import connection
from .ledger import Ledger
from .experiments import Experiments
from .subscription_variants import variant_findings
from .customer_workflow_store import CustomerWorkflows
from .growth_review_store import GrowthReviews
from .growth_review_contract import context_of
from .benchmark_ads import source_report
from .worker import jobs


def subscription_experiments(store, app, observed_at):
    """Read immutable assessments and separately surface current billing/configuration drift."""
    rows = [row for row in Experiments(store).list(app["id"]) if row["data"]["control"].get("variant_type") == "SUBSCRIPTION"]
    results = []
    with connection(store.path) as db:
        for row in rows:
            issues = []
            for arm in ("control", "treatment"):
                variant = row["data"][arm]
                issues.extend(arm + ": " + item for item in variant_findings(db, app["id"], variant, observed_at))
                cohort = variant["cohort"]
                if any(cohort[field] != app["data"].get(field) for field in ("release", "locale", "currency")):
                    issues.append(arm + ": app release, locale or currency changed")
            results.append(dict(row, current_source_findings=issues,
                review_state="SOURCE_REVIEW_NEEDED" if issues else row["decision_status"],
                execution_authority=False))
    return results


def ads_sources(store, app_id, observed_at):
    """Offer only app-owned saved source selectors, never credentials or raw provider rows."""
    results = []
    with connection(store.path) as db:
        for job in jobs(store, app_id):
            report = job.get("result")
            if job["action"] != "sync" or job["status"] != "SUCCEEDED" or not isinstance(report, dict):
                continue
            if report.get("provider") != "apple_ads" or report.get("operation") not in ("campaign_report", "keyword_report"):
                continue
            item = dict(job_id=job["id"], report_hash=report.get("source_hash"), operation=report["operation"],
                        observed_at=report.get("observed_at"), request=report.get("request"), coverage=report.get("coverage"))
            try:
                source_report(db, app_id, job["id"], report.get("source_hash"), observed_at)
                item.update(state="CURRENT_SAVED_SOURCE", reason=None)
            except Invalid as exc:
                item.update(state="SOURCE_REVIEW_NEEDED", reason=str(exc))
            results.append(item)
    return results


def review_issues(growth, journeys, experiments, customer, sources):
    """Keep missing inputs and recovery visible rather than synthesizing success."""
    issues = []
    kinds = {row["kind"] for row in growth["history"]}
    missing = {"ASO_LISTING": ("listings", "Save the original localized listing and inspect its field preflight."),
               "BENCHMARK_REFERENCE": ("benchmarks", "Save a sourced benchmark with its exact dataset period and scope."),
               "BENCHMARK_COMPARISON": ("benchmarks", "Compare a saved reference with an app-owned account read, retaining classification assumptions.")}
    for kind, (area, repair) in missing.items():
        if kind not in kinds:
            issues.append(dict(area=area, code="NO_" + kind, next_action=repair))
    if not journeys:
        issues.append(dict(area="journeys", code="NO_COHORTS", next_action="Define a cohort and import current journey observations in Results."))
    if not sources:
        issues.append(dict(area="benchmarks", code="NO_ACCOUNT_READ", next_action="Load a dated Apple Ads campaign or keyword read in Connections."))
    if not customer["history"]:
        issues.append(dict(area="customer_evidence", code="NO_CUSTOMER_WORKFLOW", next_action="Record a narrow customer workflow and its inspected sources."))
    if not experiments:
        issues.append(dict(area="subscription_experiments", code="NO_SUBSCRIPTION_EXPERIMENT", next_action="Preregister a paywall or offer experiment when billing-source evidence is ready."))
    return issues + recovery_issues(growth, experiments)


def recovery_issues(growth, experiments):
    """Surface retained evidence that needs repair independently of absent inputs."""
    issues = []
    for row in growth["history"]:
        state = row["readout"]["analysis"]["status"]
        if row["readout"]["availability"] != "CURRENT_LOCAL_EVIDENCE" or state in ("NEEDS_REPAIR", "REFERENCE_EXPIRED", "SOURCE_METRICS_UNAVAILABLE", "INCOMPATIBLE", "SOURCE_REVIEW_NEEDED"):
            issues.append(dict(area="saved_review", id=row["id"], code=state, next_action="Inspect this exact source and save a corrected new version; retained history is unchanged."))
    for row in experiments:
        if row["current_source_findings"]:
            issues.append(dict(area="subscription_experiments", id=row["id"], code="SOURCE_REVIEW_NEEDED", next_action="Refresh source/configuration evidence and assess again before recording a decision."))
    return issues


def review_status(store, app_id, clock=None, expected=None):
    """Join the actual upgrade backends without granting approval or certifying outcomes."""
    stamp = (clock or (lambda: datetime.now(timezone.utc)))()
    observed_at = stamp.isoformat()
    app = store.app(app_id)
    context = context_of(app)
    if expected is not None and context_of(expected) != context:
        raise Invalid("App setup changed while loading the review; refresh")
    ledger = Ledger(store.path).reports(app_id, observed_at)
    journeys = [dict(cohort_id=row["cohort"]["cohort_id"], currency=row["cohort"]["currency"],
                     status=row["status"], as_of=row["as_of"], source_hash=row["source_hash"], journey=row["subscription_journey"])
                for row in ledger]
    experiments = subscription_experiments(store, app, observed_at)
    growth = GrowthReviews(store, lambda: stamp).list(app_id)
    customer = CustomerWorkflows(store, lambda: stamp).list(app_id)
    sources = ads_sources(store, app_id, observed_at)
    issues = review_issues(growth, journeys, experiments, customer, sources)
    if context_of(store.app(app_id)) != context:
        raise Invalid("App setup changed during the review; refresh without discarding saved work")
    value = dict(schema="growth.subscription-review.v1", app_id=app_id, context=context, observed_at=observed_at,
        status="NEEDS_INPUT" if issues else "LOCAL_REVIEW_AVAILABLE", journeys=journeys, experiments=experiments,
        history=growth, customer_workflows=customer, ads_sources=sources, issues=issues,
        evidence_states={"local_evidence":dict(state="RECORDED" if journeys or growth["history"] or customer["history"] or experiments else "NEEDS_INPUT"),
                         "provider_verification":dict(state="SEPARATE_ACCEPTANCE_REQUIRED", reason="Saved reads and supplied eligibility do not prove current purchase, restore, entitlement or provider approval."),
                         "outcomes":dict(state="NOT_ESTABLISHED_BY_THIS_REVIEW", reason="Supplied counts and advisory benchmarks do not prove demand, retained value or causal growth.")},
        execution_authority=False, external_writes=False, spend_minor=0,
        scope="Sequential local source reads with an app-version check. Cohorts, currencies and experiment configurations remain separate. Editorial notes grant no human or provider approval. All requested UI, agent and provider acceptance remains separately required.")
    return dict(value, source_hash=digest(value))
