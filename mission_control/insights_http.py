"""Existing analytics routes plus native OpenSEO reads with unchanged owner/CSRF admission."""

from typing import TYPE_CHECKING
from urllib.parse import urlparse

from .common import Invalid
from .insights import Insights
from .openseo_read import require_web_source, save_reading

if TYPE_CHECKING:
    from .server import Handler


def post(handler: "Handler", parts: list[str], data: dict) -> object:
    """Dispatch only exact analytics route shapes after existing session admission."""
    if urlparse(handler.path).query:
        raise Invalid("Use the exact analytics action address without a query")
    work = Insights(handler.server.service.store)
    if len(parts) == 5 and parts[4] == "setup":
        return handler.send(201, work.setup(parts[2], data))
    if len(parts) != 6:
        raise KeyError("Analytics route not found")
    app, resource, action = parts[2], parts[4], parts[5]
    if action == "save-web-evidence":
        return handler.send(201, save_reading(work.store, app, resource, data))
    if action == "web-read":
        require_web_source(work.store, app, resource)
        return handler.send(200, work.refresh(app, resource, data))
    routes = {"read": work.refresh, "events": work.update_events, "disconnect": work.disconnect}
    if action not in routes:
        raise KeyError("Analytics route not found")
    return handler.send(200, routes[action](app, resource, data))
