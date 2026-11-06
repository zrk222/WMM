"""Actual scoped bearer gateway for existing owner-approved video artifacts."""
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from mission_control.common import Invalid,uid
from mission_control.db import connection
from mission_control.operator_client import OperatorClient,ClientError
from mission_control.campaign_contract import REEL_SCHEMA
from mission_control import campaign_video_execution as video
from mission_control.campaign_video_transport import Context
from mission_control.organic_video_access import dispatch
from tests import test_organic_video_policy_http as fixture
from tests import test_organic_video_policy as policy_fixture
from tests.test_campaign_video_execution import Transport
from tests import test_agent_mcp as sdk
from tests import test_agent_review_clients as clients
from tests import test_video_edit_clients as editing

APP=policy_fixture.APP
NAMES=['organic-video.policy-read','organic-video.policy-reserve','organic-video.policy-admit',
       'organic-video.workflow-prepare','organic-video.intent-create','organic-video.intent-read','organic-video.intent-execute','hypit.queue']


class VideoGatewayTests(unittest.TestCase):
    setUp_base=fixture.PolicyHTTPTests.setUp
    close=fixture.PolicyHTTPTests.close
    request=fixture.PolicyHTTPTests.request

    def setUp(self):
        self.setUp_base()
        self.policy=self.request('policy-create',dict(request_id=uid(),policy=dict(self.f.policy,max_calls=40)))
        self.issued=self.owner.request('POST','/api/apps/'+APP+'/agent-grants/issue',dict(agent_id='video-agent',
            manifest_version=self.store.app(APP)['version'],operations=NAMES,expires=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),max_calls=50))
        self.agent=OperatorClient(self.origin,grant_token=self.issued['token'])

    def call(self,action,body):
        return self.agent.call(dict(app_id=APP,operation='organic-video.'+action,input=body))

    def admit(self):
        reservation=self.call('policy-reserve',self.f.reservation_body(self.policy))
        body=dict(data=reservation['data']['render_input'],request_key=reservation['data']['job_request_key'])
        with patch('mission_control.hypit_jobs.identity',return_value=dict(launcher='fixture',launcher_sha256='0'*64)):
            queued=self.agent.call(dict(app_id=APP,operation='hypit.queue',input=body))
        artifact=self.f.render_artifact(reservation)
        artifact['reservation']=reservation
        admission=self.call('policy-admit',self.f.admission(self.policy,artifact,reserve_calls=40))
        with connection(self.store.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM jobs WHERE id=?',(queued['id'],)).fetchone()[0],1)
        return admission

    def intent(self):
        admitted=self.admit();output=admitted['data']['output']
        body=dict(schema=REEL_SCHEMA,request_id=uid(),app_id=APP,page_id='123',policy_id=self.policy['id'],policy_hash=self.policy['hash'],
            admission_id=admitted['id'],admission_hash=admitted['hash'],artifact_id=output['artifact_id'],artifact_sha256=output['artifact_sha256'],
            caption=output['caption'],rights_hashes=sorted({x['rights_hash'] for x in admitted['data']['proofs']['sources']}))
        return self.call('intent-create',body)

    def test_actual_gateway_reads_reserves_queues_admits_and_executes_once(self):
        selected=dict(policy_id=self.policy['id'],policy_hash=self.policy['hash'])
        self.assertEqual(self.call('policy-read',selected),self.policy)
        intent=self.intent();transport=Transport();transport.Context=Context
        def facebook(config,secret,token,alive):
            alive();return SimpleNamespace(subject_id='fixture-subject',permissions=['pages_manage_posts','pages_show_list','pages_read_engagement'])
        def page(secret,token,identity,alive):alive();return dict(id='123',tasks=['CREATE_CONTENT']),'synthetic-page'
        with patch.object(video,'_credentials',return_value=({},'synthetic-secret',dict(access_token='synthetic-user'))),patch.object(video,'facebook',side_effect=facebook),patch.object(video,'selected_page',side_effect=page),patch.object(video,'provider',transport):
            result=self.call('intent-execute',dict(intent_id=intent['id']))
            self.assertEqual(self.call('intent-execute',dict(intent_id=intent['id'])),result)
        self.assertEqual(result['stage'],'PROVIDER_PHASE_COMPLETE');self.assertEqual(transport.calls.count('publish'),1)
        self.assertEqual(self.call('intent-read',dict(intent_id=intent['id']))['remote_id'],'456')
        self.assertEqual(len(self.agent.cookies),0);self.assertIsNone(self.agent.csrf)
        self.assertNotIn(self.issued['token'],str(result))

    def test_unbound_dispatch_and_owner_mutations_are_not_agent_tools(self):
        selected=dict(policy_id=self.policy['id'],policy_hash=self.policy['hash'])
        with self.assertRaises(PermissionError):dispatch(self.store,APP,'policy-read',selected)
        for name in ('policy-create','policy-revoke','intent-reconcile','intake'):
            with self.assertRaises((ClientError,ValueError)):
                self.call(name,selected)
        with self.assertRaises(Invalid):
            self.call('policy-read',dict(selected,approved=True))
        with self.assertRaises(ClientError):
            self.agent.call(dict(app_id='sample-two',operation='organic-video.policy-read',input=selected))

    def test_standing_render_requires_exact_human_approval_before_credentials(self):
        self.policy = self.request('policy-create', dict(request_id=uid(), policy=dict(
            self.f.policy, mode='STANDING_GENERATED', approved_output_hashes=[], max_calls=40,
        )))
        intent = self.intent()
        body = dict(intent_id=intent['id'])
        with patch.object(video, '_credentials', side_effect=AssertionError('Credentials must not be read')):
            for execute in (self.call, self.request):
                with self.subTest(caller=execute.__name__), self.assertRaises(ClientError) as denied:
                    execute('intent-execute', body)
                self.assertEqual(denied.exception.status, 403)
        retained = self.call('intent-read', body)
        self.assertEqual(retained['stage'], 'NEW')
        self.assertEqual(retained['calls_used'], 0)
        self.assertIsNone(retained['remote_id'])

    def test_current_grant_revocation_stops_read_and_reserved_generation(self):
        selected=dict(policy_id=self.policy['id'],policy_hash=self.policy['hash'])
        self.call('policy-read',selected)
        self.owner.request('POST','/api/apps/'+APP+'/agent-grants/revoke',dict(id=self.issued['grant']['id'],version=1))
        with self.assertRaises(ClientError):self.call('policy-read',selected)
        with self.assertRaises(ClientError):self.call('policy-reserve',self.f.reservation_body(self.policy))

    def test_policy_revocation_prevents_agent_admission_and_new_mutations(self):
        reservation=self.call('policy-reserve',self.f.reservation_body(self.policy))
        self.request('policy-revoke',dict(policy_id=self.policy['id'],policy_hash=self.policy['hash']))
        with self.assertRaises(ClientError):self.call('policy-read',dict(policy_id=self.policy['id'],policy_hash=self.policy['hash']))
        body=dict(data=reservation['data']['render_input'],request_key=reservation['data']['job_request_key'])
        with patch('mission_control.hypit_jobs.identity',return_value=dict(launcher='fixture',launcher_sha256='0'*64)):
            with self.assertRaises(ClientError):self.agent.call(dict(app_id=APP,operation='hypit.queue',input=body))
        with connection(self.store.path) as db:self.assertEqual(db.execute('SELECT count(*) FROM jobs').fetchone()[0],0)

    def test_other_current_owner_grant_cannot_borrow_this_owners_policy(self):
        from mission_control.review_access import Access
        from mission_control.agent_grants import Grants
        other=dict(principal='github:999',login='other-synthetic-owner')
        with connection(self.store.path) as db:
            Access(self.store).write(db,APP,other,'OWNER','ACTIVE',1,other['principal'])
        issued=Grants(self.store).issue(APP,other,dict(agent_id='other-agent',manifest_version=self.store.app(APP)['version'],
            operations=['organic-video.policy-read'],expires=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),max_calls=1))
        client=OperatorClient(self.origin,grant_token=issued['token'])
        with self.assertRaises(ClientError):
            client.call(dict(app_id=APP,operation='organic-video.policy-read',input=dict(policy_id=self.policy['id'],policy_hash=self.policy['hash'])))

    def test_finite_grant_calls_are_shared_for_new_policy_reads(self):
        issued=self.owner.request('POST','/api/apps/'+APP+'/agent-grants/issue',dict(agent_id='one-call',
            manifest_version=self.store.app(APP)['version'],operations=['organic-video.policy-read'],
            expires=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),max_calls=1))
        client=OperatorClient(self.origin,grant_token=issued['token'])
        envelope=dict(app_id=APP,operation='organic-video.policy-read',input=dict(policy_id=self.policy['id'],policy_hash=self.policy['hash']))
        self.assertEqual(client.call(envelope),self.policy)
        with self.assertRaises(ClientError):client.call(envelope)


