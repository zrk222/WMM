"""Owner-issued local operation credentials; independent human review stays separate."""

import hashlib
import json
import re
import secrets
import sqlite3
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta, timezone
from typing import Protocol, TypedDict, cast

from . import agent_review_policy
from .common import Invalid, canonical, digest, iso_time, uid
from .db import connection
from .operation_catalog import OPERATIONS, exact_keys, path_segment, request_data
from .review_access import exact_role, member
from .schema_types import AgentGrantsRow, AppsRow, AutomationPoliciesRow
from .store import Store, audit


class ContextValue(Protocol):
    def get(self) -> object: ...


class ReviewPolicy(Protocol):
    def validate(self, body: Mapping[str, object]) -> list[str]: ...
    def save(self, db: sqlite3.Connection, grant_id: str, body: Mapping[str, object]) -> None: ...
    def ordinary_dispatch(self, db: sqlite3.Connection, grant_id: str, operation: str) -> object: ...
    def operations(self, db: sqlite3.Connection, grant_id: str) -> object: ...


REVIEW_POLICY = cast(ReviewPolicy, agent_review_policy)


class GrantPublic(TypedDict):
    id: str
    app_id: str
    agent_id: str
    owner: str
    owner_version: int
    app_version: int
    app_hash: str
    expires: str
    max_calls: int
    used: int
    status: str
    version: int
    created: str
    updated: str
    operations: list[str]


class IssuedGrant(GrantPublic):
    review_operations: list[str]


class GrantIssue(TypedDict):
    grant: IssuedGrant
    token: str
    token_delivery: str


class GrantAdmission(TypedDict):
    grant_id: str
    agent_id: str
    attempt: int


def token_digest(token: object) -> str:
    """Validate only the delegated credential format; never persist plaintext tokens."""
    if not isinstance(token, str) or not re.fullmatch(r"wmmg_[A-Za-z0-9_-]{43}", token):
        raise PermissionError("A valid scoped WMM agent grant is required")
    return hashlib.sha256(token.encode()).hexdigest()


def validate_grant_operations(names: object) -> None:
    if not isinstance(names, list) or not names:
        raise Invalid("Select only fixed local operation names")
    names = cast(list[object], names)
    for name in names:
        if not isinstance(name, str) or name not in OPERATIONS:
            raise Invalid("Select only fixed local operation names")
    typed = cast(list[str], names)
    if set(typed) & {"experiment.schedule", "experiment.schedule-run"}:
        raise Invalid("Experiment monitoring requires a verified owner")
    if len(typed) != len(set(typed)):
        raise Invalid("Grant operations must be unique")


def issue_data(body: object, observed: datetime) -> None:
    """Validate a finite exact operation scope and owner-selected lifetime/quota."""
    exact_keys(
        body,
        ("agent_id", "manifest_version", "operations", "expires", "max_calls"),
        ("review_operations", "extended_expiry_consent"),
    )
    body = cast(dict[str, object], body)
    path_segment(body["agent_id"])
    validate_grant_operations(body["operations"])
    REVIEW_POLICY.validate(body)
    calls = body["max_calls"]
    if type(calls) is not int or not 1 <= calls <= 10000:
        raise Invalid("Use a call ceiling from 1 through 10000")
    if "extended_expiry_consent" in body and type(body["extended_expiry_consent"]) is not bool:
        raise Invalid("Expiry consent must be an explicit boolean")
    from .authority_expiry import deadline

    deadline(body["expires"], observed, cast(bool, body.get("extended_expiry_consent", False)))


def public(row: AgentGrantsRow | sqlite3.Row) -> GrantPublic:
    """Return public delegation metadata, excluding credential hashes as well as secrets."""
    names = (
        "id",
        "app_id",
        "agent_id",
        "owner",
        "owner_version",
        "app_version",
        "app_hash",
        "expires",
        "max_calls",
        "used",
        "status",
        "version",
        "created",
        "updated",
    )
    return cast(
        GrantPublic,
        dict({key: cast(Mapping[str, object], row)[key] for key in names}, operations=json.loads(row["operations"])),
    )


