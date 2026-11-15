"""Source-bound approved inference; draft text has no publication authority."""

import sqlite3
import time
import uuid
from collections.abc import Callable, Mapping
from datetime import timedelta
from typing import Protocol, TypedDict, cast

from . import (
    agent_api,
    agent_context,
    agent_contract,
    agent_native,
    agent_registry,
    agent_usage,
    cloudflare_inference,
    draft_recipes,
    worker,
)
from .agent_access import AgentAccess
from .agent_registry import NATIVE, TASKS
from .common import Invalid, canonical, digest, iso_time, now, uid
from .db import connection
from .store import Store


def api_run(
    profile: Mapping[str, object],
    key: str | None,
    prompt: str,
    max_tokens: object,
    alive: Callable[[], None],
) -> tuple[object, object]:
    return cast(
        Callable[..., tuple[object, object]],
        vars(agent_api).get("request"),
    )(profile, key, prompt, max_tokens, alive)


def snapshot(store: Store, app_id: str) -> Mapping[str, object]:
    return cast(
        Callable[[Store, str], Mapping[str, object]],
        vars(agent_context).get("snapshot"),
    )(store, app_id)


def bounded_text(value: object, label: str, limit: int) -> str:
    return cast(
        Callable[[object, str, int], str],
        vars(agent_contract).get("bounded_text"),
    )(value, label, limit)


def draft(value: object, source_ids: object) -> object:
    return cast(
        Callable[[object, object], object],
        vars(agent_contract).get("draft"),
    )(value, source_ids)


def exact(value: object, keys: object) -> None:
    cast(
        Callable[[object, object], None],
        vars(agent_contract).get("exact"),
    )(value, keys)


def output_contract() -> object:
    return cast(
        Callable[[], object],
        vars(agent_contract).get("output_contract"),
    )()


def prompt(app: object, task: str, focus: object, context: object) -> str:
    return cast(
        Callable[[object, str, object, object], str],
        vars(agent_contract).get("prompt"),
    )(app, task, focus, context)


def native_run(
    provider: object,
    frozen: object,
    prompt: object,
    model: object,
    secret: str | None,
    alive: Callable[[], None],
) -> tuple[object, object]:
    return cast(
        Callable[..., tuple[object, object]],
        vars(agent_native).get("run"),
    )(provider, frozen, prompt, model, secret, alive)


def usage_observation(value: object) -> Mapping[str, object]:
    return cast(
        Callable[[object], Mapping[str, object]],
        vars(agent_usage).get("observation"),
    )(value)


def recipe(task: object, focus: object) -> object:
    return cast(
        Callable[[object, object], object],
        vars(draft_recipes).get("recipe"),
    )(task, focus)


def validate_recipe(value: object, selected: object) -> Mapping[str, object] | None:
    return cast(
        Callable[[object, object], Mapping[str, object] | None],
        vars(draft_recipes).get("validate"),
    )(value, selected)


def json_job(row: sqlite3.Row | None) -> Mapping[str, object]:
    return cast(
        Callable[[sqlite3.Row | None], Mapping[str, object]],
        vars(worker).get("json_job"),
    )(row)


REGISTRY = cast(
    Mapping[str, Mapping[str, object]],
    vars(agent_registry).get("REGISTRY"),
)


class AccessLike(Protocol):
    def view(self, app_id: str) -> Mapping[str, object]: ...

    def get(self, app_id: str, identity: str) -> Mapping[str, object]: ...

    def secret(self, app_id: str, row: Mapping[str, object]) -> str | None: ...


class StopLike(Protocol):
    def is_set(self) -> bool: ...


class _SourceContext(TypedDict):
    sources: list[dict[str, object]]


SCHEMA = "growth.agent-draft-job.v2"


class ApprovalContextChanged(Invalid):
    """The task needs review without asserting that its connection is broken."""


def request_key(value: object) -> str:
    """Require canonical identities, never command fragments."""
    try:
        if str(uuid.UUID(cast(str, value))) != value:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise Invalid("Use a canonical agent request identity") from None
    return cast(str, value)


def selected(
    store: Store,
    app_id: str,
    task: str,
    connection_id: str | None,
) -> tuple[Mapping[str, object], Mapping[str, object]]:
    """Select an app-owned route without a hidden paid-provider fallback."""
    access = cast(AccessLike, AgentAccess(store))
    view = access.view(app_id)
    routing = cast(Mapping[str, object], view["routing"])
    route_data = cast(Mapping[str, object], routing["data"])
    mode = cast(str, route_data["mode"])
    routes = cast(Mapping[str, str], route_data["routes"])
    chosen = connection_id or routes.get(task)
    if not chosen:
        profiles = cast(list[Mapping[str, object]], view["profiles"])
        rows = [p for p in profiles if permitted(p, mode)]
        if not rows:
            raise Invalid("Test an agent connection in this access mode, or approve another route")
        chosen = cast(str, rows[0]["id"])
    row = access.get(app_id, chosen)
    if row["status"] == "DISCONNECTED":
        raise Invalid("This app connection is disconnected")
    if task != "connection_test":
        if row["status"] != "TESTED":
            raise Invalid("Test this connection before approving campaign work")
        data = cast(Mapping[str, object], row["data"])
        if mode != "mixed" and REGISTRY[cast(str, data["provider"])]["mode"] != mode:
            raise Invalid("Connection is outside this app access mode")
    return row, routing


