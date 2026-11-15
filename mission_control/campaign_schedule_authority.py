"""Exact retained campaign capability for one leased scheduled post."""

import json
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from sqlite3 import Connection, Row
from typing import TYPE_CHECKING, Any, TypedDict

from .app_launch_history import removed_listing
from .common import digest, iso_time
from .db import connection

if TYPE_CHECKING:
    from .store import Store


class ScheduledJob(TypedDict):
    """Fields captured when the worker takes a lease."""

    id: str
    attempts: int
    data: object


ActiveLease = tuple[str, str, int, str]
SavedRow = Row | Mapping[str, Any]
Packet = Mapping[str, Any]

CURRENT: ContextVar[ActiveLease | None] = ContextVar("wmm_scheduled_campaign", default=None)


def _leased_row(db: Connection, job_id: str) -> Row | None:
    """Read the same retained job, item and batch for both dispatch paths."""
    return db.execute(
        """SELECT b.id AS batch_id,b.summary,b.summary_hash,b.status AS batch_status,
        i.body,i.body_hash,i.due,i.status AS item_status,i.job_id,j.status AS job_status,
        j.attempts,j.lease,j.data,j.app_id,j.action
        FROM campaign_schedule_items i JOIN campaign_schedule_batches b ON b.id=i.batch_id
        JOIN jobs j ON j.id=i.job_id WHERE i.job_id=?""",
        (job_id,),
    ).fetchone()


@contextmanager
def bound(store: "Store", job: ScheduledJob) -> Iterator[None]:
    """Bind only a worker-owned job; validation happens at every effect boundary."""
    token = CURRENT.set((str(store.path.resolve()), job["id"], job["attempts"], digest(job["data"])))
    try:
        yield
    finally:
        CURRENT.reset(token)


def check(store: "Store", app_id: str, actor: str, scope: Packet, action: str) -> bool:
    """Fail closed unless this exact due job remains owned and approved."""
    active = CURRENT.get()
    if active is None:
        return False
    if (
        action not in ("RUN_POST", "RUN_AD")
        or actor != "schedule:" + active[1]
        or active[0] != str(store.path.resolve())
    ):
        raise PermissionError("Scheduled capability cannot authorize this operation")
    with connection(store.path) as db:
        row = _leased_row(db, active[1])
        if row is None:
            raise PermissionError("Scheduled campaign job is unavailable")
        summary = json.loads(row["summary"])
        body = json.loads(row["body"])
        data = json.loads(row["data"])
        if digest(data) != active[3]:
            raise PermissionError("Scheduled worker input changed")
        operation = body.get("operation", "campaign.publish")
        if (action, operation) not in (("RUN_POST", "campaign.publish"), ("RUN_AD", "campaign.ad-launch")):
            raise PermissionError("Scheduled operation does not match effect")
        check_lease(row, app_id, active)
        check_content(row, data, body, summary, app_id, scope)
        if removed_listing(db, app_id, body["request"].get("link")):
            raise PermissionError("Scheduled post paused because this app was removed from the App Store")
    return True


def check_lease(row: SavedRow, app_id: str, active: ActiveLease | tuple[str, str, int]) -> None:
    """Check the lease identity; payload proof is checked separately."""
    if (
        row["app_id"] != app_id
        or row["action"] not in ("campaign_post", "campaign_ad")
        or row["batch_status"] != "ACTIVE"
        or row["item_status"] != "QUEUED"
        or row["job_status"] != "RUNNING"
        or row["attempts"] != active[2]
        or row["lease"] <= time.time()
        or row["due"] > time.time()
    ):
        raise PermissionError("Scheduled campaign worker lease changed")


def check_content(row: SavedRow, data: Packet, body: Packet, summary: Packet, app_id: str, scope: Packet) -> None:
    expected = {
        "batch_id": summary["batch_id"],
        "item_id": body["item_id"],
        "scope_id": summary["scope_id"],
        "request": body["request"],
    }
    if "operation" in body:
        expected["operation"] = body["operation"]
    expected_job = "campaign_ad" if body.get("operation") == "campaign.ad-launch" else "campaign_post"
    if row["action"] != expected_job:
        raise PermissionError("Scheduled worker operation changed")
    if (
        digest(summary) != row["summary_hash"]
        or digest(body) != row["body_hash"]
        or body not in summary["items"]
        or data != expected
        or body["item_id"] != data["item_id"]
        or row["due"] != iso_time(body["due_at"]).timestamp()
    ):
        raise PermissionError("Scheduled campaign inputs changed")
    check_scope(row, summary, app_id, scope)


