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

    def native_media_upload(self,session,app_id,filename,raw,payload,inspection):
        from .ios_media_adapter import NativeMediaAdapter,inspection_from_native
        return NativeMediaAdapter(self.service,self.identities,inspection_from_native(inspection)).upload(
            session,app_id,filename,raw,payload)

    def native_media_list(self,session,app_id):
        from .ios_media_adapter import NativeMediaAdapter,no_native_inspection
        return NativeMediaAdapter(self.service,self.identities,no_native_inspection).list(session,app_id)

    def native_media_review(self,session,app_id,media_id,payload):
        from .ios_media_adapter import NativeMediaAdapter,no_native_inspection
        return NativeMediaAdapter(self.service,self.identities,no_native_inspection).review(session,app_id,media_id,payload)

    def enroll(self, session, app_id):
        return self.owner.enroll(session, app_id, {'confirm_owner': True})

    def create_workspace(self, session, payload):
        """One explicit local owner action, committed with its first membership.

        Workspace IDs are immutable creation keys. Repeating an identical creation
        returns the existing result only for its current owner; nothing overwrites.
        """
        from .common import canonical, identifier, now
        from .db import connection
        from .ios_bridge import decode_document
        from .review_access import Access, member
        from .store import app_data, audit, decode
        body = decode_document(payload)
        if not isinstance(body, dict) or set(body) != {'app_id', 'manifest', 'confirm_owner'} or body['confirm_owner'] is not True:
            raise Invalid('Confirm ownership and provide an exact app identifier and manifest')
        if not isinstance(body['manifest'], dict): raise Invalid('Use an app manifest object')
        app_id = identifier(body['app_id'])
        manifest = app_data(body['manifest'])
        user = self.identities.fresh(session)
        def current():
            self.identities.local(session, user['principal'], user['session_generation'])
        with connection(self.service.store.path) as db:
            db.execute('BEGIN IMMEDIATE')
            existing = db.execute('SELECT * FROM apps WHERE id=?', (app_id,)).fetchone()
            if existing is not None:
                member(db, app_id, user['principal'], 'OWNER')
                if existing['version'] != 1 or existing['data'] != canonical(manifest):
                    raise Invalid('Workspace already exists with different setup; reload it')
            else:
                db.execute('INSERT INTO apps(id,data,updated) VALUES(?,?,?)', (app_id, canonical(manifest), now()))
                audit(db, app_id, 'workspace.saved', {'version': 1})
                Access(self.service.store).write(db, app_id, user, 'OWNER', 'ACTIVE', 1, user['principal'])
                audit(db, app_id, 'access.owner_established',
                      {'principal': user['principal'], 'policy': 'NATIVE_LOCAL_BOOTSTRAP'})
            current()
            row = db.execute('SELECT * FROM apps WHERE id=?', (app_id,)).fetchone()
            result = encode_response({'app': decode(row), 'identity_provider': 'NATIVE_DEVICE',
                                      'status': 'LOCAL_WORKSPACE_CREATED', 'publication': 'NOT_RUN'})
        return result

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

    def report(self, session, app_id):
        """Project one consistent app-owned read transaction with current authority."""
        import json
        from .common import now, iso_time
        from .db import connection
        from .ios_reports import projection
        from .ledger import report
        from .review_access import member, exact_role
        from .store import decode
        user = self.identities.fresh(session)
        observed = now()
        with connection(self.service.store.path) as db:
            # Serialize the source snapshot and role check with local mutations.
            db.execute('BEGIN IMMEDIATE')
            role = member(db, app_id, user['principal'], 'OWNER')
            app = decode(db.execute('SELECT * FROM apps WHERE id=?',(app_id,)).fetchone())
            records = [decode(r) for r in db.execute('SELECT * FROM records WHERE app_id=? ORDER BY updated,id',(app_id,))]
            cohorts = [json.loads(r['data']) for r in db.execute('SELECT data FROM growth_cohorts WHERE app_id=? ORDER BY id',(app_id,))]
            events = [dict(cohort_id=r['cohort_id'],data=json.loads(r['data'])) for r in db.execute('SELECT cohort_id,data FROM growth_events WHERE app_id=? ORDER BY provider,external_id',(app_id,))]
            reports = [report(c,[r['data'] for r in events if r['cohort_id']==c['cohort_id']],iso_time(observed)) for c in cohorts]
            result = encode_response(projection(app,records,reports,observed))
            self.identities.local(session,user['principal'],user['session_generation'])
            exact_role(db,app_id,user['principal'],role['version'],'OWNER')
        return result