@unittest.skipUnless(sdk.HAS_MCP, 'Official MCP SDK required for video gateway acceptance')
class VideoGatewayClientTests(unittest.IsolatedAsyncioTestCase):
    setUp_base = VideoGatewayTests.setUp_base
    close = VideoGatewayTests.close
    request = VideoGatewayTests.request
    setUp = VideoGatewayTests.setUp
    cli = editing.VideoClientsTests.cli
    session = clients.ReviewClientTests.session

    async def test_cli_policy_read_mcp_reserve_and_cli_replay_share_one_reservation(self):
        self.token = self.issued['token']
        envelope = dict(app_id=APP, operation='organic-video.policy-read',
                        input=dict(policy_id=self.policy['id'], policy_hash=self.policy['hash']))
        self.assertEqual(self.cli(envelope), self.policy)
        body = self.f.reservation_body(self.policy)
        async with self.session() as client:
            names = {row.name for row in (await client.list_tools()).tools}
            self.assertTrue({'wmm_' + name.replace('.', '_') for name in NAMES[:-1]} <= names)
            self.assertNotIn('wmm_organic-video_policy-create', names)
            result = await client.call_tool('wmm_organic-video_policy-reserve', dict(app_id=APP, input=body))
            self.assertFalse(result.isError, result.content)
            reserved = result.structuredContent['data']
        self.assertEqual(self.cli(dict(app_id=APP, operation='organic-video.policy-reserve', input=body)), reserved)
        with connection(self.store.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM organic_video_generation_reservations').fetchone()[0], 1)


if __name__=='__main__':unittest.main()
