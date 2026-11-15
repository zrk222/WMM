"""Owner-only exception for a blocked or stale scheduled Results review."""

from sqlite3 import Connection

from .automation_proposal_schedule import checked_definition, schedule_row
from .common import Invalid, iso_time, now
from .review_access import member
from .weekly_exception_card import exception_card


def watch_rule_schedule_exception(db: Connection, app: dict, principal: str) -> dict[str, str] | None:
    """Watch shows a repair route, not the weekly card's private identifiers or evidence."""
    try:
        owner = member(db, app["id"], principal, "OWNER")
    except PermissionError:
        return None
    card = rule_schedule_exception(db, app, principal, owner["version"])
    if card is None:
        return None
    unavailable = card["state"] == "SOURCE_UNAVAILABLE"
    return {
        "state": "RULE_SCHEDULE_UNAVAILABLE" if unavailable else "RULE_SCHEDULE_BLOCKED",
        "source": "Saved Results reviews",
        "reason": card["reason"],
        "next_action": (
            "Open saved recommendations to inspect what is available, or refresh Watch to retry."
            if unavailable
            else "Open saved recommendations, review the app and rule version, then decide whether to start a new schedule."
        ),
        "repair_route": "rule-reviews",
    }


def rule_schedule_exception(db: Connection, app: dict, principal: str, owner_revision: int) -> dict | None:
    try:
        return _project_rule_schedule(db, app, principal, owner_revision)
    except Exception:  # noqa: BLE001 - preserve other weekly sources on an unexpected schedule read failure
        return exception_card(
            app,
            principal,
            "rule_schedule",
            "unavailable",
            "SOURCE_UNAVAILABLE",
            "Scheduled reviews unavailable",
            "WMM could not read the saved schedule.",
            "Open saved recommendations to inspect what is available, or refresh the weekly review to retry.",
            "results",
            {},
            {"status": "SOURCE_UNAVAILABLE"},
            2,
        )


def _project_rule_schedule(db: Connection, app: dict, principal: str, owner_revision: int) -> dict | None:
    row = schedule_row(db, app["id"])
    if row is None or row["owner"] != principal or row["status"] not in ("ACTIVE", "BLOCKED"):
        return None
    if row["status"] == "BLOCKED":
        reason = "WMM stopped these reviews when it could no longer use the saved schedule."
    else:
        try:
            if iso_time(row["expires"]) <= iso_time(now()) or _exhausted(row["run_count"], row["max_runs"]):
                return None
            checked_definition(row)
        except (Invalid, TypeError, ValueError, OverflowError):
            reason = "WMM cannot verify the saved schedule."
        else:
            if (row["app_version"], row["owner_version"]) == (app["version"], owner_revision):
                return None
            reason = "App setup or owner access changed after these reviews were approved."
    return exception_card(
        app,
        principal,
        "rule_schedule",
        str(row["version"]),
        "BLOCKED",
        "Scheduled reviews need attention",
        reason,
        "Open saved recommendations, review the app and rule version, then decide whether to start a new schedule.",
        "results",
        {},
        {"status": row["status"], "schedule_version": row["version"], "app_version": row["app_version"]},
        2,
    )


def _exhausted(run_count: object, max_runs: object) -> bool:
    return type(run_count) is int and type(max_runs) is int and 1 <= max_runs <= 30 and run_count == max_runs