def app_scope(db: sqlite3.Connection, app_id: str) -> tuple[int, str]:
    """Read the exact app revision and content hash inside the authorization transaction."""
    app = db.execute("SELECT * FROM apps WHERE id=?", (app_id,)).fetchone()
    if not app:
        raise Invalid("Grant app does not exist")
    typed_app = cast(AppsRow, dict(app))
    return typed_app["version"], digest(json.loads(typed_app["data"]))


def current(
    db: sqlite3.Connection,
    row: AgentGrantsRow | sqlite3.Row,
    envelope: Mapping[str, object],
    observed: datetime,
    check_quota: bool = True,
) -> None:
    """Check delegated scope, owner membership and quota before reserving admission."""
    if envelope["operation"] in ("experiment.schedule", "experiment.schedule-run"):
        raise PermissionError("Experiment monitoring requires a verified owner")
    from .authority_expiry import effective_expiry

    expiry = effective_expiry(db, "AGENT_GRANT", row, row["expires"])["expires"]
    if row["status"] != "ACTIVE" or iso_time(expiry) <= observed:
        raise PermissionError("Agent grant is revoked or expired")
    if row["app_id"] != envelope["app_id"] or envelope["operation"] not in json.loads(row["operations"]):
        raise PermissionError("Agent grant does not allow this app or operation")
    exact_role(db, row["app_id"], row["owner"], row["owner_version"], "OWNER")
    if app_scope(db, row["app_id"]) != (row["app_version"], row["app_hash"]):
        raise PermissionError("Agent grant app scope changed; request a new grant")
    if check_quota and row["used"] >= row["max_calls"]:
        raise PermissionError("Agent grant call ceiling is exhausted")


def authenticated(
    db: sqlite3.Connection, token: object, envelope: object, observed: datetime, check_quota: bool = True
) -> sqlite3.Row:
    """Resolve delegated identity and current scope inside the admission transaction."""
    request_data(envelope)
    row = db.execute("SELECT * FROM agent_grants WHERE token_hash=?", (token_digest(token),)).fetchone()
    if not row:
        raise PermissionError("Agent grant is unknown")
    typed_row = cast(AgentGrantsRow, dict(row))
    current(db, typed_row, cast(Mapping[str, object], envelope), observed, check_quota=check_quota)
    return row


def consume(
    db: sqlite3.Connection, row: AgentGrantsRow | sqlite3.Row, envelope: Mapping[str, object], observed: datetime
) -> GrantAdmission:
    """Record one reserved attempt after all admission checks have passed."""
    db.execute("UPDATE agent_grants SET used=used+1,updated=? WHERE id=?", (observed.isoformat(), row["id"]))
    audit(
        db,
        row["app_id"],
        "agent_grant.admitted",
        dict(grant_id=row["id"], agent_id=row["agent_id"], operation=envelope["operation"], attempt=row["used"] + 1),
    )
    return {"grant_id": row["id"], "agent_id": row["agent_id"], "attempt": row["used"] + 1}


def _batch_input(body: object, operation: str, plan_hash: str | None) -> None:
    if not isinstance(body, dict):
        raise PermissionError("Batch plan or expiry differs from the admitted request")
    body = cast(dict[str, object], body)
    if (
        operation != "creative.batch.create"
        or set(body) != {"plan", "plan_hash", "request_key"}
        or not isinstance(body["plan"], str)
        or body["plan_hash"] != plan_hash
    ):
        raise PermissionError("Batch plan or expiry differs from the admitted request")


