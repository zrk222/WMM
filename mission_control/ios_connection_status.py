"""Native connection status projection without desktop credential inference."""
from contextlib import contextmanager
from pathlib import Path

from .connection_setup import bound_status_source


@contextmanager
def native_connection_status(service, identities, session, vault_callback):
    """Bind status reads to a trusted host and current owner for local preparation.

    The current native callback only supports AgentGrowth inference API keys.
    AppGrowth connection credentials have no native onboarding or compatible
    Keychain namespace yet. Do not probe them or infer migration from a reference.
    """
    user = identities.fresh(session)
    expected = Path(service.store.path).resolve()

    def statuses(store, app_id):
        from .db import connection
        from .review_access import member
        if Path(store.path).resolve() != expected:
            raise PermissionError('Native connection status cannot cross its datastore')
        identities.local(session, user['principal'], user['session_generation'])
        with connection(store.path) as db:
            member(db, app_id, user['principal'], 'OWNER')
        result = {}
        for record in store.records(app_id):
            if record['kind'] != 'connection':continue
            data = record['data']
            if data.get('auth_mode') == 'disconnected':
                value = dict(status='DISCONNECTED', cleanup='UNCONFIRMED' if data.get('credential_ref') else 'NO_PROTECTED_KEY')
            else:
                value = dict(status='RECONNECT_REQUIRED', repair='NATIVE_PROVIDER_ONBOARDING_REQUIRED')
            result[record['id']] = value
        identities.local(session, user['principal'], user['session_generation'])
        return result

    with bound_status_source(statuses):
        yield
