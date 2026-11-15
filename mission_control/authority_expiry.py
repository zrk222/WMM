"""Owner-reviewed expiry amendments for existing fixed-scope authority."""

import json
import sqlite3
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import TypedDict, cast

from .common import Invalid, digest, iso_time
from .db import connection
from .operation_catalog import exact_keys, path_segment
from .review_access import exact_role, member
from .schema_types import AuthorityExpiryConsentsRow

KINDS = ("AGENT_GRANT", "AUTOMATION", "CAMPAIGN", "ORGANIC_POLICY")


class ExpiryProof(TypedDict):
    """Validated head of one unchanged authority's consent chain."""

    expires: str
    revision: int
    receipt_hash: str
    base_hash: str


AuthorityRow = sqlite3.Row | Mapping[str, object]


def deadline(value: object, observed: datetime, consent: bool = False) -> datetime:
    """Parse a finite timezone-bearing deadline and require consent past 24h."""
    try:
        result = iso_time(value).astimezone(timezone.utc)
    except (OverflowError, TypeError, ValueError):
        raise Invalid("Use a representable timezone-bearing expiry") from None
    if result <= observed:
        raise Invalid("Choose a future expiry")
    if result > observed + timedelta(hours=24) and consent is not True:
        raise Invalid("Explicit consent is required for expiry beyond 24 hours")
    return result


def _binding(kind: str, row: AuthorityRow) -> dict[str, object]:
    if kind == "AGENT_GRANT":
        keys = (
            "id",
            "app_id",
            "agent_id",
            "owner",
            "owner_version",
            "app_version",
            "app_hash",
            "operations",
            "token_hash",
            "expires",
            "max_calls",
            "version",
        )
        return {key: row[key] for key in keys}
    if kind == "AUTOMATION":
        keys = ("id", "app_id", "grant_id", "owner", "version", "proposal", "summary", "summary_hash")
        return {key: row[key] for key in keys}
    if kind == "CAMPAIGN":
        keys = ("id", "app_id", "owner", "owner_version", "summary", "summary_hash")
        return {key: row[key] for key in keys}
    keys = ("id", "app_id", "request_id", "request_hash", "data", "hash")
    return {key: row[key] for key in keys}


def _valid_proof(proof: AuthorityExpiryConsentsRow, revision: int, binding: str, prior: str, current: str) -> bool:
    fields = dict(proof)
    fields.pop("receipt_hash")
    if not fields.get("stable_hash"):
        fields.pop("stable_hash", None)
    return all(
        (
            proof["revision"] == revision + 1,
            proof["base_hash"] == binding,
            proof["previous_hash"] == prior,
            proof["old_expiry"] == current,
            digest(fields) == proof["receipt_hash"],
            iso_time(proof["new_expiry"]) > iso_time(current),
        )
    )


def effective_expiry(db: sqlite3.Connection, kind: str, row: AuthorityRow, base_expiry: object) -> ExpiryProof:
    """Validate the entire contiguous chain against the unchanged base record."""
    binding_value = _binding(kind, row)
    if kind == "AGENT_GRANT":
        review = db.execute(
            "SELECT operations FROM agent_grant_review_policy WHERE grant_id=?", (row["id"],)
        ).fetchone()
        binding_value = dict(scope=binding_value, review_operations=review["operations"] if review else None)
    binding = digest(binding_value)
    prior = ""
    current = iso_time(base_expiry).astimezone(timezone.utc).isoformat()
    revision = 0
    for saved in db.execute(
        "SELECT * FROM authority_expiry_consents WHERE app_id=? AND kind=? AND authority_id=? ORDER BY revision",
        (row["app_id"], kind, row["id"]),
    ):
        proof = cast(AuthorityExpiryConsentsRow, dict(saved))
        if not _valid_proof(proof, revision, binding, prior, current):
            raise PermissionError("Expiry consent chain is invalid or authority changed")
        revision = proof["revision"]
        prior = proof["receipt_hash"]
        current = proof["new_expiry"]
    return ExpiryProof(expires=current, revision=revision, receipt_hash=prior, base_hash=binding)


