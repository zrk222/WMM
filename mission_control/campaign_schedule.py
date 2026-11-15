"""Finite owner-reviewed Page post and existing-post promotion schedules."""

import json
import time
from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractContextManager
from datetime import datetime, timezone
from sqlite3 import Connection, Row
from typing import Any, Protocol, cast

from .app_launch_history import removed_listing
from .campaign_contract import ad_data, post_data
from .campaign_execution import CampaignExecutionService
from .common import Invalid, canonical, digest, iso_time, now, uid
from .db import connection
from .review_access import member
from .store import Store


class VideoStatusLike(Protocol):
    def status(self, app_id: str, batch_id: str) -> dict[str, object]: ...


class CampaignServiceLike(Protocol):
    def _row(self, db: Connection, app_id: str, scope_id: str) -> Row | None: ...

    def _check(
        self,
        db: Connection,
        app_id: str,
        actor: str,
        scope: Mapping[str, object],
        action: str,
        active: bool = True,
    ) -> None: ...

    def run_post(self, app_id: str, actor: str, scope_id: str, body: Mapping[str, object]) -> object: ...

    def run_ad(self, app_id: str, actor: str, scope_id: str, body: Mapping[str, object]) -> object: ...


def _scope_view(db: Connection, row: Row | None) -> Mapping[str, object]:
    from . import campaign_execution

    return cast(
        Callable[[Connection, Row | None], Mapping[str, object]],
        vars(campaign_execution).get("scope_view"),
    )(db, row)


def _saved_pause_receipt(db: Connection, intent: Mapping[str, object]) -> Mapping[str, object] | None:
    from . import campaign_execution

    value = cast(
        Callable[[Connection, Mapping[str, object]], Mapping[str, object] | None],
        vars(campaign_execution).get("saved_pause_receipt"),
    )(db, intent)
    return value


def _identity(store: Store, app_id: str) -> tuple[Mapping[str, object], str]:
    from . import campaign_access

    context, actor = cast(
        Callable[[Store, str], tuple[Mapping[str, object], str]],
        vars(campaign_access).get("identity"),
    )(store, app_id)
    return context, actor


def _policy_checker(store: Store) -> object:
    from . import campaign_access

    return cast(
        Callable[[Store], object],
        vars(campaign_access).get("policy_checker"),
    )(store)


def _service(store: Store) -> CampaignServiceLike:
    return cast(
        CampaignServiceLike,
        CampaignExecutionService(store, _policy_checker(store)),
    )


def _service_check(
    service: CampaignServiceLike,
    db: Connection,
    app_id: str,
    actor: str,
    scope: Mapping[str, object],
    action: str,
) -> None:
    check = cast(
        Callable[..., None] | None,
        getattr(service, _CHECK, None),
    )
    if check is None:
        raise RuntimeError("Campaign schedule authority check is unavailable")
    check(db, app_id, actor, scope, action)


def _check_deadline(summary: Mapping[str, object], expires_at: object) -> None:
    from . import campaign_schedule_authority

    cast(
        Callable[[Mapping[str, object], object], None],
        vars(campaign_schedule_authority).get("check_deadline"),
    )(summary, expires_at)


def _bound(store: Store, job: Row) -> AbstractContextManager[None]:
    from . import campaign_schedule_authority

    return cast(
        Callable[[Store, Row], AbstractContextManager[None]],
        vars(campaign_schedule_authority).get("bound"),
    )(store, job)


MAX_ITEMS = 20
_ROW = "_row"
_CHECK = "_check"
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


def initialize(store: Store) -> None:
    with connection(store.path) as db:
        db.executescript(SCHEMA)


def schedule_table_exists(db: Connection) -> bool:
    return (
        db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='campaign_schedule_batches'").fetchone()
        is not None
    )


def owner_context(store: Store, app_id: str) -> str:
    context, actor = _identity(store, app_id)
    if "principal" not in context:
        raise PermissionError("A freshly authenticated owner is required")
    return actor