def _batch_request(envelope: Mapping[str, object], operation: str, plan_hash: str | None, expires: object) -> None:
    body = cast(dict[str, object], envelope.get("input"))
    _batch_input(body, operation, plan_hash)
    from .operator_client import strict_json

    try:
        plan = strict_json(cast(str, body["plan"]).encode("utf-8"))
    except (Invalid, UnicodeError):
        raise PermissionError("Batch plan is not canonical JSON") from None
    if not isinstance(plan, dict):
        raise PermissionError("Batch plan or expiry differs from the admitted request")
    plan = cast(dict[str, object], plan)
    if canonical(plan) != body["plan"] or digest(plan) != plan_hash or plan.get("expires") != expires:
        raise PermissionError("Batch plan or expiry differs from the admitted request")


def _batch_envelope(
    store: Store, app_id: str, operation: str, plan_hash: str | None, expires: object
) -> tuple[Mapping[str, object], Mapping[str, object]]:
    from . import operation_authority

    protected = cast(ContextValue, vars(operation_authority)["PROTECTED"])
    identity = cast(Callable[[Store], object], vars(operation_authority)["store_identity"])
    context = cast(Mapping[str, object] | None, protected.get())
    if not context or context.get("store") != identity(store):
        raise PermissionError("Protected batch admission is required")
    envelope = cast(Mapping[str, object], json.loads(cast(str, context["envelope"])))
    if (
        envelope["app_id"] != app_id
        or envelope["operation"] != operation
        or not re.fullmatch("[a-f0-9]{64}", plan_hash or "")
    ):
        raise PermissionError("Batch admission does not match the exact plan")
    _batch_request(envelope, operation, plan_hash, expires)
    return context, envelope


def _capture_standing_batch(db: sqlite3.Connection, result: dict[str, object], deadline: datetime) -> None:
    from . import authority_expiry, automation_execution, ios_agent_media

    base_fn = cast(Callable[[object, str, object], str], vars(authority_expiry)["initial_base"])
    deadline_fn = cast(
        Callable[[sqlite3.Connection, sqlite3.Row], datetime], vars(automation_execution)["execution_deadline"]
    )
    row_fn = cast(Callable[[sqlite3.Connection, object], sqlite3.Row], vars(automation_execution)["execution_row"])
    hash_fn = cast(Callable[[sqlite3.Row], str], vars(ios_agent_media)["execution_hash"])
    row = row_fn(db, result["execution_id"])
    if deadline > deadline_fn(db, row):
        raise PermissionError("Batch deadline exceeds its standing execution")
    policy = cast(
        AutomationPoliciesRow,
        db.execute("SELECT * FROM automation_policies WHERE id=?", (row["policy_id"],)).fetchone(),
    )
    proposal = cast(dict[str, object], json.loads(policy["proposal"]))
    limits = cast(dict[str, object], proposal["limits"])
    base = base_fn(limits["expires"], policy["created"], proposal.get("extended_expiry_consent"))
    proof = authority_expiry.effective_expiry(db, "AUTOMATION", policy, base)
    if deadline > iso_time(proof["expires"]):
        raise PermissionError("Batch deadline exceeds standing approval")
    result["policy_consent_revision"] = proof["revision"]
    result["policy_consent_hash"] = proof["receipt_hash"]
    result["execution_hash"] = hash_fn(row)


