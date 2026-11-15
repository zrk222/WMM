"""Request-local standing authority and commit/worker interlocks for fixed services."""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import AbstractContextManager, contextmanager
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path
from sqlite3 import Connection, Row
from typing import TYPE_CHECKING, NotRequired, Protocol, TypedDict, cast

from .common import Invalid, digest, iso_time

if TYPE_CHECKING:
    from .store import Store


class StandingExecutionContext(TypedDict):
    store: str
    id: str
    job_id: NotRequired[str]
    attempt: NotRequired[int]


class WorkerLease(TypedDict):
    id: str
    attempts: int


class ServiceLike(Protocol):
    store: Store


ACTIVE: ContextVar[StandingExecutionContext | None] = ContextVar("wmm_standing_execution", default=None)


def execution_row(db: Connection, identity: str) -> Row:
    """Require an exact retained execution; identity never comes from an envelope."""
    row = db.execute("SELECT * FROM automation_executions WHERE id=?", (identity,)).fetchone()
    if row is None:
        raise PermissionError("Standing execution is unavailable")
    return row


def _checked_policy(
    db: Connection, policy_id: object, observed: datetime
) -> tuple[Mapping[str, object], Mapping[str, object]]:
    from . import complete_automation

    check = cast(
        Callable[..., tuple[Mapping[str, object], Mapping[str, object]]],
        vars(complete_automation)["checked_policy"],
    )
    return check(db, policy_id, observed)


def _verify_access(store: Store, app_id: str, identity: str) -> None:
    from . import complete_automation

    verify = cast(Callable[..., None], vars(complete_automation)["verify_access"])
    verify(store, app_id, identity)


def capture_deadline(
    db: Connection,
    identity: str,
    policy: Mapping[str, object],
    grant: Mapping[str, object],
) -> None:
    """Freeze the parent permission clocks at admission in the same transaction."""
    from . import authority_expiry

    proposal = cast(dict[str, object], json.loads(cast(str, policy["proposal"])))
    limits = cast(Mapping[str, object], proposal["limits"])
    initial_base = cast(
        Callable[[object, object, object], str],
        vars(authority_expiry)["initial_base"],
    )
    base = initial_base(
        limits["expires"],
        policy["created"],
        proposal.get("extended_expiry_consent"),
    )
    policy_proof = authority_expiry.effective_expiry(db, "AUTOMATION", policy, base)
    grant_proof = authority_expiry.effective_expiry(db, "AGENT_GRANT", grant, grant["expires"])
    expiry = min(iso_time(policy_proof["expires"]), iso_time(grant_proof["expires"])).isoformat()
    data: dict[str, object] = dict(
        execution_id=identity,
        permission_expires_at=expiry,
        policy_revision=policy_proof["revision"],
        policy_hash=policy_proof["receipt_hash"],
        grant_revision=grant_proof["revision"],
        grant_hash=grant_proof["receipt_hash"],
    )
    data["record_hash"] = digest(data)
    db.execute("INSERT INTO automation_execution_authority VALUES (?,?,?,?,?,?,?)", tuple(data.values()))


def execution_deadline(db: Connection, execution: Row) -> datetime:
    """Legacy work keeps its original clipped clocks; new work keeps its captured clock."""
    saved = db.execute(
        "SELECT * FROM automation_execution_authority WHERE execution_id=?", (execution["id"],)
    ).fetchone()
    if saved:
        data = cast(
            dict[str, object],
            {key: saved[key] for key in saved.keys() if key != "record_hash"},  # noqa: SIM118 - sqlite3.Row
        )
        if digest(data) != saved["record_hash"]:
            raise PermissionError("Standing execution authority changed")
        return iso_time(saved["permission_expires_at"])
    policy = db.execute("SELECT summary FROM automation_policies WHERE id=?", (execution["policy_id"],)).fetchone()
    grant = db.execute("SELECT expires FROM agent_grants WHERE id=?", (execution["grant_id"],)).fetchone()
    if not policy or not grant:
        raise PermissionError("Standing execution original authority is unavailable")
    summary = cast(Mapping[str, object], json.loads(cast(str, policy["summary"])))
    return min(iso_time(summary["stops_at"]), iso_time(grant["expires"]))


def check_execution_deadline(db: Connection, execution: Row, observed: datetime) -> None:
    if execution_deadline(db, execution) <= observed:
        raise PermissionError("Standing execution approval expired; prepare new work")