def checked_scope(
    db: Connection,
    service: CampaignServiceLike,
    app_id: str,
    actor: str,
    scope_id: str,
) -> Mapping[str, object]:
    row_fn = cast(
        Callable[[Connection, str, str], Row | None] | None,
        getattr(service, _ROW, None),
    )
    if row_fn is None:
        raise RuntimeError("Campaign schedule row reader is unavailable")
    row = row_fn(db, app_id, scope_id)
    scope = _scope_view(db, row)
    if scope["owner_principal"] != actor:
        raise PermissionError("Campaign scope belongs to another owner")
    _service_check(service, db, app_id, actor, scope, "RUN_POST")
    return scope


def prepare_items(
    items: Sequence[object],
    scope: Mapping[str, object],
    db: Connection,
    app_id: str,
) -> list[dict[str, object]]:
    prepared: list[dict[str, object]] = []
    seen: set[object] = set()
    for item in items:
        due, operation, post = prepare_item(item, scope, db, app_id)
        if post["request_id"] in seen:
            raise Invalid("Scheduled request identities must be unique")
        seen.add(post["request_id"])
        value: dict[str, object] = dict(item_id=uid(), due_at=due.isoformat(), request=post)
        if "operation" in cast(Mapping[str, object], item):
            value["operation"] = operation
        prepared.append(value)
    return prepared


def prepare_item(
    item: object,
    scope: Mapping[str, object],
    db: Connection,
    app_id: str,
) -> tuple[datetime, str, Mapping[str, object]]:
    if not isinstance(item, dict):
        raise Invalid("Each scheduled item needs an exact due time and post")
    item = cast(dict[str, object], item)
    if set(item) not in (
        {"due_at", "request"},
        {"due_at", "request", "operation"},
    ):
        raise Invalid("Each scheduled item needs an exact due time and post")
    due = iso_time(item["due_at"])
    if not datetime.now(timezone.utc) < due < iso_time(scope.get("permission_expires_at", scope["expires_at"])):
        raise Invalid("Scheduled post must be due before scope expiry")
    operation = item.get("operation", "campaign.publish")
    if operation not in ("campaign.publish", "campaign.ad-launch"):
        raise Invalid("Unsupported scheduled campaign operation")
    post: Mapping[str, object] = (
        ad_data(item["request"]) if operation == "campaign.ad-launch" else post_data(item["request"])
    )
    if post["content_hash"] not in cast(list[object], scope["approved_content_hashes"]) or post[
        "rights_hash"
    ] not in cast(list[object], scope["approved_rights_hashes"]):
        raise PermissionError("Scheduled post is outside campaign approval")
    check_measurement_schedule(db, app_id, scope, cast(str, operation), post, due)
    return due, cast(str, operation), post


def check_measurement_schedule(
    db: Connection,
    app_id: str,
    scope: Mapping[str, object],
    operation: str,
    post: Mapping[str, object],
    due: datetime,
) -> None:
    if operation == "campaign.ad-launch":
        check_paid_review(db, app_id, scope, post, due)
    plan = scope.get("measurement_plan")
    if plan:
        from .evidence_gate import measurement_plan

        parsed = cast(Mapping[str, object], measurement_plan(plan, retained=True))
        if operation == "campaign.publish" and post.get("link") != parsed["link"]:
            raise Invalid("The scheduled post must use the approved tagged link.")
        starts, ends = iso_time(parsed["starts_at"]), iso_time(parsed["ends_at"])
        if not starts <= due < ends:
            raise Invalid("Schedule work inside the approved measurement window.")
        if operation == "campaign.ad-launch" and iso_time(post["end_time"]) > ends:
            raise Invalid("Paid delivery must end inside the approved measurement window.")


