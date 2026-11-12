"""Closed freshly authenticated owner monitor controls; no agent catalog expansion."""

import secrets
from .common import Invalid, identifier
from .managed_media_http import singleton
from .discovery_http import json_body
from .operation_authority import bound_owner, protected
from .campaign_monitor import Monitors

FIELDS = {
    "prepare": {"proposal"},
    "activate": {"monitor_id", "summary_hash"},
    "status": {"monitor_id"},
    "history": set(),
    "off": {"monitor_id", "version"},
}


def dispatch(store, app_id, action, body):
    """Owner controls never accept actor names, credentials or arbitrary operations."""
    if action not in FIELDS or not isinstance(body, dict) or set(body) != FIELDS[action]:
        raise Invalid("Use the exact campaign monitor fields")
    service = Monitors(store)
    routes = {
        "prepare": lambda: service.prepare(app_id, body["proposal"]),
        "activate": lambda: service.activate(app_id, body["monitor_id"], body["summary_hash"]),
        "status": lambda: service.status(app_id, body["monitor_id"]),
        "history": lambda: service.history(app_id),
        "off": lambda: service.off(app_id, body["monitor_id"], body["version"]),
    }
    return routes[action]()


def post(handler, parts):
    """Root dispatch hook for exact /api/apps/{app}/campaign-monitor/{action}."""
    _request(handler, parts)
    session = handler.session()
    if not secrets.compare_digest(singleton(handler, "X-CSRF-Token"), session):
        raise PermissionError("Reload the current monitor session")
    user = handler.server.identities.fresh(session)
    store = handler.server.service.store
    envelope = dict(app_id=parts[2], operation="campaign.monitor.owner." + parts[4], input={})
    with (
        bound_owner(store, envelope, handler.server.identities, session, user),
        protected(store, envelope),
    ):
        result = dispatch(store, parts[2], parts[4], json_body(handler, "Campaign monitor"))
        return handler.send(200, result)


def _request(handler, parts):
    if len(parts) != 5 or parts[:2] != ["api", "apps"] or parts[3] != "campaign-monitor" or parts[4] not in FIELDS:
        raise Invalid("Use an exact campaign monitor address")
    identifier(parts[2])
    if handler.command != "POST" or handler.path != "/" + "/".join(parts):
        raise Invalid("Use an exact monitor POST without query")
    origin = "http://127.0.0.1:" + str(handler.server.server_port)
    if handler.headers.get_all("Host") != [origin[7:]] or handler.headers.get_all("Origin") != [origin]:
        raise PermissionError("Use the exact local monitor origin")