def job_hash(job: Mapping[str, object]) -> str:
    """Bind immutable job intent separately from its changing status and lease."""
    return digest({key: job[key] for key in ("app_id", "action", "data", "request_key")})


def guard_connection(path: str | Path, db: Connection, committing: bool = False) -> None:
    """Recheck policy inside the same transaction as a local business commit."""
    context = ACTIVE.get()
    if context is None:
        return
    if str(Path(path).resolve()) != context["store"]:
        raise PermissionError("Standing execution cannot cross its local datastore")
    from .complete_automation import utc

    row = execution_row(db, context["id"])
    policy, _ = _checked_policy(db, row["policy_id"], utc())
    check_execution_deadline(db, row, utc())
    if policy["version"] != row["policy_version"]:
        raise PermissionError("Standing approval revision changed before commit")
    if context.get("job_id"):
        check_job(db, context, row)
    elif row["status"] != "DISPATCHED":
        raise PermissionError("Standing execution was cancelled or already completed")
    if committing and db.in_transaction and db.total_changes:
        db.execute(
            "UPDATE automation_executions SET write_commits=write_commits+1 WHERE id=?",
            (row["id"],),
        )


def check_job(db: Connection, context: StandingExecutionContext, execution: Row) -> None:
    """Cancelled, modified or replaced worker leases cannot inherit old authority."""
    job_id = context.get("job_id")
    attempt = context.get("attempt")
    if job_id is None or attempt is None:
        raise PermissionError("Standing job context is incomplete")
    row = db.execute(
        "SELECT j.*,s.execution_id,s.request_hash FROM jobs j JOIN automation_job_scopes s ON s.job_id=j.id WHERE j.id=?",
        (job_id,),
    ).fetchone()
    if (
        row is None
        or row["execution_id"] != execution["id"]
        or row["status"] != "RUNNING"
        or row["attempts"] != attempt
        or row["lease"] <= time.time()
    ):
        raise PermissionError("Standing job is cancelled or its worker lease changed")
    value = cast(dict[str, object], dict(row))
    value["data"] = json.loads(cast(str, value["data"]))
    if row["request_hash"] != job_hash(value):
        raise PermissionError("Standing job input changed after admission")
    data = cast(Mapping[str, object], value["data"])
    if data.get("native_runtime") == "IOS_LOCAL_V1":
        from . import ios_jobs

        source_hash = cast(Callable[..., str], vars(ios_jobs)["source_hash"])
        require_native_sources = cast(Callable[..., None], vars(ios_jobs)["require_native_sources"])
        app = db.execute("SELECT version,data FROM apps WHERE id=?", (row["app_id"],)).fetchone()
        if (
            app is None
            or app["version"] != data.get("manifest_version")
            or digest(json.loads(cast(str, app["data"]))) != data.get("manifest_hash")
            or source_hash(db, row["app_id"]) != data.get("source_hash")
        ):
            raise PermissionError("Standing native job sources changed before commit")
        require_native_sources(db, row["app_id"])


def attach_job(db: Connection, job: Mapping[str, object], created: bool) -> None:
    """Attach new owned jobs or retain an exact same-policy idempotent queue result."""
    context = ACTIVE.get()
    if context is None:
        return
    previous = db.execute(
        "SELECT s.*,e.policy_id FROM automation_job_scopes s JOIN automation_executions e ON e.id=s.execution_id WHERE s.job_id=?",
        (job["id"],),
    ).fetchone()
    if previous:
        original = execution_row(db, context["id"])
        if previous["policy_id"] != original["policy_id"] or previous["request_hash"] != job_hash(job):
            raise PermissionError("Existing job belongs to a different standing scope")
        return
    if not created:
        raise PermissionError("Standing scope cannot adopt an unrelated existing job")
    db.execute("INSERT INTO automation_job_scopes VALUES(?,?,?)", (job["id"], context["id"], job_hash(job)))


@contextmanager
def bound(store: Store, identity: str, job: WorkerLease | None = None) -> Iterator[None]:
    """Keep authority local to this request/worker and clear it even on failure."""
    value: StandingExecutionContext = {"store": str(store.path.resolve()), "id": identity}
    if job:
        value["job_id"] = job["id"]
        value["attempt"] = job["attempts"]
    token = ACTIVE.set(value)
    try:
        yield
    finally:
        ACTIVE.reset(token)


