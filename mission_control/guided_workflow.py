"""Read-only operator guidance over the existing authoritative readiness checks."""
from .common import Invalid, digest
from .pipeline import evaluate, missing_evidence, critical_findings
from .automatic_preparation import check_scope
from .catalog import stages

TOOLS = {
    "app": ("App identity and release", "app"),
    "readiness": ("Record journey test", "readiness"),
    "measurement": ("Measurement and consent", "measurement"),
    "connections": ("Connect and test providers", "connections"),
    "cohort": ("Add economics evidence", "cohort"),
    "events": ("Define event cohort", "events"),
    "results": ("Reconcile observations and costs", "results"),
    "claim": ("Add a supported claim", "claim"),
    "upload": ("Upload authentic screen", "upload"),
    "store": ("Record store destination", "store"),
    "aeo": ("Check public page", "aeo"),
    "public_store": ("Check public App Store listing", "activity"),
    "pmf": ("Find the next PMF test", "pmf"),
    "experiment": ("Record experiment plan", "experiment"),
    "sources": ("Add permitted reference", "sources"),
    "inspection": ("Inspect reference mechanisms", "evidence"),
    "ranking": ("Compare creative references", "ranking"),
    "capability": ("Set production resources", "capability"),
    "brief": ("Prepare original creative", "brief"),
    "render": ("Render reviewed screen plan", "render"),
    "distribution": ("Define distribution limits", "distribution"),
    "intent": ("ASA / AEO intent and panels", "intent"),
    "activity": ("Review exact execution evidence", "activity"),
    "route": ("Test first-value routes", "route"),
    "billing": ("Verify billing and restore", "billing"),
    "subscriptions": ("Read subscriptions and resolve billing prerequisites", "connections"),
    "release": ("Select and inspect the promoted Apple release", "connections"),
    "retention": ("Record retained value", "retention"),
    "followup": ("Consent and value follow-up", "followup"),
    "experiments": ("Register or evaluate experiment", "experiments"),
    "evaluation": ("Record decision evidence", "evaluation"),
    "learning": ("Record learning proposal", "learning"),
    "adoption": ("Review holdout and adoption", "adoption"),
    "findings": ("Resolve critical findings", "findings"),
}
STEP_TOOLS = {
    1: ("app", "pmf"), 2: ("readiness",),
    3: ("measurement", "connections", "events"),
    4: ("cohort", "results"),
    5: ("claim", "release", "upload", "store", "aeo", "public_store"),
    6: ("experiment", "sources", "inspection", "ranking", "capability", "brief", "render"),
    7: ("distribution", "intent", "activity"),
    8: ("route",), 9: ("billing", "subscriptions"), 10: ("retention", "followup", "pmf"),
    11: ("evaluation", "experiments", "results"),
    12: ("learning", "adoption"),
}


def tool(identity):
    """Return a fixed named tool; no source data becomes a dynamic URL."""
    title, route = TOOLS[identity]
    return {"id": identity, "title": title, "route": route}


def primary(stage, direct, critical):
    """Resolve a real missing input before unrelated advanced tools."""
    if critical:
        return tool("findings")
    if any(message.startswith('Verify selected App Store release:') for message in direct):
        return tool('release')
    if any(message.startswith('Verify App Store subscription catalog:') for message in direct):
        return tool('subscriptions')
    if direct and direct[0].startswith("Reconcile "):
        return tool("results")
    for kind in stage["inputs"]:
        if any(message.startswith("Add current " + kind + " evidence") for message in direct):
            return tool("upload" if kind == "asset" else kind)
    return tool(STEP_TOOLS[stage["id"]][0])


def step(stage, app, records, reports, catalog=None, release=None):
    """Keep direct gaps, dependent stages and critical findings distinct."""
    direct = missing_evidence(stage, app, records, reports, catalog, release)
    critical = critical_findings(records) if stage["id"] in (5, 6, 7, 11) else []
    return {"id": stage["id"], "title": stage["title"], "description": stage["description"],
            "local_status": "LOCAL_INPUTS_READY" if stage["status"] == "READY" else "NEEDS_INPUT",
            "direct_needs": direct, "dependency_needs": [r for r in stage["missing"] if r.startswith("Finish stage ")],
            "critical_findings": critical, "primary": primary(stage, direct, critical),
            "tools": [tool(identity) for identity in STEP_TOOLS[stage["id"]]],
            "record_ids": [r["id"] for r in records if r["kind"] in stage["inputs"]],
            "verify": stage["operations"]["verify"]}


def guide(app, records, evaluations, reports=(), catalog=None, release=None):
    """Bind current steps without granting execution or outcome authority."""
    check_scope(app, records, reports)
    expected = evaluate(app, records, reports, catalog, release)
    if evaluations != expected or len(evaluations) != len(stages()):
        raise Invalid("Workflow stage context changed or is malformed; reload this app")
    steps = [step(stage, app, records, reports, catalog, release) for stage in evaluations]
    unresolved = next((r for r in steps if r["direct_needs"] or r["critical_findings"]), None)
    next_action = unresolved["primary"] if unresolved else tool("activity")
    source = {"app": app, "records": sorted((r["id"], r["version"], r["hash"]) for r in records),
              "cohorts": sorted(r["source_hash"] for r in reports), "steps": steps, "subscription_catalog":catalog, "release_inventory":release}
    return {"schema": "growth.guided-workflow.v1", "app_id": app["id"], "app_version": app["version"],
            "source_hash": digest(source), "steps": steps, "next_action": next_action,
            "next_step": unresolved["id"] if unresolved else None,
            "local_ready_count": sum(r["local_status"] == "LOCAL_INPUTS_READY" for r in steps),
            "checklist_storage": "DERIVED_FROM_SAVED_APP_EVIDENCE",
            "classification": "LOCAL_GUIDANCE_NOT_RELEASE_APPROVAL",
            "execution": "INSPECT_EXACT_ACTION_RECORDS", "outcomes": "INSPECT_MATURE_SOURCE_REPORTS",
            "automatic_external_writes": False, "authorized_spend_minor": 0}
