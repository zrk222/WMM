"""Finite owner-reviewed Page post and existing-post promotion schedules."""

import json
import time
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from sqlite3 import Connection, Row
from typing import Any

from .app_launch_history import removed_listing
from .campaign_contract import ad_data, post_data
from .campaign_execution import CampaignExecutionService, saved_pause_receipt, scope_view
from .common import Invalid, canonical, digest, iso_time, now, uid
from .db import connection
from .review_access import member

MAX_ITEMS = 20
SCHEMA = """
CREATE TABLE IF NOT EXISTS campaign_schedule_batches (
 id TEXT PRIMARY KEY, app_id TEXT NOT NULL, owner TEXT NOT NULL, scope_id TEXT NOT NULL,
 summary TEXT NOT NULL, summary_hash TEXT NOT NULL, status TEXT NOT NULL,
 version INTEGER NOT NULL, created TEXT NOT NULL, updated TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS campaign_schedule_items (
 id TEXT PRIMARY KEY, batch_id TEXT NOT NULL REFERENCES campaign_schedule_batches(id),
 due REAL NOT NULL, body TEXT NOT NULL, body_hash TEXT NOT NULL,
 status TEXT NOT NULL, job_id TEXT UNIQUE, created TEXT NOT NULL, updated TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS campaign_schedule_due ON campaign_schedule_items(status,due);
"""


def initialize(store):
    with connection(store.path) as db:
        db.executescript(SCHEMA)


def owner_context(store, app_id):
    from .campaign_access import identity

    context, actor = identity(store, app_id)
    if "principal" not in context:
        raise PermissionError("A freshly authenticated owner is required")
    return actor


def checked_scope(db, service, app_id, actor, scope_id):
    row = service._row(db, app_id, scope_id)
    scope = scope_view(db, row)
    if scope["owner_principal"] != actor:
        raise PermissionError("Campaign scope belongs to another owner")
    service._check(db, app_id, actor, scope, "RUN_POST")
    return scope


def prepare_items(items, scope, db, app_id):
    prepared, seen = [], set()
    for item in items:
        due, operation, post = prepare_item(item, scope, db, app_id)
        if post["request_id"] in seen:
            raise Invalid("Scheduled request identities must be unique")
        seen.add(post["request_id"])
        value = dict(item_id=uid(), due_at=due.isoformat(), request=post)
        if "operation" in item:
            value["operation"] = operation
        prepared.append(value)
    return prepared


def prepare_item(item, scope, db, app_id):
    if not isinstance(item, dict) or set(item) not in ({"due_at", "request"}, {"due_at", "request", "operation"}):
        raise Invalid("Each scheduled item needs an exact due time and post")
    due = iso_time(item["due_at"])
    if not datetime.now(timezone.utc) < due < iso_time(scope.get("permission_expires_at", scope["expires_at"])):
        raise Invalid("Scheduled post must be due before scope expiry")
    operation = item.get("operation", "campaign.publish")
    if operation not in ("campaign.publish", "campaign.ad-launch"):
        raise Invalid("Unsupported scheduled campaign operation")
    post = ad_data(item["request"]) if operation == "campaign.ad-launch" else post_data(item["request"])
    if (
        post["content_hash"] not in scope["approved_content_hashes"]
        or post["rights_hash"] not in scope["approved_rights_hashes"]
    ):
        raise PermissionError("Scheduled post is outside campaign approval")
    check_measurement_schedule(db, app_id, scope, operation, post, due)
    return due, operation, post


def check_measurement_schedule(db, app_id, scope, operation, post, due):
    if operation == "campaign.ad-launch":
        check_paid_review(db, app_id, scope, post, due)
    plan = scope.get("measurement_plan")
    if plan:
        from .evidence_gate import measurement_plan

        parsed = measurement_plan(plan, retained=True)
        if operation == "campaign.publish" and post.get("link") != parsed["link"]:
            raise Invalid("The scheduled post must use the approved tagged link.")
        starts, ends = iso_time(parsed["starts_at"]), iso_time(parsed["ends_at"])
        if not starts <= due < ends:
            raise Invalid("Schedule work inside the approved measurement window.")
        if operation == "campaign.ad-launch" and iso_time(post["end_time"]) > ends:
            raise Invalid("Paid delivery must end inside the approved measurement window.")


