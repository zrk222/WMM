"""Freeze the owner's selected local action against the exact reviewed sources."""

import json
from sqlite3 import Connection
from typing import Any

from .common import Invalid, canonical, digest, now
from .operation_authority import PROTECTED, check


def _receipts(db: Connection, app_id: str, review_hash: str) -> list[dict[str, Any]]:
    rows = db.execute(
        "SELECT action_id,data,hash FROM search_store_action_receipts "
        "WHERE app_id=? AND review_hash=? ORDER BY action_id",
        (app_id, review_hash),
    )
    receipts = []
    for action_id, data, checksum in rows:
        receipt = json.loads(data)
        if (
            digest(receipt) != checksum
            or receipt["app_id"] != app_id
            or receipt["action_id"] != action_id
            or receipt["review_hash"] != review_hash
        ):
            raise Invalid("Saved search and store action failed its integrity check")
        receipts.append(receipt)
    return receipts


def bind_review(
    db: Connection, result: dict[str, Any], expected: Any, body: dict[str, Any], *, save: bool = False
) -> dict[str, Any]:
    """The route rebuilds result inside the same guarded transaction as the save."""
    if not db.in_transaction:
        raise Invalid("Search and store review requires a current database snapshot")
    review = result["search_review"]
    scope = {
        "app_id": result["app_id"],
        "store_app_id": result["store_app_id"],
        "manifest_version": expected.manifest_version,
        "connection_id": expected.connection_id,
        "connection_version": expected.connection_version,
        "connection_hash": expected.connection_hash,
        "start": result["start"],
        "end": result["end"],
    }
    review_hash = digest({"version": 1, "scope": scope, "apple_rows": result["rows"], "review": review})
    app_id = result["app_id"]
    receipts = _receipts(db, app_id, review_hash)
    if not save:
        from .search_team import team_view

        return dict(
            result,
            search_review=dict(
                review, review_hash=review_hash, saved_actions=receipts, **team_view(db, app_id, review_hash)
            ),
        )
    context = PROTECTED.get()
    if context is None or "grant_id" in context:
        raise PermissionError("Saving a search and store action requires current owner access")
    envelope = json.loads(str(context["envelope"]))
    operations = {"apple.analytics.owner.search-review-save", "apple.analytics.owner.search-review-assign"}
    if envelope.get("operation") not in operations or envelope.get("app_id") != app_id:
        raise PermissionError("Use the selected app owner action")
    principal = check(db, context)
    if body["review_hash"] != review_hash:
        raise Invalid("The evidence or proposed actions changed. Review the current plan before saving.")
    action = next((item for item in review["actions"] if item["id"] == body["action_id"]), None)
    if action is None:
        raise Invalid("Choose an action from the current search and store review")
    previous = next((item for item in receipts if item["action_id"] == action["id"]), None)
    if previous is None:
        previous = dict(
            id=digest([app_id, review_hash, action["id"]]),
            app_id=app_id,
            review_hash=review_hash,
            action_id=action["id"],
            action=action,
            start=scope["start"],
            end=scope["end"],
            manifest_version=scope["manifest_version"],
            store_app_id=scope["store_app_id"],
            evidence={
                "web_evidence_sha256": review.get("web_evidence_sha256"),
                "apple_sources": [
                    dict(
                        family=family,
                        event_date=row["date"],
                        processing_date=row[family]["processing_date"],
                        source_sha256=row[family]["source_sha256"],
                    )
                    for row in result["rows"]
                    for family in ("discovery", "downloads")
                    if row[family]["source_sha256"]
                ],
            },
            saved_by=principal,
            status="SAVED",
            created=now(),
        )
        db.execute(
            "INSERT INTO search_store_action_receipts(app_id,review_hash,action_id,data,hash) VALUES(?,?,?,?,?)",
            (app_id, review_hash, action["id"], canonical(previous), digest(previous)),
        )
    return dict(app_id=app_id, review_hash=review_hash, receipt=previous)