def check_paid_review(
    db: Connection,
    app_id: str,
    scope: Mapping[str, object],
    body: Mapping[str, object],
    due: datetime,
) -> None:
    if (
        not scope["ad_account_id"]
        or body["targeting_hash"] not in cast(list[object], scope["approved_targeting_hashes"])
        or cast(int, body["lifetime_budget_minor"]) > cast(int, scope["max_campaign_minor"])
        or cast(int, body["lifetime_budget_minor"]) > cast(int, scope["max_total_minor"])
        or not due < iso_time(body["end_time"]) <= iso_time(scope.get("permission_expires_at", scope["expires_at"]))
    ):
        raise PermissionError("Paid promotion exceeds the approved scope")
    post = db.execute(
        """SELECT result FROM campaign_intents WHERE app_id=? AND page_id=? AND remote_id=?
        AND status='VERIFIED' AND content_hash=? AND rights_hash=?""",
        (
            app_id,
            scope["page_id"],
            body["post_id"],
            body["content_hash"],
            body["rights_hash"],
        ),
    ).fetchone()
    if post is None:
        raise PermissionError("Schedule only a verified saved Page post")
    if scope.get("measurement_plan"):
        from .evidence_gate import check_promotion_link

        check_promotion_link(post, scope["measurement_plan"])


def validate_items(
    rows: Sequence[Row],
    summary: Mapping[str, object],
    *,
    require_future: bool = True,
) -> None:
    summary_items = cast(list[object], summary["items"])
    if len(rows) != len(summary_items):
        raise Invalid("Scheduled items changed or are no longer in the future")
    for item in rows:
        body = cast(Mapping[str, object], json.loads(cast(str, item["body"])))
        if (
            digest(body) != item["body_hash"]
            or body not in summary_items
            or item["id"] != body["item_id"]
            or item["due"] != iso_time(body["due_at"]).timestamp()
            or (require_future and item["due"] <= time.time())
        ):
            raise Invalid("Scheduled items changed or are no longer in the future")