def check_paid_review(db, app_id, scope, body, due):
    if (
        not scope["ad_account_id"]
        or body["targeting_hash"] not in scope["approved_targeting_hashes"]
        or body["lifetime_budget_minor"] > scope["max_campaign_minor"]
        or body["lifetime_budget_minor"] > scope["max_total_minor"]
        or not due < iso_time(body["end_time"]) <= iso_time(scope.get("permission_expires_at", scope["expires_at"]))
    ):
        raise PermissionError("Paid promotion exceeds the approved scope")
    post = db.execute(
        """SELECT result FROM campaign_intents WHERE app_id=? AND page_id=? AND remote_id=?
        AND status='VERIFIED' AND content_hash=? AND rights_hash=?""",
        (app_id, scope["page_id"], body["post_id"], body["content_hash"], body["rights_hash"]),
    ).fetchone()
    if post is None:
        raise PermissionError("Schedule only a verified saved Page post")
    if scope.get("measurement_plan"):
        from .evidence_gate import check_promotion_link

        check_promotion_link(post, scope["measurement_plan"])


def validate_items(rows, summary, *, require_future=True):
    if len(rows) != len(summary["items"]):
        raise Invalid("Scheduled items changed or are no longer in the future")
    for item in rows:
        body = json.loads(item["body"])
        if (
            digest(body) != item["body_hash"]
            or body not in summary["items"]
            or item["id"] != body["item_id"]
            or item["due"] != iso_time(body["due_at"]).timestamp()
            or (require_future and item["due"] <= time.time())
        ):
            raise Invalid("Scheduled items changed or are no longer in the future")