def capture_batch_authority(
    db: sqlite3.Connection,
    store: Store,
    app_id: str,
    operation: str,
    plan_hash: str | None,
    expires: object,
) -> dict[str, object]:
    """Capture finite, secret-free provenance only from an exact protected admission."""
    from . import operation_authority

    check_fn = cast(Callable[[sqlite3.Connection, Mapping[str, object]], str], vars(operation_authority)["check"])
    observed = datetime.now(timezone.utc)
    deadline = iso_time(expires)
    context, envelope = _batch_envelope(store, app_id, operation, plan_hash, expires)
    if not observed < deadline:
        raise Invalid("Batch authority must have a future expiry")
    check_fn(db, context)
    version, app_hash = app_scope(db, app_id)
    result: dict[str, object] = dict(
        schema="growth.batch-authority.v1",
        app_id=app_id,
        operation=operation,
        plan_hash=plan_hash,
        envelope_hash=digest(envelope),
        expires=deadline.isoformat(),
        app_version=version,
        app_hash=app_hash,
    )
    if "grant_id" not in context:
        if deadline > observed + timedelta(hours=24):
            raise Invalid("Owner batch authority remains limited to 24 hours")
        result.update(
            kind="OWNER",
            principal=cast(str, context["principal"]),
            role_version=cast(int, context["role_version"]),
        )
        return result
    grant = cast(AgentGrantsRow, db.execute("SELECT * FROM agent_grants WHERE id=?", (context["grant_id"],)).fetchone())
    from .authority_expiry import effective_expiry

    grant_proof = effective_expiry(db, "AGENT_GRANT", grant, grant["expires"])
    if deadline > iso_time(grant_proof["expires"]):
        raise PermissionError("Batch deadline exceeds the source grant")
    result.update(
        kind="AGENT",
        grant_id=grant["id"],
        grant_version=grant["version"],
        agent_id=grant["agent_id"],
        attempt=cast(int, context["attempt"]),
        review=cast(Mapping[str, object] | None, context["review"]),
        execution_id=cast(str | None, context.get("execution_id")),
        native_host_required=context.get("host_check") is not None,
        grant_consent_revision=grant_proof["revision"],
        grant_consent_hash=grant_proof["receipt_hash"],
    )
    if result["execution_id"]:
        _capture_standing_batch(db, result, deadline)
    return result