def start(store: Store, admission: Mapping[str, object], envelope: Mapping[str, object]) -> str:
    """Linearize dispatch against OFF and reject intent substitution or replay."""
    from .complete_automation import utc
    from .db import connection

    identity = cast(str, admission["automation_execution_id"])
    with connection(store.path) as db:
        db.execute("BEGIN IMMEDIATE")
        row = execution_row(db, identity)
        _checked_policy(db, row["policy_id"], utc())
        check_execution_deadline(db, row, utc())
        if (
            row["grant_id"] != admission["grant_id"]
            or row["input_hash"] != digest(envelope)
            or row["status"] != "ADMITTED"
        ):
            raise PermissionError("Standing dispatch binding changed or was already claimed")
        db.execute(
            "UPDATE automation_executions SET status='DISPATCHED',updated=? WHERE id=?",
            (utc().isoformat(), identity),
        )
    return identity


def finish(
    store: Store,
    identity: str,
    result: object = None,
    error: BaseException | None = None,
) -> None:
    """Persist outcome outside domain authority; partial failures stay uncertain."""
    from .complete_automation import utc
    from .db import connection

    with connection(store.path) as db:
        db.execute("BEGIN IMMEDIATE")
        row = execution_row(db, identity)
        if row["status"] not in ("DISPATCHED", "CANCEL_REQUESTED"):
            raise Invalid("Standing execution result is already recorded or was never dispatched")
        outcome = execution_outcome(row, error)
        try:
            result_hash = digest(result) if error is None else None
        except (TypeError, ValueError):
            result_hash, outcome = None, "UNKNOWN"
        db.execute(
            "UPDATE automation_executions SET status=?,result_hash=?,updated=? WHERE id=?",
            (outcome, result_hash, utc().isoformat(), identity),
        )


def execution_outcome(row: Row, error: BaseException | None) -> str:
    """Separate known success, cancelled work and partial-write uncertainty decisions."""
    from .operation_outcome import EffectUncertain

    if error is None:
        return "SUCCEEDED"
    if isinstance(error, EffectUncertain):
        return "UNKNOWN"
    if row["status"] == "CANCEL_REQUESTED":
        return "UNKNOWN" if row["write_commits"] else "CANCELLED"
    if isinstance(error, (Invalid, PermissionError, KeyError)) and not row["write_commits"]:
        return "FAILED"
    return "UNKNOWN"


def execute_admitted(
    service: ServiceLike,
    envelope: Mapping[str, object],
    admission: Mapping[str, object],
) -> object:
    """Use the fixed dispatcher with admitted context; legacy grants remain intact."""
    from . import operation_runtime, video_edit_projects
    from .operation_authority import bound_agent

    dispatcher = cast(
        Callable[[ServiceLike, Mapping[str, object]], object],
        vars(operation_runtime)["execute"],
    )
    admitted_caller = cast(
        Callable[[Mapping[str, object]], AbstractContextManager[None]],
        vars(video_edit_projects)["admitted_caller"],
    )
    with bound_agent(service.store, envelope, admission), admitted_caller(admission):
        return dispatch_admitted(service, envelope, admission, dispatcher)


def dispatch_admitted(
    service: ServiceLike,
    envelope: Mapping[str, object],
    admission: Mapping[str, object],
    execute: Callable[[ServiceLike, Mapping[str, object]], object],
) -> object:
    """Retain exact admission and standing-write guards within the caller context."""
    if "automation_execution_id" not in admission:
        return execute(service, envelope)
    identity = start(service.store, admission, envelope)
    try:
        with bound(service.store, identity):
            result = execute(service, envelope)
    except BaseException as error:
        finish(service.store, identity, error=error)
        raise
    finish(service.store, identity, result=result)
    return result


@contextmanager
def job_execution(store: Store, job: WorkerLease) -> Iterator[None]:
    """Workers inherit only their durable exact job scope, never ambient credentials."""
    from .complete_automation import utc
    from .db import connection

    with connection(store.path) as db:
        row = db.execute("SELECT execution_id FROM automation_job_scopes WHERE job_id=?", (job["id"],)).fetchone()
        if row is not None:
            execution = execution_row(db, row["execution_id"])
            policy, summary = _checked_policy(db, execution["policy_id"], utc())
            check_execution_deadline(db, execution, utc())
            inventory = cast(Mapping[str, object], summary["inventory"])
            selection = cast(Mapping[str, object], inventory["selection"])
            _verify_access(
                store,
                cast(str, policy["app_id"]),
                cast(str, selection["agent_connection_id"]),
            )
    if row is None:
        yield
        return
    with bound(store, cast(str, row["execution_id"]), job):
        with connection(store.path):
            pass
        yield