def _row(db, app_id, kind, identity):
    tables = {
        "AGENT_GRANT": "agent_grants",
        "AUTOMATION": "automation_policies",
        "CAMPAIGN": "campaign_scopes",
        "ORGANIC_POLICY": "organic_video_policies",
    }
    if not isinstance(kind, str) or kind not in tables:
        raise Invalid("Unknown expiry authority kind")
    try:
        row = db.execute(
            "SELECT * FROM " + tables[kind] + " WHERE app_id=? AND id=?",  # noqa: S608 - closed table map
            (app_id, identity),
        ).fetchone()
    except Exception as exc:
        import sqlite3

        if isinstance(exc, sqlite3.OperationalError) and "no such table" in str(exc):
            raise Invalid("Authority is unavailable") from None
        raise
    if not row:
        raise Invalid("Authority is unavailable")
    return row


def _scope_data(db, app_id, kind, row):
    if kind == "AGENT_GRANT":
        data = dict(
            owner=row["owner"],
            owner_version=row["owner_version"],
            app_version=row["app_version"],
            app_hash=row["app_hash"],
        )
        expiry = row["expires"]
    elif kind == "AUTOMATION":
        data = json.loads(row["summary"])
        if digest(data) != row["summary_hash"]:
            raise PermissionError("Standing approval integrity changed")
        grant = _row(db, app_id, "AGENT_GRANT", row["grant_id"])
        data = dict(
            owner=row["owner"],
            owner_version=grant["owner_version"],
            app_version=grant["app_version"],
            app_hash=grant["app_hash"],
        )
        proposal = json.loads(row["proposal"])
        expiry = initial_base(proposal["limits"]["expires"], row["created"], proposal.get("extended_expiry_consent"))
    elif kind == "CAMPAIGN":
        data = json.loads(row["summary"])
        if digest(data) != row["summary_hash"]:
            raise PermissionError("Campaign approval integrity changed")
        expiry = initial_base(data["expires_at"], row["created"], data.get("extended_expiry_consent"))
        data = dict(
            owner=data["owner_principal"],
            owner_version=data["owner_version"],
            app_version=data["app_version"],
            app_hash=data["app_hash"],
        )
    else:
        data = json.loads(row["data"])
        if digest(data) != row["hash"]:
            raise PermissionError("Organic approval integrity changed")
        expiry = initial_base(
            data["policy"]["expires_at"], row["created"], data["policy"].get("extended_expiry_consent")
        )
    return data, expiry


def _scope(db, app_id, kind, identity):
    row = _row(db, app_id, kind, identity)
    data, base_date = _scope_data(db, app_id, kind, row)
    if kind != "ORGANIC_POLICY" and row["status"] != "ACTIVE":
        raise PermissionError("Authority is not active")
    if (
        kind == "ORGANIC_POLICY"
        and db.execute("SELECT 1 FROM organic_video_policy_revocations WHERE policy_id=?", (identity,)).fetchone()
    ):
        raise PermissionError("Authority is revoked")
    exact_role(db, app_id, data["owner"], data["owner_version"], "OWNER")
    from .agent_grants import app_scope

    if app_scope(db, app_id) != (data["app_version"], data["app_hash"]):
        raise PermissionError("Authority app scope changed")
    return row, data, effective_expiry(db, kind, row, base_date)


def _campaign_facts(db, app_id, row):
    scope = json.loads(row["summary"])
    connection_row = db.execute(
        "SELECT * FROM social_connections WHERE app_id=? AND id=?", (app_id, scope["connection_id"])
    ).fetchone()
    if (
        not connection_row
        or connection_row["version"] != scope["connection_version"]
        or connection_row["provider"] != "facebook"
        or connection_row["status"] != "CONNECTED_READ_TESTED"
        or connection_row["lease"]
    ):
        raise PermissionError("Campaign connection changed or is uncertain")
    if json.loads(connection_row["data"]).get("destination", {}).get("id") != scope["page_id"]:
        raise PermissionError("Campaign Page changed")
    config = db.execute("SELECT * FROM social_configs WHERE app_id=? AND provider='facebook'", (app_id,)).fetchone()
    if not config or config["version"] != connection_row["config_version"] or config["status"] == "DISCONNECTED":
        raise PermissionError("Campaign configuration changed")