class CampaignSchedules:
    def __init__(self, store):
        self.store = store
        initialize(store)

    def prepare(self, app_id, body):
        actor = owner_context(self.store, app_id)
        if not isinstance(body, dict) or set(body) != {"scope_id", "items"}:
            raise Invalid("Provide the exact campaign scope and scheduled items")
        items = body["items"]
        if not isinstance(items, list) or not 1 <= len(items) <= MAX_ITEMS:
            raise Invalid("Choose one to twenty scheduled posts")
        from .campaign_access import policy_checker

        service = CampaignExecutionService(self.store, policy_checker(self.store))
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            scope = checked_scope(db, service, app_id, actor, body["scope_id"])
            identity = uid()
            prepared = prepare_items(items, scope, db, app_id)
            if any(item.get("operation") == "campaign.ad-launch" for item in prepared):
                service._check(db, app_id, actor, scope, "RUN_AD")
            summary = dict(
                batch_id=identity,
                app_id=app_id,
                owner=actor,
                scope_id=scope["scope_id"],
                scope_hash=scope["approval_hash"],
                items=prepared,
                permission_expires_at=scope["permission_expires_at"],
            )
            stamp = now()
            db.execute(
                "INSERT INTO campaign_schedule_batches VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    identity,
                    app_id,
                    actor,
                    scope["scope_id"],
                    canonical(summary),
                    digest(summary),
                    "DRAFT",
                    1,
                    stamp,
                    stamp,
                ),
            )
            for item in prepared:
                db.execute(
                    "INSERT INTO campaign_schedule_items VALUES(?,?,?,?,?,?,?,?,?)",
                    (
                        item["item_id"],
                        identity,
                        iso_time(item["due_at"]).timestamp(),
                        canonical(item),
                        digest(item),
                        "DRAFT",
                        None,
                        stamp,
                        stamp,
                    ),
                )
            audit(db, app_id, "prepared", dict(batch_id=identity, summary_hash=digest(summary)))
        return dict(summary=summary, summary_hash=digest(summary), status="DRAFT")

    def activate(self, app_id, batch_id, summary_hash):
        actor = owner_context(self.store, app_id)
        from .campaign_access import policy_checker

        service = CampaignExecutionService(self.store, policy_checker(self.store))
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM campaign_schedule_batches WHERE id=? AND app_id=?", (batch_id, app_id)
            ).fetchone()
            if row is None or row["owner"] != actor or row["status"] != "DRAFT":
                raise Invalid("Scheduled batch is unavailable for activation")
            summary = json.loads(row["summary"])
            scope = checked_scope(db, service, app_id, actor, row["scope_id"])
            if (
                digest(summary) != row["summary_hash"]
                or summary_hash != row["summary_hash"]
                or scope["approval_hash"] != summary["scope_hash"]
            ):
                raise Invalid("Scheduled batch or scope changed; review again")
            from .campaign_schedule_authority import check_deadline

            check_deadline(summary, scope["expires_at"])
            rows = db.execute("SELECT * FROM campaign_schedule_items WHERE batch_id=?", (batch_id,)).fetchall()
            validate_items(rows, summary)
            if scope.get("measurement_plan"):
                for item in summary["items"]:
                    check_measurement_schedule(
                        db,
                        app_id,
                        scope,
                        item.get("operation", "campaign.publish"),
                        item["request"],
                        iso_time(item["due_at"]),
                    )
            db.execute(
                "UPDATE campaign_schedule_batches SET status='ACTIVE',version=version+1,updated=? WHERE id=?",
                (now(), batch_id),
            )
            db.execute(
                "UPDATE campaign_schedule_items SET status='READY',updated=? WHERE batch_id=?", (now(), batch_id)
            )
            audit(db, app_id, "activated", dict(batch_id=batch_id, summary_hash=summary_hash))
        return self.status(app_id, batch_id)

    def status(self, app_id, batch_id):
        actor = owner_context(self.store, app_id)
        with connection(self.store.path) as db:
            row = db.execute(
                "SELECT * FROM campaign_schedule_batches WHERE id=? AND app_id=? AND owner=?", (batch_id, app_id, actor)
            ).fetchone()
            if row is None:
                raise Invalid("Scheduled batch is unavailable")
            try:
                summary = retained_object(row["summary"], row["summary_hash"])
                if summary.get("kind") == "ADMITTED_ORGANIC_VIDEO_V1":
                    from .organic_video_schedule import VideoSchedules

                    return VideoSchedules(self.store).status(app_id, batch_id)
                rows = db.execute(
                    "SELECT * FROM campaign_schedule_items WHERE batch_id=? ORDER BY due,id", (batch_id,)
                ).fetchall()
                items = [item_status(db, app_id, row["scope_id"], item) for item in rows]
                try:
                    validate_items(rows, summary, require_future=False)
                except Invalid:
                    progress = (
                        "NEEDS_RECONCILIATION"
                        if any(item["effective_status"] == "NEEDS_RECONCILIATION" for item in items)
                        else "NEEDS_REPAIR"
                    )
                else:
                    progress = batch_progress(db, row, summary, items, datetime.now(timezone.utc))
            except (Invalid, KeyError, TypeError, ValueError, OverflowError, RecursionError):
                return repair_view(row)
            return dict(
                id=row["id"],
                status=row["status"],
                version=row["version"],
                scope_id=row["scope_id"],
                summary=summary,
                summary_hash=row["summary_hash"],
                items=items,
                progress=progress,
            )

    def history(self, app_id):
        """Return the latest 50 owner-owned batches with saved local receipt state."""
        actor = owner_context(self.store, app_id)
        with connection(self.store.path) as db:
            ids = [
                row["id"]
                for row in db.execute(
                    "SELECT id FROM campaign_schedule_batches WHERE app_id=? AND owner=? ORDER BY created DESC,id DESC LIMIT 50",
                    (app_id, actor),
                )
            ]
        return {"batches": [self.status(app_id, identity) for identity in ids]}

    def revoke(self, app_id, batch_id, version):
        actor = owner_context(self.store, app_id)
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            member(db, app_id, actor, "OWNER")
            row = db.execute(
                "SELECT * FROM campaign_schedule_batches WHERE id=? AND app_id=? AND owner=?", (batch_id, app_id, actor)
            ).fetchone()
            if row is None or type(version) is not int or row["version"] != version:
                raise Invalid("Scheduled batch revision changed; reload")
            db.execute(
                "UPDATE campaign_schedule_batches SET status='OFF',version=version+1,updated=? WHERE id=?",
                (now(), batch_id),
            )
            db.execute(
                "UPDATE jobs SET status='CANCELLED',updated=? WHERE status='QUEUED' AND id IN (SELECT job_id FROM campaign_schedule_items WHERE batch_id=?)",
                (now(), batch_id),
            )
            db.execute(
                "UPDATE campaign_schedule_items SET status='CANCELLED',updated=? WHERE batch_id=? AND status IN ('READY','DRAFT')",
                (now(), batch_id),
            )
            audit(db, app_id, "off", dict(batch_id=batch_id, version=version + 1))
        return self.status(app_id, batch_id)


