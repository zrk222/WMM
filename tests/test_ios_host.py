"""Real shared SQLite through the native callback seam; no native-device claim."""
import json
from pathlib import Path
import tempfile
import time
import unittest
from uuid import uuid4

from mission_control.ios_host import NativeIdentities, Runtime
from mission_control.common import Invalid


class NativeIdentityTests(unittest.TestCase):
    def test_requires_exact_host_metadata_and_bounded_current_session(self):
        session=str(uuid4()); stamp=1000
        valid=dict(principal=str(uuid4()),session_generation=str(uuid4()),expires_at_epoch=stamp+100)
        source=[valid]
        identities=NativeIdentities(lambda token:source[0],lambda:stamp)
        user=identities.fresh(session)
        self.assertEqual(user['provider'],'NATIVE_DEVICE')
        self.assertEqual(identities.local(session,user['principal'],user['session_generation']),user)
        for bad in (None,{},dict(valid,role='OWNER'),dict(valid,expires_at_epoch=True),
                    dict(valid,expires_at_epoch=float('nan')),dict(valid,expires_at_epoch=stamp),
                    dict(valid,expires_at_epoch=stamp+901),dict(valid,principal='not-a-uuid')):
            source[0]=bad
            with self.subTest(bad=bad),self.assertRaises(PermissionError):identities.fresh(session)
        source[0]=dict(valid,session_generation=str(uuid4()))
        with self.assertRaises(PermissionError):identities.local(session,user['principal'],user['session_generation'])
        with self.assertRaises(PermissionError):identities.fresh('caller-supplied-name')

    def test_callback_errors_do_not_disclose_native_details(self):
        def fail(token):raise RuntimeError('PRIVATE_KEYCHAIN_DETAIL')
        with self.assertRaises(PermissionError) as result:NativeIdentities(fail).fresh(str(uuid4()))
        self.assertNotIn('PRIVATE_KEYCHAIN_DETAIL',str(result.exception))


class NativeRuntimeTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        self.path=Path(folder.name)/'native.sqlite3'
        self.session=str(uuid4());self.principal=str(uuid4());self.generation=str(uuid4())
        self.available=True
        self.runtime=Runtime(self.path,self.verify)
        for app in ('own','other'):
            self.runtime.service.store.save_app(app,dict(name='Synthetic app',release='build-1',locale='en-US',currency='USD'))

    def verify(self,token):
        if not self.available or token!=self.session:return None
        return dict(principal=self.principal,session_generation=self.generation,expires_at_epoch=time.time()+300)

    def creation(self, app='new-app', **extra):
        body=dict(app_id=app,manifest=dict(name='My synthetic app',job='Improve activation',release='build-1',locale='en-US',currency='USD'),confirm_owner=True)
        body.update(extra)
        return json.dumps(body).encode()

    def test_native_agent_turn_host_requires_current_owner_and_fixed_action(self):
        self.runtime.create_workspace(self.session,self.creation())
        self.assertEqual(json.loads(self.runtime.native_agent_loop(self.session,'new-app','history',b'{}')),{'items':[]})
        with self.assertRaises(Invalid):
            self.runtime.native_agent_loop(self.session,'new-app','approve',b'{}')
        with self.assertRaises(PermissionError):
            self.runtime.native_agent_loop(self.session,'other','history',b'{}')
        self.available=False
        with self.assertRaises(PermissionError):
            self.runtime.native_agent_loop(self.session,'new-app','history',b'{}')

    def test_creation_and_owner_are_atomic_idempotent_and_persisted(self):
        from mission_control.db import connection
        payload=self.creation()
        result=json.loads(self.runtime.create_workspace(self.session,payload))
        self.assertEqual(result['status'],'LOCAL_WORKSPACE_CREATED')
        self.assertEqual(result['app']['version'],1)
        self.assertEqual(result['app']['data']['authorized_spend_minor'],0)
        self.assertEqual(json.loads(self.runtime.create_workspace(self.session,payload)),result)
        with connection(self.path) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM operator_roles WHERE app_id='new-app'").fetchone()[0],1)
            self.assertEqual(db.execute("SELECT count(*) FROM audit WHERE app_id='new-app'").fetchone()[0],2)
        reopened=Runtime(self.path,self.verify)
        self.assertEqual([a['id'] for a in json.loads(reopened.workspaces(self.session))['apps']],['new-app'])

    def test_native_workspace_navigation_reads_actual_twelve_stage_engine_state(self):
        self.runtime.create_workspace(self.session,self.creation())
        request=json.dumps(dict(app_id='new-app',operation='workspace.read',input={})).encode()
        snapshot=json.loads(self.runtime.owner_call(self.session,request))
        self.assertEqual(snapshot['app']['id'],'new-app')
        self.assertEqual([s['id'] for s in snapshot['stages']],list(range(1,13)))
        for stage in snapshot['stages']:
            self.assertIn(stage['status'],('READY','BLOCKED'))
            self.assertIsInstance(stage['missing'],list)
            self.assertTrue(stage['description'])

    def test_native_evidence_form_uses_shared_schema_and_versioned_owner_save(self):
        from mission_control.catalog import FIELDS
        self.runtime.create_workspace(self.session,self.creation())
        form=json.loads(self.runtime.evidence_form(self.session,'new-app'))
        self.assertEqual(form['fields']['measurement'],FIELDS['measurement'])
        self.assertNotIn('connection',form['fields'])
        from mission_control.journey_readiness import JOURNEYS,REQUIRED
        self.assertEqual(form['readiness']['journeys'],list(JOURNEYS))
        self.assertEqual(set(form['readiness']['required']),REQUIRED)
        body=dict(id='measurement-proof',manifest_version=form['manifest_version'],kind='measurement',
                  title='Synthetic observation',source='Synthetic test receipt',data=dict(release='build-1',result='PASS',
                  attribution_method='synthetic method',consent_review=True,refund_reconciliation=True))
        envelope=dict(app_id='new-app',operation='evidence.save',input=body)
        saved=json.loads(self.runtime.owner_call(self.session,json.dumps(envelope).encode()))
        self.assertEqual(saved['version'],1)
        form=json.loads(self.runtime.evidence_form(self.session,'new-app'))
        self.assertEqual(form['records'][0]['id'],body['id'])
        with self.assertRaises(Invalid):self.runtime.owner_call(self.session,json.dumps(envelope).encode())
        with self.assertRaises(PermissionError):self.runtime.evidence_form(self.session,'other')
        self.available=False
        with self.assertRaises(PermissionError):self.runtime.evidence_form(self.session,'new-app')

    def update_payload(self, version=1, **extra):
        fields=dict(name='Revised app',job='Improve activation',audience='Synthetic owners',
                    activation='Create first plan',release='build-2',locale='en-US',currency='USD')
        return json.dumps(dict(version=version,changes=fields,confirm_update=True,**extra)).encode()

    def test_native_app_facts_preserve_settings_and_reject_stale_revision(self):
        body=json.loads(self.creation());body['manifest']['brand_voice']='Retain this setting'
        self.runtime.create_workspace(self.session,json.dumps(body).encode())
        result=json.loads(self.runtime.update_workspace(self.session,'new-app',self.update_payload()))
        self.assertEqual(result['version'],2)
        self.assertEqual(result['data']['name'],'Revised app')
        self.assertEqual(result['data']['brand_voice'],'Retain this setting')
        self.assertEqual(result['data']['authorized_spend_minor'],0)
        with self.assertRaises(Invalid):self.runtime.update_workspace(self.session,'new-app',self.update_payload())
        self.assertEqual(self.runtime.service.store.app('new-app')['version'],2)

    def test_native_app_facts_cannot_edit_authority_or_foreign_apps(self):
        self.runtime.create_workspace(self.session,self.creation())
        with self.assertRaises(PermissionError):self.runtime.update_workspace(self.session,'other',self.update_payload())
        for key,value in [('authorized_spend_minor',100),('principal','other-owner')]:
            body=json.loads(self.update_payload());body['changes'][key]=value
            with self.assertRaises(Invalid):self.runtime.update_workspace(self.session,'new-app',json.dumps(body).encode())
        self.available=False
        with self.assertRaises(PermissionError):self.runtime.update_workspace(self.session,'new-app',self.update_payload())

    def test_native_app_facts_lock_before_commit_rolls_back_audit_and_manifest(self):
        from unittest.mock import patch
        from mission_control.db import connection
        self.runtime.create_workspace(self.session,self.creation())
        # Revoke after the UPDATE/audit inside the real transaction, before its
        # shared protected-connection commit check.
        import mission_control.store as store_module
        audit=store_module.audit
        def lock_after_audit(db,app,action,detail):
            audit(db,app,action,detail)
            self.available=False
        with patch.object(store_module,'audit',side_effect=lock_after_audit):
            with self.assertRaises(PermissionError):self.runtime.update_workspace(self.session,'new-app',self.update_payload())
        self.available=True
        self.assertEqual(self.runtime.service.store.app('new-app')['version'],1)
        with connection(self.path) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM audit WHERE app_id='new-app'").fetchone()[0],2)

    def test_creation_never_claims_foreign_or_unowned_existing_workspaces(self):
        for app in ('own','other'):
            with self.assertRaises(PermissionError):self.runtime.create_workspace(self.session,self.creation(app))
        self.runtime.create_workspace(self.session,self.creation())
        self.principal=str(uuid4())
        with self.assertRaises(PermissionError):self.runtime.create_workspace(self.session,self.creation())

    def test_revoked_session_during_creation_rolls_back_workspace_membership_and_audit(self):
        from unittest.mock import patch
        from mission_control.db import connection
        from mission_control.review_access import Access
        original=Access.write
        def write_then_lock(instance,*args):
            original(instance,*args)
            self.available=False
        with patch.object(Access,'write',write_then_lock):
            with self.assertRaises(PermissionError):self.runtime.create_workspace(self.session,self.creation())
        with connection(self.path) as db:
            for table in ('apps','operator_roles','audit'):
                field='id' if table=='apps' else 'app_id'
                self.assertEqual(db.execute(f'SELECT count(*) FROM {table} WHERE {field}=?',('new-app',)).fetchone()[0],0)

    def test_creation_rejects_invalid_confirmation_duplicates_scope_and_manifest(self):
        invalid=[self.creation(confirm_owner=False),self.creation(role='OWNER'),self.creation(app='../outside'),
                 self.creation(manifest=[]),self.creation(manifest={'name':''}),
                 b'{"app_id":"a","app_id":"b","manifest":{},"confirm_owner":true}',
                 self.creation(manifest={'name':'Bad','nested':float('nan')})]
        for payload in invalid:
            with self.subTest(payload=payload),self.assertRaises(Invalid):
                self.runtime.create_workspace(self.session,payload)
        self.assertEqual(json.loads(self.runtime.workspaces(self.session)),{'apps':[]})

    def test_concurrent_creation_cannot_establish_two_owners(self):
        from concurrent.futures import ThreadPoolExecutor
        from mission_control.db import connection
        other_principal=str(uuid4())
        def other_verify(token):
            return dict(self.verify(token),principal=other_principal)
        other=Runtime(self.path,other_verify)
        payload=self.creation()
        def attempt(runtime):
            try:
                runtime.create_workspace(self.session,payload)
                return 'CREATED'
            except PermissionError:return 'DENIED'
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(attempt,[self.runtime,other]))
        self.assertEqual(sorted(results),['CREATED','DENIED'])
        with connection(self.path) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM operator_roles WHERE app_id='new-app'").fetchone()[0],1)

    def test_explicit_owner_enrollment_scoped_read_and_process_reopen(self):
        self.assertEqual(json.loads(self.runtime.workspaces(self.session)),{'apps':[]})
        result=json.loads(self.runtime.enroll(self.session,'own'))
        self.assertEqual(result['identity_provider'],'NATIVE_DEVICE')
        self.assertEqual([a['id'] for a in json.loads(self.runtime.workspaces(self.session))['apps']],['own'])
        payload=b'{"app_id":"own","operation":"growth.history","input":{}}'
        self.assertEqual(json.loads(self.runtime.owner_call(self.session,payload))['app_id'],'own')
        with self.assertRaises(PermissionError):self.runtime.owner_call(self.session,payload.replace(b'own',b'other'))
        reopened=Runtime(self.path,self.verify)
        self.assertEqual(json.loads(reopened.owner_call(self.session,payload))['app_id'],'own')
        self.available=False
        with self.assertRaises(PermissionError):reopened.owner_call(self.session,payload)

    def test_missing_or_replaced_native_identity_never_adopts_saved_owner(self):
        self.runtime.enroll(self.session,'own')
        self.principal=str(uuid4())
        self.assertEqual(json.loads(self.runtime.workspaces(self.session)),{'apps':[]})
        with self.assertRaises(Invalid):self.runtime.enroll(self.session,'own')
        self.available=False
        with self.assertRaises(PermissionError):self.runtime.workspaces(self.session)