def check_batch_authority(db: sqlite3.Connection, store: Store, app_id: str, reference: object, plan_hash: str) -> None:
    """Recheck retained owner, grant, checkpoint and standing scope without reviving a session."""
    from .review_access import exact_role

    observed = datetime.now(timezone.utc)
    if not isinstance(reference, dict):
        raise PermissionError("Batch authority changed or expired")
    reference = cast(dict[str, object], reference)
    if (
        reference.get("schema") != "growth.batch-authority.v1"
        or reference.get("app_id") != app_id
        or reference.get("plan_hash") != plan_hash
        or iso_time(reference.get("expires")) <= observed
        or app_scope(db, app_id) != (reference.get("app_version"), reference.get("app_hash"))
    ):
        raise PermissionError("Batch authority changed or expired")
    if reference.get("kind") == "OWNER":
        exact_role(db, app_id, cast(str, reference["principal"]), cast(int, reference["role_version"]), "OWNER")
        return
    if reference.get("kind") != "AGENT":
        raise PermissionError("Unknown batch authority")
    row = cast(
        AgentGrantsRow | None,
        db.execute("SELECT * FROM agent_grants WHERE id=?", (reference.get("grant_id"),)).fetchone(),
    )
    if not row or row["version"] != reference.get("grant_version") or row["agent_id"] != reference.get("agent_id"):
        raise PermissionError("Batch source grant changed")
    current(db, row, dict(app_id=app_id, operation=reference["operation"]), observed, check_quota=False)
    if reference.get("native_host_required"):
        from . import ios_host, operation_authority

        identities_type = cast(type[object], vars(ios_host)["NativeIdentities"])
        protected = cast(ContextValue, vars(operation_authority)["PROTECTED"])
        identity = cast(Callable[[Store], object], vars(operation_authority)["store_identity"])
        check_fn = cast(Callable[[sqlite3.Connection, Mapping[str, object]], str], vars(operation_authority)["check"])
        host = cast(Mapping[str, object] | None, protected.get())
        if (
            not host
            or not isinstance(host.get("identities"), identities_type)
            or host.get("store") != identity(store)
            or host.get("principal") != row["owner"]
            or cast(dict[str, object], json.loads(cast(str, host["envelope"]))).get("app_id") != app_id
        ):
            raise PermissionError("Fresh native owner and host verification are required")
        check_fn(db, host)
    if type(reference.get("attempt")) is not int or not 1 <= cast(int, reference["attempt"]) <= row["used"]:
        raise PermissionError("Batch source admission is unavailable")
    review = reference.get("review")
    if review is None:
        REVIEW_POLICY.ordinary_dispatch(db, row["id"], cast(str, reference["operation"]))
    else:
        from . import agent_checkpoints, agent_review_dispatch

        review = cast(dict[str, object], review)
        current_fn = cast(Callable[..., None], vars(agent_checkpoints)["current"])
        read_fn = cast(Callable[..., Mapping[str, object]], vars(agent_checkpoints)["read_row"])
        request_fn = cast(Callable[..., Mapping[str, object]], vars(agent_review_dispatch)["saved_request"])
        request = request_fn(db, app_id, review["id"])
        checkpoint = read_fn(db, app_id, review["id"])
        if (
            request["grant_id"] != row["id"]
            or request["input_hash"] != review["input_hash"]
            or digest(request["envelope"]) != reference["envelope_hash"]
            or checkpoint["state"] != "SUCCEEDED"
            or checkpoint["hash"] != review["packet_hash"]
        ):
            raise PermissionError("Batch review is no longer current")
        raw_packet = checkpoint.get("packet")
        if not isinstance(raw_packet, dict):
            raise PermissionError("Batch review is no longer current")
        packet = cast(Mapping[str, object], raw_packet)
        if packet.get("input_hash") != request["input_hash"] or packet.get("agent_id") != row["agent_id"]:
            raise PermissionError("Batch review is no longer current")
        current_fn(db, checkpoint, observed)
    identity = reference.get("execution_id")
    policy = cast(
        Mapping[str, object] | None,
        db.execute("SELECT id FROM automation_policies WHERE grant_id=?", (row["id"],)).fetchone(),
    )
    if identity:
        from . import automation_execution, complete_automation, ios_agent_media

        access = cast(ContextValue, vars(complete_automation)["ACCESS_VERIFIER"])
        verifier = access.get
        if reference.get("native_host_required") and not callable(verifier()):
            raise PermissionError("Fresh native protected-access verification is required")
        execution = cast(
            Callable[[sqlite3.Connection, object], sqlite3.Row], vars(automation_execution)["execution_row"]
        )(db, identity)
        if (
            not policy
            or policy["id"] != execution["policy_id"]
            or execution["status"] != "SUCCEEDED"
            or execution["grant_id"] != row["id"]
            or cast(
                Callable[[sqlite3.Row], str],
                vars(ios_agent_media)["execution_hash"],
            )(execution)
            != reference.get("execution_hash")
        ):
            raise PermissionError("Batch standing execution requires reconciliation")
        checked, _ = cast(
            Callable[..., tuple[Mapping[str, object], object]],
            vars(complete_automation)["checked_policy"],
        )(db, execution["policy_id"], observed)
        if checked["version"] != execution["policy_version"]:
            raise PermissionError("Batch standing authority changed")
    elif policy:
        raise PermissionError("Batch standing execution provenance is unavailable")


def _batch_review_pending(db: sqlite3.Connection, reference: dict[str, object]) -> bool:
    review = reference.get("review")
    if isinstance(review, dict):
        review = cast(dict[str, object], review)
        row = cast(
            Mapping[str, object] | None,
            db.execute(
                "SELECT data FROM agent_checkpoints WHERE app_id=? AND id=?",
                (reference.get("app_id"), review.get("id")),
            ).fetchone(),
        )
        if row:
            try:
                state = cast(dict[str, object], json.loads(cast(str, row["data"]))).get("state")
                if state == "RUNNING":
                    return True
            except (ValueError, TypeError, AttributeError):
                pass
    identity = reference.get("execution_id")
    if identity:
        row = cast(
            Mapping[str, object] | None,
            db.execute("SELECT status FROM automation_executions WHERE id=?", (identity,)).fetchone(),
        )
        if row and row["status"] == "DISPATCHED":
            return True
    return False