class CampaignSchedules:
    def __init__(self, store: Store) -> None:
        self.store = store

    def prepare(self, app_id: str, body: object) -> dict[str, object]:
        actor = owner_context(self.store, app_id)
        if not isinstance(body, dict):
            raise Invalid("Provide the exact campaign scope and scheduled items")
        body = cast(dict[str, object], body)
        if set(body) != {"scope_id", "items"}:
            raise Invalid("Provide the exact campaign scope and scheduled items")
        items = body["items"]
        if not isinstance(items, list):
            raise Invalid("Choose one to twenty scheduled posts")
        items = cast(list[object], items)
        if not 1 <= len(items) <= MAX_ITEMS:
            raise Invalid("Choose one to twenty scheduled posts")
        initialize(self.store)
        service = _service(self.store)
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            scope = checked_scope(db, service, app_id, actor, cast(str, body["scope_id"]))
            identity = uid()
            prepared = prepare_items(items, scope, db, app_id)
            if any(item.get("operation") == "campaign.ad-launch" for item in prepared):
                _service_check(service, db, app_id, actor, scope, "RUN_AD")
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

    def activate(self, app_id: str, batch_id: str, summary_hash: str) -> dict[str, object]:
        actor = owner_context(self.store, app_id)
        service = _service(self.store)
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            if not schedule_table_exists(db):
                raise Invalid("Scheduled batch is unavailable for activation")
            row = db.execute(
                "SELECT * FROM campaign_schedule_batches WHERE id=? AND app_id=?", (batch_id, app_id)
            ).fetchone()
            if row is None or row["owner"] != actor or row["status"] != "DRAFT":
                raise Invalid("Scheduled batch is unavailable for activation")
            summary = cast(Mapping[str, object], json.loads(cast(str, row["summary"])))
            scope = checked_scope(db, service, app_id, actor, cast(str, row["scope_id"]))
            if (
                digest(summary) != row["summary_hash"]
                or summary_hash != row["summary_hash"]
                or scope["approval_hash"] != summary["scope_hash"]
            ):
                raise Invalid("Scheduled batch or scope changed; review again")
            _check_deadline(summary, scope["expires_at"])
            rows = db.execute("SELECT * FROM campaign_schedule_items WHERE batch_id=?", (batch_id,)).fetchall()
            validate_items(rows, summary)
            if scope.get("measurement_plan"):
                for item in cast(list[Mapping[str, object]], summary["items"]):
                    check_measurement_schedule(
                        db,
                        app_id,
                        scope,
                        cast(str, item.get("operation", "campaign.publish")),
                        cast(Mapping[str, object], item["request"]),
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

    def status(self, app_id: str, batch_id: str) -> dict[str, object]:
        actor = owner_context(self.store, app_id)
        with connection(self.store.path) as db:
            if not schedule_table_exists(db):
                raise Invalid("Scheduled batch is unavailable")
            row = db.execute(
                "SELECT * FROM campaign_schedule_batches WHERE id=? AND app_id=? AND owner=?", (batch_id, app_id, actor)
            ).fetchone()
            if row is None:
                raise Invalid("Scheduled batch is unavailable")
            try:
                summary = retained_object(row["summary"], row["summary_hash"])
                if summary.get("kind") == "ADMITTED_ORGANIC_VIDEO_V1":
                    from . import organic_video_schedule

                    video_cls = cast(
                        Callable[[Store], object],
                        vars(organic_video_schedule).get("VideoSchedules"),
                    )
                    video = cast(VideoStatusLike, video_cls(self.store))
                    return video.status(app_id, batch_id)
                rows = db.execute(
                    "SELECT * FROM campaign_schedule_items WHERE batch_id=? ORDER BY due,id", (batch_id,)
                ).fetchall()
                items = [item_status(db, app_id, cast(str, row["scope_id"]), item) for item in rows]
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

    def history(self, app_id: str) -> dict[str, object]:
        """Return the latest 50 owner-owned batches with saved local receipt state."""
        actor = owner_context(self.store, app_id)
        with connection(self.store.path) as db:
            if not schedule_table_exists(db):
                return {"batches": []}
            ids = [
                cast(str, row["id"])
                for row in db.execute(
                    "SELECT id FROM campaign_schedule_batches WHERE app_id=? AND owner=? ORDER BY created DESC,id DESC LIMIT 50",
                    (app_id, actor),
                )
            ]
        return {"batches": [self.status(app_id, identity) for identity in ids]}

    def revoke(self, app_id: str, batch_id: str, version: int) -> dict[str, object]:
        actor = owner_context(self.store, app_id)
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            member(db, app_id, actor, "OWNER")
            if not schedule_table_exists(db):
                raise Invalid("Scheduled batch is unavailable")
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


def audit(db: Connection, app_id: str, action: str, detail: object) -> None:
    db.execute(
        "INSERT INTO audit(app_id,action,detail,created) VALUES(?,?,?,?)",
        (app_id, "campaign_schedule." + action, canonical(detail), now()),
    )


def retained_object(raw: object, expected_hash: object) -> dict[str, object]:
    """Read a hash-bound schedule record without surfacing malformed contents."""
    try:
        value = json.loads(cast(str, raw))
        if isinstance(value, dict):
            record = cast(dict[str, object], value)
            if digest(record) == expected_hash:
                return record
    except (TypeError, ValueError):
        pass
    raise Invalid("Retained schedule evidence needs repair")


def repair_view(row: Row) -> dict[str, object]:
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
        iso_time(_scope_view(db, scope)["permission_expires_at"]),
    )
    if expiry <= observed:
        return "APPROVAL_EXPIRED"
    if "BLOCKED" in states:
        return "BLOCKED"
    return "RUNNING" if "RUNNING" in states else "SCHEDULED"


def item_status(db: Connection, app_id: str, scope_id: str, item: Row) -> dict[str, object]:
    job = (
        db.execute("SELECT status,result FROM jobs WHERE id=? AND app_id=?", (item["job_id"], app_id)).fetchone()
        if item["job_id"]
        else None
    )
    body = retained_object(item["body"], item["body_hash"])
    raw_request = body.get("request")
    if not isinstance(raw_request, dict):
        raise Invalid("Retained schedule evidence needs repair")
    request = cast(Mapping[str, object], raw_request)
    if not isinstance(request.get("request_id"), str) or not isinstance(body.get("due_at"), str):
        raise Invalid("Retained schedule evidence needs repair")
    operation = cast(str, body.get("operation", "campaign.publish"))
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
    parsed_intent: dict[str, object] | None
    if intent is not None and operation == "campaign.ad-launch":
        source = cast(Mapping[str, object], intent)
        if source["status"] == "PAUSED_campaign":
            receipt = _saved_pause_receipt(db, source)
            pause_confirmed = receipt is not None and receipt["effective_status"] == "PAUSED"
        parsed_intent = {key: source[key] for key in ("id", "status", "ids", "commitment", "currency")}
    else:
        parsed_intent = cast(dict[str, object], dict(intent)) if intent else None
    if parsed_intent and "ids" in parsed_intent:
        parsed_intent["ids"] = json.loads(cast(str, parsed_intent["ids"]))
    return dict(
        item_id=item["id"],
        due_at=body["due_at"],
        status=item["status"],
        operation=operation,
        effective_status=effective_status(cast(str, item["status"]), job, parsed_intent, operation, pause_confirmed),
        job_id=item["job_id"],
        job_status=job["status"] if job else None,
        **(
            {"attention": "This post points to an app removed from the App Store. Review the link before rescheduling."}
            if (item["status"] == "BLOCKED" or (job and job["status"] == "FAILED"))
            and removed_listing(db, app_id, request.get("link"))
            else {}
        ),
        intent=parsed_intent,
    )


