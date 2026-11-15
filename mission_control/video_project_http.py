"""Route existing local video-project operations."""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urlparse

from .common import Invalid

if TYPE_CHECKING:
    from .server import Handler


def post(handler: Handler, parts: list[str], data: object) -> None:
    service = handler.server.service
    app_id = parts[2]
    if urlparse(handler.path).query:
        raise Invalid("Use the exact video project address")
    from .video_edit_projects import Projects

    projects = Projects(service.store)
    if len(parts) == 4:
        return handler.send(201, projects.save(app_id, data))
    if len(parts) == 6 and parts[5] in ("edits", "history", "diff"):
        operation = "edit" if parts[5] == "edits" else parts[5]
        return handler.send(200, getattr(projects, operation)(app_id, parts[4], data))
    raise KeyError("Video project route not found")
