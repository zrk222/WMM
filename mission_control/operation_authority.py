"""Trusted request-local execution scope, separate from public actor attribution."""

import json
import sqlite3
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol, cast

from .common import canonical, digest
from .schema_types import AgentGrantsRow
from .store import Store


class IdentitiesLike(Protocol):
    def local(self, session: str, principal: str, generation: str | None = None) -> Mapping[str, object]: ...


Context = dict[str, object]

REQUEST: ContextVar[Context | None] = ContextVar("wmm_operation_authority", default=None)
PROTECTED: ContextVar[Context | None] = ContextVar("wmm_protected_operation", default=None)
NATIVE_MEDIA_CHECKING: ContextVar[bool] = ContextVar("wmm_native_media_checking", default=False)


def utc() -> datetime:
    return datetime.now(timezone.utc)


def store_identity(store: Store) -> str:
    return str(Path(store.path).resolve())


@contextmanager
def bound_agent(
    store: Store,
    envelope: Mapping[str, object],
    admission: Mapping[str, object],
    review: Mapping[str, object] | None = None,
    host_check: Callable[[], object] | None = None,
) -> Iterator[None]:
    """Only authenticated dispatchers bind this context; retain no bearer credential."""
    from .db import connection

    context = cast(
        Context,
        dict(
            store=store_identity(store),
            envelope=canonical(envelope),
            grant_id=cast(str, admission["grant_id"]),
            agent_id=cast(str, admission["agent_id"]),
            attempt=cast(int, admission["attempt"]),
            review=review,
            execution_id=cast(str | None, admission.get("automation_execution_id")),
            host_check=host_check,
        ),
    )
    with connection(store.path) as db:
        row = cast(
            Mapping[str, object] | None,
            db.execute("SELECT * FROM agent_grants WHERE id=?", (context["grant_id"],)).fetchone(),
        )
        if row is None:
            raise PermissionError("Admitted grant is unavailable")
        context["grant_version"] = cast(int, row["version"])
    token = REQUEST.set(context)
    try:
        yield
    finally:
        REQUEST.reset(token)


@contextmanager
def bound_owner(
    store: Store,
    envelope: Mapping[str, object],
    identities: IdentitiesLike,
    session: str,
    user: Mapping[str, object],
) -> Iterator[None]:
    """HTTP admission supplies a freshly provider-verified user, never body identity."""
    from .db import connection
    from .review_access import member

    principal = cast(str, user["principal"])
    local = identities.local(session, principal)
    with connection(store.path) as db:
        role = member(db, cast(str, envelope["app_id"]), principal, "OWNER")
    context = cast(
        Context,
        dict(
            store=store_identity(store),
            envelope=canonical(envelope),
            principal=principal,
            role_version=role["version"],
            identities=identities,
            session=session,
            generation=cast(str | None, local["session_generation"]),
        ),
    )
    token = REQUEST.set(context)
    try:
        yield
    finally:
        REQUEST.reset(token)


def check_agent(db: sqlite3.Connection, context: Context, envelope: Mapping[str, object]) -> str:
    host_check = context.get("host_check")
    if host_check is not None:
        cast(Callable[[], object], host_check)()
    from . import agent_review_policy
    from .agent_grants import current

    row = cast(
        AgentGrantsRow | None,
        db.execute("SELECT * FROM agent_grants WHERE id=?", (context["grant_id"],)).fetchone(),
    )
    if row is None or row["version"] != context["grant_version"] or row["agent_id"] != context["agent_id"]:
        raise PermissionError("Admitted grant identity changed")
    current(db, row, envelope, utc(), check_quota=False)
    attempt = context["attempt"]
    if type(attempt) is not int or not 1 <= attempt <= row["used"]:
        raise PermissionError("Grant admission attempt is unavailable")
    if context["review"] is None:
        agent_review_policy.ordinary_dispatch(db, row["id"], cast(str, envelope["operation"]))
    else:
        check_review(db, context, envelope)
    check_standing(db, context, envelope, row)
    return "grant:" + row["id"]


