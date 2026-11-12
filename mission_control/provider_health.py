"""Read-only provider health projection; login and key presence are not analytics permission."""

import re

ACTIONABLE = {
    "RECONNECT_REQUIRED",
    "PROTECTED_STORAGE_UNAVAILABLE",
    "DISCONNECTED",
    "EXPIRED",
    "UNCONFIRMED",
    "PERMISSION_REQUIRED",
}
PENDING = {"CONFIGURED_UNTESTED", "ENVIRONMENT_REFERENCE", "PENDING", "EXCHANGING"}


def _entry(
    provider, kind, state, permission, scope=None, expires=None, failure=None, action=None, route=None, as_of=None
):
    """Keep one provider row free of credentials, tokens and raw provider payloads."""
    return dict(
        provider=provider,
        kind=kind,
        state=state,
        login_state=state,
        permission_state=permission,
        scope=scope or {},
        expires_at=expires,
        failure=failure,
        next_action=action,
        recovery_route=route,
        as_of=as_of,
    )


def _failure(value):
    """Retain only a bounded uppercase failure code, never a raw provider message."""
    if isinstance(value, str) and re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", value):
        return value
    return "READ_FAILED" if value else None


def _store_records(workspace):
    statuses = workspace.get("connections") or {}
    entries = []
    for record in workspace.get("records") or []:
        if record.get("kind") != "connection":
            continue
        data = record.get("data") or {}
        provider = data.get("provider")
        if provider not in ("app_store", "apple_ads"):
            continue
        status = (statuses.get(record.get("id")) or {}).get("status", "UNKNOWN")
        scope = {key: data[key] for key in ("store_app_id", "account_id") if data.get(key)}
        if status in ("RECONNECT_REQUIRED", "PROTECTED_STORAGE_UNAVAILABLE", "DISCONNECTED"):
            action, route = "Reconnect this protected key and test its current scope", "connections"
        elif status == "ENVIRONMENT_REFERENCE":
            action, route = "Move this access into protected local storage", "connections"
        else:
            action, route = "Run a supported read test to confirm the current provider scope", "connections"
        entries.append(
            _entry(provider, "STORE_READ", status, "ANALYTICS_READ_UNVERIFIED", scope=scope, action=action, route=route)
        )
    return entries


def _insights(workspace):
    entries = []
    for source in (workspace.get("insights") or {}).get("sources") or []:
        provider = source.get("provider")
        if provider not in ("posthog", "clarity", "revenuecat"):
            continue
        status = source.get("status") or "UNKNOWN"
        data = source.get("data") or {}
        scope = {key: data[key] for key in ("project_id", "region") if data.get(key)}
        failure = _failure(source.get("last_error"))
        if status == "CONNECTED":
            permission = "ANALYTICS_READ_CONFIGURED"
            action, route = "Inspect the latest saved reading or refresh within its schedule", "measurement-connections"
        elif status == "PERMISSION_REQUIRED":
            permission = "ANALYTICS_PERMISSION_REQUIRED"
            action, route = "Grant the exact analytics permission or reconnect this source", "measurement-connections"
        else:
            permission = "ANALYTICS_READ_UNVERIFIED"
            action, route = (
                "Reconnect this analytics source and test its current project scope",
                "measurement-connections",
            )
        entries.append(
            _entry(
                provider,
                "ANALYTICS_READ",
                status,
                permission,
                scope=scope,
                failure=failure,
                action=action,
                route=route,
                as_of=source.get("updated"),
            )
        )
    return entries


def _social(workspace):
    entries = []
    for account in (workspace.get("social_access") or {}).get("accounts") or []:
        provider = account.get("provider")
        if not provider:
            continue
        reconnect = bool(account.get("reconnect_required"))
        status = "RECONNECT_REQUIRED" if reconnect else (account.get("status") or "UNKNOWN")
        action = (
            "Reconnect this publishing account before the next approved post"
            if reconnect
            else "Review the exact publishing scope; this login is not analytics permission"
        )
        entries.append(
            _entry(
                provider,
                "PUBLISHING",
                status,
                "PUBLISHING_ONLY_NOT_ANALYTICS",
                scope={},
                expires=account.get("expires"),
                action=action,
                route="connections",
                as_of=account.get("updated"),
            )
        )
    return entries


def _play(workspace):
    entries = []
    for flow in (workspace.get("play") or {}).get("flows") or []:
        status = flow.get("status") or "UNKNOWN"
        config = flow.get("config") or {}
        action = (
            "Reconnect Google Play if this local login expired or was not confirmed"
            if status in ("EXPIRED", "UNCONFIRMED", "CANCELLED")
            else "Finish the local Google login if it is still pending; a login is not a report read"
        )
        entries.append(
            _entry(
                "google_play",
                "PROVIDER_LOGIN",
                status,
                "NOT_ANALYTICS_PERMISSION",
                scope={key: config[key] for key in ("package_name",) if config.get(key)},
                expires=flow.get("expires"),
                action=action,
                route="connections",
                as_of=flow.get("updated"),
            )
        )
    return entries


def _priority(entry):
    if entry["state"] in ACTIONABLE:
        return 0
    if entry["failure"]:
        return 1
    if entry["state"] in PENDING:
        return 2
    return 3


def project(workspace):
    """Unify supported provider state and one exact recovery path without new authority."""
    entries = _store_records(workspace) + _insights(workspace) + _social(workspace) + _play(workspace)
    entries.sort(key=lambda item: (item["provider"], item["kind"], item["state"]))
    ordered = sorted(entries, key=_priority)
    recovery = ordered[0] if ordered and _priority(ordered[0]) < 3 else None
    return dict(
        schema="growth.provider-health.v1",
        entries=entries,
        recovery=recovery,
        scope="Current saved local state only. Login, key presence and publishing access are not analytics permission, provider delivery or measured outcomes.",
    )


def recovery_text(value):
    """Render one exact next action; absence is an explicit no-recovery state."""
    if not value:
        return "No provider needs repair from the saved local state. Missing scope or delivery is not inferred."
    return value["next_action"]
