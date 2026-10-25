"""Real human HTTP, bearer, CLI and official MCP transport to one owned manager."""
from contextlib import asynccontextmanager
from datetime import datetime,timedelta,timezone
import json,os,socket,subprocess,sys,threading,unittest
from email.message import Message
from types import SimpleNamespace
from unittest.mock import patch
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from mission_control.server import Server
from mission_control.operator_client import OperatorClient,ClientError,request_timeout
from mission_control.agent_checkpoints import Checkpoints
from mission_control.review_access import Access
from mission_control.operation_outcome import EffectUncertain
from tests import test_hypit_studio_sessions as fixture
from tests import test_agent_mcp as sdk
from tests import test_verified_review as identities
from tests import test_complete_automation as standing

APP=fixture.APP


class StudioStandingBoundaryTests(standing.AuthorityFixture,unittest.TestCase):
    def test_standing_local_scope_cannot_silently_gain_native_studio_authority(self):
        self.setup_authority();self.addCleanup(self.cleanup_authority)
        with patch('mission_control.operator_identity.github_read',side_effect=identities.synthetic_identity):
            server=Server(('127.0.0.1',0),self.store)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                origin='http://127.0.0.1:'+str(server.server_port)
                owner=OperatorClient(origin);owner.bootstrap()
                owner.request('POST','/api/identity/login',dict(token=identities.OWNER_TOKEN))
                base='/api/apps/sample-one/agent-grants/'
                preview=owner.request('POST',base+'automation-preview',self.proposal())
                issued=owner.request('POST',base+'automation-activate',dict(
                    proposal=preview['proposal'],summary_hash=preview['summary_hash']))
                agent=OperatorClient(origin,grant_token=issued['token'])
                with patch.object(server.service.studio,'dispatch') as dispatch:
                    with self.assertRaises(ClientError):
                        agent.call(dict(app_id='sample-one',operation='studio.sessions',input={}))
                    dispatch.assert_not_called()
                owner.request('POST',base+'automation-off',dict(id=issued['policy_id'],version=1))
                video=owner.request('POST',base+'automation-preview',self.proposal(['video_authoring_editing']))
                self.assertNotEqual(video['summary']['inventory']['scope_status'],'READY_FOR_SCOPE_REVIEW')
                with self.assertRaises(ClientError):
                    owner.request('POST',base+'automation-activate',dict(
                        proposal=video['proposal'],summary_hash=video['summary_hash']))
            finally:
                server.shutdown();server.server_close();thread.join(timeout=10)


