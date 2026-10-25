"""Owner-only loopback Drive lifecycle and durable import transport."""
from contextlib import contextmanager
import hashlib
import re
import secrets
from .common import Invalid
from .db import connection
from .managed_media_http import singleton, body
from .operation_authority import bound_owner, protected
from .operator_client import strict_json
from .drive_flows import Flows
from .drive_accounts import Accounts
from .drive_connection_state import Connections
from .drive_import_jobs import Imports
from . import drive_auth as auth


def route(handler, parts):
    """Reject alternate path encodings and unbounded route shapes before identity."""
    if len(parts) not in (4, 5, 6, 7) or parts[:2] != ['api', 'apps'] or parts[3] != 'drive':
        raise Invalid('Use the exact app Drive address')
    if handler.path != '/' + '/'.join(parts) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,79}', parts[2]):
        raise Invalid('Use the exact app Drive address')


@contextmanager
def owner(handler, parts):
    """Revalidate the session and OWNER role at each business transaction commit."""
    route(handler, parts); origin = 'http://127.0.0.1:' + str(handler.server.server_port)
    if handler.headers.get_all('Host') != [origin[7:]]:raise PermissionError('Use the exact local Drive host')
    origins = handler.headers.get_all('Origin')
    if (origins is not None or handler.command == 'POST') and origins != [origin]:
        raise PermissionError('Use the exact local Drive origin')
    session = handler.session(); user = handler.server.identities.fresh(session)
    if handler.command == 'POST' and not secrets.compare_digest(singleton(handler, 'X-CSRF-Token'), session):
        raise PermissionError('Reload the current Drive session')
    store = handler.server.service.store
    envelope = dict(app_id=parts[2], operation='drive.owner', input=dict(method=handler.command, path=handler.path))
    with bound_owner(store, envelope, handler.server.identities, session, user):
        with protected(store, envelope):yield store, user


def callback(store, app_id, value, port):
    """Bind parsed callback state to the route app before token-code claim/exchange."""
    if not isinstance(value, dict) or set(value) != {'query'}:raise Invalid('Provide only the Drive callback query')
    fields = auth.callback(value['query']); hashed = hashlib.sha256(fields['state'].encode()).hexdigest()
    with connection(store.path) as db:
        row = db.execute('SELECT id FROM drive_flows WHERE app_id=? AND state_hash=?', (app_id, hashed)).fetchone()
        if row is None:raise Invalid('Drive callback does not belong to this app')
    return Accounts(store, port).finish(value['query'])


def empty(value):
    """Recovery and cancellation accept no extra fields or body-supplied authority."""
    if value != {}:raise Invalid('This Drive action requires an empty object')


def get(handler, parts):
    """Return private account, consent and worker state only to the current owner."""
    with owner(handler, parts) as (store, user):
        app_id = parts[2]; port = handler.server.server_port; tail = parts[4:]
        if not tail:
            result = dict(connection=Connections(store, port).status(app_id),
                          consent=Flows(store, port).status(app_id), imports=Imports(store).list(app_id, user['principal']))
        elif len(tail) == 2 and tail[0] == 'flows':result = Accounts(store, port).review(app_id, tail[1])
        elif len(tail) == 2 and tail[0] == 'imports':result = Imports(store).read(app_id, tail[1], user['principal'])
        else:raise Invalid('Use the exact Drive status or review address')
        return handler.send(200, result)


def action(store, app_id, tail, value, port, principal):
    """Dispatch only explicit lifecycle operations; provider media runs in the worker."""
    operations = {
        ('start',): lambda: Flows(store, port).start(app_id, value),
        ('callback',): lambda: callback(store, app_id, value, port),
        ('disconnect',): lambda: Connections(store, port).disconnect(app_id, value),
        ('imports',): lambda: Imports(store).queue(app_id, value, principal),
    }
    key = tuple(tail)
    if key in operations:return operations[key]()
    if tail == ['cleanup']:
        empty(value); return Connections(store, port).cleanup_result(app_id)
    return nested(store, app_id, tail, value, port, principal)


def nested(store, app_id, tail, value, port, principal):
    """Keep exact flow and job authority separate from generic public job commands."""
    if len(tail) != 3:raise Invalid('Use the exact Drive operation address')
    kind, identity, operation = tail
    if kind == 'flows' and operation == 'confirm':return Accounts(store, port).confirm(app_id, identity, value)
    if operation != 'cancel' or kind not in ('flows', 'imports'):raise Invalid('Unsupported Drive operation')
    empty(value)
    if kind == 'flows':return Flows(store, port).stop(app_id, identity)
    return Imports(store).cancel(app_id, identity, principal)


def post(handler, parts):
    """Bound strict object parsing before any lifecycle or queue mutation."""
    with owner(handler, parts) as (store, user):
        value = strict_json(body(handler, 'application/json', 16384))
        if not isinstance(value, dict):raise Invalid('Drive input must be an object')
        result = action(store, parts[2], parts[4:], value, handler.server.server_port, user['principal'])
        return handler.send(201 if parts[4:] in (['start'], ['imports']) else 200, result)
