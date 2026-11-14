"""Retain aggregate first-party outcomes in the existing workspace audit ledger."""

import json
from datetime import datetime, timezone
from pathlib import Path

from .common import Invalid, canonical, digest, iso_time, now
from .db import connection
from .first_party_outcomes import HASH, OutcomeBatch, join

ACTION = "outcomes.first_party.retained"


def retain(
    path: Path,
    *,
    app_id: str,
    app_version: int,
    environment: str,
    campaign: str,
    starts_at: str,
    ends_at: str,
    matures_at: str,
    as_of: str,
    product: OutcomeBatch,
    billing: OutcomeBatch,
) -> dict[str, object]:
    """Save an immutable aggregate from admitted normalized evidence; no raw events are retained here."""
    if iso_time(as_of) > datetime.now(timezone.utc):
        raise Invalid("Outcome reports cannot observe the future")
    report = join(app_id, environment, campaign, starts_at, ends_at, matures_at, as_of, product, billing)
    with connection(path, write=True) as db:
        app = db.execute("SELECT version FROM apps WHERE id=?", (app_id,)).fetchone()
        if app is None or type(app_version) is not int or app["version"] != app_version:
            raise Invalid("Outcome report requires the current app version")
        payload = dict(report=report, app_version=app_version)
        receipt_hash = digest(payload)
        receipt: dict[str, object] = dict(payload, receipt_sha256=receipt_hash)
        raw = canonical(receipt)
        exists = db.execute(
            "SELECT 1 FROM audit WHERE app_id=? AND action=? AND detail=? LIMIT 1", (app_id, ACTION, raw)
        ).fetchone()
        if not exists:
            db.execute("INSERT INTO audit(app_id,action,detail,created) VALUES(?,?,?,?)", (app_id, ACTION, raw, now()))
    return receipt


def read(path: Path, app_id: str, receipt_hash: str) -> dict[str, object]:
    """Read a receipt by app and fingerprint; callers must enforce current owner authority."""
    if not HASH.fullmatch(receipt_hash):
        raise Invalid("A valid outcome receipt fingerprint is required")
    with connection(path) as db:
        row = db.execute(
            """SELECT detail FROM audit WHERE app_id=? AND action=?
               AND json_extract(detail, '$.receipt_sha256')=? ORDER BY id DESC LIMIT 1""",
            (app_id, ACTION, receipt_hash),
        ).fetchone()
    if row is None:
        raise Invalid("Outcome receipt is unavailable for the selected app")
    try:
        result = json.loads(row["detail"])
    except (TypeError, ValueError):
        raise Invalid("Stored outcome receipt integrity differs") from None
    if not isinstance(result, dict) or set(result) != {"report", "app_version", "receipt_sha256"}:
        raise Invalid("Stored outcome receipt integrity differs")
    payload = {key: result[key] for key in ("report", "app_version")}
    report = result["report"]
    if not isinstance(report, dict) or report.get("app_id") != app_id or digest(payload) != receipt_hash:
        raise Invalid("Stored outcome receipt integrity differs")
    return result
