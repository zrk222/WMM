"""Local marketing-review transport uses the common authenticated operation gateway."""

import secrets
from typing import Any

from .common import Invalid, identifier
from .discovery_http import json_body
from .managed_media_http import singleton
from .marketing_review import FIELDS
from .operation_authority import bound_owner
from .operation_runtime import execute


def post(handler: Any, parts: list[str]) -> Any:
    """Reject alternate origins, ambiguous CSRF, query routes and stale owners."""
    if (
        len(parts) != 5
        or parts[:2] != ["api", "apps"]
        or parts[3] != "marketing-review"
        or parts[4] not in FIELDS
        or handler.command != "POST"
        or handler.path != "/" + "/".join(parts)
    ):
        raise Invalid("Use the exact marketing-review POST address")
    app = identifier(parts[2])
    host = "127.0.0.1:" + str(handler.server.server_port)
    if handler.headers.get_all("Host") != [host] or handler.headers.get_all("Origin") != ["http://" + host]:
        raise PermissionError("Use the current local WMM window")
    session = handler.session()
    if not secrets.compare_digest(singleton(handler, "X-CSRF-Token"), session):
        raise PermissionError("Reload the current WMM session")
    owner = handler.server.identities.fresh(session)
    service = handler.server.service
    envelope = dict(app_id=app, operation="marketing-review." + parts[4], input=json_body(handler, "Marketing review"))
    with bound_owner(service.store, envelope, handler.server.identities, session, owner):
        return handler.send(200, execute(service, envelope, caller="LOCAL_SESSION"))
