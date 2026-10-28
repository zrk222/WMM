"""Real approved jobs and protected vault seam; synthetic transport makes no API call."""
import json
import unittest
from uuid import uuid4
from tests import test_ios_host as fixture
from tests import test_ios_provider_access as providers
from tests.test_agent_access import answer,connection_test_fixture
from mission_control.common import Invalid
from mission_control.db import connection
from mission_control.ios_inference import NativeInference


class NativeInferenceTests(unittest.TestCase):
    setUp=fixture.NativeRuntimeTests.setUp
    verify=fixture.NativeRuntimeTests.verify
    creation=fixture.NativeRuntimeTests.creation
    vault=providers.NativeProviderTests.vault
    setup_access=providers.NativeProviderTests.setup_access

    def setup_inference(self, transport=None):
        from tests.test_agent_access import body
        self.setup_access()
        raw=self.runtime.native_providers(self.session,'new-app','save',json.dumps(dict(confirm_storage=True,profile=body())).encode())
        self.profile_id=json.loads(raw)['connection'];self.network_calls=0
        self.inference=NativeInference(self.runtime.service,self.runtime.identities,self.vault,transport or self.transport)

    def transport(self,profile,key,prompt,max_tokens,alive):
        self.network_calls+=1
        self.assertEqual(key,'synthetic-key-0123456789')
        alive()
        return (connection_test_fixture() if max_tokens==256 else answer()),dict(prompt_tokens=12,completion_tokens=8,total_tokens=20)

    def call(self,action,body,app='new-app'):
        return json.loads(self.inference.call(self.session,app,action,json.dumps(body).encode()))

    def prepare(self,task='connection_test'):
        return self.call('prepare',dict(task=task,focus='',connection_id=self.profile_id))

    def start(self,prepared=None,key=None,confirm=True):
        p=prepared or self.prepare()
        return self.call('start',dict(task=p['proposal']['task'],focus=p['proposal']['focus'],
            connection_id=self.profile_id,source_hash=p['source_hash'],request_key=key or str(uuid4()),confirm_transmission=confirm))

    def test_review_start_result_usage_and_idempotent_read_do_not_repeat_inference(self):
        self.setup_inference();prepared=self.prepare();self.assertEqual(self.network_calls,0)
        self.assertEqual(prepared['destination'],'https://synthetic.example/v1')
        self.assertNotIn('synthetic-key',json.dumps(prepared))
        with self.assertRaises(Invalid):self.start(prepared,confirm=False)
        key=str(uuid4());queued=self.start(prepared,key)
        self.assertEqual(queued['status'],'QUEUED')
        complete=self.call('run',dict(id=queued['id']))
        self.assertEqual(complete['status'],'SUCCEEDED')
        self.assertEqual(complete['result']['publication'],'NOT_RUN')
        self.assertEqual(complete['result']['usage']['total_tokens'],20)
        self.assertEqual(self.call('run',dict(id=queued['id'])),complete)
        self.assertEqual(self.start(prepared,key)['id'],queued['id'])
        self.assertEqual(self.call('read',dict(id=queued['id'])),complete)
        self.assertEqual(self.network_calls,1)
        self.assertNotIn('synthetic-key',json.dumps(complete))

    def test_tested_provider_and_explicit_mode_enable_app_context_draft(self):
        self.setup_inference()
        with self.assertRaises(Invalid):self.prepare('campaign_plan')
        self.call('run',dict(id=self.start()['id']))
        with self.assertRaises(Invalid):self.prepare('campaign_plan')
        self.call('mode',dict(version=0,confirm_api_mode=True))
        prepared=self.prepare('campaign_plan')
        self.assertIn('Approved app context:',prepared['proposal']['prompt'])
        result=self.call('run',dict(id=self.start(prepared)['id']))
        self.assertEqual(result['status'],'SUCCEEDED')
        self.assertEqual(result['result']['draft']['summary'],'Synthetic draft')

    def test_uncertain_transport_and_expired_running_request_never_replay(self):
        def fail(*args):
            self.network_calls+=1
            raise RuntimeError('PRIVATE_KEY_DETAIL')
        self.setup_inference(fail);queued=self.start()
        result=self.call('run',dict(id=queued['id']))
        self.assertEqual(result['status'],'UNKNOWN')
        self.assertNotIn('PRIVATE_KEY_DETAIL',json.dumps(result))
        self.call('run',dict(id=queued['id']));self.assertEqual(self.network_calls,1)
        second=self.start()
        with connection(self.path) as db:
            db.execute("UPDATE jobs SET status='RUNNING',attempts=1,lease=0 WHERE id=?",(second['id'],))
        self.assertEqual(self.call('run',dict(id=second['id']))['status'],'UNKNOWN')
        self.assertEqual(self.network_calls,1)

    def test_live_lease_foreign_owner_and_changed_source_deny(self):
        self.setup_inference();prepared=self.prepare();queued=self.start(prepared)
        original=self.principal;self.principal=str(uuid4())
        with self.assertRaises(PermissionError):self.call('read',dict(id=queued['id']))
        self.principal=original
        with self.assertRaises(PermissionError):self.call('read',dict(id=queued['id']),app='other')
        with connection(self.path) as db:db.execute("UPDATE apps SET version=version+1 WHERE id='new-app'")
        with self.assertRaises(Invalid):self.call('run',dict(id=queued['id']))
        self.assertEqual(self.network_calls,0)

    def test_lock_after_request_retains_uncertainty_until_owner_recovers(self):
        def locking(*args):
            self.network_calls+=1;self.available=False
            return connection_test_fixture(),None
        self.setup_inference(locking);queued=self.start()
        with self.assertRaises(PermissionError):self.call('run',dict(id=queued['id']))
        self.available=True
        with connection(self.path) as db:
            self.assertEqual(db.execute('SELECT status FROM jobs WHERE id=?',(queued['id'],)).fetchone()[0],'RUNNING')
            db.execute('UPDATE jobs SET lease=0 WHERE id=?',(queued['id'],))
        self.assertEqual(self.call('run',dict(id=queued['id']))['status'],'UNKNOWN')
        self.assertEqual(self.network_calls,1)

    def test_exact_native_body_does_not_accept_prompt_token_or_authority(self):
        self.setup_inference()
        for action,body in [('shell',{}),('run',dict(id='x',role='OWNER')),('prepare',dict(task='connection_test',focus='',connection_id=self.profile_id,prompt='execute'))]:
            with self.assertRaises(Invalid):self.call(action,body)
        self.assertEqual(self.network_calls,0)


if __name__=='__main__':unittest.main()
