"""Fresh-owner consent routes; delegated agents cannot extend their authority."""
import secrets

from .common import Invalid, identifier
from .discovery_http import json_body
from .managed_media_http import singleton
from .operation_authority import bound_owner, protected

ACTIONS = frozenset(('preview', 'confirm', 'history'))


def validate_route(handler, parts):
    """Accept only finite exact action addresses before resolving owner state."""
    if (len(parts) != 5 or parts[:2] != ['api', 'apps']
            or parts[3] != 'authority-expiry' or parts[4] not in ACTIONS):
        raise Invalid('Use an exact owner permission-expiry action')
    if handler.command != 'POST' or handler.path != '/' + '/'.join(parts):
        raise Invalid('Use an exact permission-expiry POST without query')
    identifier(parts[2])


def post(handler, parts):
    """Keep permission-clock changes within exact authenticated owner requests."""
    validate_route(handler, parts)
    origin = 'http://127.0.0.1:' + str(handler.server.server_port)
    if handler.headers.get_all('Host') != [origin[7:]] or handler.headers.get_all('Origin') != [origin]:
        raise PermissionError('Use the exact local permission-expiry origin')
    session = handler.session()
    if not secrets.compare_digest(singleton(handler, 'X-CSRF-Token'), session):
        raise PermissionError('Reload the current owner session')
    user = handler.server.identities.fresh(session)
    store = handler.server.service.store
    envelope = dict(app_id=parts[2], operation='authority-expiry.owner.' + parts[4], input={})
    with bound_owner(store, envelope, handler.server.identities, session, user), protected(store, envelope):
        body = json_body(handler, 'Permission expiry')
        return handler.send(200, dispatch(store, parts[2], user, parts[4], body))


def dispatch(store, app_id, user, action, body):
    """Only fixed owner services; no credential or effect dispatch is exposed."""
    from .authority_expiry import AuthorityExpiry
    service = AuthorityExpiry(store)
    if action == 'preview':
        return service.preview(app_id, user, body)
    if action == 'confirm':
        return service.confirm(app_id, user, body)
    if not isinstance(body, dict) or set(body) != {'kind', 'id'}:
        raise Invalid('Use the exact permission history fields')
    return service.history(app_id, user, body['kind'], body['id'])