def audit(db, app_id, action, detail):
    db.execute(
        "INSERT INTO audit(app_id,action,detail,created) VALUES(?,?,?,?)",
        (app_id, "campaign_schedule." + action, canonical(detail), now()),
    )


def retained_object(raw, expected_hash):
    """Read a hash-bound schedule record without surfacing malformed contents."""
    try:
        value = json.loads(raw)
        if isinstance(value, dict) and digest(value) == expected_hash:
            return value
    except (TypeError, ValueError):
        pass
    raise Invalid("Retained schedule evidence needs repair")


def repair_view(row):
    return dict(
        id=row["id"],
        status="OFF" if row["status"] == "OFF" else "NEEDS_REPAIR",
        version=row["version"],
        scope_id=row["scope_id"],
        summary=None,
        summary_hash=None,
        items=[],
        evidence_unavailable=True,
        repair="Saved schedule evidence is unreadable. Check campaign receipts before retrying.",
    )


def batch_progress(
    db: Connection, batch: Row, summary: Mapping[str, object], items: Sequence[Mapping[str, object]], observed: datetime
) -> str:
    """Describe saved progress separately from the batch's persisted authority switch."""
    states = {item["effective_status"] for item in items}
    if "NEEDS_RECONCILIATION" in states:
        return "NEEDS_RECONCILIATION"
    if states and states <= {"VERIFIED", "ACTIVE_VERIFIED", "PAUSED_VERIFIED"}:
        return "DELIVERY_VERIFIED"
    if batch["status"] != "ACTIVE":
        return batch["status"]

    scope = db.execute(
        "SELECT * FROM campaign_scopes WHERE app_id=? AND id=? AND owner=?",
        (batch["app_id"], batch["scope_id"], batch["owner"]),
    ).fetchone()
    if (
        scope is None
        or scope["summary_hash"] != summary.get("scope_hash")
        or (summary.get("app_id"), summary.get("owner"), summary.get("scope_id"), summary.get("batch_id"))
        != (batch["app_id"], batch["owner"], batch["scope_id"], batch["id"])
    ):
        return "NEEDS_REPAIR"
    if scope["status"] != "ACTIVE":
        return "APPROVAL_INACTIVE"
    base = retained_object(scope["summary"], scope["summary_hash"])
    expiry = min(
        iso_time(summary.get("permission_expires_at", base["expires_at"])),
        iso_time(scope_view(db, scope)["permission_expires_at"]),
    )
    if expiry <= observed:
        return "APPROVAL_EXPIRED"
    if "BLOCKED" in states:
        return "BLOCKED"
    return "RUNNING" if "RUNNING" in states else "SCHEDULED"