def check_standing(
    db: sqlite3.Connection,
    context: Context,
    envelope: Mapping[str, object],
    grant: Mapping[str, object],
) -> None:
    """A live standing execution cannot borrow an ordinary or different admission."""
    from .automation_execution import ACTIVE, execution_row

    active = ACTIVE.get()
    execution_id = context["execution_id"]
    if active is not None and execution_id is None:
        raise PermissionError("Standing operation cannot borrow another admission")
    if execution_id is not None:
        if active is None or active["id"] != execution_id:
            raise PermissionError("Standing operation context is unavailable")
        execution = execution_row(db, active["id"])
        actual = (
            active["store"],
            execution["grant_id"],
            execution["operation"],
            execution["input_hash"],
            execution["status"],
        )
        expected = (context["store"], grant["id"], envelope["operation"], digest(envelope), "DISPATCHED")
        if actual != expected:
            raise PermissionError("Standing operation authority changed")


def check_review(db: sqlite3.Connection, context: Context, envelope: Mapping[str, object]) -> None:
    from . import agent_checkpoints
    from .agent_review_dispatch import saved_request

    read_fn = cast(Callable[..., Mapping[str, object]], vars(agent_checkpoints)["read_row"])
    current_fn = cast(Callable[..., None], vars(agent_checkpoints)["current"])
    review = cast(Mapping[str, object], context["review"])
    request = saved_request(db, cast(str, envelope["app_id"]), cast(str, review["id"]))
    row = read_fn(db, envelope["app_id"], review["id"], review["revision"])
    packet = cast(Mapping[str, object], row["packet"])
    if (
        request["grant_id"] != context["grant_id"]
        or request["input_hash"] != review["input_hash"]
        or canonical(request["envelope"]) != context["envelope"]
        or row["state"] != "RUNNING"
        or row["hash"] != review["packet_hash"]
        or packet["agent_id"] != context["agent_id"]
        or packet["input_hash"] != request["input_hash"]
    ):
        raise PermissionError("Reviewed operation authority changed")
    current_fn(db, row, utc())


def check(db: sqlite3.Connection, context: Context) -> str:
    envelope = cast(Mapping[str, object], json.loads(cast(str, context["envelope"])))
    if "grant_id" in context:
        return check_agent(db, context, envelope)
    from .review_access import exact_role

    identities = cast(IdentitiesLike, context["identities"])
    identities.local(
        cast(str, context["session"]),
        cast(str, context["principal"]),
        cast(str | None, context["generation"]),
    )
    exact_role(
        db,
        cast(str, envelope["app_id"]),
        cast(str, context["principal"]),
        cast(int, context["role_version"]),
        "OWNER",
    )
    return cast(str, context["principal"])


def guard_connection(path: str | Path, db: sqlite3.Connection) -> None:
    """Runs in the business connection at entry and immediately before commit."""
    context = PROTECTED.get()
    if context is None:
        return
    if str(Path(path).resolve()) != context["store"]:
        raise PermissionError("Protected operation cannot cross its local datastore")
    check(db, context)
    checks = context.get("native_media_checks")
    if checks and not NATIVE_MEDIA_CHECKING.get():
        from . import ios_agent_media

        verify = cast(Callable[..., object], vars(ios_agent_media)["check_authority"])
        token = NATIVE_MEDIA_CHECKING.set(True)
        try:
            for app_id, kind, job_id in cast(list[tuple[str, str, str]], checks):
                verify(db, app_id, kind, job_id)
        finally:
            NATIVE_MEDIA_CHECKING.reset(token)


@contextmanager
def protected(store: Store, envelope: Mapping[str, object]) -> Iterator[object]:
    """Opt in only around an exact synchronous operation, never a whole native session."""
    from .db import connection

    context = REQUEST.get()
    if context is None or context["store"] != store_identity(store) or context["envelope"] != canonical(envelope):
        raise PermissionError("Current exact operation authority is required")
    token = PROTECTED.set(context)
    try:
        with connection(store.path) as db:
            actor = check(db, context)
        yield actor
    finally:
        PROTECTED.reset(token)