def _organic_facts(db, store, app_id, row):
    from .organic_video_policy import _proofs

    saved = json.loads(row["data"])
    policy = saved["policy"]
    page = db.execute(
        "SELECT * FROM social_connections WHERE app_id=? AND id=?", (app_id, policy["connection_id"])
    ).fetchone()
    if not _connected_page(page):
        raise PermissionError("Organic Page changed or is uncertain")
    binding = dict(
        version=page["version"], config_version=page["config_version"], data_hash=digest(json.loads(page["data"]))
    )
    if binding != saved["page"] or _proofs(db, store, app_id, policy) != saved["proofs"]:
        raise PermissionError("Organic Page, rights or evidence changed")
    config = db.execute("SELECT * FROM social_configs WHERE app_id=? AND provider='facebook'", (app_id,)).fetchone()
    if not config or config["version"] != page["config_version"] or config["status"] == "DISCONNECTED":
        raise PermissionError("Organic provider configuration changed")
    if "taste_auto_review" in policy:
        from .organic_video_taste_review import selected_grant

        reviewer = selected_grant(db, app_id, saved["owner"], policy["taste_auto_review"])
        if (reviewer["id"], reviewer["version"]) != (saved["taste_reviewer"]["id"], saved["taste_reviewer"]["version"]):
            raise PermissionError("Organic reviewer changed")


def _connected_page(page):
    return bool(
        page and not page["lease"] and page["provider"] == "facebook" and page["status"] == "CONNECTED_READ_TESTED"
    )


def _current_facts(db, store, app_id, kind, row, observed):
    """Recheck bound facts without treating verification age as permission."""
    if kind == "AUTOMATION":
        from .complete_automation import same_scope_after_verification, scope_summary

        saved = json.loads(row["summary"])
        actual = scope_summary(db, app_id, dict(principal=row["owner"]), json.loads(row["proposal"]), observed)
        proposal = json.loads(row["proposal"])
        legacy_refresh = legacy_verification_bound(db, row, proposal)
        if not same_scope_after_verification(saved, actual, ignore_readiness=True, allow_legacy_refresh=legacy_refresh):
            raise PermissionError("Standing scope changed; review a new scope")
    elif kind == "CAMPAIGN":
        _campaign_facts(db, app_id, row)
    elif kind == "ORGANIC_POLICY":
        _organic_facts(db, store, app_id, row)


def _bundle(db, app_id, kind, identity, row, data, requested, observed):
    if (
        kind == "AGENT_GRANT"
        and db.execute("SELECT 1 FROM automation_policies WHERE grant_id=? AND status='ACTIVE'", (identity,)).fetchone()
    ):
        raise Invalid("Extend the linked standing approval and grant together")
    bundle = []
    if kind == "AUTOMATION":
        grant, _, grant_current = _scope(db, app_id, "AGENT_GRANT", row["grant_id"])
        if grant["owner"] != row["owner"] or grant["owner_version"] != data["owner_version"]:
            raise PermissionError("Linked grant owner changed")
        if not observed < iso_time(grant_current["expires"]) < iso_time(requested):
            raise Invalid("Linked grant must be active and expire before the requested date")
        bundle.append(dict(kind="AGENT_GRANT", id=grant["id"], **grant_current))
        if db.execute(
            "SELECT 1 FROM automation_executions WHERE policy_id=? AND status IN ('UNKNOWN','CANCEL_REQUESTED','DISPATCHED')",
            (identity,),
        ).fetchone():
            raise Invalid("Standing execution needs reconciliation before extension")
    return bundle


