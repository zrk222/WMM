"""Fixed native-host runtime: shared domain state, no HTTP server or desktop worker."""
import math
import time
from uuid import UUID

from .common import Invalid
from .ios_bridge import encode_response
from .ios_owner_adapter import OwnerAdapter


class NativeIdentities:
    """The bundled native callback rechecks Keychain and process session each time.

    The callback is installed by the embedding API, never decoded from a request.
    Its metadata is not itself proof; the native verifier is the authority source.
    """
    def __init__(self, verifier, clock=time.time):
        if not callable(verifier): raise TypeError('A native session verifier is required')
        self.verifier = verifier
        self.clock = clock

    def fresh(self, session):
        if not isinstance(session, str) or len(session) != 36:
            raise PermissionError('A current native session is required')
        try:
            UUID(session)
            value = self.verifier(session)
            if not isinstance(value, dict) or set(value) != {'principal', 'session_generation', 'expires_at_epoch'}:
                raise ValueError('Invalid native metadata')
            principal = str(UUID(value['principal']))
            generation = str(UUID(value['session_generation']))
            expires = value['expires_at_epoch']
            current = self.clock()
            if type(expires) not in (int, float) or not math.isfinite(expires) or not current < expires <= current + 900:
                raise ValueError('Invalid session lifetime')
        except Exception:
            raise PermissionError('Native identity is locked, expired or unavailable') from None
        return dict(principal='native:'+principal, login='Device owner', provider='NATIVE_DEVICE',
                    session_generation=generation)

    def local(self, session, principal, generation=None):
        value = self.fresh(session)
        if value['principal'] != principal or (generation is not None and value['session_generation'] != generation):
            raise PermissionError('Native session was replaced or revoked')
        return value


class Runtime:
    """One app-container database with fixed owner entry points and scoped agents."""
    def __init__(self, database_path, verifier):
        from .service import Service
        from .store import Store
        self.identities = NativeIdentities(verifier)
        self.service = Service(Store(database_path, seed=False))
        self.owner = OwnerAdapter(self.service, self.identities)

    def owner_call(self, session, payload):
        return self.owner.call(session, payload)

    def enroll(self, session, app_id):
        return self.owner.enroll(session, app_id, {'confirm_owner': True})

    def workspaces(self, session):
        from .db import connection
        from .store import decode
        user = self.identities.fresh(session)
        with connection(self.service.store.path) as db:
            rows = [decode(row) for row in db.execute(
                "SELECT a.* FROM apps a JOIN operator_roles r ON a.id=r.app_id "
                "WHERE r.principal=? AND r.role='OWNER' AND r.status='ACTIVE' ORDER BY a.id",
                (user['principal'],))]
            self.identities.local(session, user['principal'], user['session_generation'])
        return encode_response({'apps': rows})
