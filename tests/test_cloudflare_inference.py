"""Offline Cloudflare approval and allowance behavior, with no provider calls."""
import concurrent.futures
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from mission_control.agent_access import AgentAccess
from mission_control.agent_contract import profile
from mission_control.agent_tasks import AgentWork, proposal
from mission_control.common import Invalid, canonical, digest
from mission_control.db import connection
from mission_control.service import Service
from mission_control.store import Store
from mission_control.worker import run_once
from tests.test_measurement_connectors import FakeVault
from tests.test_agent_access import connection_test_fixture


def cloudflare(**changes):
    return dict(provider='cloudflare_api',label='Test',model='@cf/meta/llama-3.2-3b-instruct',endpoint='',
        api_key='synthetic-token-123456',allow_api_charges=False,id=None,version=None,
        account_id='a'*32,billing_mode='free',daily_request_limit=1,max_output_tokens=128,**changes)


class CloudflareTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.store=Store(Path(self.folder.name)/'cloudflare.sqlite3');FakeVault.values={}
        vault=patch('mission_control.agent_access.Vault',FakeVault);vault.start();self.addCleanup(vault.stop)
        self.access=AgentAccess(self.store);self.identity=self.access.save('sample-one',cloudflare())['connection']

    def reviewed(self):
        request=dict(task='connection_test',focus='',connection_id=self.identity)
        return {**request,'source_hash':proposal(self.store,'sample-one',request)['source_hash'],'request_key':str(uuid.uuid4())}

    def test_validation_and_explicit_paid_mode(self):
        valid=profile(cloudflare());self.assertEqual(valid['endpoint'],'https://api.cloudflare.com/client/v4/accounts/'+'a'*32+'/ai/v1')
        cases=[{'account_id':'a'*31},{'endpoint':'https://evil.example'},
               {'model':'@cf/paid/model'},{'billing_mode':'paid'}, {'allow_api_charges':True},
               {'daily_request_limit':0},{'daily_request_limit':True},{'max_output_tokens':2049},
               {'max_output_tokens':63},{'account_id':'a'*32+'/../'}]
        for change in cases:
            with self.subTest(change=change),self.assertRaises(Invalid):profile({**cloudflare(),**change})
        paid=profile({**cloudflare(),'model':'@cf/paid/model','billing_mode':'paid','allow_api_charges':True})
        self.assertEqual(paid['billing_policy']['mode'],'paid')

    def test_concurrent_approval_at_daily_boundary(self):
        requests=[self.reviewed(),self.reviewed()]
        def start(body):
            def finish(db,job):db.execute("UPDATE jobs SET status='BLOCKED' WHERE id=?",(job['id'],))
            try:return AgentWork(self.store,on_start=finish).start('sample-one',body)
            except Invalid as error:return str(error)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:out=list(pool.map(start,requests))
        self.assertEqual(sum(isinstance(x,dict) for x in out),1)
        self.assertIn('daily approval limit',next(x for x in out if isinstance(x,str)))

    def test_uncertain_attempt_consumes_limit_and_is_not_replayed(self):
        job=AgentWork(self.store).start('sample-one',self.reviewed())
        with connection(self.store.path) as db:db.execute("UPDATE jobs SET status='RUNNING',attempts=1,lease=0 WHERE id=?",(job['id'],))
        with patch('mission_control.agent_tasks.api_run') as transport:
            run_once(self.store);transport.assert_not_called()
        with self.assertRaisesRegex(Invalid,'daily approval limit'):AgentWork(self.store).start('sample-one',self.reviewed())

    def test_approved_request_uses_exact_endpoint_and_output_cap(self):
        AgentWork(self.store).start('sample-one',self.reviewed())
        with patch('mission_control.agent_tasks.api_run',return_value=(connection_test_fixture(),{})) as transport:
            run_once(self.store)
        self.assertEqual(transport.call_count,1)
        self.assertEqual(transport.call_args.args[0]['endpoint'],'https://api.cloudflare.com/client/v4/accounts/'+'a'*32+'/ai/v1')
        self.assertEqual(transport.call_args.args[3],128)
        self.assertEqual(self.access.get('sample-one',self.identity)['status'],'TESTED')

    def test_existing_https_transport_receives_fixed_route_and_bearer(self):
        from mission_control.agent_api import request
        import json
        value=profile(cloudflare())
        with patch('mission_control.agent_api.address',return_value='203.0.113.1'), \
             patch('mission_control.agent_api.trust_context'), \
             patch('mission_control.agent_api.PinnedHTTPS') as wire, \
             patch('mission_control.agent_api.response_headers'), \
             patch('mission_control.agent_api.response_body',return_value=b'{}'), \
             patch('mission_control.agent_api.message',return_value=canonical(connection_test_fixture())):
            wire.return_value.getresponse.return_value.status=200
            request(value,'synthetic-token-123456','approved prompt',128)
        args=wire.return_value.request.call_args
        self.assertEqual(args.args[:2],('POST','/client/v4/accounts/'+'a'*32+'/ai/v1/chat/completions'))
        self.assertEqual(args.kwargs['headers']['Authorization'],'Bearer synthetic-token-123456')
        self.assertEqual(json.loads(args.kwargs['body'])['max_tokens'],128)

    def test_real_response_parser_accepts_complete_choice_and_rejects_failures(self):
        from mission_control.agent_api import request
        import json
        good={'choices':[{'finish_reason':'stop','message':{'content':canonical(connection_test_fixture())}}],
              'usage':{'prompt_tokens':3,'completion_tokens':4,'total_tokens':7}}
        cases=[(200,good,True),(200,{'choices':[{'finish_reason':'length','message':{'content':'{}'}}]},False),
               (200,{'choices':[{'finish_reason':'stop','message':{'content':'{}','tool_calls':[{}]}}]},False),
               (200,{'choices':[]},False),(200,{'choices':[{'finish_reason':'stop','message':{'content':'not json'}}]},False),
               (403,{},False),(429,{},False)]
        for status,response,accepted in cases:
            with self.subTest(status=status,response=response), \
                 patch('mission_control.agent_api.address',return_value='203.0.113.1'), \
                 patch('mission_control.agent_api.trust_context'), \
                 patch('mission_control.agent_api.PinnedHTTPS') as wire, \
                 patch('mission_control.agent_api.response_headers'), \
                 patch('mission_control.agent_api.response_body',return_value=json.dumps(response).encode()):
                wire.return_value.getresponse.return_value.status=status
                if accepted:
                    result,usage=request(profile(cloudflare()),'synthetic-token-123456','approved',128)
                    self.assertEqual(result,connection_test_fixture());self.assertEqual(usage['total_tokens'],7)
                else:
                    with self.assertRaises(Invalid):request(profile(cloudflare()),'synthetic-token-123456','approved',128)
                self.assertEqual(wire.return_value.request.call_count,1)

    def test_cancel_consumes_limit_until_utc_rollover(self):
        job=AgentWork(self.store).start('sample-one',self.reviewed());Service(self.store).cancel('sample-one',job['id'])
        with self.assertRaisesRegex(Invalid,'daily approval limit'):AgentWork(self.store).start('sample-one',self.reviewed())
        tomorrow=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()
        with patch('mission_control.agent_tasks.now',return_value=tomorrow):
            second=AgentWork(self.store).start('sample-one',self.reviewed())
        self.assertNotEqual(job['id'],second['id'])

    def test_policy_and_approval_tamper_fail_before_transport(self):
        job=AgentWork(self.store).start('sample-one',self.reviewed())
        with connection(self.store.path) as db:
            import json
            data=json.loads(db.execute('SELECT data FROM jobs WHERE id=?',(job['id'],)).fetchone()[0])
            data['envelope']['billing_policy']['mode']='paid';data['envelope_hash']=digest(data['envelope'])
            db.execute('UPDATE jobs SET data=? WHERE id=?',(canonical(data),job['id']))
        with patch('mission_control.agent_tasks.api_run') as transport:
            run_once(self.store);transport.assert_not_called()
        with connection(self.store.path) as db:self.assertEqual(db.execute('SELECT status FROM jobs WHERE id=?',(job['id'],)).fetchone()[0],'BLOCKED')


if __name__=='__main__':unittest.main()
