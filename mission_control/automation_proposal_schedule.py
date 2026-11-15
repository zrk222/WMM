"""Bounded local evaluation on the existing WMM worker, in one durable transaction."""

import json
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from sqlite3 import Connection, Row
from typing import cast

from .automation_proposals import RuleRef, duration, evaluate_in_snapshot, version_matches
from .automation_rule_report_integration import integrate, prepare, saved_action
from .automation_rules import _study_facts
from .automation_store import version_in_snapshot
from .common import Invalid, canonical, digest, iso_time, now, safe_data
from .db import connection
from .review_access import exact_role, member
from .store import Store

ENABLED_FIELDS = {"enabled", "version", "app_version", "saved", "study", "interval_hours", "expires_at", "max_runs"}


def schedule_row(db: Connection, app_id: str) -> Row | None:
    return db.execute("SELECT * FROM automation_rule_schedules WHERE app_id=?", (app_id,)).fetchone()


def view(row: Row) -> dict[str, object]:
    try:
        binding = checked_definition(row)
    except (Invalid, TypeError, ValueError):
        binding = None
    return {
        "version": row["version"],
        "status": row["status"] if binding is not None or row["status"] == "OFF" else "BLOCKED",
        "next_due": row["next_due"] if row["status"] == "ACTIVE" else None,
        "expires_at": row["expires"],
        "run_count": row["run_count"],
        "max_runs": row["max_runs"],
        "latest_receipt_id": row["receipt_id"],
        "reason": row["stopped_reason"],
        "binding": binding,
        "mode": "SAVE_PRIVATE_REPORT" if binding and "report_integration" in binding else "PROPOSE_ONLY",
    }


def checked_definition(row: Row) -> dict:
    document = json.loads(row["definition"])
    if not isinstance(document, dict) or digest(document) != row["definition_hash"]:
        raise Invalid("Saved schedule definition changed")
    if (
        document.get("expires_at") != row["expires"]
        or document.get("max_runs") != row["max_runs"]
        or document.get("app_version") != row["app_version"]
        or not 1 <= row["max_runs"] <= 30
        or not 0 <= row["run_count"] <= row["max_runs"]
    ):
        raise Invalid("Saved schedule limits changed")
    return document


def read(store: Store, app_id: str, owner: str) -> dict[str, object] | None:
    with connection(store.path) as db:
        db.execute("BEGIN")
        member(db, app_id, owner, "OWNER")
        row = schedule_row(db, app_id)
        if row is None or row["owner"] != owner:
            return None
        result = view(row)
        binding = cast(dict | None, result["binding"])
        if binding and "report_integration" in binding:
            try:
                result["saved_report"] = saved_action(db, app_id, owner, binding["report_integration"]["capture_key"])
            except Invalid:
                result["saved_report"] = None
        return result


def configure(
    store: Store,
    app_id: str,
    owner: str,
    body: dict,
    *,
    commit_check: Callable[[], object] | None = None,
) -> dict[str, object]:
    """Enable a finite schedule or stop its exact currently saved version."""
    enabled, expected = validated_request(body)
    with connection(store.path, write=True) as db:
        stamp = iso_time(now()).astimezone(timezone.utc)
        role = member(db, app_id, owner, "OWNER")
        row = exact_schedule(db, app_id, owner, expected)
        if enabled:
            save_enabled(db, store, app_id, owner, role["version"], body, stamp)
        elif row is None:
            raise Invalid("There is no rule schedule to turn off")
        else:
            db.execute(
                "UPDATE automation_rule_schedules SET status='OFF',version=version+1,stopped_reason=NULL WHERE app_id=?",
                (app_id,),
            )
        saved = schedule_row(db, app_id)
        if commit_check is not None:
            commit_check()
        return view(cast(Row, saved))


def validated_request(body: dict) -> tuple[bool, int | None]:
    safe_data(body)
    enabled = body.get("enabled")
    allowed = (ENABLED_FIELDS, ENABLED_FIELDS | {"report_integration"}) if enabled else ({"enabled", "version"},)
    if type(enabled) is not bool or set(body) not in allowed:
        raise Invalid("Choose the exact schedule fields")
    expected = body["version"]
    if expected is not None and (type(expected) is not int or expected < 1):
        raise Invalid("Choose the current rule schedule version")
    return enabled, expected


def exact_schedule(db: Connection, app_id: str, owner: str, expected: int | None) -> Row | None:
    row = schedule_row(db, app_id)
    if expected != (row["version"] if row is not None else None):
        raise Invalid("Rule schedule changed. Refresh and review it.")
    if row is not None and row["owner"] != owner:
        raise PermissionError("This schedule belongs to a different owner")
    return row


