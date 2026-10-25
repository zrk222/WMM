"""Actual owner HTTP, CLI and official MCP editing share one durable project."""
import json
import os
import subprocess
import sys
import unittest
from urllib.request import Request
from urllib.error import HTTPError

from mission_control.creative_rendering import Renders
from mission_control.operator_client import OperatorClient, ClientError
from mission_control.worker import run_once
from mission_control.video_edit_projects import CALLER
from mission_control.review_access import Access
from tests import test_verified_review as identities
from tests import test_agent_grants as fixture
from tests import test_agent_mcp as sdk
from tests import test_agent_review_clients as clients
from tests.test_creative_rendering import prepared_render
from tests.test_video_edit_projects import project_data

APP='sample-one'


class VideoClientsTests(unittest.IsolatedAsyncioTestCase):
    body=fixture.GrantTests.body
    envelope=fixture.GrantTests.envelope
    session=clients.ReviewClientTests.session

    def setUp(self):
        fixture.GrantTests.setUp(self)
        app=self.store.app(APP)
        self.store.save_app(APP,dict(app['data'],job='Synthetic job',audience='Synthetic audience',
                                   activation='Saved fictional step'),app['version'])
        brief,request=prepared_render(self.store,APP)
        Renders(self.store).queue(APP,dict(data=request,request_key='editor-client-source'))
        assert run_once(self.store)
        native=Renders(self.store).list(APP)['items'][0]
        self.data=project_data(native['id'],native['data']['artifact']['sha256'])

    def tearDown(self):
        self.assertIsNone(CALLER.get())
        fixture.GrantTests.tearDown(self)

    def grant(self,operations):
        body=dict(self.body(operations,100),manifest_version=self.store.app(APP)['version'])
        issued=self.owner.request('POST','/api/apps/'+APP+'/agent-grants/issue',body)
        self.token=issued['token'];self.issued=issued
        return OperatorClient(self.origin,grant_token=self.token)

    def create(self):
        return self.owner.request('POST','/api/apps/'+APP+'/video-projects',dict(id='client-project',revision=0,
            manifest_version=self.store.app(APP)['version'],data=self.data,request_key='client-create'))

    def mutation(self,revision,key='client-trim'):
        return dict(revision=revision,manifest_version=self.store.app(APP)['version'],request_key=key,
                    command=dict(operation='trim',clip_id='clip-one',in_frame=24,out_frame=216))

    def cli(self,envelope):
        result=subprocess.run([sys.executable,'-m','mission_control.agent_cli','call','--origin',self.origin,'--use-grant'],
            input=json.dumps(envelope).encode(),capture_output=True,env=dict(os.environ,WMM_AGENT_GRANT=self.token),timeout=30)
        self.assertEqual(result.returncode,0,result.stderr.decode())
        self.assertNotIn(self.token,result.stdout.decode())
        return json.loads(result.stdout)

    def test_project_clients_exact_human_routes_foreign_inputs_and_scoped_denial(self):
        created=self.create()
        self.assertEqual(created['actor'],dict(kind='LOCAL_SESSION'))
        base='/api/apps/'+APP+'/video-projects/client-project'
        self.assertEqual(self.owner.request('GET',base)['revision'],1)
        self.assertEqual(self.owner.request('GET','/api/apps/'+APP+'/video-projects')['items'][0]['id'],'client-project')
        agent=self.grant(['editor.read','editor.list'])
        scoped=dict(self.envelope('editor.read'),resource_id='client-project')
        self.assertEqual(agent.call(scoped)['hash'],created['hash'])
        for envelope in (dict(scoped,app_id='sample-two'),
                         dict(self.envelope('editor.edit',self.mutation(1)),resource_id='client-project'),
                         dict(scoped,input=dict(shell='arbitrary'))):
            with self.assertRaises((ClientError,ValueError)):
                agent.call(envelope)
        for path in (base+'?extra=1',base+'/extra','/api/apps/sample-two/video-projects/client-project'):
            with self.assertRaises(ClientError):self.owner.request('GET',path)
        agent=self.grant(['editor.edit'])
        envelope=dict(self.envelope('editor.edit',dict(self.mutation(1),actor=dict(agent_id='forged'))),resource_id='client-project')
        with self.assertRaises((ClientError,ValueError)):agent.call(envelope)
        # Strict JSON parsing rejects duplicate revision fields, rather than last-value wins.
        raw=json.dumps(self.mutation(1)).replace('"revision": 1','"revision": 1,"revision": 2')
        request=Request(self.origin+base+'/edits',data=raw.encode(),method='POST',headers={
            'Origin':self.origin,'Content-Type':'application/json','X-CSRF-Token':self.owner.csrf})
        request.add_header('Cookie','; '.join(cookie.name+'='+cookie.value for cookie in self.owner.cookies))
        with self.assertRaises(HTTPError) as rejected:self.owner.opener.open(request)
        self.assertEqual(rejected.exception.code,400)
        self.assertEqual(self.owner.request('GET',base)['revision'],1)

    @unittest.skipUnless(sdk.HAS_MCP,'Official MCP SDK required for shared client acceptance')
    async def test_project_clients_cli_edit_mcp_read_human_undo_mcp_redo_and_diff(self):
        one=self.create()
        self.grant(['editor.read','editor.edit','editor.history','editor.diff','editor.list'])
        envelope=dict(self.envelope('editor.edit',self.mutation(1)),resource_id='client-project')
        two=self.cli(envelope)
        self.assertEqual(two['revision'],2)
        self.assertEqual(two['actor']['agent_id'],'generic-agent')
        self.assertEqual(two['actor']['grant_id'],self.issued['grant']['id'])
        self.assertEqual(self.cli(envelope),two)
        async with self.session() as client:
            names={row.name for row in (await client.list_tools()).tools}
            self.assertTrue({'wmm_editor_read','wmm_editor_edit','wmm_editor_history','wmm_editor_diff'} <= names)
            read=await client.call_tool('wmm_editor_read',dict(app_id=APP,resource_id='client-project',input={}))
            self.assertFalse(read.isError,read.content)
            self.assertEqual(read.structuredContent['data']['hash'],two['hash'])
            undo=self.owner.request('POST','/api/apps/'+APP+'/video-projects/client-project/history',dict(
                operation='UNDO',revision=2,manifest_version=self.store.app(APP)['version'],request_key='human-undo'))
            self.assertEqual(undo['data'],one['data'])
            self.assertEqual(undo['actor'],dict(kind='LOCAL_SESSION'))
            redo=await client.call_tool('wmm_editor_history',dict(app_id=APP,resource_id='client-project',input=dict(
                operation='REDO',revision=3,manifest_version=self.store.app(APP)['version'],request_key='agent-redo')))
            self.assertFalse(redo.isError,redo.content)
            self.assertEqual(redo.structuredContent['data']['data'],two['data'])
            denied=await client.call_tool('wmm_editor_edit',dict(app_id='sample-two',resource_id='client-project',input=self.mutation(4)))
            self.assertTrue(denied.isError)
        difference=self.cli(dict(self.envelope('editor.diff',dict(from_revision=1,to_revision=4)),resource_id='client-project'))
        self.assertEqual(difference['changed_fields'],['clips'])
        self.assertEqual(self.owner.request('GET','/api/apps/'+APP+'/video-projects/client-project')['revision'],4)

    def test_project_clients_reviewed_edit_requires_distinct_checker_and_retains_agent_identity(self):
        self.create()
        Access(self.store).save(APP,identities.OWNER,identities.CHECKER,dict(
            login=identities.CHECKER['login'],role='CHECKER',status='ACTIVE',version=None))
        checker=OperatorClient(self.origin);checker.bootstrap()
        checker.request('POST','/api/identity/login',dict(token=identities.CHECKER_TOKEN))
        body=dict(self.body(['editor.edit'],100),manifest_version=self.store.app(APP)['version'],review_operations=['editor.edit'])
        issued=self.owner.request('POST','/api/apps/'+APP+'/agent-grants/issue',body)
        agent=OperatorClient(self.origin,grant_token=issued['token'])
        envelope=dict(self.envelope('editor.edit',self.mutation(1,'reviewed-trim')),resource_id='client-project')
        with self.assertRaises(ClientError):agent.call(envelope)
        view=agent.review('prepare',dict(id='reviewed-editor',envelope=envelope))
        approve=dict(id=view['id'],revision=view['checkpoint']['revision'],packet_hash=view['checkpoint']['hash'])
        with self.assertRaises(ClientError):self.owner.request('POST','/api/apps/'+APP+'/agent-reviews/approve',approve)
        approved=checker.request('POST','/api/apps/'+APP+'/agent-reviews/approve',approve)
        done=agent.review('resume',dict(app_id=APP,id=view['id'],revision=approved['revision'],packet_hash=approved['hash']))
        self.assertEqual(done['checkpoint']['state'],'SUCCEEDED',done)
        self.assertEqual(done['result']['data']['actor']['agent_id'],'generic-agent')
        self.assertEqual(done['result']['data']['actor']['grant_id'],issued['grant']['id'])
        self.assertNotIn(issued['token'],json.dumps(done))
        # Approval binds the exact expected project head; an intervening human edit wins.
        envelope=dict(self.envelope('editor.edit',self.mutation(2,'stale-approved-trim')),resource_id='client-project')
        view=agent.review('prepare',dict(id='stale-reviewed-editor',envelope=envelope))
        approved=checker.request('POST','/api/apps/'+APP+'/agent-reviews/approve',dict(
            id=view['id'],revision=view['checkpoint']['revision'],packet_hash=view['checkpoint']['hash']))
        self.owner.request('POST','/api/apps/'+APP+'/video-projects/client-project/edits',self.mutation(2,'human-intervenes'))
        done=agent.review('resume',dict(app_id=APP,id=view['id'],revision=approved['revision'],packet_hash=approved['hash']))
        self.assertEqual(done['checkpoint']['state'],'FAILED')
        self.assertEqual(self.owner.request('GET','/api/apps/'+APP+'/video-projects/client-project')['revision'],3)

    @unittest.skipUnless(sdk.HAS_MCP,'Official MCP SDK required for uploaded-source parity')
    async def test_managed_source_cli_save_and_mcp_edit_share_owner_review(self):
        from mission_control.managed_media_store import Media
        from mission_control.creative_rendering import artifact_file
        native=self.data['clips'][0]['source']
        path,_=artifact_file(self.store,APP,native['id'])
        media=Media(self.store);version=self.store.app(APP)['version']
        row=media.upload(APP,'owned-source.mp4',path.read_bytes(),dict(manifest_version=version,request_key='agent-managed-upload'))
        row=media.review(APP,row['id'],dict(expected_version=0,manifest_version=version,source_sha256=row['source_sha256'],status='ALLOWED',basis='OWNED',evidence='Synthetic owner source permission.'),identities.OWNER)
        self.data['clips'][0].update(source=dict(kind='MANAGED',id=row['id'],sha256=row['source_sha256']),audio='RETAIN')
        self.grant(['editor.save','editor.read','editor.edit'])
        saved=self.cli(self.envelope('editor.save',dict(id='uploaded-client',revision=0,manifest_version=version,data=self.data,request_key='agent-managed-save')))
        self.assertEqual(saved['data']['sources'][0]['kind'],'MANAGED')
        async with self.session() as client:
            edited=await client.call_tool('wmm_editor_edit',dict(app_id=APP,resource_id='uploaded-client',input=self.mutation(1,'managed-trim')))
            self.assertFalse(edited.isError,edited.content)
            result=edited.structuredContent['data']
            self.assertEqual(result['revision'],2)
            self.assertEqual(result['data']['definition']['clips'][0]['audio'],'RETAIN')
            self.assertEqual(result['data']['sources'][0]['review_version'],1)
            media.review(APP,row['id'],dict(expected_version=1,manifest_version=version,source_sha256=row['source_sha256'],status='REVOKED',basis='OWNED',evidence='Synthetic source revoked.'),identities.OWNER)
            refused=await client.call_tool('wmm_editor_edit',dict(app_id=APP,resource_id='uploaded-client',input=self.mutation(2,'managed-revoked')))
            self.assertTrue(refused.isError)