def _usage(db, app_id, kind, identity, row):
    usage = {}
    if kind == "AGENT_GRANT":
        usage = dict(used=row["used"], max_calls=row["max_calls"])
    elif kind == "AUTOMATION":
        grant = _row(db, app_id, "AGENT_GRANT", row["grant_id"])
        usage = dict(used=grant["used"], max_calls=grant["max_calls"])
    elif kind == "CAMPAIGN":
        scope = json.loads(row["summary"])
        posts = db.execute(
            "SELECT id,status FROM campaign_intents WHERE app_id=? AND scope_id=?", (app_id, identity)
        ).fetchall()
        paid = db.execute(
            "SELECT id,status,commitment FROM campaign_paid_intents WHERE app_id=? AND scope_id=?", (app_id, identity)
        ).fetchall()
        usage = dict(
            calls=row["calls"],
            max_calls=scope["max_calls"],
            posts=[dict(item) for item in posts],
            paid_commitments=[dict(item) for item in paid],
            max_posts=scope["max_posts"],
            max_total_minor=scope["max_total_minor"],
        )
        usage["safety_calls"] = [
            dict(item)
            for item in db.execute(
                "SELECT category,used FROM campaign_safety_calls WHERE app_id=? AND scope_id=?", (app_id, identity)
            )
        ]
        for table in ("campaign_intents", "campaign_paid_intents"):
            if db.execute(
                "SELECT 1 FROM "  # noqa: S608 - closed table tuple
                + table
                + " WHERE app_id=? AND scope_id=? AND (status IN ('UNKNOWN','DISPATCHING') OR status LIKE 'PENDING_%')",
                (app_id, identity),
            ).fetchone():
                raise Invalid("Campaign outcome needs reconciliation before extension")
    elif kind == "ORGANIC_POLICY":
        policy = json.loads(row["data"])["policy"]
        generations = db.execute(
            "SELECT count(*) FROM organic_video_generation_reservations WHERE policy_id=?", (identity,)
        ).fetchone()[0]
        admissions = db.execute(
            "SELECT count(*),coalesce(sum(calls),0) FROM organic_video_admissions WHERE policy_id=?", (identity,)
        ).fetchone()
        usage = dict(
            generations=generations,
            max_generations=policy["max_generations"],
            posts=admissions[0],
            max_posts=policy["max_posts"],
            calls=admissions[1],
            max_calls=policy["max_calls"],
            max_model_minor=policy["max_model_minor"],
        )
    return usage


def _reviewed_scope(db, kind, row):
    if kind == "AGENT_GRANT":
        from .agent_review_policy import operations

        return dict(
            agent_id=row["agent_id"],
            operations=json.loads(row["operations"]),
            review_operations=operations(db, row["id"]),
            app_version=row["app_version"],
            app_hash=row["app_hash"],
            max_calls=row["max_calls"],
        )
    if kind in ("AUTOMATION", "CAMPAIGN"):
        return json.loads(row["summary"])
    return json.loads(row["data"])


def _readiness(db, app_id, kind, row, observed):
    if kind == "AUTOMATION":
        from .complete_automation import scope_summary, stable_connection_binding

        proposal = json.loads(row["proposal"])
        actual = scope_summary(db, app_id, dict(principal=row["owner"]), proposal, observed)
        return dict(
            status=actual["inventory"]["scope_status"],
            verification_due_at=actual["inventory"]["inference"].get("fresh_until"),
            verification_binding=stable_connection_binding(db, app_id, proposal["selection"]["agent_connection_id"]),
        )
    if kind in ("CAMPAIGN", "ORGANIC_POLICY"):
        scope = json.loads(row["summary"]) if kind == "CAMPAIGN" else json.loads(row["data"])["policy"]
        selected = db.execute(
            "SELECT expires,status FROM social_connections WHERE app_id=? AND id=?", (app_id, scope["connection_id"])
        ).fetchone()
        provider_expiry = (
            datetime.fromtimestamp(selected["expires"], timezone.utc).isoformat()
            if selected["expires"] is not None
            else None
        )
        return dict(connection_status=selected["status"], provider_expires_at=provider_expiry)
    return dict(status="INDEPENDENT_CHECKS_UNCHANGED")


