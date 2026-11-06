"""Authenticated owner access to the same study actions used by scoped agents."""
import secrets

from .common import Invalid, identifier
from .discovery_http import json_body
from .managed_media_http import singleton
from .observational_campaign_contract import ACTION_FIELDS
from .operation_authority import bound_owner
from .operation_runtime import execute


def post(handler, parts):
    if (len(parts) != 5 or parts[:2] != ['api', 'apps']
            or parts[3] != 'observational-campaign' or parts[4] not in ACTION_FIELDS
            or handler.command != 'POST' or handler.path != '/' + '/'.join(parts)):
        raise Invalid('Use the exact observational campaign address')
    app_id = identifier(parts[2])
    host = '127.0.0.1:' + str(handler.server.server_port)
    if (handler.headers.get_all('Host') != [host]
            or handler.headers.get_all('Origin') != ['http://' + host]):
        raise PermissionError('Use the current local WMM window')
    session = handler.session()
    if not secrets.compare_digest(singleton(handler, 'X-CSRF-Token'), session):
        raise PermissionError('Reload the current WMM session')
    owner = handler.server.identities.fresh(session)
    service = handler.server.service
    envelope = dict(app_id=app_id, operation='observational-campaign.' + parts[4],
                    input=json_body(handler, 'Observational campaign'))
    with bound_owner(service.store, envelope, handler.server.identities, session, owner):
        return handler.send(200, execute(service, envelope, caller='LOCAL_SESSION'))