def check_scope(row: SavedRow, summary: Packet, app_id: str, scope: Packet) -> None:
    if summary["batch_id"] != row["batch_id"]:
        raise PermissionError("Scheduled campaign batch changed")
    if (
        summary["app_id"] != app_id
        or summary["scope_id"] != scope["scope_id"]
        or summary["scope_hash"] != scope["approval_hash"]
        or summary["owner"] != scope["owner_principal"]
    ):
        raise PermissionError("Scheduled campaign scope changed")
    check_deadline(summary, scope.get("expires_at"))


def check_deadline(summary: Packet, legacy_expiry: object) -> None:
    """Parent renewal never changes a child's reviewed execution deadline."""
    expiry = summary.get("permission_expires_at", legacy_expiry)
    if iso_time(expiry).timestamp() <= time.time():
        raise PermissionError("Scheduled campaign approval expired")


def video_context(
    db: Connection, store: "Store", app_id: str, actor: str, operation: str, body: Packet
) -> dict[str, str]:
    """Only the exact currently leased schedule may execute its retained intent."""
    active = CURRENT.get()
    if active is None or operation != "organic-video.intent-execute":
        raise PermissionError("Current scheduled Reel execution authority is required")
    if actor != "schedule:" + active[1] or active[0] != str(store.path.resolve()):
        raise PermissionError("Scheduled Reel actor or datastore changed")
    row = _leased_row(db, active[1])
    if row is None or row["action"] != "campaign_post":
        raise PermissionError("Scheduled Reel job is unavailable")
    check_lease(row, app_id, active)
    context = video_content(db, row, active, app_id, operation, body)
    db.execute(
        "UPDATE jobs SET lease=? WHERE id=? AND status='RUNNING' AND attempts=?",
        (time.time() + 60, active[1], active[2]),
    )
    return context


def video_content(
    db: Connection, row: SavedRow, active: ActiveLease, app_id: str, operation: str, body: Packet
) -> dict[str, str]:
    from .campaign_video_execution import _row
    from .organic_video_schedule import KIND

    summary, item, data = [json.loads(row[key]) for key in ("summary", "body", "data")]
    expected = dict(
        batch_id=summary["batch_id"],
        item_id=item["item_id"],
        scope_id=summary["scope_id"],
        operation=operation,
        request=item["request"],
    )
    if (
        summary.get("kind") != KIND
        or summary["app_id"] != app_id
        or summary["batch_id"] != row["batch_id"]
        or digest(summary) != row["summary_hash"]
        or digest(item) != row["body_hash"]
        or item not in summary["items"]
        or data != expected
        or digest(data) != active[3]
        or item["operation"] != operation
        or body != dict(intent_id=item["request"]["intent_id"])
        or row["due"] != iso_time(item["due_at"]).timestamp()
    ):
        raise PermissionError("Scheduled Reel inputs changed")
    intent = _row(db, app_id, body["intent_id"])
    request = json.loads(intent["data"])["request"]
    if intent["hash"] != item["request"]["intent_hash"] or (request["policy_id"], request["policy_hash"]) != (
        summary["scope_id"],
        summary["scope_hash"],
    ):
        raise PermissionError("Scheduled Reel intent or policy changed")
    video_deadline(db, app_id, request, item)
    return dict(principal=summary["owner"], scheduled_job=row["job_id"])


def video_deadline(db: Connection, app_id: str, request: Packet, item: Packet) -> None:
    """Use the scheduled item's captured deadline or its legacy policy bound."""
    policy = db.execute(
        "SELECT data FROM organic_video_policies WHERE app_id=? AND id=?", (app_id, request["policy_id"])
    ).fetchone()
    if policy is None:
        raise PermissionError("Scheduled Reel policy is unavailable")
    check_deadline(item, json.loads(policy["data"])["policy"]["expires_at"])