def effective_status(
    item_status: str,
    job: Row | None,
    intent: Mapping[str, object] | None,
    operation: str,
    pause_confirmed: bool = False,
) -> str:
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


def due_payload(row: Row) -> tuple[str, dict[str, Any]]:
    """Validate retained queue inputs before a single item can reserve a job."""
    body = retained_object(row["body"], row["body_hash"])
    summary = retained_object(row["summary"], row["summary_hash"])
    operation = cast(str, body.get("operation", "campaign.publish"))
    if (
        operation not in ("campaign.publish", "campaign.ad-launch", "organic-video.intent-execute")
        or not isinstance(body["request"], dict)
        or not isinstance(summary["items"], list)
    ):
        raise Invalid("Retained schedule inputs changed")
    items = cast(list[object], summary["items"])
    if (
        body not in items
        or body["item_id"] != row["id"]
        or (summary["batch_id"], summary["app_id"], summary["scope_id"])
        != (row["batch_id"], row["app_id"], row["scope_id"])
        or row["due"] != iso_time(body["due_at"]).timestamp()
    ):
        raise Invalid("Retained schedule inputs changed")
    data: dict[str, Any] = dict(
        batch_id=row["batch_id"],
        item_id=row["id"],
        scope_id=row["scope_id"],
        request=cast(Mapping[str, object], body["request"]),
    )
    if "operation" in body:
        data["operation"] = operation
    action = "campaign_ad" if operation == "campaign.ad-launch" else "campaign_post"
    return action, data


def tick(store: Store) -> int:
    """Atomically enqueue each due item once; no provider calls occur here."""
    initialize(store)
    from . import organic_video_monitor, publication_execution, publication_schedule

    publication_initialize = cast(
        Callable[[Store], None],
        vars(publication_schedule).get("initialize"),
    )
    execution_initialize = cast(
        Callable[[Store], None],
        vars(publication_execution).get("initialize"),
    )
    publication_initialize(store)
    execution_initialize(store)
    advance_publications = cast(
        Callable[[Connection, Store], int],
        vars(publication_schedule).get("advance"),
    )
    advance_video = cast(
        Callable[[Connection, Store], int],
        vars(organic_video_monitor).get("advance"),
    )
    count = 0
    with connection(store.path) as db:
        db.execute("BEGIN IMMEDIATE")
        count += advance_publications(db, store)
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


def execute(store: Store, job: Row) -> object:
    from . import campaign_video_execution

    with _bound(store, job):
        data = cast(Mapping[str, object], job["data"])
        operation = data.get("operation")
        if operation == "organic-video.intent-execute":
            request = cast(Mapping[str, object], data["request"])
            execute_video = cast(
                Callable[[Store, str, str, str, object], object],
                vars(campaign_video_execution).get("execute"),
            )
            return execute_video(
                store,
                cast(str, job["app_id"]),
                "schedule:" + cast(str, job["id"]),
                cast(str, request["intent_id"]),
                None,
            )
        service = _service(store)
        run = service.run_ad if operation == "campaign.ad-launch" else service.run_post
        return run(
            cast(str, job["app_id"]),
            "schedule:" + cast(str, job["id"]),
            cast(str, data["scope_id"]),
            cast(Mapping[str, object], data["request"]),
        )
