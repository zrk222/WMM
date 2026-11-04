"""Real loopback owner policy controls with synthetic assets and identities."""
import json
import threading
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from mission_control.operator_client import OperatorClient, ClientError
from mission_control.server import Server
from mission_control.db import connection
from mission_control.common import uid
from tests import test_organic_video_policy as fixtures
from tests import test_verified_review as identities
from tests import test_organic_video_intake as intake_fixtures
from tests.test_campaign_video_execution import Transport
from mission_control import campaign_video_execution as video
from mission_control.campaign_contract import REEL_SCHEMA
from types import SimpleNamespace


class PolicyHTTPTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.OrganicPolicyTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.store = self.f.store
        def synthetic_owner(path, token):
            user = identities.synthetic_identity(path, token)
            return dict(user, principal=fixtures.OWNER['principal'], login=fixtures.OWNER['login'])
        self.mock = patch('mission_control.operator_identity.github_read', side_effect=synthetic_owner)
        self.mock.start()
        self.addCleanup(self.mock.stop)
        self.server = Server(('127.0.0.1', 0), self.store)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close)
        self.origin = 'http://127.0.0.1:' + str(self.server.server_port)
        self.owner = OperatorClient(self.origin)
        self.owner.bootstrap()
        self.owner.request('POST', '/api/identity/login', dict(token=identities.OWNER_TOKEN))
        self.base = '/api/apps/'+fixtures.APP+'/organic-video/'

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self, action, body):
        return self.owner.request('POST', self.base+action, body)

    def test_owner_create_read_reserve_and_revoke_use_exact_domain_authority(self):
        policy = self.request('policy-create', dict(request_id=uid(), policy=self.f.policy))
        selected = dict(policy_id=policy['id'], policy_hash=policy['hash'])
        self.assertEqual(self.request('policy-read', selected), policy)
        reserve = self.f.reservation_body(policy)
        result = self.request('policy-reserve', reserve)
        self.assertEqual(self.request('policy-reserve', reserve), result)
        self.assertEqual(result['data']['status'], 'HELD')
        self.assertNotIn('access_token', json.dumps(result))
        self.assertEqual(self.request('policy-revoke', selected)['status'], 'REVOKED')
        with self.assertRaises(ClientError):
            self.request('policy-read', selected)
        with connection(self.store.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM organic_video_generation_reservations').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT count(*) FROM jobs').fetchone()[0], 0)

    def test_domain_validation_and_paths_cannot_widen_owner_authority(self):
        for action, body in (('policy-create', dict(request_id='bad', policy=dict(self.f.policy, max_posts=21))),
                             ('policy-create?x=1', {}), ('policy-create/', {}),
                             ('policy-execute', {}), ('policy-admit', dict(actor='forged'))):
            with self.subTest(action=action), self.assertRaises(ClientError):
                self.request(action, body)
        anonymous = OperatorClient(self.origin)
        anonymous.bootstrap()
        with self.assertRaises(ClientError):
            anonymous.request('POST', self.base+'policy-create', dict(request_id='anonymous', policy=self.f.policy))

    def test_missing_csrf_and_bearer_cookie_mixture_are_rejected(self):
        body = dict(request_id='forged', policy=self.f.policy)
        raw = json.dumps(body).encode()
        for origin, csrf, bearer in ((self.origin, 'wrong', False), ('http://foreign.invalid', self.owner.csrf, False),
                                     (self.origin, self.owner.csrf, True)):
            headers = {'Origin':origin,'Content-Type':'application/json','X-CSRF-Token':csrf,
                       'Cookie':'; '.join(c.name+'='+c.value for c in self.owner.cookies)}
            if bearer:
                headers['Authorization'] = 'Bearer synthetic-bearer'
            request = Request(self.origin+self.base+'policy-create',data=raw,method='POST',headers=headers)
            with self.assertRaises(HTTPError) as error:
                self.owner.opener.open(request, timeout=10)
            error.exception.close()
        with connection(self.store.path) as db:
            self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='organic_video_policies'").fetchone())

    def test_owner_exact_admission_to_intent_execute_and_retained_read(self):
        policy=self.request('policy-create',dict(request_id=uid(),policy=dict(self.f.policy,max_calls=40)))
        admission_body=self.f.admission(policy,reserve_calls=40)
        admitted=self.request('policy-admit',admission_body)
        output=admitted['data']['output']
        request=dict(schema=REEL_SCHEMA,request_id=uid(),app_id=fixtures.APP,page_id='123',
            policy_id=policy['id'],policy_hash=policy['hash'],admission_id=admitted['id'],admission_hash=admitted['hash'],
            artifact_id=output['artifact_id'],artifact_sha256=output['artifact_sha256'],caption=output['caption'],
            rights_hashes=sorted({x['rights_hash'] for x in admitted['data']['proofs']['sources']}))
        intent=self.request('intent-create',request)
        self.assertEqual(self.request('intent-read',dict(intent_id=intent['id']))['stage'],'NEW')
        transport=Transport()
        def facebook(config,secret,token,alive):
            alive();return SimpleNamespace(subject_id='fixture-subject',permissions=['pages_manage_posts','pages_show_list','pages_read_engagement'])
        def page(secret,token,identity,alive):alive();return dict(id='123',tasks=['CREATE_CONTENT']),'synthetic-page'
        with patch.object(video,'_credentials',return_value=({},'synthetic-secret',dict(access_token='synthetic-user'))),patch.object(video,'facebook',side_effect=facebook),patch.object(video,'selected_page',side_effect=page),patch.object(video,'provider',transport):
            # The fake provider carries the real private context type; no network.
            from mission_control.campaign_video_transport import Context
            transport.Context=Context
            result=self.request('intent-execute',dict(intent_id=intent['id']))
            repeated=self.request('intent-execute',dict(intent_id=intent['id']))
        self.assertEqual(result,repeated)
        self.assertEqual(result['stage'],'PROVIDER_PHASE_COMPLETE')
        self.assertEqual(transport.calls.count('publish'),1)
        self.assertEqual(self.request('intent-read',dict(intent_id=intent['id']))['remote_id'],'456')
        self.request('policy-revoke',dict(policy_id=policy['id'],policy_hash=policy['hash']))
        self.assertEqual(self.request('intent-read',dict(intent_id=intent['id']))['remote_id'],'456')
        with self.assertRaises(ClientError):self.request('intent-execute',dict(intent_id=intent['id']))

    def test_intent_actions_reject_unapproved_artifact_and_extra_fields(self):
        for action,body in (('intent-create',dict(approved=True)),('intent-execute',dict(intent_id=uid(),force=True)),
                            ('intent-reconcile',dict(intent_id=uid(),actor='forged'))):
            with self.subTest(action=action),self.assertRaises(ClientError):self.request(action,body)

    def test_owner_reviews_and_activates_exact_video_schedule_then_turns_it_off(self):
        from datetime import datetime, timedelta, timezone
        policy = self.request('policy-create', dict(request_id=uid(), policy=dict(self.f.policy, max_calls=40)))
        admitted = self.request('policy-admit', self.f.admission(policy, reserve_calls=40))
        output = admitted['data']['output']
        intent = self.request('intent-create', dict(schema=REEL_SCHEMA, request_id=uid(), app_id=fixtures.APP,
            page_id='123', policy_id=policy['id'], policy_hash=policy['hash'], admission_id=admitted['id'],
            admission_hash=admitted['hash'], artifact_id=output['artifact_id'], artifact_sha256=output['artifact_sha256'],
            caption=output['caption'], rights_hashes=sorted({x['rights_hash'] for x in admitted['data']['proofs']['sources']})))
        body = dict(policy_id=policy['id'], policy_hash=policy['hash'], items=[dict(intent_id=intent['id'],
                    due_at=(datetime.now(timezone.utc)+timedelta(minutes=1)).isoformat())])
        draft = self.request('schedule-prepare', body)
        identity = draft['summary']['batch_id']
        with self.assertRaises(ClientError):
            self.request('schedule-activate', dict(batch_id=identity, summary_hash='0'*64))
        active = self.request('schedule-activate', dict(batch_id=identity, summary_hash=draft['summary_hash']))
        self.assertEqual(active['status'], 'ACTIVE')
        self.assertEqual(self.request('schedule-status', dict(batch_id=identity)), active)
        issued = self.owner.request('POST', '/api/apps/'+fixtures.APP+'/agent-grants/issue', dict(
            agent_id='schedule-reader', manifest_version=self.store.app(fixtures.APP)['version'],
            operations=['organic-video.policy-read'], expires=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(), max_calls=2))
        bearer = Request(self.origin+self.base+'schedule-status', method='POST',
            data=json.dumps(dict(batch_id=identity)).encode(), headers={'Origin':self.origin,
                'Content-Type':'application/json','Authorization':'Bearer '+issued['token']})
        with self.assertRaises(HTTPError) as denied:
            urlopen(bearer, timeout=10)
        self.assertEqual(denied.exception.code, 403)
        denied.exception.close()
        with self.assertRaises(ClientError):
            self.request('schedule-revoke', dict(batch_id=identity, version=active['version']-1))
        stopped = self.request('schedule-revoke', dict(batch_id=identity, version=active['version']))
        self.assertEqual(stopped['status'], 'OFF')
        with connection(self.store.path) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM jobs WHERE action='campaign_post'").fetchone()[0], 0)


