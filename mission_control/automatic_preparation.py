"""Current app-scoped local drafts; no queue, database write or provider request."""

from .common import Invalid, digest, now
import re

GOAL_STAGES = {"research": (5, 6), "creative": (6,), "campaign": (7,), "measurement": (3, 4, 10, 11)}


def goal_request(data):
    """Close explicit local snapshot requests; clients cannot supply saved outputs."""
    if set(data) != {"stage", "goal_packet"} or type(data["stage"]) is not int or data["stage"] != 0:
        raise Invalid("Save a goal packet using pipeline stage 0")
    value = data["goal_packet"]
    if not isinstance(value, dict) or set(value) != {"goal", "manifest_version", "source_hash"}:
        raise Invalid("Choose the current goal, app version and evidence hash")
    if not isinstance(value["goal"], str) or value["goal"] not in GOAL_STAGES:
        raise Invalid("Choose one of the four supported goals")
    if type(value["manifest_version"]) is not int or value["manifest_version"] < 1:
        raise Invalid("Use the current app version")
    if not isinstance(value["source_hash"], str) or not re.fullmatch("[0-9a-f]{64}", value["source_hash"]):
        raise Invalid("Use the current evidence source hash")
    return dict(value)


def saved_goal(result, data, app, records, reports, catalog, release):
    """Freeze server-prepared goal outputs; a saved draft grants no effect authority."""
    value = goal_request(data)
    source = source_binding(app, records, reports, result["outputs"], catalog, release)
    if app["version"] != value["manifest_version"] or source != value["source_hash"]:
        raise Invalid("App or evidence changed before saving; open the current goal packet")
    selected = [dict(stage=o["stage"], output=o) for o in result["outputs"] if o["stage"] in GOAL_STAGES[value["goal"]]]
    if tuple(o["stage"] for o in selected) != GOAL_STAGES[value["goal"]]:
        raise Invalid("Current goal outputs are incomplete")
    packet = dict(
        schema="wmm.goal-evidence-packet.v1",
        app_id=app["id"],
        app_name=app["data"].get("name", app["id"]),
        manifest_version=app["version"],
        goal=value["goal"],
        source_hash=source,
        created_at=now(),
        classification="LOCAL_DRAFT_NO_AUTHORITY",
        outputs=selected,
    )
    return dict(result, goal_packet=packet, goal_packet_hash=digest(packet))


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
    source = {
        "app_id": app["id"],
        "manifest_version": app["version"],
        "manifest": app["data"],
        "records": sorted((row["id"], row["hash"]) for row in records),
        "cohorts": sorted(row["source_hash"] for row in reports),
        "readiness": [(row["stage"], row["status"], row["missing"]) for row in outputs],
        "subscription_catalog": catalog,
        "release_inventory": release,
    }
    return digest(source)


def prepare(app, records, reports=(), catalog=None, release=None):
    """Prepare twelve current packets and grouped evidence needs without side effects."""
    check_scope(app, records, reports)
    result = execute(app, records, 0, reports, catalog, release)
    for output in result["outputs"]:
        output["packet"]["local_status"] = output["status"]
    return dict(
        result,
        schema="growth.automatic-preparation.v1",
        app_id=app["id"],
        source_hash=source_binding(app, records, reports, result["outputs"], catalog, release),
        classification="CURRENT_LOCAL_DRAFTS",
        ready_count=sum(row["status"] == "PREPARED" for row in result["outputs"]),
        needs=group_needs(result["outputs"]),
        automatic_external_writes=False,
        durable_history=False,
    )
