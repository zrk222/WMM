"""Fresh-owner admission for bounded external-agent video research tasks."""
import secrets

from .common import Invalid, identifier
from .discovery_http import json_body
from .managed_media_http import singleton
from .operation_authority import bound_owner, protected
from .organic_video_collector import prepare


def post(handler, parts):
    """Preparing research is owner-only; recipient agents use the scoped gateway."""
    if (len(parts) != 5 or parts[:2] != ['api', 'apps']
            or parts[3:] != ['organic-video', 'prepare']):
        raise Invalid('Use the exact video research preparation address')
    identifier(parts[2])
    if handler.command != 'POST' or handler.path != '/' + '/'.join(parts):
        raise Invalid('Use an exact video research POST without query')
    origin = 'http://127.0.0.1:' + str(handler.server.server_port)
    if handler.headers.get_all('Host') != [origin[7:]]:
        raise PermissionError('Use the exact local video research host')
    if handler.headers.get_all('Origin') != [origin]:
        raise PermissionError('Use the exact local video research origin')
    if handler.headers.get_all('Authorization') is not None:
        raise PermissionError('Video research preparation requires an owner session only')
    session = handler.session()
    user = handler.server.identities.fresh(session)
    if not secrets.compare_digest(singleton(handler, 'X-CSRF-Token'), session):
        raise PermissionError('Reload the current video research session')
    body = json_body(handler, 'Video research')
    store = handler.server.service.store
    envelope = dict(app_id=parts[2], operation='organic-video.prepare', input=body)
    with bound_owner(store, envelope, handler.server.identities, session, user):
        with protected(store, envelope) as actor:
            result = prepare(store, parts[2], actor, body)
            return handler.send(200, result)
