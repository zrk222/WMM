"""Fresh-owner admission for bounded external-agent video research tasks."""

import secrets

from .common import Invalid, identifier
from .discovery_http import json_body
from .managed_media_http import singleton
from .operation_authority import bound_owner, protected
from .organic_video_collector import prepare

POLICY_ACTIONS = {
    "policy-create": "create",
    "policy-read": "read",
    "policy-revoke": "revoke",
    "policy-reserve": "reserve",
    "policy-admit": "admit",
}
WORKFLOW_ACTIONS = {"workflow-prepare": "prepare", "render-status": "render_status", "render-queue": "queue_render"}
INTENT_ACTIONS = {"intent-create", "intent-read", "intent-execute", "intent-reconcile"}
SCHEDULE_ACTIONS = {"schedule-prepare", "schedule-activate", "schedule-status", "schedule-revoke"}


def post(handler, parts):
    """Preparing research is owner-only; recipient agents use the scoped gateway."""
    if (
        len(parts) != 5
        or parts[:2] != ["api", "apps"]
        or parts[3] != "organic-video"
        or parts[4]
        not in {
            "prepare",
            "task-list",
            "task-read",
            "intake",
            "policy-context",
            "policy-history",
            *POLICY_ACTIONS,
            *WORKFLOW_ACTIONS,
            *INTENT_ACTIONS,
            *SCHEDULE_ACTIONS,
            "import-demo",
        }
    ):
        raise Invalid("Use the exact video research preparation address")
    identifier(parts[2])
    if handler.command != "POST" or handler.path != "/" + "/".join(parts):
        raise Invalid("Use an exact video research POST without query")
    origin = "http://127.0.0.1:" + str(handler.server.server_port)
    if handler.headers.get_all("Host") != [origin[7:]]:
        raise PermissionError("Use the exact local video research host")
    if handler.headers.get_all("Origin") != [origin]:
        raise PermissionError("Use the exact local video research origin")
    if handler.headers.get_all("Authorization") is not None:
        raise PermissionError("Video research preparation requires an owner session only")
    session = handler.session()
    user = handler.server.identities.fresh(session)
    if not secrets.compare_digest(singleton(handler, "X-CSRF-Token"), session):
        raise PermissionError("Reload the current video research session")
    if parts[4] == "import-demo":
        # One closed JSON selection header and original MP4 bytes, never a path,
        # actor, credential scope or caller-supplied byte digest.
        from .managed_media_http import body as media_body, MAX_BYTES
        from .operator_client import strict_json
        from .organic_video_capture import intake_envelope, import_owner_demo

        selection_header = singleton(handler, "X-WMM-Demo-Selection")
        if len(selection_header) > 4096:
            raise Invalid("Demo selection exceeds its bounded header limit")
        selection = strict_json(selection_header.encode("utf-8"))
        raw = media_body(handler, "application/octet-stream", MAX_BYTES)
        envelope = intake_envelope(parts[2], selection, raw)
        store = handler.server.service.store
        with bound_owner(store, envelope, handler.server.identities, session, user):
            result = import_owner_demo(store, parts[2], selection, raw)
        return handler.send(201, result)
    body = json_body(handler, "Video research")
    store = handler.server.service.store
    action = parts[4]
    envelope = dict(app_id=parts[2], operation="organic-video." + action, input=body)
    with bound_owner(store, envelope, handler.server.identities, session, user):
        with protected(store, envelope) as actor:
            if action == "prepare":
                result = prepare(store, parts[2], actor, body)
            elif action in WORKFLOW_ACTIONS:
                from . import organic_video_workflow

                result = getattr(organic_video_workflow, WORKFLOW_ACTIONS[action])(store, parts[2], actor, body)
            elif action in {"policy-context", "policy-history"}:
                from .organic_video_policy_ui import context, history

                result = (context if action == "policy-context" else history)(store, parts[2], actor, body)
            elif action in SCHEDULE_ACTIONS:
                result = schedule(store, parts[2], action, body)
            elif action == "intake":
                from .organic_video_intake import adopt

                result = adopt(store, parts[2], actor, body)
            elif action in {"task-read", "task-list"}:
                from .organic_video_collector import owner_read, owner_history

                result = (owner_read if action == "task-read" else owner_history)(store, parts[2], actor, body)
            elif action in INTENT_ACTIONS:
                from . import campaign_video_execution as video
                from .campaign_contract import exact

                if action == "intent-create":
                    result = video.create_intent(store, parts[2], actor, body)
                else:
                    exact(body, ("intent_id",))
                    if action == "intent-read":
                        from .db import connection
                        from .organic_video_policy import _saved
                        import json

                        with connection(store.path) as db:
                            row = video._row(db, parts[2], body["intent_id"])
                            request = json.loads(row["data"])["request"]
                            policy = _saved(
                                db.execute(
                                    "SELECT * FROM organic_video_policies WHERE app_id=? AND id=?",
                                    (parts[2], request["policy_id"]),
                                ).fetchone()
                            )
                            if policy["data"]["owner"] != actor:
                                raise PermissionError("Reel intent belongs to another owner")
                            result = video._view(row)
                    else:
                        run = video.execute if action == "intent-execute" else video.reconcile
                        result = run(store, parts[2], actor, body["intent_id"], None)
            else:
                from .organic_video_policy import Policies

                result = getattr(Policies(store), POLICY_ACTIONS[action])(parts[2], body)
            return handler.send(200, result)


def schedule(store, app_id, action, body):
    from .campaign_contract import exact
    from .organic_video_schedule import VideoSchedules

    service = VideoSchedules(store)
    if action == "schedule-prepare":
        return service.prepare(app_id, body)
    if action == "schedule-activate":
        return service.activate(app_id, body)
    if action == "schedule-status":
        exact(body, ("batch_id",))
        return service.status(app_id, body["batch_id"])
    exact(body, ("batch_id", "version"))
    from .campaign_schedule import CampaignSchedules

    return CampaignSchedules(store).revoke(app_id, body["batch_id"], body["version"])
