"""Exact scoped-agent video operations; owner approval is never an agent tool."""

from .common import Invalid
from .campaign_contract import REEL_FIELDS
from .db import connection
from .organic_video_policy import Policies, _authority, _saved
from . import campaign_video_execution as video

FIELDS = {
    "policy-read": {"policy_id", "policy_hash"},
    "policy-reserve": {"policy_id", "policy_hash", "request_id", "template_id", "render_input"},
    "policy-admit": {"policy_id", "policy_hash", "output"},
    "workflow-prepare": {
        "request_id",
        "intake_id",
        "intake_hash",
        "policy_id",
        "policy_hash",
        "template_id",
        "render_input",
    },
    "intent-create": set(REEL_FIELDS),
    "intent-read": {"intent_id"},
    "intent-execute": {"intent_id"},
}


def dispatch(store, app_id, action, body):
    """Reuse the current protected admission and exact current approving owner."""
    if action not in FIELDS or not isinstance(body, dict) or set(body) != FIELDS[action]:
        raise Invalid("Use the exact supported scoped video operation fields")
    with connection(store.path) as db:
        context = _authority(db, store, app_id, "organic-video." + action, body)
        if "grant_id" not in context:
            raise PermissionError("Use a scoped video grant; owner controls have separate routes")
        grant = db.execute("SELECT owner FROM agent_grants WHERE id=?", (context["grant_id"],)).fetchone()
        if action in ("intent-read", "intent-execute"):
            row = video._row(db, app_id, body["intent_id"])
            import json

            policy_id = json.loads(row["data"])["request"]["policy_id"]
        else:
            policy_id = body["policy_id"]
        policy = _saved(
            db.execute("SELECT * FROM organic_video_policies WHERE app_id=? AND id=?", (app_id, policy_id)).fetchone()
        )
        if grant is None or grant["owner"] != policy["data"]["owner"]:
            raise PermissionError("Video policy belongs to another approving owner")
        if action == "intent-read":
            return video._view(row)
        from .operation_authority import check

        actor = check(db, context)
    if action.startswith("policy-"):
        return getattr(Policies(store), action.removeprefix("policy-"))(app_id, body)
    if action == "workflow-prepare":
        from .organic_video_workflow import prepare

        return prepare(store, app_id, actor, body)
    if action == "intent-create":
        return video.create_intent(store, app_id, actor, body)
    return video.execute(store, app_id, actor, body["intent_id"], None)