def item_status(db, app_id, scope_id, item):
    job = (
        db.execute("SELECT status,result FROM jobs WHERE id=? AND app_id=?", (item["job_id"], app_id)).fetchone()
        if item["job_id"]
        else None
    )
    body = retained_object(item["body"], item["body_hash"])
    request = body.get("request")
    if (
        not isinstance(request, dict)
        or not isinstance(request.get("request_id"), str)
        or not isinstance(body.get("due_at"), str)
    ):
        raise Invalid("Retained schedule evidence needs repair")
    operation = body.get("operation", "campaign.publish")
    pause_confirmed = False
    if operation == "campaign.ad-launch":
        intent = db.execute(
            "SELECT id,status,ids,commitment,currency,app_id,scope_id,request_hash,account_id FROM campaign_paid_intents WHERE app_id=? AND scope_id=? AND request_id=? AND request_hash=?",
            (app_id, scope_id, request["request_id"], digest(request)),
        ).fetchone()
    else:
        intent = db.execute(
            "SELECT id,status,remote_id FROM campaign_intents WHERE app_id=? AND scope_id=? AND request_id=? AND request_hash=?",
            (app_id, scope_id, request["request_id"], digest(request)),
        ).fetchone()
    if intent is not None and operation == "campaign.ad-launch":
        if intent["status"] == "PAUSED_campaign":
            receipt = saved_pause_receipt(db, intent)
            pause_confirmed = receipt is not None and receipt["effective_status"] != "ACTIVE"
        intent = {key: intent[key] for key in ("id", "status", "ids", "commitment", "currency")}
    else:
        intent = dict(intent) if intent else None
    if intent and "ids" in intent:
        intent["ids"] = json.loads(intent["ids"])
    return dict(
        item_id=item["id"],
        due_at=body["due_at"],
        status=item["status"],
        operation=operation,
        effective_status=effective_status(item["status"], job, intent, operation, pause_confirmed),
        job_id=item["job_id"],
        job_status=job["status"] if job else None,
        **(
            {"attention": "This post points to an app removed from the App Store. Review the link before rescheduling."}
            if (item["status"] == "BLOCKED" or (job and job["status"] == "FAILED"))
            and removed_listing(db, app_id, request.get("link"))
            else {}
        ),
        intent=intent,
    )


def effective_status(item_status, job, intent, operation, pause_confirmed=False):
    if intent:
        state = intent["status"]
        if state == "VERIFIED" and operation == "campaign.publish":
            return "VERIFIED"
        if state == "ACTIVE_campaign" and operation == "campaign.ad-launch":
            return "ACTIVE_VERIFIED"
        if state == "PAUSED_campaign" and operation == "campaign.ad-launch":
            return "PAUSED_VERIFIED" if pause_confirmed else "NEEDS_RECONCILIATION"
        if job and job["status"] == "RUNNING":
            return "RUNNING"
        return "NEEDS_RECONCILIATION"
    if job:
        return {
            "QUEUED": "QUEUED",
            "RUNNING": "RUNNING",
            "CANCELLED": "CANCELLED",
            "BLOCKED": "BLOCKED",
            "FAILED": "BLOCKED",
            "SUCCEEDED": "NEEDS_RECONCILIATION",
        }.get(job["status"], "BLOCKED")
    return item_status