def permitted(row: Mapping[str, object], mode: str) -> bool:
    """An automatic recommendation is limited to tested providers in the chosen mode."""
    data = cast(Mapping[str, object], row["data"])
    return row["status"] == "TESTED" and (mode == "mixed" or REGISTRY[cast(str, data["provider"])]["mode"] == mode)


def proposal(store: Store, app_id: str, body: Mapping[str, object]) -> dict[str, object]:
    """Derive the exact reviewed app-fact transmission rather than accept a prompt."""
    exact(body, ("task", "focus", "connection_id"))
    raw_task = body["task"]
    if not isinstance(raw_task, str) or (raw_task not in TASKS and raw_task != "connection_test"):
        raise Invalid("Choose a supported agent task")
    task = raw_task
    bounded_text(body["focus"], "Task focus", 1000)
    connection_id = body["connection_id"]
    if connection_id is not None:
        request_key(connection_id)
    app = store.app(app_id)
    row, routing = selected(store, app_id, task, cast(str | None, connection_id))
    context = cast(_SourceContext, snapshot(store, app_id)) if task != "connection_test" else None
    text = (
        prompt(app, task, body["focus"], context)
        if task != "connection_test"
        else (
            "Return only this JSON, without tools: "
            + canonical(
                dict(
                    summary="Connection test completed",
                    items=[],
                    unknowns=["Quota and price are not independently verified"],
                )
            )
        )
    )
    connection_data = cast(Mapping[str, object], row["data"])
    frozen: dict[str, object] = dict(
        schema=SCHEMA,
        app_id=app_id,
        app_version=app["version"],
        app_hash=digest(app["data"]),
        connection_id=row["id"],
        connection_version=row["version"],
        connection_hash=digest(row["data"]),
        routing_hash=digest(routing),
        task=task,
        focus=body["focus"],
        prompt=text,
        provider=connection_data["provider"],
        model=connection_data["model"],
        max_output_tokens=256 if task == "connection_test" else 2048,
        external_effect="MODEL_REQUEST_ONLY_NO_PUBLICATION",
        fallback="REQUIRES_ANOTHER_APPROVAL",
    )
    if connection_data["provider"] == "cloudflare_api":
        verify = cast(
            Callable[[Mapping[str, object]], Mapping[str, object]],
            vars(cloudflare_inference).get("verify"),
        )
        policy = verify(connection_data)
        frozen["billing_policy"] = policy
        frozen["max_output_tokens"] = min(
            cast(int, frozen["max_output_tokens"]),
            cast(int, policy["max_output_tokens"]),
        )
    frozen.update(
        output_contract_hash=digest(output_contract()),
        draft_recipe=recipe(task, body["focus"]),
    )
    frozen.update(
        context=context,
        context_hash=digest(context),
        source_ids=[s["id"] for s in context["sources"]] if context else [],
    )
    return dict(
        proposal=frozen,
        source_hash=digest(frozen),
        cost="Existing provider allowance or approved API charges; exact cost/quota unknown",
        recommendation="Selected app-owned route; comparative quality and cost are not yet measured",
        automatically_verified=False,
    )


