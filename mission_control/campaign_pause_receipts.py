"""Validate and read durable Meta campaign pause observations."""

import json
from pathlib import Path
from sqlite3 import Connection, Row, connect

from .common import Invalid, canonical, digest, iso_time, now

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


def pause_revision(db: Connection, app_id: str, intent_id: str) -> int:
    """Read the append-only pause receipt revision inside the caller's snapshot."""
    return int(
        db.execute(
            "SELECT COALESCE(MAX(rowid),0) FROM campaign_pause_receipts WHERE app_id=? AND intent_id=?",
            (app_id, intent_id),
        ).fetchone()[0]
    )


def confirm_paid_transition(
    path: Path,
    app_id: str,
    intent_id: str,
    expected: str,
    status: str,
    readback: object,
    pause_snapshot: tuple[str, int] | None,
) -> tuple[Row, dict[str, object] | None]:
    """Atomically confirm an acknowledged status or refresh an exact saved pause."""
    permitted = {
        ("ACK_ACTIVE_adset", "ACTIVE_adset"),
        ("ACK_ACTIVE_ad", "ACTIVE_ad"),
        ("ACK_ACTIVE_campaign", "ACTIVE_campaign"),
        ("ACK_PAUSED_campaign", "PAUSED_campaign"),
        ("PAUSED_campaign", "PAUSED_campaign"),
    }
    if (expected, status) not in permitted:
        raise Invalid("Invalid campaign confirmation transition")
    db = connect(str(path), timeout=15)
    db.row_factory = Row
    try:
        with db:
            db.execute("BEGIN IMMEDIATE")
            updated = None
            if pause_snapshot is not None:
                updated, revision = pause_snapshot
                if pause_revision(db, app_id, intent_id) != revision:
                    raise Invalid("Campaign verification state changed")
            receipt = None
            statement = "SELECT * FROM campaign_paid_intents WHERE app_id=? AND id=?"
            if status == "PAUSED_campaign":
                intent = db.execute(statement, (app_id, intent_id)).fetchone()
                if intent is None:
                    raise Invalid("Paid campaign intent was not found")
                receipt = pause_receipt_data(intent, readback)
            changed = db.execute(
                "UPDATE campaign_paid_intents SET status=?,updated=? WHERE app_id=? AND id=? AND status=? "
                "AND (? IS NULL OR updated=?)",
                (status, now(), app_id, intent_id, expected, updated, updated),
            ).rowcount
            if not changed:
                raise Invalid("Campaign verification state changed")
            if receipt is not None:
                fingerprint = digest(receipt)
                db.execute(
                    "INSERT INTO campaign_pause_receipts VALUES(?,?,?,?,?)",
                    (app_id, intent_id, fingerprint, canonical(receipt), receipt["observed_at"]),
                )
                receipt["sha256"] = fingerprint
            saved = db.execute(statement, (app_id, intent_id)).fetchone()
            if saved is None:
                raise Invalid("Paid campaign intent was not found")
            return saved, receipt
    finally:
        db.close()


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