def batch_authority_pending(db: sqlite3.Connection, reference: object) -> bool:
    """Defer a queued child while its exact parent is still completing; grants no authority."""
    if not isinstance(reference, dict):
        return False
    reference = cast(dict[str, object], reference)
    if reference.get("kind") != "AGENT":
        return False
    try:
        if iso_time(reference.get("expires")) <= datetime.now(timezone.utc):
            return False
    except (Invalid, TypeError, ValueError):
        return False
    grant = cast(
        AgentGrantsRow | None,
        db.execute("SELECT * FROM agent_grants WHERE id=?", (reference.get("grant_id"),)).fetchone(),
    )
    if not grant or grant["status"] != "ACTIVE" or grant["version"] != reference.get("grant_version"):
        return False
    try:
        from .authority_expiry import effective_expiry

        proof = effective_expiry(db, "AGENT_GRANT", grant, grant["expires"])
        if iso_time(proof["expires"]) <= datetime.now(timezone.utc):
            return False
    except (Invalid, TypeError, ValueError):
        return False
    return _batch_review_pending(db, reference)


def issue_in_db(
    db: sqlite3.Connection,
    app_id: str,
    user: Mapping[str, object],
    body: object,
    observed: datetime,
    token: str,
) -> GrantIssue:
    """Issue inside an existing owner transaction, allowing atomic policy attachment."""
    issue_data(body, observed)
    body = cast(dict[str, object], body)
    owner = member(db, app_id, cast(str, user["principal"]), "OWNER")
    version, app_hash = app_scope(db, app_id)
    if type(body["manifest_version"]) is not int or body["manifest_version"] != version:
        raise Invalid("App version changed before grant issuance")
    stamp = observed.isoformat()
    identity = uid()
    from . import authority_expiry

    record = cast(
        Callable[[sqlite3.Connection, str, AgentGrantsRow, str, str, str, int, Mapping[str, object], datetime], object],
        vars(authority_expiry)["record_initial"],
    )
    requested = iso_time(body["expires"]).astimezone(timezone.utc)
    base = min(requested, observed + timedelta(hours=24))
    row = cast(
        AgentGrantsRow,
        dict(
            id=identity,
            app_id=app_id,
            agent_id=cast(str, body["agent_id"]),
            owner=cast(str, user["principal"]),
            owner_version=owner["version"],
            app_version=version,
            app_hash=app_hash,
            operations=canonical(sorted(cast(list[str], body["operations"]))),
            token_hash=token_digest(token),
            expires=base.isoformat(),
            max_calls=cast(int, body["max_calls"]),
            used=0,
            status="ACTIVE",
            version=1,
            created=stamp,
            updated=stamp,
        ),
    )
    db.execute("INSERT INTO agent_grants VALUES(" + ",".join("?" for _ in row) + ")", tuple(row.values()))
    REVIEW_POLICY.save(db, identity, body)
    record(
        db,
        "AGENT_GRANT",
        row,
        row["expires"],
        requested.isoformat(),
        cast(str, user["principal"]),
        owner["version"],
        body,
        observed,
    )
    audit(
        db,
        app_id,
        "agent_grant.issued",
        dict(grant_id=identity, agent_id=cast(str, body["agent_id"]), owner=cast(str, user["principal"])),
    )
    return {
        "grant": {**public(row), "expires": requested.isoformat(), "review_operations": REVIEW_POLICY.validate(body)},
        "token": token,
        "token_delivery": "ONCE_ONLY",
    }