class IntakeHTTPTests(unittest.TestCase):
    close = PolicyHTTPTests.close
    request = PolicyHTTPTests.request

    def setUp(self):
        self.f=intake_fixtures.IntakeTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.store=self.f.store
        def synthetic_owner(path,token):
            user=identities.synthetic_identity(path,token)
            return dict(user,principal=self.f.fixture.owner['principal'],login=self.f.fixture.owner['login'])
        self.mock=patch('mission_control.operator_identity.github_read',side_effect=synthetic_owner)
        self.mock.start();self.addCleanup(self.mock.stop)
        self.server=Server(('127.0.0.1',0),self.store)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.addCleanup(self.close)
        self.origin='http://127.0.0.1:'+str(self.server.server_port)
        self.owner=OperatorClient(self.origin);self.owner.bootstrap()
        self.owner.request('POST','/api/identity/login',dict(token=identities.OWNER_TOKEN))
        self.base='/api/apps/'+self.f.app+'/organic-video/'

    def test_owner_reads_report_and_adopts_exact_candidate_without_provider_effect(self):
        task=self.request('task-read',dict(task_id=self.f.body['task_id']))
        self.assertEqual(task['result_hash'],self.f.body['result_hash'])
        self.assertEqual(task['submission_hash'],self.f.body['submission_hash'])
        self.assertEqual(task['submission']['candidates'][0]['candidate']['post_id'],self.f.body['candidate_id'])
        adopted=self.request('intake',self.f.body)
        self.assertEqual(self.request('intake',self.f.body),adopted)
        self.assertEqual(adopted['data']['publication'],'NOT_RUN')
        self.assertEqual(adopted['data']['foreign_bytes'],'NOT_AUTHORIZED')
        self.assertNotIn(self.f.fixture.grant['token'],json.dumps(task))

    def test_missing_identity_and_wrong_app_cannot_read_or_adopt(self):
        anonymous=OperatorClient(self.origin);anonymous.bootstrap()
        with self.assertRaises(ClientError):
            anonymous.request('POST',self.base+'task-read',dict(task_id=self.f.body['task_id']))
        with self.assertRaises(ClientError):
            self.owner.request('POST',self.base.replace('sample-one','sample-two')+'task-read',dict(task_id=self.f.body['task_id']))
        with self.assertRaises(ClientError):
            self.request('intake',dict(self.f.body,actor='forged'))


if __name__ == '__main__':
    unittest.main()