def _organic_deadlines(db, identity, row):
    original = json.loads(row["data"])["policy"]["expires_at"]
    result = []
    for table, child_kind in (
        ("organic_video_generation_reservations", "GENERATION"),
        ("organic_video_admissions", "ADMISSION"),
    ):
        for child in db.execute(
            "SELECT id,data FROM " + table + " WHERE policy_id=?",  # noqa: S608 - closed table tuple
            (identity,),
        ):
            child_data = json.loads(child["data"])
            result.append(
                dict(
                    kind=child_kind,
                    id=child["id"],
                    expires=child_data.get("permission_expires_at", original),
                    status=child_data.get("status"),
                )
            )
    return result


def _table_present(db, name):
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def _schedule_deadlines(db, app_id, kind, identity, original):
    if not _table_present(db, "campaign_schedule_batches"):
        return []
    result = []
    batches = db.execute("SELECT * FROM campaign_schedule_batches WHERE app_id=? AND scope_id=?", (app_id, identity))
    for batch in batches:
        summary = json.loads(batch["summary"])
        if digest(summary) != batch["summary_hash"]:
            raise Invalid("Dependent schedule history changed")
        organic = summary.get("kind") == "ADMITTED_ORGANIC_VIDEO_V1"
        if organic != (kind == "ORGANIC_POLICY"):
            continue
        items = db.execute("SELECT * FROM campaign_schedule_items WHERE batch_id=?", (batch["id"],)).fetchall()
        from .campaign_schedule import validate_items

        validate_items(items, summary, require_future=False)
        for item in items:
            body = json.loads(item["body"])
            if digest(body) != item["body_hash"] or body not in summary["items"]:
                raise Invalid("Dependent schedule item history changed")
            expires = body.get("permission_expires_at", summary.get("permission_expires_at", original))
            result.append(
                dict(
                    kind="REEL_SCHEDULE" if organic else "CAMPAIGN_SCHEDULE",
                    id=item["id"],
                    batch_id=batch["id"],
                    expires=expires,
                    due_at=body["due_at"],
                    status=item["status"],
                )
            )
    return result


def _monitor_deadlines(db, app_id, identity):
    if not _table_present(db, "campaign_monitors"):
        return []
    result = []
    for row in db.execute("SELECT * FROM campaign_monitors WHERE app_id=?", (app_id,)):
        summary = json.loads(row["summary"])
        if summary.get("proposal", {}).get("scope_id") != identity:
            continue
        if digest(summary) != row["summary_hash"]:
            raise Invalid("Dependent monitor history changed")
        result.append(
            dict(kind="CAMPAIGN_MONITOR", id=row["id"], expires=summary["proposal"]["expires_at"], status=row["status"])
        )
    return result


def _dependent_deadlines(db, app_id, kind, identity, row):
    dependent_deadlines = []
    grant_id = identity if kind == "AGENT_GRANT" else (row["grant_id"] if kind == "AUTOMATION" else None)
    if grant_id:
        handoffs = db.execute(
            "SELECT id,expires,status FROM agent_handoffs WHERE app_id=? AND source_grant_id=?", (app_id, grant_id)
        )
        dependent_deadlines.extend(dict(kind="HANDOFF", **dict(item)) for item in handoffs)
        batches = db.execute("SELECT id,plan,state FROM creative_batches WHERE app_id=?", (app_id,))
        for item in batches:
            envelope = json.loads(item["plan"])
            if envelope.get("authority", {}).get("grant_id") == grant_id:
                dependent_deadlines.append(
                    dict(kind="BATCH", id=item["id"], expires=envelope["authority"]["expires"], status=item["state"])
                )
    if kind == "ORGANIC_POLICY":
        dependent_deadlines.extend(_organic_deadlines(db, identity, row))
        original = json.loads(row["data"])["policy"]["expires_at"]
        dependent_deadlines.extend(_schedule_deadlines(db, app_id, kind, identity, original))
    if kind == "CAMPAIGN":
        original = json.loads(row["summary"])["expires_at"]
        dependent_deadlines.extend(_schedule_deadlines(db, app_id, kind, identity, original))
        dependent_deadlines.extend(_monitor_deadlines(db, app_id, identity))
    if kind == "AUTOMATION":
        from .automation_execution import execution_deadline

        for execution in db.execute(
            "SELECT * FROM automation_executions WHERE policy_id=? ORDER BY created,id", (identity,)
        ):
            dependent_deadlines.append(
                dict(
                    kind="STANDING_EXECUTION",
                    id=execution["id"],
                    expires=execution_deadline(db, execution).isoformat(),
                    status=execution["status"],
                )
            )
    return dependent_deadlines


