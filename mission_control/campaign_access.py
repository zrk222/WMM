"""Fresh owner or scoped-agent access to finite external campaign effects."""

import json
import re

from .common import Invalid
from .db import connection
from .operation_authority import PROTECTED, REQUEST, check, store_identity
from .social_contract import reference

OWNER_ACTIONS = {"prepare", "activate", "revoke"}
FIELDS = {
    "history": set(),
    "prepare": {"scope"},
    "activate": {"scope_id", "approval_hash"},
    "revoke": {"scope_id"},
    "status": {"scope_id"},
    "publish": {"scope_id", "request"},
    "ad-launch": {"scope_id", "request"},
    "pause": {"scope_id", "intent_id"},
    "reconcile": {"scope_id", "intent_id"},
}


def identity(store, app_id):
    """Body identities and local cookies alone cannot approve external effects."""
    context = REQUEST.get()
    if context is None or PROTECTED.get() is not context or context["store"] != store_identity(store):
        raise PermissionError("Current protected campaign authority is required")
    if json.loads(context["envelope"])["app_id"] != app_id:
        raise PermissionError("Campaign authority belongs to another app")
    with connection(store.path) as db:
        actor = check(db, context)
    return context, actor


def policy_checker(store):
    """Recheck the live gateway and owner relationship at every effect boundary."""

    def verify(app_id, actor, scope, action):
        if retained_check(store, app_id, actor, scope, action):
            return
        context, current_actor = identity(store, app_id)
        if actor != current_actor:
            raise PermissionError("Campaign actor changed")
        if action in {"PREPARE", "ACTIVATE", "REVOKE"} and "principal" not in context:
            raise PermissionError("Only the authenticated owner may approve campaign scope")
        if "grant_id" in context:
            with connection(store.path) as db:
                grant = db.execute("SELECT owner FROM agent_grants WHERE id=?", (context["grant_id"],)).fetchone()
                if grant is None or scope.get("owner_principal") != grant["owner"]:
                    raise PermissionError("Campaign scope belongs to another owner")
        elif scope.get("owner_principal", current_actor) != current_actor:
            raise PermissionError("Campaign scope belongs to another owner")

    return verify


def retained_check(store, app_id, actor, scope, action):
    """Try closed host-job capabilities before existing owner or grant access."""
    from .campaign_monitor_authority import check as monitor_check
    from .campaign_schedule_authority import check as schedule_check

    return any(validator(store, app_id, actor, scope, action) for validator in (monitor_check, schedule_check))


def scope_owner(store, context, actor):
    """Resolve only the authenticated owner behind the currently admitted grant."""
    if "grant_id" not in context:
        return actor
    with connection(store.path) as db:
        row = db.execute("SELECT owner FROM agent_grants WHERE id=?", (context["grant_id"],)).fetchone()
        if row is None:
            raise PermissionError("Campaign grant is unavailable")
        return row["owner"]


def dispatch(store, app_id, action, body):
    """All clients share the same scope, budget, idempotency and provider checks."""
    validate_fields(action, body)
    context, actor = identity(store, app_id)
    if action in OWNER_ACTIONS and "principal" not in context:
        raise PermissionError("Agents cannot create, activate or widen campaign authority")
    from .campaign_execution import CampaignExecutionService

    service = CampaignExecutionService(store, policy_checker(store))

    def read_scope(value):
        if "principal" in context:
            return value
        return {key: item for key, item in value.items() if key != "measurement_plan"}

    def read_intent(value):
        if "principal" in context or not isinstance(value.get("result"), dict):
            return value
        return dict(value, result={key: item for key, item in value["result"].items() if key != "destination_check"})

    if action == "history":
        owner = scope_owner(store, context, actor)
        if "approved_link_sha256" not in body:
            return dict(scopes=[read_scope(scope) for scope in service.list_scopes(app_id, owner)])
        if "principal" not in context:
            raise PermissionError("Only the authenticated owner can look up tracked post receipts")
        return dict(
            scopes=service.list_scopes(app_id, owner),
            tracked_posts=service.tracked_posts(app_id, owner, body["approved_link_sha256"]),
        )
    if action == "prepare":
        return service.prepare_scope(app_id, actor, body["scope"])
    scope_id = reference(body["scope_id"])
    if "intent_id" in body:
        reference(body["intent_id"])
    with connection(store.path) as db:
        owned = db.execute(
            "SELECT 1 FROM campaign_scopes WHERE app_id=? AND id=? AND owner=?",
            (app_id, scope_id, scope_owner(store, context, actor)),
        ).fetchone()
        if owned is None:
            raise PermissionError("Campaign scope is unavailable for this owner")
    scope = service.get_scope(app_id, scope_id)
    policy_checker(store)(app_id, actor, scope, "ACCESS")
    routes = {
        "activate": lambda: service.activate_scope(app_id, actor, scope_id, body["approval_hash"]),
        "revoke": lambda: service.revoke_scope(app_id, actor, scope_id),
        "status": lambda: dict(
            scope=read_scope(scope), intents=[read_intent(intent) for intent in service.list_intents(app_id, scope_id)]
        ),
        "publish": lambda: service.run_post(app_id, actor, scope_id, body["request"]),
        "ad-launch": lambda: service.run_ad(app_id, actor, scope_id, body["request"]),
        "pause": lambda: service.run_pause(app_id, actor, scope_id, body["intent_id"]),
        "reconcile": lambda: service.reconcile(app_id, actor, scope_id, body["intent_id"]),
    }
    result = routes[action]()
    return read_intent(result) if action in {"publish", "reconcile"} else result


def validate_fields(action, body):
    """Close every owner and agent campaign payload before resolving authority."""
    if action == "history" and isinstance(body, dict) and set(body) == {"approved_link_sha256"}:
        value = body["approved_link_sha256"]
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
            raise Invalid("Choose a valid tracked-link fingerprint")
        return
    if action not in FIELDS or not isinstance(body, dict) or set(body) != FIELDS[action]:
        raise Invalid("Use the exact campaign operation fields")
