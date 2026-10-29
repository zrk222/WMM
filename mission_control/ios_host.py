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
    def __init__(self, database_path, verifier, vault_callback=None):
        from .service import Service
        from .store import Store
        self.identities = NativeIdentities(verifier)
        self.service = Service(Store(database_path, seed=False))
        self.owner = OwnerAdapter(self.service, self.identities)
        self.vault_callback = vault_callback
        from .ios_human_review import NativeHumanReview
        self.human_review=NativeHumanReview(self.service,self.identities)

    def native_human_review(self,session,app_id,action,payload):
        return self.human_review.call(session,app_id,action,payload)

    def native_review_logout(self):
        self.human_review.logout()

    def native_agent_review(self,session,credential,action,payload):
        from .ios_agent_access import NativeAgentAccess
        return NativeAgentAccess(self.service,self.identities).review(session,credential,action,payload)

    def owner_call(self, session, payload):
        return self.owner.call(session, payload)

    def snapshot_export(self,session,app_id):
        from .ios_snapshots import NativeSnapshots
        return NativeSnapshots(self.service,self.identities).export(session,app_id)

    def snapshot_restore(self,session,app_id,payload,confirmed):
        from .ios_snapshots import NativeSnapshots
        return NativeSnapshots(self.service,self.identities).restore(session,app_id,payload,confirmed)

    def native_providers(self,session,app_id,action,payload):
        from .ios_provider_access import NativeProviderAccess
        return NativeProviderAccess(self.service,self.identities,self.vault_callback).call(session,app_id,action,payload)

    def native_insights(self,session,app_id,action,payload):
        from .ios_insights import NativeInsights
        return NativeInsights(self.service,self.identities,self.vault_callback).call(session,app_id,action,payload)

    def native_store_connection(self,session,app_id,action,payload):
        from .ios_store_connection import NativeStoreConnection
        return NativeStoreConnection(self.service,self.identities,self.vault_callback,self.vault_callback).call(session,app_id,action,payload)

    def native_agent_timeline(self,session,app_id,action,payload):
        from .ios_agent_media import NativeAgentTimeline
        if action=='finish':raise Invalid('Timeline finish requires trusted decoded output')
        from .ios_automation import native_access
        with native_access(self.service,self.identities,session,self.vault_callback):
            return NativeAgentTimeline(self.service,self.identities).call(session,app_id,action,payload)

    def native_agent_timeline_finish(self,session,app_id,payload,inspection):
        from .ios_agent_media import NativeAgentTimeline
        from .ios_bridge import decode_document
        from .ios_automation import native_access
        with native_access(self.service,self.identities,session,self.vault_callback):
            return NativeAgentTimeline(self.service,self.identities).call(session,app_id,'finish',payload,inspection=decode_document(inspection))

    def native_agent_timeline_source(self,session,app_id,payload):
        from .ios_agent_media import NativeAgentTimeline
        from .ios_automation import native_access
        with native_access(self.service,self.identities,session,self.vault_callback):
            return NativeAgentTimeline(self.service,self.identities).source(session,app_id,payload)

    def native_inference(self,session,app_id,action,payload):
        from .ios_inference import NativeInference
        return NativeInference(self.service,self.identities,self.vault_callback).call(session,app_id,action,payload)

    def native_agent_loop(self,session,app_id,action,payload):
        from .ios_agent_loop import NativeAgentLoop
        return NativeAgentLoop(self.service,self.identities,self.vault_callback).call(session,app_id,action,payload)

    def native_automation(self,session,app_id,action,payload):
        from .ios_automation import NativeAutomation
        return NativeAutomation(self.service,self.identities,self.vault_callback).manage(session,app_id,action,payload)

    def native_studio(self,session,app_id,action,payload):
        from .ios_studio import NativeStudio
        if action=='finish':raise Invalid('Studio completion requires trusted native artifact inspection')
        from .ios_automation import native_access
        with native_access(self.service,self.identities,session,self.vault_callback):
            return NativeStudio(self.service,self.identities).call(session,app_id,action,payload)

    def native_studio_finish(self,session,app_id,payload,inspection):
        from .ios_studio import NativeStudio
        from .ios_bridge import decode_document
        from .ios_automation import native_access
        with native_access(self.service,self.identities,session,self.vault_callback):
            return NativeStudio(self.service,self.identities).call(session,app_id,'finish',payload,inspection=decode_document(inspection))

    def native_studio_source(self,session,app_id,payload):
        from .ios_studio import NativeStudio
        from .ios_bridge import decode_document
        body=decode_document(payload)
        if not isinstance(body,dict) or set(body)!={'job_id','packet_hash','media_id','sha256'}:
            raise Invalid('Exact Studio source binding required')
        from .ios_automation import native_access
        with native_access(self.service,self.identities,session,self.vault_callback):
            path=NativeStudio(self.service,self.identities).source(session,app_id,**body)
        return encode_response(dict(path=str(path)))

    def evidence_form(self,session,app_id):
        """Expose shared evidence fields without connection records or credentials."""
        from .catalog import FIELDS,LABELS
        from .journey_readiness import JOURNEYS,REQUIRED,STATUSES
        from .operation_authority import bound_owner,protected
        user=self.identities.fresh(session)
        envelope=dict(app_id=app_id,operation='native.evidence.form',input={})
        with bound_owner(self.service.store,envelope,self.identities,session,user):
            with protected(self.service.store,envelope):
                app=self.service.store.app(app_id)
                records=[r for r in self.service.store.records(app_id) if r['kind']!='connection']
                return encode_response(dict(app_id=app_id,manifest_version=app['version'],
                    fields={k:v for k,v in FIELDS.items() if k!='connection'},
                    labels={k:v for k,v in LABELS.items() if k!='connection'},records=records,
                    readiness=dict(journeys=list(JOURNEYS),required=sorted(REQUIRED),statuses=sorted(STATUSES))))

    def native_jobs(self, session, app_id, action, payload):
        from .ios_jobs import NativeJobs
        from .ios_automation import native_access
        with native_access(self.service,self.identities,session,self.vault_callback):
            return NativeJobs(self.service, self.identities,vault_callback=self.vault_callback).call(session, app_id, action, payload)

    def native_agent_access(self, session, app_id, action, payload):
        from .ios_agent_access import NativeAgentAccess
        return NativeAgentAccess(self.service, self.identities).manage(session, app_id, action, payload)

    def native_agent_call(self, session, credential, payload):
        from .ios_agent_access import NativeAgentAccess
        from .ios_automation import native_access
        from .ios_jobs import native_pipeline_context
        with native_access(self.service,self.identities,session,self.vault_callback), native_pipeline_context(self.service,self.identities,session):
            return NativeAgentAccess(self.service, self.identities).call(session, credential, payload)

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

    def native_production(self,session,app_id,action,payload):
        """Fixed signed-host interface; absent from public agent operation JSON."""
        from .ios_bridge import decode_document
        from .ios_production import NativeProduction
        body=decode_document(payload)
        fields={'project_id','revision','project_hash'}
        if action in ('validate','source'):fields.add('packet_hash')
        if action=='source':fields.update(('kind','source_id','sha256'))
        if action not in ('prepare','validate','source') or not isinstance(body,dict) or set(body)!=fields:
            raise Invalid('Use an exact native production action and saved project binding')
        production=NativeProduction(self.service,self.identities)
        args=(session,app_id,body['project_id'],body['revision'],body['project_hash'])
        if action=='prepare':return production.prepare(*args)
        if action=='validate':return encode_response(production.validate(*args,body['packet_hash']))
        path=production.source(*args,body['packet_hash'],body['kind'],body['source_id'],body['sha256'])
        # This native-only response must not be forwarded to an agent or report.
        return encode_response({'path':str(path)})

    def enroll(self, session, app_id):
        return self.owner.enroll(session, app_id, {'confirm_owner': True})

    def update_workspace(self, session, app_id, payload):
        """Edit selected app facts without replacing other settings or authority."""
        from .ios_bridge import decode_document
        from .operation_authority import bound_owner, protected
        body=decode_document(payload)
        fields={'name','job','audience','activation','release','locale','currency'}
        if (not isinstance(body,dict) or set(body)!={'version','changes','confirm_update'}
                or body['confirm_update'] is not True or type(body['version']) is not int
                or not isinstance(body['changes'],dict) or set(body['changes']) not in (fields,fields|{'store_app_id'})
                or any(not isinstance(value,str) for value in body['changes'].values())):
            raise Invalid('Confirm the exact versioned app-facts update')
        if body['changes'].get('store_app_id'):
            import re
            if not re.fullmatch(r'[0-9]{1,30}',body['changes']['store_app_id']):raise Invalid('Use the numeric App Store app ID')
        user=self.identities.fresh(session)
        envelope=dict(app_id=app_id,operation='native.workspace.update',input=body)
        with bound_owner(self.service.store,envelope,self.identities,session,user):
            with protected(self.service.store,envelope):
                current=self.service.store.app(app_id)
                result=self.service.store.save_app(app_id,dict(current['data'],**body['changes']),body['version'])
                return encode_response(result)

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
        if body['manifest'].get('store_app_id'):
            import re
            if not isinstance(body['manifest']['store_app_id'],str) or not re.fullmatch(r'[0-9]{1,30}',body['manifest']['store_app_id']):
                raise Invalid('Use the numeric App Store app ID')
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
        from .common import now
        from .db import connection
        from .ios_reports import snapshot
        from .review_access import member, exact_role
        user = self.identities.fresh(session)
        observed = now()
        with connection(self.service.store.path) as db:
            # Serialize the source snapshot and role check with local mutations.
            db.execute('BEGIN IMMEDIATE')
            role = member(db, app_id, user['principal'], 'OWNER')
            result = encode_response(snapshot(db,self.service.store,app_id,observed))
            self.identities.local(session,user['principal'],user['session_generation'])
            exact_role(db,app_id,user['principal'],role['version'],'OWNER')
        return result