def due_payload(row):
    """Validate retained queue inputs before a single item can reserve a job."""
    body = retained_object(row["body"], row["body_hash"])
    summary = retained_object(row["summary"], row["summary_hash"])
    operation = body.get("operation", "campaign.publish")
    if (
        operation not in ("campaign.publish", "campaign.ad-launch", "organic-video.intent-execute")
        or not isinstance(body["request"], dict)
        or not isinstance(summary["items"], list)
        or body not in summary["items"]
        or body["item_id"] != row["id"]
        or (summary["batch_id"], summary["app_id"], summary["scope_id"])
        != (row["batch_id"], row["app_id"], row["scope_id"])
        or row["due"] != iso_time(body["due_at"]).timestamp()
    ):
        raise Invalid("Retained schedule inputs changed")
    data: dict[str, Any] = dict(
        batch_id=row["batch_id"], item_id=row["id"], scope_id=row["scope_id"], request=body["request"]
    )
    if "operation" in body:
        data["operation"] = operation
    action = "campaign_ad" if operation == "campaign.ad-launch" else "campaign_post"
    return action, data


def tick(store):
    """Atomically enqueue each due item once; no provider calls occur here."""
    initialize(store)
    from .publication_execution import initialize as execution_initialize
    from .publication_schedule import advance as advance_publications
    from .publication_schedule import initialize as publication_initialize

    publication_initialize(store)
    execution_initialize(store)
    count = 0
    with connection(store.path) as db:
        db.execute("BEGIN IMMEDIATE")
        count += advance_publications(db, store)
        from .organic_video_monitor import advance as advance_video

        count += advance_video(db, store)
        rows = db.execute(
            """SELECT i.*,b.app_id,b.scope_id,b.summary,b.summary_hash
            FROM campaign_schedule_items i JOIN campaign_schedule_batches b ON b.id=i.batch_id
            WHERE i.status='READY' AND b.status='ACTIVE' AND i.due<=?
            ORDER BY i.due,i.id LIMIT ?""",
            (time.time(), max(0, MAX_ITEMS - count)),
        ).fetchall()
        for row in rows:
            try:
                action, data = due_payload(row)
                if removed_listing(db, row["app_id"], data["request"].get("link")):
                    db.execute(
                        "UPDATE campaign_schedule_items SET status='BLOCKED',updated=? WHERE id=?",
                        (now(), row["id"]),
                    )
                    audit(db, row["app_id"], "blocked", dict(item_id=row["id"], reason="APP_STORE_LISTING_REMOVED"))
                    continue
            except (ValueError, TypeError, KeyError, OverflowError, OSError):
                db.execute(
                    "UPDATE campaign_schedule_items SET status='BLOCKED',updated=? WHERE id=?", (now(), row["id"])
                )
                audit(
                    db,
                    row["app_id"],
                    "blocked",
                    dict(batch_id=row["batch_id"], item_id=row["id"], reason="SAVED_ITEM_INTEGRITY"),
                )
                continue
            job_id = uid()
            db.execute(
                "INSERT INTO jobs(id,app_id,action,data,status,created,updated,request_key) VALUES(?,?,?,?,?,?,?,?)",
                (
                    job_id,
                    row["app_id"],
                    action,
                    canonical(data),
                    "QUEUED",
                    now(),
                    now(),
                    "campaign-schedule-" + row["id"],
                ),
            )
            db.execute(
                "UPDATE campaign_schedule_items SET status='QUEUED',job_id=?,updated=? WHERE id=? AND status='READY'",
                (job_id, now(), row["id"]),
            )
            audit(db, row["app_id"], "queued", dict(batch_id=row["batch_id"], item_id=row["id"], job_id=job_id))
            count += 1
    return count


def execute(store, job):
    from .campaign_access import policy_checker
    from .campaign_schedule_authority import bound

    with bound(store, job):
        data = job["data"]
        if data.get("operation") == "organic-video.intent-execute":
            from .campaign_video_execution import execute as execute_video

            return execute_video(store, job["app_id"], "schedule:" + job["id"], data["request"]["intent_id"], None)
        service = CampaignExecutionService(store, policy_checker(store))
        run = service.run_ad if data.get("operation") == "campaign.ad-launch" else service.run_post
        return run(job["app_id"], "schedule:" + job["id"], data["scope_id"], data["request"])