class Grants:
    """Serialize delegation changes and admissions without granting human identity."""

    def __init__(self, store: Store, clock: Callable[[], datetime] | None = None) -> None:
        self.store = store
        self.clock: Callable[[], datetime] = clock or (lambda: datetime.now(timezone.utc))

    def issue(self, app_id: str, user: Mapping[str, object], body: object) -> GrantIssue:
        """The HTTP adapter must supply its freshly verified owner, never a body identity."""
        observed = self.clock()
        issue_data(body, observed)
        token = "wmmg_" + secrets.token_urlsafe(32)
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            result = issue_in_db(db, app_id, user, body, self.clock(), token)
        return result

    def list(self, app_id: str, user: Mapping[str, object]) -> dict[str, object]:
        """Owner-only operational metadata; snapshot imports cannot create grants."""
        with connection(self.store.path) as db:
            member(db, app_id, cast(str, user["principal"]), "OWNER")
            from .authority_expiry import effective_expiry

            grants: list[dict[str, object]] = []
            for row in db.execute("SELECT * FROM agent_grants WHERE app_id=? ORDER BY created,id", (app_id,)):
                row = cast(AgentGrantsRow, row)
                try:
                    proof = effective_expiry(db, "AGENT_GRANT", row, row["expires"])
                    permitted_until, revision = proof["expires"], proof["revision"]
                except PermissionError:
                    permitted_until, revision = None, None
                grants.append(
                    dict(
                        public(row),
                        permission_expires_at=permitted_until,
                        consent_revision=revision,
                        review_operations=REVIEW_POLICY.operations(db, row["id"]),
                    )
                )
                if permitted_until is not None:
                    grants[-1]["expires"] = permitted_until
            return dict(grants=grants)

    def authority_status(self, grant_id: str, app_id: str) -> dict[str, object]:
        """Return current, secret-free grant facts after an authenticated admission."""
        from .authority_expiry import effective_expiry

        with connection(self.store.path) as db:
            row = db.execute("SELECT * FROM agent_grants WHERE id=? AND app_id=?", (grant_id, app_id)).fetchone()
            row = cast(AgentGrantsRow | None, row)
            if not row:
                raise PermissionError("Agent grant is unavailable")
            names = cast(list[str], json.loads(row["operations"]))
            if not names:
                raise PermissionError("Agent grant has no operations")
            current(db, row, dict(app_id=app_id, operation=names[0]), self.clock(), check_quota=False)
            proof = effective_expiry(db, "AGENT_GRANT", row, row["expires"])
            return dict(
                grant_id=row["id"],
                effective_expires=proof["expires"],
                used=row["used"],
                max_calls=row["max_calls"],
                remaining_calls=max(0, row["max_calls"] - row["used"]),
                consent_revision=proof["revision"],
            )

    def revoke(self, app_id: str, user: Mapping[str, object], body: object) -> GrantPublic:
        """Block future admissions with exact optimistic revision; do not claim cancellation."""
        exact_keys(body, ("id", "version"))
        body = cast(dict[str, object], body)
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            member(db, app_id, cast(str, user["principal"]), "OWNER")
            row = db.execute("SELECT * FROM agent_grants WHERE app_id=? AND id=?", (app_id, body["id"])).fetchone()
            row = cast(AgentGrantsRow | None, row)
            if not row or type(body["version"]) is not int or row["version"] != body["version"]:
                raise Invalid("Grant revision changed; reload")
            db.execute(
                "UPDATE agent_grants SET status='REVOKED',version=version+1,updated=? WHERE id=?",
                (self.clock().isoformat(), body["id"]),
            )
            audit(db, app_id, "agent_grant.revoked", dict(grant_id=body["id"], owner=user["principal"]))
            return public(db.execute("SELECT * FROM agent_grants WHERE id=?", (body["id"],)).fetchone())

    def admit(self, token: object, envelope: object) -> dict[str, object]:
        """Consume one attempt atomically; a later business failure does not refund it."""
        request = cast(Mapping[str, object], envelope)
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            row = authenticated(db, token, request, self.clock())
            REVIEW_POLICY.ordinary_dispatch(db, row["id"], cast(str, request["operation"]))
            from . import complete_automation

            reserve_fn = cast(Callable[..., str | None], vars(complete_automation)["reserve"])
            execution = reserve_fn(db, self.store, row, request, self.clock())
            result = consume(db, row, request, self.clock())
            return cast(
                dict[str, object],
                dict(result, automation_execution_id=execution) if execution else result,
            )