class AgentWork:
    def __init__(
        self,
        store: Store,
        on_start: Callable[[sqlite3.Connection, Mapping[str, object]], None] | None = None,
    ) -> None:
        self.store = store
        self.on_start = on_start

    def start(self, app_id: str, body: Mapping[str, object]) -> Mapping[str, object]:
        """Freeze one exact app/connection approval and idempotent durable job."""
        exact(body, ("task", "focus", "connection_id", "source_hash", "request_key"))
        key = "agent-" + request_key(body["request_key"])
        self.store.app(app_id)
        with connection(self.store.path) as db:
            old = db.execute("SELECT * FROM jobs WHERE app_id=? AND request_key=?", (app_id, key)).fetchone()
        if old:
            return replay(old, body)
        current = proposal(self.store, app_id, {k: body[k] for k in ("task", "focus", "connection_id")})
        if current["source_hash"] != body["source_hash"]:
            raise Invalid("App, route or connection changed; review a new proposal")
        frozen = cast(dict[str, object], current["proposal"])
        frozen["expires_at"] = (iso_time(now()) + timedelta(seconds=1800)).isoformat()
        data = dict(envelope=frozen, envelope_hash=digest(frozen), original_request=body)
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT * FROM jobs WHERE app_id=? AND request_key=?", (app_id, key)).fetchone()
            if old:
                return replay(old, body)
            guard(self.store, app_id, frozen)
            if db.execute(
                "SELECT 1 FROM jobs WHERE app_id=? AND action='agent_run' AND status IN ('QUEUED','RUNNING')", (app_id,)
            ).fetchone():
                raise Invalid("Finish or cancel this app current agent work before approving another request")
            created = now()
            if frozen["provider"] == "cloudflare_api":
                reserve = cast(
                    Callable[..., None],
                    vars(cloudflare_inference).get("reserve"),
                )
                reserve(db, app_id, frozen, created)
            db.execute(
                "INSERT INTO jobs(id,app_id,action,data,status,created,updated,request_key) VALUES(?,?,?,?,?,?,?,?)",
                (uid(), app_id, "agent_run", canonical(data), "QUEUED", created, created, key),
            )
            job = json_job(
                db.execute(
                    "SELECT * FROM jobs WHERE app_id=? AND request_key=?",
                    (app_id, key),
                ).fetchone()
            )
            if self.on_start is not None:
                self.on_start(db, job)
            return job


def replay(row: sqlite3.Row, body: Mapping[str, object]) -> Mapping[str, object]:
    """A repeated request reads its original receipt instead of repeating inference."""
    saved = json_job(row)
    data = cast(Mapping[str, object], saved["data"])
    if saved["action"] != "agent_run" or data["original_request"] != body:
        raise Invalid("Agent request identity was reused for different work")
    return saved


def guard(store: Store, app_id: str, frozen: Mapping[str, object]) -> Mapping[str, object]:
    """Reject changed sources, routes, access or approval expiry before and after IO."""
    app = store.app(app_id)
    if (
        frozen["schema"] != SCHEMA
        or frozen["app_id"] != app_id
        or frozen["app_version"] != app["version"]
        or frozen["app_hash"] != digest(app["data"])
    ):
        raise ApprovalContextChanged("Agent app facts changed; approve the current task")
    if iso_time(now()) > iso_time(frozen["expires_at"]):
        raise ApprovalContextChanged("Agent task approval expired")
    if frozen.get("output_contract_hash") != digest(output_contract()) or frozen.get("draft_recipe") != recipe(
        frozen["task"], frozen["focus"]
    ):
        raise ApprovalContextChanged("Agent output contract or recipe changed; review the current task")
    guard_context(store, app_id, frozen)
    row, routing = selected(
        store,
        app_id,
        cast(str, frozen["task"]),
        cast(str | None, frozen["connection_id"]),
    )
    connection_data = cast(Mapping[str, object], row["data"])
    if (
        row["version"] != frozen["connection_version"]
        or digest(row["data"]) != frozen["connection_hash"]
        or digest(routing) != frozen["routing_hash"]
    ):
        raise Invalid("Agent route or connection changed; approve a new task")
    if connection_data["provider"] == "cloudflare_api":
        verify = cast(
            Callable[[Mapping[str, object]], Mapping[str, object]],
            vars(cloudflare_inference).get("verify"),
        )
        policy = verify(connection_data)
        default_cap = 1024 if "native_turn" in frozen else 256 if frozen["task"] == "connection_test" else 2048
        cap = min(default_cap, cast(int, policy["max_output_tokens"]))
        if (
            frozen.get("billing_policy") != policy
            or frozen.get("max_output_tokens") != cap
            or frozen.get("model") != connection_data["model"]
            or frozen.get("provider") != "cloudflare_api"
        ):
            raise Invalid("Cloudflare policy or approved output limit changed")
    return row


def guard_context(store: Store, app_id: str, frozen: Mapping[str, object]) -> None:
    """Rebuild bounded campaign sources without consulting protected credentials."""
    current = cast(_SourceContext, snapshot(store, app_id)) if frozen["task"] != "connection_test" else None
    if frozen.get("context") != current or frozen.get("context_hash") != digest(current):
        raise ApprovalContextChanged("Agent evidence changed or approved context is absent; review a new proposal")
    expected = [s["id"] for s in current["sources"]] if current else []
    if frozen.get("source_ids") != expected:
        raise ApprovalContextChanged("Approved agent source index changed")


