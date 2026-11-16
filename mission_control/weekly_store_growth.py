"""Project one owner-only App Store growth decision from current retained evidence."""

from sqlite3 import Connection, DatabaseError

from .apple_analytics import DISCOVERY, DOWNLOADS
from .apple_metrics_http import inventory, source
from .common import Invalid, digest, now
from .growth_review_contract import context_of, entry_readout
from .growth_review_store import decoded
from .weekly_exception_card import exception_card

CATEGORY = "store_growth"


def store_growth_exception(db: Connection, app: dict, principal: str) -> dict | None:
    """Choose one next action without collecting, changing metadata or issuing authority."""
    try:
        selected = _latest_research(db, app["id"])
        if selected is None:
            return None
        state, reason, next_action, tool, fact = _project(db, app, selected)
    except (Invalid, DatabaseError, ValueError, TypeError, KeyError, AttributeError):
        selected = None
        state = "SOURCE_UNAVAILABLE"
        reason = "The saved store research or Apple evidence could not be verified."
        next_action = "Open Growth Review and verify the app's current research and Apple connection."
        tool, fact = "results", {}
    evidence = dict(
        state=state,
        research_hash=selected["hash"] if selected is not None else None,
        app_version=app["version"],
        **fact,
    )
    return exception_card(
        app,
        principal,
        CATEGORY,
        digest(evidence),
        state,
        "Next App Store growth move",
        reason,
        next_action,
        tool,
        {},
        evidence,
        5,
    )


def _latest_research(db: Connection, app_id: str) -> dict | None:
    # The case protects json_extract from malformed historical data. A malformed
    # latest row must not silently resurrect an older proposal.
    row = db.execute(
        """
        SELECT * FROM growth_review_entries
        WHERE app_id=? AND kind='MARKET_RESEARCH' AND
          CASE WHEN json_valid(data) THEN coalesce(json_extract(data, '$.snapshot.platform'), 'iOS')='iOS' ELSE 1 END
        ORDER BY created DESC, id DESC LIMIT 1
        """,
        (app_id,),
    ).fetchone()
    return decoded(row) if row is not None else None


def _project(db: Connection, app: dict, row: dict) -> tuple[str, str, str, str, dict]:
    readout = entry_readout(row, context_of(app), now())
    if readout["availability"] != "CURRENT_LOCAL_EVIDENCE":
        return (
            "RESEARCH_REVIEW_NEEDED",
            "The saved iOS research is imported or belongs to a previous app setup.",
            "Recheck the release, locale and storefront, then save a current local research snapshot.",
            "results",
            {},
        )
    analysis = readout["analysis"]
    if not isinstance(analysis, dict) or not isinstance(opportunities := analysis.get("intent_opportunities"), list):
        raise Invalid("Store growth research has no structured review")
    if not opportunities:
        return (
            "CHOOSE_SEARCH_INTENT",
            "The saved research has no decision about which audience to test.",
            "Group the relevant phrases by one customer problem and propose one listing or creative change.",
            "results",
            {},
        )
    best = opportunities[0]
    if not isinstance(best, dict) or not isinstance(action := best.get("next_action"), str):
        raise Invalid("Store growth action is unavailable")
    fact: dict[str, object] = {"opportunity_id": best["id"], "action_code": best["next_action_code"]}
    if best["status"] != "REVIEW_TEST":
        return (
            "RESEARCH_EVIDENCE_NEEDED",
            "The next search intent is missing evidence for a reviewable test.",
            action,
            "results",
            fact,
        )
    version, store_id, connection = source(db, app["id"])
    if version != app["version"]:
        raise Invalid("The app setup changed during the weekly review")
    if store_id is None:
        return (
            "STORE_IDENTITY_NEEDED",
            "The app does not have a valid Apple store identifier for this baseline.",
            "Confirm this app's Apple ID in app setup before connecting analytics.",
            "connections",
            fact,
        )
    if not connection:
        return (
            "BASELINE_CONNECTION_NEEDED",
            "A proposed test is ready for review. Its Apple analytics baseline is missing.",
            "Open App Store Connect for this app and set up a read connection before freezing the baseline.",
            "connections",
            fact,
        )
    observed, reports = inventory(db, app["id"], version, store_id, connection)
    fact = dict(fact, inventory_job_id=observed["job_id"] if observed else None)
    available = {r["name"] for r in reports if r["coverage"] == "COMPLETE" and r["instance_count"] > 0}
    if not {DISCOVERY, DOWNLOADS}.issubset(available):
        return (
            "BASELINE_REPORTS_NEEDED",
            "Current evidence does not show both available discovery and download reports.",
            "In Apple analytics, check report availability for this app. Keep missing impressions and downloads unknown.",
            "connections",
            fact,
        )
    return (
        "FREEZE_STORE_BASELINE",
        "Both report families show available files. Comparable counts and a growth result are not yet verified.",
        "Collect impressions and first-time downloads for the same storefront; freeze the window, sample floor and conversion guardrail before seeking approval for one change.",
        "connections",
        fact,
    )
