"""Owner-scoped rules and recommendation routes over the local runtime."""

import re
from urllib.parse import urlparse

from .common import Invalid


def get(handler, app_id: str, route: list[str]) -> None:
    query = urlparse(handler.path).query
    if route not in (["proposals"], ["rules"], ["rules", "history"]):
        raise KeyError("Unknown automation route")
    if query and (route != ["rules", "history"] or not re.fullmatch(r"before=[1-9][0-9]{0,18}", query)):
        raise Invalid("Use the exact automation address or one rule history cursor")
    user, recheck = handler.automation_owner_session()
    store = handler.server.service.store
    owner = user["principal"]
    if route == ["proposals"]:
        from .automation_proposal_schedule import read as read_rule_schedule
        from .automation_proposals import inbox

        result = {**inbox(store, app_id, owner), "schedule": read_rule_schedule(store, app_id, owner)}
    elif route == ["rules", "history"]:
        from .automation_store import version_index

        result = version_index(store, app_id, owner, int(query[7:]) if query else None)
    else:
        from .automation_store import current

        result = current(store, app_id, owner)
    recheck()
    return handler.send(200, result)


def post(handler, parts: list[str], data: object) -> None:
    """Preview or save local owner-authored rules without granting action authority."""
    if len(parts) == 6 and parts[4] == "proposals" and not urlparse(handler.path).query:
        return post_proposals(handler, parts[2], parts[5], data)
    if len(parts) != 5 or parts[4] not in ("evaluate", "rules") or urlparse(handler.path).query:
        raise Invalid("Use the exact automation rule preview or save address")
    user, recheck = handler.automation_owner_session()
    store = handler.server.service.store
    if parts[4] == "rules":
        if not isinstance(data, dict) or set(data) != {"document"}:
            raise Invalid("Submit the exact rules document")
        from .automation_store import save

        return handler.send(201, save(store, parts[2], user, data["document"], commit_check=recheck))
    if not isinstance(data, dict) or set(data) - {"study"} not in ({"rules"}, {"saved"}):
        raise Invalid("Submit a rules draft or an exact saved version")
    if "saved" in data and not isinstance(data["saved"], dict):
        raise Invalid("Choose a saved version and its exact fingerprint")
    if "study" in data and not isinstance(data["study"], dict):
        raise Invalid("Choose the exact study and its fingerprint")
    from .automation_rules import simulate_database

    result = simulate_database(
        store.path,
        parts[2],
        user["principal"],
        rules=data.get("rules"),
        reference=data.get("saved"),
        study=data.get("study"),
    )
    recheck()
    return handler.send(200, result)


def post_proposals(handler, app_id: str, operation: str, data: object) -> None:
    """Save or dismiss recommendations, or configure a proposal-only schedule."""
    user, recheck = handler.automation_owner_session()
    store = handler.server.service.store
    if not isinstance(data, dict):
        raise Invalid("Submit an exact proposal request")
    if operation == "run" and set(data) == {"app_version", "saved", "study", "request_id"}:
        from .automation_proposals import run as run_proposals

        if not isinstance(data["request_id"], str):
            raise Invalid("A valid rule request ID is required")
        result = run_proposals(
            store,
            app_id,
            user["principal"],
            data["app_version"],
            data["saved"],
            data["study"],
            request_id=data["request_id"],
            commit_check=recheck,
        )
    elif operation == "dismiss" and set(data) == {"id"}:
        from .automation_proposals import dismiss

        result = dismiss(store, app_id, user["principal"], data["id"], commit_check=recheck)
    elif operation == "schedule":
        from .automation_proposal_schedule import configure

        result = configure(store, app_id, user["principal"], data, commit_check=recheck)
    else:
        raise Invalid("Choose an exact saved-proposal action")
    return handler.send(200, result)