def live_guard(
    store: Store,
    job: Mapping[str, object],
    stop: StopLike | None = None,
) -> Callable[[], None]:
    """Maintain only the current owned lease and stop cancelled native work."""
    last: list[float] = [0]

    def alive() -> None:
        if stop is not None and stop.is_set():
            raise ApprovalContextChanged("Agent worker is stopping; review before another inference")
        if time.monotonic() - last[0] < 0.25:
            return
        last[0] = time.monotonic()
        with connection(store.path, write=True) as db:
            row = db.execute(
                "SELECT status,attempts FROM jobs WHERE app_id=? AND id=?", (job["app_id"], job["id"])
            ).fetchone()
            if row is None or row["status"] != "RUNNING" or row["attempts"] != job["attempts"]:
                raise ApprovalContextChanged("Agent job was cancelled or its lease changed")
            db.execute(
                "UPDATE jobs SET lease=? WHERE id=? AND attempts=?", (time.time() + 60, job["id"], job["attempts"])
            )
        data = cast(Mapping[str, object], job["data"])
        guard(store, cast(str, job["app_id"]), cast(Mapping[str, object], data["envelope"]))

    return alive


def execute(
    store: Store,
    job: Mapping[str, object],
    stop: StopLike | None = None,
    access: AccessLike | None = None,
    transport: Callable[..., tuple[object, object]] | None = None,
) -> dict[str, object]:
    """Interrupted inference is not replayed because allowance may already be consumed."""
    if job["attempts"] != 1:
        raise ApprovalContextChanged(
            "Interrupted inference may have consumed allowance; approve a new request instead of replay"
        )
    data = cast(Mapping[str, object], job["data"])
    if (
        set(data) != {"envelope", "envelope_hash", "original_request"}
        or digest(data["envelope"]) != data["envelope_hash"]
    ):
        raise Invalid("Agent approval envelope integrity failed")
    frozen = cast(Mapping[str, object], data["envelope"])
    access = cast(AccessLike, access or AgentAccess(store))
    row = guard(store, cast(str, job["app_id"]), frozen)
    connection_data = cast(Mapping[str, object], row["data"])
    original = cast(Mapping[str, object], data["original_request"])
    if connection_data["provider"] == "cloudflare_api" and digest(
        {k: v for k, v in frozen.items() if k != "expires_at"}
    ) != original.get("source_hash"):
        raise Invalid("Cloudflare approval no longer matches the reviewed proposal")
    alive = live_guard(store, job, stop)
    alive()
    secret = access.secret(cast(str, job["app_id"]), row)
    if frozen["provider"] in NATIVE:
        result, usage = native_run(
            frozen["provider"],
            connection_data["tool"],
            frozen["prompt"],
            frozen["model"],
            secret,
            alive,
        )
    else:
        runner = transport or api_run
        result, usage = runner(
            connection_data,
            secret,
            cast(str, frozen["prompt"]),
            frozen["max_output_tokens"],
            alive,
        )
    alive()
    guard(store, cast(str, job["app_id"]), frozen)
    result = draft(result, frozen["source_ids"])
    pack = validate_recipe(result, frozen["draft_recipe"])
    if secret and secret in canonical(result):
        raise Invalid("Agent result exposed a protected key and was rejected")
    measured = usage_observation(usage)
    accepted: dict[str, object] = dict(
        status="DRAFT_READY",
        draft=result,
        sha256=digest(result),
        **measured,
        quota="UNKNOWN",
        cost="UNKNOWN",
        publication="NOT_RUN",
        automatically_verified=False,
        next_actions=["Review this draft and its unknowns before preparing any external action"],
    )
    if pack is not None:
        accepted["draft_recipe"] = pack
    return accepted


def complete(
    db: sqlite3.Connection,
    job: Mapping[str, object],
    result: Mapping[str, object],
    status: str,
) -> None:
    """Only an accepted worker completion can update the connection test state."""
    data = cast(Mapping[str, object], job.get("data", {}))
    raw_frozen = data.get("envelope")
    if not isinstance(raw_frozen, dict):
        return
    frozen = cast(Mapping[str, object], raw_frozen)
    if digest(frozen) != data.get("envelope_hash"):
        return
    if frozen.get("app_id") != job["app_id"] or frozen.get("schema") != SCHEMA:
        return
    if not all(k in frozen for k in ("task", "connection_id", "connection_version")):
        return
    if status == "SUCCEEDED" and frozen["task"] == "connection_test":
        db.execute(
            "UPDATE agent_connections SET status='TESTED',last_test=?,updated=? WHERE app_id=? AND id=? AND version=? AND status!='DISCONNECTED'",
            (now(), now(), job["app_id"], frozen["connection_id"], frozen["connection_version"]),
        )
    if status == "BLOCKED" and result.get("connection_health") != "UNCHANGED":
        db.execute(
            "UPDATE agent_connections SET status='NEEDS_ATTENTION',updated=? WHERE app_id=? AND id=? AND version=? AND status!='DISCONNECTED'",
            (now(), job["app_id"], frozen["connection_id"], frozen["connection_version"]),
        )