def _preview(db, store, app_id, user, body, observed):
    exact_keys(body, ("kind", "id", "expires"))
    kind, identity = body["kind"], body["id"]
    path_segment(identity)
    owner = member(db, app_id, user["principal"], "OWNER")
    row, data, current = _scope(db, app_id, kind, identity)
    _current_facts(db, store, app_id, kind, row, observed)
    if data["owner"] != user["principal"]:
        raise PermissionError("Only the approving owner may extend this authority")
    requested = deadline(body["expires"], observed, True).isoformat()
    if not observed < iso_time(current["expires"]) < iso_time(requested):
        raise Invalid("Authority must be active and the new expiry later than its current expiry")
    bundle = _bundle(db, app_id, kind, identity, row, data, requested, observed)
    usage = _usage(db, app_id, kind, identity, row)
    dependent_deadlines = _dependent_deadlines(db, app_id, kind, identity, row)
    return dict(
        kind=kind,
        id=identity,
        app_id=app_id,
        owner=user["principal"],
        owner_version=owner["version"],
        old_expiry=current["expires"],
        new_expiry=requested,
        revision=current["revision"],
        receipt_hash=current["receipt_hash"],
        base_hash=current["base_hash"],
        scope=_reviewed_scope(db, kind, row),
        usage=usage,
        bundle=bundle,
        readiness=_readiness(db, app_id, kind, row, observed),
        dependent_deadlines=dependent_deadlines,
        dependent_work="Existing child deadlines and independent verification remain unchanged; reapprove new work as required.",
    )


def _append(
    db,
    app_id,
    kind,
    identity,
    current,
    new_expiry,
    owner,
    owner_version,
    preview_hash,
    request_id,
    confirmed,
    stable_hash=None,
):
    fields = dict(
        app_id=app_id,
        kind=kind,
        authority_id=identity,
        revision=current["revision"] + 1,
        base_hash=current["base_hash"],
        previous_hash=current["receipt_hash"],
        old_expiry=current["expires"],
        new_expiry=new_expiry,
        owner=owner,
        owner_version=owner_version,
        preview_hash=preview_hash,
        request_id=request_id,
        confirmed=confirmed,
    )
    if stable_hash:
        fields["stable_hash"] = stable_hash
    fields["receipt_hash"] = digest(fields)
    fields.setdefault("stable_hash", "")
    db.execute(
        "INSERT INTO authority_expiry_consents ("  # noqa: S608 - fields are fixed local keys
        + ",".join(fields)
        + ") VALUES ("
        + ",".join("?" for _ in fields)
        + ")",
        tuple(fields.values()),
    )
    return fields


def legacy_verification_bound(db, row, proposal):
    """Use only a stable configuration captured by an exact active-owner review."""
    from .complete_automation import stable_connection_binding

    proof = db.execute(
        "SELECT stable_hash FROM authority_expiry_consents WHERE app_id=? AND kind='AUTOMATION' AND authority_id=? ORDER BY revision DESC LIMIT 1",
        (row["app_id"], row["id"]),
    ).fetchone()
    if not proof or not proof["stable_hash"]:
        return False
    return proof["stable_hash"] == stable_connection_binding(
        db, row["app_id"], proposal["selection"]["agent_connection_id"]
    )