def save_enabled(
    db: Connection, store: Store, app_id: str, owner: str, owner_version: int, body: dict, stamp: datetime
) -> None:
    version_matches(db, app_id, body["app_version"])
    saved = version_in_snapshot(db, app_id, body["saved"])
    interval, max_runs = body["interval_hours"], body["max_runs"]
    if type(interval) is not int or not 1 <= interval <= 24 or type(max_runs) is not int or not 1 <= max_runs <= 30:
        raise Invalid("Choose 1 to 24 hours between reviews and 1 to 30 evaluations")
    expiry = iso_time(body["expires_at"]).astimezone(timezone.utc)
    first_due = stamp + timedelta(hours=interval)
    if not first_due < expiry <= stamp + timedelta(days=7):
        raise Invalid("End after the first evaluation and within seven days")
    if saved is None:
        raise Invalid("The saved rule version is unavailable")
    for rule in saved["document"]["rules"]:
        duration(rule["cooldown"])
    timestamp = stamp.isoformat(timespec="microseconds")
    study = _study_facts(db, app_id, body["study"], timestamp) if body["study"] is not None else None
    definition = {**body, "expires_at": expiry.isoformat(timespec="microseconds")}
    if "report_integration" in body:
        definition["report_integration"] = prepare(db, store, app_id, owner, body, saved["document"], study)
    db.execute(
        """INSERT INTO automation_rule_schedules VALUES(?,?,?,?,?,?,?,?,?,?,?,'ACTIVE',NULL,NULL)
           ON CONFLICT(app_id) DO UPDATE SET
              owner=excluded.owner,owner_version=excluded.owner_version,app_version=excluded.app_version,
              version=excluded.version,definition=excluded.definition,definition_hash=excluded.definition_hash,
              next_due=excluded.next_due,expires=excluded.expires,run_count=0,max_runs=excluded.max_runs,
              status='ACTIVE',receipt_id=NULL,stopped_reason=NULL""",
        (
            app_id,
            owner,
            owner_version,
            body["app_version"],
            (body["version"] or 0) + 1,
            canonical(definition),
            digest(definition),
            first_due.isoformat(timespec="microseconds"),
            expiry.isoformat(timespec="microseconds"),
            0,
            max_runs,
        ),
    )


def stop(db: Connection, row: Row, state: str, reason: str | None = None) -> None:
    db.execute(
        "UPDATE automation_rule_schedules SET status=?,stopped_reason=? WHERE app_id=?",
        (state, reason, row["app_id"]),
    )


def ready(db: Connection, row: Row, stamp: datetime, expires: datetime) -> bool:
    if expires <= stamp:
        stop(db, row, "EXPIRED")
        return False
    if row["run_count"] >= row["max_runs"]:
        stop(db, row, "EXHAUSTED")
        return False
    return iso_time(row["next_due"]) <= stamp


def evaluate_due(store: Store, app_id: str, clock: datetime | None = None) -> None:
    with connection(store.path, write=True) as db:
        row = schedule_row(db, app_id)
        if row is None or row["status"] != "ACTIVE":
            return
        stamp = clock if clock is not None else iso_time(now()).astimezone(timezone.utc)
        db.execute("SAVEPOINT rule_due")
        try:
            definition = checked_definition(row)
            expires = iso_time(row["expires"])
            if not ready(db, row, stamp, expires):
                return
            exact_role(db, app_id, row["owner"], row["owner_version"], "OWNER")
            receipt = evaluate_in_snapshot(
                db,
                app_id,
                row["owner"],
                row["app_version"],
                cast(RuleRef, definition["saved"]),
                stamp.isoformat(timespec="microseconds"),
                study=definition["study"],
                slot=digest([row["version"], row["next_due"]]),
            )
            if "report_integration" in definition:
                integrate(db, store, app_id, row["owner"], definition["report_integration"], receipt)
            finished = clock if clock is not None else iso_time(now()).astimezone(timezone.utc)
            if finished >= expires:
                db.execute("ROLLBACK TO rule_due")
                stop(db, row, "EXPIRED")
                return
        except (Invalid, PermissionError, KeyError, ValueError, TypeError):
            db.execute("ROLLBACK TO rule_due")
            stop(
                db,
                row,
                "BLOCKED",
                "Review the app, saved rules, study and any selected private report before starting again.",
            )
            return
        finally:
            db.execute("RELEASE rule_due")
        next_due = finished + timedelta(hours=definition["interval_hours"])
        state = "EXHAUSTED" if row["run_count"] + 1 >= row["max_runs"] else "ACTIVE"
        db.execute(
            """UPDATE automation_rule_schedules
               SET run_count=run_count+1,next_due=?,receipt_id=?,status=? WHERE app_id=?""",
            (next_due.isoformat(timespec="microseconds"), receipt["id"], state, app_id),
        )


def tick(store: Store) -> int:
    """Process a small due batch; each transaction rechecks current owner consent."""
    stamp = iso_time(now()).astimezone(timezone.utc)
    with connection(store.path) as db:
        rows = db.execute(
            """SELECT app_id FROM automation_rule_schedules
               WHERE status='ACTIVE' AND (next_due<=? OR expires<=?) ORDER BY next_due LIMIT 8""",
            (stamp.isoformat(timespec="microseconds"), stamp.isoformat(timespec="microseconds")),
        ).fetchall()
    for row in rows:
        evaluate_due(store, row["app_id"])
    return len(rows)