class StudioClientTests(unittest.IsolatedAsyncioTestCase):
    login=fixture.ManagerTests.login
    create=fixture.ManagerTests.create
    broker=fixture.ManagerTests.broker
    envelope=fixture.ManagerTests.envelope
    call=fixture.ManagerTests.call
    startup=fixture.ManagerTests.startup

    def setUp(self):
        fixture.ManagerTests.setUp(self)
        p=patch('mission_control.operator_identity.github_read',side_effect=identities.synthetic_identity);p.start();self.addCleanup(p.stop)
        self.server=Server(('127.0.0.1',0),self.store);self.server.service.studio=self.manager
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.origin='http://127.0.0.1:'+str(self.server.server_port)
        self.owner=OperatorClient(self.origin);self.owner.bootstrap()
        self.owner.request('POST','/api/identity/login',dict(token=identities.OWNER_TOKEN))
        self.addCleanup(self.close_server)

    def close_server(self):
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=10)

    def grant(self,review=False):
        operations=['studio.plan','studio.start','studio.sessions','studio.read','studio.edit','studio.inspect','studio.close']
        body=dict(agent_id='studio-agent',manifest_version=self.store.app(APP)['version'],operations=operations,
            max_calls=100,expires=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),review_operations=['studio.start'] if review else [])
        return self.owner.request('POST','/api/apps/'+APP+'/agent-grants/issue',body)

    def cli(self,token,envelope):
        env=dict(os.environ,WMM_AGENT_GRANT=token,PYTHONUTF8='1',PYTHONIOENCODING='utf-8')
        result=subprocess.run([sys.executable,'-m','mission_control.agent_cli','call','--origin',self.origin,'--use-grant'],
            input=json.dumps(envelope).encode(),capture_output=True,env=env,timeout=30)
        return result,json.loads(result.stdout or result.stderr)

    @asynccontextmanager
    async def mcp(self,token):
        from mcp import ClientSession,StdioServerParameters
        from mcp.client.stdio import stdio_client
        params=StdioServerParameters(command=sys.executable,args=['-m','mission_control.agent_mcp','--origin',self.origin,'--use-grant'],
            env=dict(os.environ,WMM_AGENT_GRANT=token,PYTHONUTF8='1',PYTHONIOENCODING='utf-8'))
        async with stdio_client(params) as streams:
            async with ClientSession(*streams) as session:
                await session.initialize();yield session

    async def test_human_start_agent_cli_read_edit_and_same_human_close(self):
        body=self.startup();started=self.owner.call(self.envelope('start',body));identity=started['session']['id']
        token=self.grant()['token'];result,read=self.cli(token,self.envelope('read',identity=identity))
        self.assertEqual(result.returncode,0);self.assertEqual(read['controls'],started['controls'])
        agent=OperatorClient(self.origin,grant_token=token)
        edit=dict(request_key='agent-edit',base_version=1,base_hash='a'*64,parameter={'value':46})
        self.assertEqual(agent.call(self.envelope('edit',edit,identity))['attempt']['status'],'APPLIED')
        self.assertEqual(len(self.created),1);self.assertEqual(self.brokers[0].sent,1)
        self.assertEqual(self.owner.call(self.envelope('close',identity=identity))['session']['state'],'CLOSED')

    @unittest.skipUnless(sdk.HAS_MCP,'Optional official MCP SDK required')
    async def test_real_mcp_catalog_sessions_and_cross_app_denial(self):
        identity=self.owner.call(self.envelope('start',self.startup()))['session']['id'];token=self.grant()['token']
        async with self.mcp(token) as client:
            tools=await client.list_tools();names={t.name for t in tools.tools}
            self.assertTrue({'wmm_studio_start','wmm_studio_read','wmm_studio_close'}<=names)
            result=await client.call_tool('wmm_studio_read',dict(app_id=APP,input={},resource_id=identity))
            self.assertFalse(result.isError,result.content);self.assertEqual(result.structuredContent['data']['controls']['revision'],1)
            foreign=await client.call_tool('wmm_studio_read',dict(app_id='sample-two',input={},resource_id=identity))
            self.assertTrue(foreign.isError)

    async def test_unsigned_and_wrong_owner_cannot_access_human_sessions(self):
        unsigned=OperatorClient(self.origin)
        with self.assertRaises(ClientError):unsigned.call(self.envelope('sessions'))
        checker=OperatorClient(self.origin);checker.bootstrap()
        checker.request('POST','/api/identity/login',dict(token=identities.CHECKER_TOKEN))
        with self.assertRaises(ClientError):checker.call(self.envelope('sessions'))
        self.assertEqual(self.created,[])

    async def test_human_framing_and_duplicate_keys_reject_before_manager(self):
        path='/api/apps/'+APP+'/studio/sessions'
        request=Request(self.origin+path,data=b'{"x":1,"x":2}',method='POST',headers={
            'Content-Type':'application/json','Origin':self.origin,'X-CSRF-Token':self.owner.csrf})
        with self.assertRaises(HTTPError) as error:self.owner.opener.open(request,timeout=5)
        self.assertEqual(error.exception.code,400)
        with self.assertRaises(ClientError):self.owner.request('POST',path+'?extra=1',{})
        self.assertEqual(self.created,[])

    async def test_exact_studio_target_and_any_transfer_encoding_reject(self):
        from mission_control.hypit_studio_routes import framing,human
        path='/api/apps/'+APP+'/studio/sessions'
        headers=Message();headers['Host']='127.0.0.1:'+str(self.server.server_port)
        headers['Origin']=self.origin
        with patch.object(self.manager,'dispatch') as dispatch:
            for target in (path+'/',path+'?',path+'?extra=1',self.origin+path,path+'#fragment'):
                handler=SimpleNamespace(server=self.server,headers=headers,path=target)
                with self.subTest(target=target),self.assertRaises(fixture.Invalid):
                    human(handler,path.strip('/').split('/'),{})
            dispatch.assert_not_called()
        for values in ([''],['chunked'],['','chunked']):
            framed=Message();framed['Content-Type']='application/json';framed['Content-Length']='2'
            for value in values:framed['Transfer-Encoding']=value
            with self.subTest(values=values),self.assertRaises(fixture.Invalid):
                framing(SimpleNamespace(headers=framed))

    async def test_reviewed_start_requires_checker_and_unknown_never_replays(self):
        token=self.grant(review=True)['token'];client=OperatorClient(self.origin,grant_token=token)
        envelope=self.envelope('start',self.startup())
        with self.assertRaises(ClientError):client.call(envelope)
        Access(self.store).save(APP,identities.OWNER,identities.CHECKER,dict(login=identities.CHECKER['login'],role='CHECKER',status='ACTIVE',version=None))
        prepared=client.review('prepare',dict(id='studio-review',envelope=envelope));row=prepared['checkpoint']
        approved=Checkpoints(self.store).approve(APP,'studio-review',identities.CHECKER['principal'],row['revision'],row['hash'])
        with patch.object(fixture.ControlledBroker,'start',side_effect=EffectUncertain()):
            done=client.review('resume',dict(app_id=APP,id='studio-review',revision=approved['revision'],packet_hash=approved['hash']))
        self.assertEqual(done['result']['outcome'],'UNKNOWN');self.assertTrue(done['reconciliation_required'])
        with self.assertRaises(ClientError):client.review('resume',dict(app_id=APP,id='studio-review',revision=approved['revision'],packet_hash=approved['hash']))
        self.assertEqual(len(self.created),1)

    async def test_server_close_retains_owned_cleanup_result(self):
        self.owner.call(self.envelope('start',self.startup()))
        self.server.shutdown()
        self.server.server_close()
        self.assertEqual(self.server.studio_shutdown_result['shutdown'],'CONFIRMED')
        self.assertTrue(self.created[0].closed)

    async def test_human_unknown_response_explicitly_requires_reconciliation(self):
        body=self.startup()
        with patch.object(fixture.ControlledBroker,'start',side_effect=EffectUncertain()):
            path='/api/apps/'+APP+'/studio/start'
            request=Request(self.origin+path,data=json.dumps(body).encode(),method='POST',headers={
                'Content-Type':'application/json','Origin':self.origin,'X-CSRF-Token':self.owner.csrf})
            with self.assertRaises(HTTPError) as error:self.owner.opener.open(request,timeout=10)
        value=json.loads(error.exception.read())
        self.assertEqual(error.exception.code,409);self.assertEqual(value['outcome'],'UNKNOWN')
        self.assertTrue(value['reconciliation_required']);self.assertEqual(len(self.created),1)

    async def test_fixed_client_observation_bounds_preserve_default_and_no_retry(self):
        self.assertEqual(request_timeout('/api/bootstrap',None),15)
        self.assertEqual(request_timeout('/api/agent-operations/call',self.envelope('start',self.startup())),900)
        self.assertEqual(request_timeout('/api/apps/'+APP+'/studio/sessions',{}),900)
        self.assertEqual(request_timeout('/api/agent-operations/reviews/resume',{}),900)

    @unittest.skipUnless(sdk.HAS_MCP,'Official MCP SDK required')
    async def test_ordinary_cli_and_mcp_preserve_unknown_retained_retry_without_resend(self):
        identity=self.owner.call(self.envelope('start',self.startup()))['session']['id']
        token=self.grant()['token'];broker=self.brokers[0]
        edit=dict(request_key='lost-reply',base_version=1,base_hash='a'*64,parameter={'value':46})
        def uncertain(body):
            broker.check('edit',body)
            if broker.sent==0:
                broker.sent+=1;raise EffectUncertain()
            return dict(attempt=dict(status='UNCERTAIN'),execution='NOT_RESENT')
        with patch.object(broker,'edit',side_effect=uncertain):
            result,value=self.cli(token,self.envelope('edit',edit,identity))
            self.assertEqual(result.returncode,3);self.assertEqual(value['error']['code'],'OUTCOME_UNKNOWN')
            self.assertEqual(value['error']['outcome'],'UNKNOWN');self.assertTrue(value['error']['reconciliation_required'])
            async with self.mcp(token) as client:
                retry=await client.call_tool('wmm_studio_edit',dict(app_id=APP,input=edit,resource_id=identity))
                self.assertTrue(retry.isError)
                self.assertIn('UNKNOWN',str(retry.content));self.assertIn('reconciliation_required',str(retry.content))
                self.assertNotIn('HTTP_REJECTED',str(retry.content))
        self.assertEqual(broker.sent,1)

    def raw_request(self,half_close):
        cookies=[]
        for handler in self.owner.opener.handlers:
            if hasattr(handler,'cookiejar'):cookies.extend(c.name+'='+c.value for c in handler.cookiejar)
        path='/api/apps/'+APP+'/studio/sessions'
        request=('POST '+path+' HTTP/1.1\r\nHost: 127.0.0.1:'+str(self.server.server_port)+
            '\r\nOrigin: '+self.origin+'\r\nContent-Type: application/json\r\nX-CSRF-Token: '+self.owner.csrf+
            '\r\nCookie: '+'; '.join(cookies)+'\r\nContent-Length: 1000\r\nConnection: close\r\n\r\n{}').encode()
        with socket.create_connection(('127.0.0.1',self.server.server_port),timeout=10) as client:
            client.sendall(request)
            if half_close:client.shutdown(socket.SHUT_WR)
            data=b''
            while True:
                part=client.recv(65536)
                if not part:break
                data+=part
            return data

    async def test_truncated_and_stalled_human_bodies_reject_before_dispatch(self):
        with patch.object(self.manager,'dispatch',side_effect=AssertionError('Truncated input must not dispatch')) as dispatch:
            for half_close in (True,False):
                response=self.raw_request(half_close)
                self.assertIn(b' 400 ',response.split(b'\r\n',1)[0])
            self.assertEqual(dispatch.call_count,0)


if __name__=='__main__':unittest.main()
