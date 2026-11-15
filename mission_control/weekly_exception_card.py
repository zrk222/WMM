"""Shared owner-private, hash-bound exception cards."""

from .common import digest, now


def exception_card(
    app: dict,
    principal: str,
    category: str,
    identity: str,
    state: str,
    title: str,
    reason: str,
    repair: str,
    tool: str,
    refs: dict,
    source: dict,
    priority: int,
) -> dict:
    receipt = dict(
        app_id=app["id"],
        manifest_version=app["version"],
        source_hash=digest(source),
        observed_at=now(),
        source_updated_at=source.get("updated"),
    )
    return dict(
        id=digest([app["id"], category, identity]),
        app_id=app["id"],
        app_name=app["data"]["name"],
        category=category,
        priority=priority,
        state=state,
        title=title,
        reason=reason,
        next_action=repair,
        resolution_route=tool,
        action=dict(tool=tool, resource_id=identity, **refs),
        source_receipt=receipt,
        change="CURRENT_EXCEPTION_NO_PRIOR_DELIVERY_COMPARISON",
        cost_minor=None,
        owner="App owner",
        owner_only=True,
        owner_principal=principal,
        evidence=source,
    )
