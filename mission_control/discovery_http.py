"""Exact loopback owner routes for the shared local research service."""

import secrets

from .common import Invalid, identifier
from .discovery_access import WRITES, dispatch
from .http_body import json_body as json_body
from .http_body import singleton
from .operation_authority import bound_owner, protected


def route(handler, parts):
    """No query, encoded path, alternate slash or unsupported read may select private research."""
    if len(parts) != 5 or parts[:2] != ["api", "apps"] or parts[3] != "discovery":
        raise Invalid("Use the exact research operation address")
    identifier(parts[2])
    if parts[4] not in {"read", "history", *WRITES}:
        raise Invalid("Unknown research operation")
    if handler.command != "POST" or handler.path != "/" + "/".join(parts):
        raise Invalid("Use an exact research POST without query")
    return parts[4]


def post(handler, parts):
    """Fresh identity is bound through every domain transaction, including final commit."""
    action = route(handler, parts)
    origin = "http://127.0.0.1:" + str(handler.server.server_port)
    if handler.headers.get_all("Host") != [origin[7:]]:
        raise PermissionError("Use the exact local research host")
    if handler.headers.get_all("Origin") != [origin]:
        raise PermissionError("Use the exact local research origin")
    session = handler.session()
    user = handler.server.identities.fresh(session)
    if not secrets.compare_digest(singleton(handler, "X-CSRF-Token"), session):
        raise PermissionError("Reload the current research session")
    store = handler.server.service.store
    envelope = dict(app_id=parts[2], operation="discovery.owner", input=dict(method=handler.command, path=handler.path))
    with bound_owner(store, envelope, handler.server.identities, session, user), protected(store, envelope):
        result = dispatch(store, parts[2], action, json_body(handler))
        return handler.send(200, result)
