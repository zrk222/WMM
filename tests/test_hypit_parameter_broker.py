"""Controlled actual HTTP transactions over owned-session and durable-ledger code."""
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import copy
import json
import socket
import threading
import unittest
from unittest.mock import patch
from mission_control.common import Invalid
from mission_control.store import Store
from mission_control.hypit_parameter_broker import ParameterBroker
from mission_control import hypit_parameter_broker as target
from tests import test_hypit_studio_process as fixture


class BrokerTests(unittest.TestCase):
    alive=fixture.StudioTests.alive
    command=fixture.StudioTests.command
    ready=fixture.StudioTests.ready

    def setUp(self):
        fixture.StudioTests.setUp(self)
        self.store=Store(self.folder/'ledger.sqlite',seed=False)
        self.store.save_app('sample-one',dict(name='Synthetic',release='build-1',locale='en-US',currency='USD'))
        self.ready();self.granted=True;self.principal='reviewed-actor';self.mode='apply'
        self.native_revision=1;self.value=38;self.scale=1;self.sent=[];self.authority_calls=[]
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def reply(self,status,value):
                raw=json.dumps(value).encode();self.send_response(status)
                self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers()
                try:self.wfile.write(raw)
                except (BrokenPipeError,ConnectionResetError):pass
            def do_GET(self):
                assert self.path=='/__studio/session'
                self.reply(200,owner.snapshot())
            def do_POST(self):
                self.assert_request()
                value=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                owner.sent.append(value)
                attempts=owner.broker.ledger.read('sample-one','project-one')['attempts']
                assert attempts[-1]['status']=='PREPARED','Intent must commit before native send'
                assert value['type']=='parameter.adjust' and value['parameterId']=='native-size-SECRET'
                if owner.mode in ('reject','server-error','unavailable','redirect'):
                    if owner.mode=='reject':owner.native_revision+=2
                    return self.reply({'reject':422,'server-error':500,'unavailable':503,'redirect':302}[owner.mode],dict(error='PRIVATE_NATIVE_DIAGNOSTIC'))
                if owner.mode!='noop':
                    owner.value=value['value']/owner.scale;owner.native_revision+=1
                    with (owner.folder/'style.svs').open('a',encoding='utf-8',newline='') as stream:
                        stream.write('\n// synthetic transaction '+str(owner.value))
                if owner.mode=='immutable':(owner.folder/'font.ttf').write_bytes(b'changed immutable input')
                if owner.mode=='revoke':owner.granted=False
                if owner.mode=='disconnect':
                    self.connection.shutdown(socket.SHUT_RDWR);self.connection.close();return
                if owner.mode=='corrupt-reject':return self.reply(422,dict(error='PRIVATE_ROLLBACK_FAILURE'))
                if owner.mode=='malformed':return self.reply(200,dict(revision='not-an-integer'))
                self.reply(200,dict(revision=owner.native_revision+(1 if owner.mode=='wrong-revision' else 0)))
            def assert_request(self):
                assert self.path=='/__studio/mutation'
                assert self.headers['Origin']==owner.session.origin
                assert self.headers['Content-Type']=='application/json'
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.server_close);self.addCleanup(thread.join,3);self.addCleanup(server.shutdown)
        self.session.origin='http://127.0.0.1:'+str(server.server_port)
        guard=patch.object(target,'revalidate',return_value=self.installation);guard.start();self.addCleanup(guard.stop)
        self.broker=ParameterBroker(self.store,'sample-one','project-one',self.session,self.admit)
        self.addCleanup(self.broker.close)
        self.initial=self.broker.start()

    def admit(self,action,scope):
        self.authority_calls.append((action,scope))
        if not self.granted:raise PermissionError('Synthetic grant revoked')
        return self.principal

    def snapshot(self):
        return dict(revision=self.native_revision,run=dict(path='build.svrun'),source=dict(path='film.svml',
            files=[dict(path=name,text=(self.folder/name).read_text(encoding='utf-8')) for name in self.compiled['files']]),
            tracks=[dict(id='native-track-SECRET',items=[dict(id='native-owner-SECRET',inspector=[
                dict(id='native-size-SECRET',label='Size',control='number',schema=dict(kind='number'),
                     number=dict(scale=self.scale),value=self.value,edit=dict(preimage='PRIVATE_SOURCE_PREIMAGE'))])])])

    def body(self,value=46,key='edit-one',view=None):
        view=view or self.initial;controls=view['controls'];owner=controls['owners'][0];field=owner['fields'][0]
        return dict(request_key=key,base_version=view['source_head']['version'],base_hash=view['source_head']['hash'],
            parameter=dict(revision=controls['revision'],view_hash=controls['view_hash'],owner_id=owner['id'],field_id=field['id'],value=value))

    def test_actual_http_success_commits_before_adoption_and_keeps_native_data_private(self):
        result=self.broker.edit(self.body())
        self.assertEqual(result['attempt']['status'],'APPLIED');self.assertEqual(result['source_head']['version'],2)
        self.assertEqual(result['controls']['owners'][0]['fields'][0]['value'],46)
        self.assertEqual(self.broker.read()['source_head'],result['source_head'])
        self.assertEqual(len(self.sent),1)
        self.assertEqual(self.session.sources['style.svs'],result['source_head']['source_hashes']['style.svs'])
        for private in ('SECRET','PRIVATE_',str(self.folder),'parameterId','preimage'):
            self.assertNotIn(private,json.dumps(result))
        self.assertTrue(all(scope['app_id']=='sample-one' and 'project_input_hash' in scope for _,scope in self.authority_calls))

    def test_noop_revision_and_native_display_normalization_are_not_raw_value_equality(self):
        self.mode='noop';result=self.broker.edit(self.body(38))
        self.assertEqual(result['attempt']['status'],'APPLIED');self.assertEqual(result['controls']['revision'],1)
        self.mode='apply';self.scale=100
        result=self.broker.edit(self.body(55,'normalized',self.broker.read()))
        self.assertEqual(result['controls']['owners'][0]['fields'][0]['value'],.55)
        self.assertEqual(result['attempt']['status'],'APPLIED')

    def test_replay_and_competing_requests_send_once_and_preserve_exact_inputs(self):
        body=self.body()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:self.broker.edit(body),range(2)))
        self.assertEqual(len(self.sent),1)
        self.assertEqual({r['attempt']['id'] for r in results},{results[0]['attempt']['id']})
        self.assertIn('NOT_RESENT',[r['execution'] for r in results])
        changed=copy.deepcopy(body);changed['parameter']['value']=47
        with self.assertRaises(Invalid):self.broker.edit(changed)
        self.assertEqual(len(self.sent),1)

    def test_stale_source_view_and_foreign_field_reject_without_intent_or_send(self):
        for key,value in [('base_hash','c'*64),('base_version',True)]:
            body=self.body();body[key]=value
            with self.assertRaises(Invalid):self.broker.edit(body)
        for key,value in [('revision',99),('view_hash','c'*64),('field_id','foreign')]:
            body=self.body();body['parameter'][key]=value
            with self.assertRaises(Invalid):self.broker.edit(body)
        self.assertEqual(self.sent,[])
        self.assertEqual(self.broker.ledger.read('sample-one','project-one')['attempts'],[])

    def test_definitive_rejection_requires_verified_unchanged_sources(self):
        for index,mode in enumerate(('reject',)):
            self.mode=mode;view=self.broker.read();result=self.broker.edit(self.body(key='rejection-'+str(index),view=view))
            self.assertEqual(result['attempt']['status'],'REJECTED')
            self.assertEqual(result['source_head']['content_hash'],self.initial['source_head']['content_hash'])
            self.assertNotIn('PRIVATE_',json.dumps(result))

    def test_server_errors_and_unexpected_status_remain_uncertain(self):
        self.mode='server-error';body=self.body()
        with self.assertRaisesRegex(Invalid,'uncertain'):self.broker.edit(body)
        retry=self.broker.edit(body)
        self.assertEqual(retry['attempt']['status'],'UNCERTAIN')
        self.assertEqual(retry['execution'],'NOT_RESENT')
        self.assertEqual(self.broker.ledger.read('sample-one','project-one')['head']['version'],1)
        with self.assertRaises(Invalid):self.broker.edit(self.body(key='different-key'))
        self.assertEqual(len(self.sent),1)

    def uncertain_response(self,mode):
        self.mode=mode
        with self.assertRaisesRegex(Invalid,'uncertain'):self.broker.edit(self.body())
        history=self.broker.ledger.read('sample-one','project-one')
        self.assertEqual(history['head']['version'],1)
        self.assertEqual(history['attempts'][0]['status'],'UNCERTAIN')
        self.assertEqual(len(self.sent),1)

    def test_redirect_never_finalizes_rejection(self):self.uncertain_response('redirect')

    def test_unavailable_response_never_finalizes_rejection(self):self.uncertain_response('unavailable')

    def test_disconnect_retains_uncertain_attempt_inspection_and_blocks_resend(self):
        body=self.body();self.mode='disconnect'
        with self.assertRaises(Exception):self.broker.edit(body)
        retry=self.broker.edit(body)
        self.assertEqual(retry['attempt']['status'],'UNCERTAIN');self.assertEqual(retry['execution'],'NOT_RESENT')
        current=self.broker.inspect()
        self.assertFalse(current['resend_allowed']);self.assertNotEqual(current['observed_source_hash'],current['source_head']['content_hash'])
        with self.assertRaises(Invalid):self.broker.edit(self.body(key='new-attempt'))
        self.assertEqual(len(self.sent),1)

    def test_failed_rollback_and_malformed_or_mismatched_revision_remain_uncertain(self):
        self.mode='corrupt-reject'
        with self.assertRaises(Invalid):self.broker.edit(self.body())
        history=self.broker.ledger.read('sample-one','project-one')
        self.assertEqual(history['head']['version'],1);self.assertEqual(history['attempts'][0]['status'],'UNCERTAIN')

    def test_malformed_revision_is_not_success(self):
        self.mode='malformed'
        with self.assertRaises(Invalid):self.broker.edit(self.body())
        self.assertEqual(self.broker.inspect()['attempts'][0]['status'],'UNCERTAIN')

    def test_intervening_revision_is_not_attributed_to_this_mutation(self):
        self.mode='wrong-revision'
        with self.assertRaises(Invalid):self.broker.edit(self.body())
        self.assertEqual(self.broker.inspect()['attempts'][0]['status'],'UNCERTAIN')

    def test_revocation_during_native_response_never_adopts_sources_but_cleanup_works(self):
        before=dict(self.session.sources);self.mode='revoke'
        with self.assertRaises(PermissionError):self.broker.edit(self.body())
        self.assertEqual(self.session.sources,before)
        self.assertEqual(self.broker.ledger.read('sample-one','project-one')['attempts'][0]['status'],'UNCERTAIN')
        self.assertTrue(self.broker.close()['closed']);self.assertIsNotNone(self.child.poll())

    def test_changed_immutable_input_or_foreign_listener_blocks_source_adoption(self):
        self.mode='immutable';before=dict(self.session.sources)
        with self.assertRaisesRegex(Invalid,'immutable'):self.broker.edit(self.body())
        self.assertEqual(self.session.sources,before)
        self.assertEqual(self.broker.ledger.read('sample-one','project-one')['head']['version'],1)

    def test_app_change_authority_denial_and_listener_loss_prevent_native_send(self):
        self.child.listener_owned=False
        with self.assertRaisesRegex(Invalid,'listener'):self.broker.edit(self.body())
        self.child.listener_owned=True;self.granted=False
        with self.assertRaises(PermissionError):self.broker.read()
        self.granted=True;app=self.store.app('sample-one')
        self.store.save_app('sample-one',dict(app['data'],release='changed'),app['version'])
        with self.assertRaises(PermissionError):self.broker.edit(self.body())
        self.assertEqual(self.sent,[])

    def test_private_diagnostic_write_failure_keeps_committed_result_and_no_replay(self):
        body=self.body()
        with patch.object(self.session,'record',side_effect=OSError('PRIVATE_DIAGNOSTIC_FAILURE')):
            result=self.broker.edit(body)
        self.assertEqual(result['attempt']['status'],'APPLIED');self.assertEqual(result['session_state'],'NEEDS_INSPECTION')
        self.assertEqual(self.broker.edit(body)['execution'],'NOT_RESENT')
        with self.assertRaises(Invalid):self.broker.edit(self.body(key='next',view=result))
        self.assertEqual(len(self.sent),1)


if __name__=='__main__':unittest.main()
