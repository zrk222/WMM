"""Validate and read durable Meta campaign pause observations."""

import json
from sqlite3 import Connection, Row

from .common import Invalid, digest, iso_time, now

EFFECTIVE_STATUSES = frozenset(
    (
        "ACTIVE",
        "PAUSED",
        "DELETED",
        "PENDING_REVIEW",
        "DISAPPROVED",
        "PREAPPROVED",
        "PENDING_BILLING_INFO",
        "CAMPAIGN_PAUSED",
        "ARCHIVED",
        "ADSET_PAUSED",
        "IN_PROCESS",
        "WITH_ISSUES",
    )
)


def pause_receipt_data(intent: Row, observed: object) -> dict[str, object]:
    """Keep only the exact identity and status fields from a confirmed pause read."""
    ids = json.loads(intent["ids"]) if isinstance(intent["ids"], str) else intent["ids"]
    if (
        not isinstance(observed, dict)
        or observed.get("id") != ids.get("campaign")
        or str(observed.get("account_id")) != intent["account_id"]
        or observed.get("status") != "PAUSED"
    ):
        raise Invalid("Pause observation differs from the saved campaign")
    effective = observed.get("effective_status")
    if not isinstance(effective, str) or effective not in EFFECTIVE_STATUSES:
        effective = None
    return dict(
        schema="wmm.campaign-pause-readback.v1",
        app_id=intent["app_id"],
        intent_id=intent["id"],
        scope_id=intent["scope_id"],
        request_hash=intent["request_hash"],
        campaign_id=ids["campaign"],
        account_id=intent["account_id"],
        configured_status="PAUSED",
        effective_status=effective,
        observed_at=now(),
    )


def saved_pause_receipt(db: Connection, intent: Row) -> dict[str, object] | None:
    """Read a retained pause observation independently of later reconciliation."""
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='campaign_pause_receipts'").fetchone():
        return None
    row = db.execute(
        "SELECT hash,data,observed_at FROM campaign_pause_receipts "
        "WHERE app_id=? AND intent_id=? ORDER BY observed_at DESC,rowid DESC LIMIT 1",
        (intent["app_id"], intent["id"]),
    ).fetchone()
    if row is None:
        return None
    try:
        receipt = json.loads(row["data"])
        expected = pause_receipt_data(
            intent,
            dict(
                id=receipt["campaign_id"],
                account_id=receipt["account_id"],
                status=receipt["configured_status"],
                effective_status=receipt["effective_status"],
            ),
        )
        expected["observed_at"] = iso_time(receipt["observed_at"]).isoformat()
        if receipt != expected or receipt["observed_at"] != row["observed_at"] or digest(receipt) != row["hash"]:
            raise Invalid("Saved pause receipt failed integrity validation")
    except (KeyError, ValueError, TypeError, AttributeError):
        raise Invalid("Saved pause receipt failed integrity validation") from None
    return dict(receipt, sha256=row["hash"])
