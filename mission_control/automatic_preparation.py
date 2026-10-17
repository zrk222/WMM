"""Current app-scoped local drafts; no queue, database write or provider request."""
from .common import Invalid, digest
from .pipeline import execute


def check_scope(app, records, reports):
    """Reject explicitly foreign evidence before any packet can be prepared."""
    if any(row.get("app_id") != app["id"] for row in records):
        raise Invalid("Automatic preparation received evidence from another app")
    if any(row["cohort"].get("app_id", app["id"]) != app["id"] for row in reports):
        raise Invalid("Automatic preparation received a cohort from another app")


def group_needs(outputs):
    """Collapse identical input requests while retaining the affected stage IDs."""
    needs = {}
    for output in outputs:
        for message in output["missing"]:
            if not message.startswith("Finish stage "):
                needs.setdefault(message, []).append(output["stage"])
    return [{"message": message, "stages": stages} for message, stages in needs.items()]


def source_binding(app, records, reports, outputs, catalog=None, release=None):
    """Bind current inputs and readiness without incorporating creation timestamps."""
    source = {"app_id": app["id"], "manifest_version": app["version"],
              "manifest": app["data"],
              "records": sorted((row["id"], row["hash"]) for row in records),
              "cohorts": sorted(row["source_hash"] for row in reports),
              "readiness": [(row["stage"], row["status"], row["missing"]) for row in outputs], "subscription_catalog":catalog, "release_inventory":release}
    return digest(source)


def prepare(app, records, reports=(), catalog=None, release=None):
    """Prepare twelve current packets and grouped evidence needs without side effects."""
    check_scope(app, records, reports)
    result = execute(app, records, 0, reports, catalog, release)
    for output in result["outputs"]:
        output["packet"]["local_status"] = output["status"]
    return dict(result, schema="growth.automatic-preparation.v1", app_id=app["id"],
                source_hash=source_binding(app, records, reports, result["outputs"], catalog, release), classification="CURRENT_LOCAL_DRAFTS",
                ready_count=sum(row["status"] == "PREPARED" for row in result["outputs"]),
                needs=group_needs(result["outputs"]),
                automatic_external_writes=False, durable_history=False)
