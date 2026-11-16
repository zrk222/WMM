"""Match one approved, verified Page post to retained measurement evidence."""

from sqlite3 import Connection
from typing import Any

from .campaign_metric_definitions import object_data
from .common import digest, iso_time
from .evidence_gate import has_campaign_tag


def matched_post(
    db: Connection, app_id: str, scope_id: str, approved: dict[str, Any], outcome: dict[str, Any]
) -> dict[str, Any]:
    """Trace one exact tagged Page post to a window-bound outcome receipt."""
    unknown = {"status": "NO_EXACT_DELIVERY_RECEIPT"}
    plan = approved.get("measurement_plan")
    if not isinstance(plan, dict) or not isinstance(plan.get("link"), str):
        return unknown
    link_hash = digest(plan["link"])
    rows = db.execute(
        """SELECT id, content_hash, rights_hash, page_id, status, remote_id, result, created, updated FROM campaign_intents
        WHERE app_id=? AND scope_id=? AND CASE WHEN json_valid(result)
        THEN json_extract(result,'$.destination_check.approved_link_sha256')=? ELSE 0 END
        ORDER BY id LIMIT 2""",
        (app_id, scope_id, link_hash),
    ).fetchall()
    if len(rows) != 1:
        return {"status": "MULTIPLE_POSTS_SHARE_TAG"} if rows else unknown
    row = rows[0]
    if (
        row["status"] != "VERIFIED"
        or not row["remote_id"]
        or row["page_id"] != approved["page_id"]
        or row["content_hash"] not in approved["approved_content_hashes"]
        or row["rights_hash"] not in approved["approved_rights_hashes"]
    ):
        return unknown
    result = object_data(row["result"])
    if result.get("id") != row["remote_id"]:
        return unknown
    report = outcome["report"]
    if (
        not iso_time(report["starts_at"])
        <= iso_time(row["created"])
        <= iso_time(row["updated"])
        < iso_time(report["ends_at"])
    ):
        return {"status": "DELIVERY_OUTSIDE_ACQUISITION_WINDOW"}
    # Another approved post can send traffic into the same tagged cohort.
    # Check within this app without including the other scope's data in the report.
    candidates = db.execute(
        """SELECT json_extract(i.result,'$.destination_check.final_url') AS url,
        json_extract(i.result,'$.destination_check.approved_link_sha256') AS link_hash,
        CASE WHEN json_valid(s.summary) THEN json_extract(s.summary,'$.measurement_plan.campaign_tag') END AS plan_tag
        FROM campaign_intents i LEFT JOIN campaign_scopes s
        ON s.app_id=i.app_id AND s.id=i.scope_id
        WHERE i.app_id=? AND i.id<>? AND i.status='VERIFIED' AND i.remote_id IS NOT NULL
        AND json_valid(i.result)""",
        (app_id, row["id"]),
    )
    for candidate in candidates:
        if candidate["link_hash"] == link_hash or (
            candidate["link_hash"] is not None
            and (has_campaign_tag(candidate["url"], report["campaign"]) or candidate["plan_tag"] == report["campaign"])
        ):
            return {"status": "MULTIPLE_POSTS_SHARE_TAG"}
    return dict(
        status="EXACT_TAGGED_POST_READBACK",
        intent_id=row["id"],
        content_sha256=row["content_hash"],
        rights_sha256=row["rights_hash"],
        destination_sha256=link_hash,
        provider_readback_at=row["updated"],
        delivery_sha256=digest(result),
        outcome_sha256=outcome["receipt_sha256"],
    )