def _confirm_input(body):
    exact_keys(body, ("preview", "preview_hash", "request_id", "extended_expiry_consent"))
    if body["extended_expiry_consent"] is not True:
        raise Invalid("Explicit owner consent is required")
    path_segment(body["request_id"])
    preview = body["preview"]
    if not isinstance(preview, dict) or digest(preview) != body["preview_hash"]:
        raise Invalid("Expiry preview changed")
    return preview


def record_initial(db, kind, row, base_expiry, requested, owner, owner_version, reviewed, observed):
    """Record the explicitly reviewed initial long lifetime in the issuing transaction."""
    current = effective_expiry(db, kind, row, base_expiry)
    if iso_time(requested) > iso_time(current["expires"]):
        return _append(
            db,
            row["app_id"],
            kind,
            row["id"],
            current,
            iso_time(requested).astimezone(timezone.utc).isoformat(),
            owner,
            owner_version,
            digest(reviewed),
            "initial-consent",
            observed.isoformat(),
        )


def initial_base(requested, created, consent):
    """Long reviewed records start their auditable chain at their default expiry."""
    expiry = iso_time(requested).astimezone(timezone.utc)
    if consent is True:
        return min(expiry, iso_time(created).astimezone(timezone.utc) + timedelta(hours=24)).isoformat()
    return expiry.isoformat()


class AuthorityExpiry:
    def __init__(self, store, clock=None):
        self.store = store
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def preview(self, app_id, user, body):
        with connection(self.store.path) as db:
            db.execute("BEGIN")
            result = _preview(db, self.store, app_id, user, body, self.clock())
        return dict(preview=result, preview_hash=digest(result))

    def confirm(self, app_id, user, body):
        preview = _confirm_input(body)
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            member(db, app_id, user["principal"], "OWNER")
            prior = db.execute(
                "SELECT * FROM authority_expiry_consents WHERE app_id=? AND kind=? AND authority_id=? AND request_id=?",
                (app_id, preview.get("kind"), preview.get("id"), body["request_id"]),
            ).fetchone()
            if prior:
                if prior["preview_hash"] != body["preview_hash"] or prior["owner"] != user["principal"]:
                    raise Invalid("Request identity was used for another approval")
                return dict(receipt=dict(prior), replay=True)
            observed = self.clock()
            fresh = _preview(
                db,
                self.store,
                app_id,
                user,
                dict(kind=preview.get("kind"), id=preview.get("id"), expires=preview.get("new_expiry")),
                observed,
            )
            if fresh != preview:
                raise Invalid("Expiry preview changed; review again")
            current = dict(
                expires=preview["old_expiry"],
                revision=preview["revision"],
                receipt_hash=preview["receipt_hash"],
                base_hash=preview["base_hash"],
            )
            stable = preview["readiness"].get("verification_binding") if preview["kind"] == "AUTOMATION" else None
            receipt = _append(
                db,
                app_id,
                preview["kind"],
                preview["id"],
                current,
                preview["new_expiry"],
                user["principal"],
                preview["owner_version"],
                body["preview_hash"],
                body["request_id"],
                observed.isoformat(),
                stable,
            )
            for item in preview["bundle"]:
                _append(
                    db,
                    app_id,
                    item["kind"],
                    item["id"],
                    item,
                    preview["new_expiry"],
                    user["principal"],
                    preview["owner_version"],
                    body["preview_hash"],
                    body["request_id"],
                    observed.isoformat(),
                )
        return dict(receipt=receipt, replay=False)

    def history(self, app_id, user, kind, identity):
        with connection(self.store.path) as db:
            member(db, app_id, user["principal"], "OWNER")
            _row(db, app_id, kind, identity)
            rows = db.execute(
                "SELECT * FROM authority_expiry_consents WHERE app_id=? AND kind=? AND authority_id=? ORDER BY revision",
                (app_id, kind, identity),
            )
            return dict(receipts=[dict(row) for row in rows])
