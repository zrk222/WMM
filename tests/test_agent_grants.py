"""Synthetic authenticated owner plus real loopback gateway and transactional quota tests."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
from pathlib import Path
import json
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from mission_control.agent_grants import Grants,token_digest
from mission_control.common import Invalid,digest
from mission_control.db import connection
from mission_control.operator_client import OperatorClient,ClientError
from mission_control.server import Server
from mission_control.store import Store
from tests import test_verified_review as identity_fixture
from tests.test_aso_validation import listing


class GrantTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.store=Store(Path(self.tmp.name)/'grants.sqlite',seed=False)
        for app in ('sample-one','sample-two'):
            self.store.save_app(app,dict(name='Synthetic grant app',release='build-1',locale='en-US',currency='USD'))
        self.mock=patch('mission_control.operator_identity.github_read',side_effect=identity_fixture.synthetic_identity)
        self.mock.start()
        self.server=Server(('127.0.0.1',0),self.store)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.origin='http://127.0.0.1:'+str(self.server.server_port)
        self.owner=OperatorClient(self.origin);self.owner.bootstrap()
        self.owner.request('POST','/api/identity/login',dict(token=identity_fixture.OWNER_TOKEN))
        self.owner.request('POST','/api/apps/sample-one/access/bootstrap',dict(confirm_owner=True))
        self.grants=Grants(self.store)

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join()
        self.mock.stop();self.tmp.cleanup()

    def body(self,operations=None,max_calls=10):
        return dict(agent_id='generic-agent',manifest_version=1,operations=operations or ['growth.read','growth.history','growth.save'],
            expires=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),max_calls=max_calls)

    def issue(self,operations=None,max_calls=10):
        return self.owner.request('POST','/api/apps/sample-one/agent-grants/issue',self.body(operations,max_calls))

    def envelope(self,operation='growth.history',body=None,app_id='sample-one'):
        return dict(app_id=app_id,operation=operation,input=body or {})

    def listing_body(self):
        return dict(id='grant-listing',manifest_version=1,kind='ASO_LISTING',data=dict(release='build-1',listing=listing()))

    def test_owner_issues_once_hash_only_persistence_and_snapshot_no_authority(self):
        issued=self.issue();token=issued['token']
        self.assertEqual(issued['token_delivery'],'ONCE_ONLY')
        rows=self.owner.request('POST','/api/apps/sample-one/agent-grants/list',{})['grants']
        self.assertNotIn(token,json.dumps(rows));self.assertNotIn('token_hash',rows[0])
        with connection(self.store.path) as db:
            self.assertEqual(db.execute('SELECT token_hash FROM agent_grants').fetchone()[0],token_digest(token))
            self.assertNotIn(token,'\n'.join(db.iterdump()))
        exported=self.store.export('sample-one')
        self.assertNotIn('agent_grants',json.dumps(exported));self.assertNotIn(token,json.dumps(exported))
        exported['payload']['agent_grants']=[dict(token=token,operations=['human.approve'])]
        exported['sha256']=digest(exported['payload'])
        clone=Store(Path(self.tmp.name)/'clone.sqlite',seed=False);clone.restore(exported)
        with connection(clone.path) as db:self.assertEqual(db.execute('SELECT count(*) FROM agent_grants').fetchone()[0],0)
        with self.assertRaises(PermissionError):Grants(clone).admit(token,self.envelope())

    def test_gateway_executes_actual_service_without_cookie_bootstrap(self):
        issued=self.issue();client=OperatorClient(self.origin,grant_token=issued['token'])
        sessions=len(self.server.sessions)
        saved=client.call(self.envelope('growth.save',self.listing_body()))
        history=client.call(self.envelope())
        self.assertEqual(saved['hash'],history['history'][0]['hash'])
        self.assertEqual(len(self.server.sessions),sessions);self.assertEqual(len(client.cookies),0);self.assertIsNone(client.csrf)
        self.assertEqual(self.grants.list('sample-one',identity_fixture.OWNER)['grants'][0]['used'],2)

    def test_cross_app_and_operation_scope_fail_without_fallback(self):
        issued=self.issue(['growth.history'])
        client=OperatorClient(self.origin,grant_token=issued['token'])
        for body in (self.envelope(app_id='sample-two'),self.envelope('growth.save',self.listing_body())):
            with self.assertRaises(ClientError) as error:client.call(body)
            self.assertEqual(error.exception.status,403)
        with self.assertRaises(Invalid):client.call(self.envelope('human.approve'))
        with self.assertRaises(Invalid):client.request('POST','/api/identity/login',{})
        self.assertEqual(self.grants.list('sample-one',identity_fixture.OWNER)['grants'][0]['used'],0)

    def test_quota_is_atomic_under_racing_admissions(self):
        issued=self.issue(['growth.history'],max_calls=1)
        def attempt(_):
            try:self.grants.admit(issued['token'],self.envelope());return True
            except PermissionError:return False
        with ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(attempt,range(8)))
        self.assertEqual(sum(results),1)
        self.assertEqual(self.grants.list('sample-one',identity_fixture.OWNER)['grants'][0]['used'],1)

    def test_revocation_exact_revision_blocks_new_admission(self):
        issued=self.issue();body=dict(id=issued['grant']['id'],version=1)
        revoked=self.owner.request('POST','/api/apps/sample-one/agent-grants/revoke',body)
        self.assertEqual(revoked['version'],2)
        with self.assertRaises(ClientError):self.owner.request('POST','/api/apps/sample-one/agent-grants/revoke',body)
        with self.assertRaises(PermissionError):self.grants.admit(issued['token'],self.envelope())

    def test_expiry_and_changed_app_or_owner_version_invalidate(self):
        issued=self.issue()
        future=Grants(self.store,clock=lambda:datetime.now(timezone.utc)+timedelta(hours=2))
        with self.assertRaises(PermissionError):future.admit(issued['token'],self.envelope())
        with connection(self.store.path) as db:db.execute('UPDATE operator_roles SET version=version+1 WHERE app_id=?',('sample-one',))
        with self.assertRaises(Invalid):self.grants.admit(issued['token'],self.envelope())
        second=self.issue()
        self.store.save_app('sample-one',dict(name='Changed grant scope',release='build-2',locale='en-US',currency='USD'),1)
        with self.assertRaises(PermissionError):self.grants.admit(second['token'],self.envelope())

    def test_issuer_requires_verified_owner_not_supplied_names(self):
        anonymous=OperatorClient(self.origin);anonymous.bootstrap()
        with self.assertRaises(ClientError) as error:anonymous.request('POST','/api/apps/sample-one/agent-grants/issue',self.body())
        self.assertEqual(error.exception.status,403)
        with self.assertRaises(ClientError):self.owner.request('POST','/api/apps/sample-one/agent-grants/issue',dict(self.body(),principal=identity_fixture.OWNER['principal']))
        with patch('mission_control.operator_identity.github_read',side_effect=Invalid('Synthetic identity unavailable')):
            with self.assertRaises(ClientError):self.issue()
        self.assertEqual(self.grants.list('sample-one',identity_fixture.OWNER)['grants'],[])

    def test_grant_validation_denies_invalid_limits_operations_and_ambiguous_json(self):
        for updates in (dict(max_calls=True),dict(max_calls=0),dict(max_calls=10001),dict(operations=['human.approve']),dict(operations=['growth.read','growth.read']),dict(manifest_version=True),dict(expires=(datetime.now(timezone.utc)+timedelta(days=2)).isoformat())):
            with self.assertRaises(ClientError):self.owner.request('POST','/api/apps/sample-one/agent-grants/issue',dict(self.body(),**updates))
        token=self.issue()['token']
        for raw in (b'{"app_id":"sample-one","app_id":"sample-two"}',b'{"x":NaN}'):
            request=Request(self.origin+'/api/agent-operations/call',data=raw,method='POST',headers=dict(Origin=self.origin,Authorization='Bearer '+token,**{'Content-Type':'application/json'}))
            with self.assertRaises(HTTPError) as error:urlopen(request,timeout=15)
            self.assertEqual(error.exception.code,400)
        client=OperatorClient(self.origin,grant_token='wmmg_'+'x'*43)
        with self.assertRaises(ClientError) as error:client.call(self.envelope())
        self.assertEqual(error.exception.status,403)

    def test_business_failure_consumes_attempt_without_saved_write(self):
        issued=self.issue(max_calls=1)
        client=OperatorClient(self.origin,grant_token=issued['token'])
        bad=dict(self.listing_body(),manifest_version=99)
        with self.assertRaises(ClientError) as error:client.call(self.envelope('growth.save',bad))
        self.assertEqual(error.exception.status,400)
        with self.assertRaises(ClientError) as error:client.call(self.envelope())
        self.assertEqual(error.exception.status,403)
        self.assertEqual(self.owner.call(self.envelope())['history'],[])
