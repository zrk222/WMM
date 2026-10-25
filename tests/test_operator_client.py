"""Actual local server/session persistence plus hostile transport fixtures."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
import json
import tempfile
import threading
import unittest
from mission_control.common import Invalid
from mission_control.server import Server
from mission_control.store import Store
from mission_control.operator_client import OperatorClient,ClientError,origin_data,strict_json,encode_body,MAX_BYTES
import socket
from tests.test_aso_validation import listing
from tests.test_customer_workflow import proposal


class OperatorClientTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.store=Store(Path(self.tmp.name)/'client.sqlite',seed=False)
        for app in ('sample-one','sample-two'):
            self.store.save_app(app,dict(name='Synthetic Café 東京',release='build-1',locale='en-US',currency='USD'))
        self.server=Server(('127.0.0.1',0),self.store)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.client=OperatorClient('http://127.0.0.1:'+str(self.server.server_port))

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.tmp.cleanup()

    def call(self,operation,value=None,app='sample-one',**extra):
        return self.client.call(dict(app_id=app,operation=operation,input=value or {},**extra))

    def test_actual_growth_save_replay_readback_and_cross_app_isolation(self):
        with patch.dict('os.environ',{'HTTP_PROXY':'http://127.0.0.1:1','http_proxy':'http://127.0.0.1:1','NO_PROXY':''}):
            workspace=self.call('workspace.read')
        self.assertEqual(workspace['app']['id'],'sample-one')
        body=dict(id='listing-one',manifest_version=1,kind='ASO_LISTING',data=dict(release='build-1',listing=listing()))
        first=self.call('growth.save',body)
        self.assertEqual(self.call('growth.save',body)['hash'],first['hash'])
        self.assertEqual(self.call('growth.history')['history'][0]['id'],'listing-one')
        self.assertEqual(self.call('growth.history',app='sample-two')['history'],[])
        self.assertTrue(self.client.csrf)
        self.assertEqual(len(list(self.client.cookies)),1)
        self.assertEqual(self.call('snapshot.export')['payload']['growth_reviews'][0]['id'],'listing-one')

    def test_customer_save_and_server_validation_preserve_original(self):
        body=dict(id='workflow-one',manifest_version=1,data=proposal())
        first=self.call('customer.save',body)
        self.assertEqual(self.call('customer.history')['history'][0]['hash'],first['hash'])
        bad=dict(body,data=dict(body['data'],locale='fr-CA'))
        with self.assertRaises(ClientError) as error:self.call('customer.save',bad)
        self.assertEqual(error.exception.status,400)
        self.assertEqual(self.call('customer.history')['history'][0]['hash'],first['hash'])

    def test_unknown_operation_never_bootstraps_and_bad_csrf_never_writes(self):
        with patch.object(self.client,'bootstrap') as bootstrap:
            with self.assertRaises(Invalid):self.call('human.approve')
            bootstrap.assert_not_called()
        self.client.bootstrap();self.client.csrf='wrong'
        body=dict(id='listing-one',manifest_version=1,kind='ASO_LISTING',data=dict(release='build-1',listing=listing()))
        with self.assertRaises(ClientError) as error:self.call('growth.save',body)
        self.assertEqual(error.exception.status,403)
        self.assertEqual(self.call('growth.history')['history'],[])

    def test_origins_and_strict_json_reject_ambiguity_and_payload_limits(self):
        self.assertEqual(origin_data('http://127.0.0.1:57599'),'http://127.0.0.1:57599')
        for value in ('https://127.0.0.1:1','http://localhost:1','http://127.0.0.1:0','http://127.0.0.1:01','http://127.0.0.1:65536','http://127.0.0.1:1/','http://u@127.0.0.1:1','http://127.0.0.1:1?x=1',None):
            with self.subTest(value=value),self.assertRaises(Invalid):origin_data(value)
        for raw in (b'{"x":1,"x":2}',b'{"n":NaN}',b'{"n":1e999}',b'\xff',b'{',b'['*1100+b']'*1100):
            with self.subTest(raw=raw[:20]),self.assertRaises(Invalid):strict_json(raw)
        self.assertEqual(strict_json('"Café 東京"'.encode()),'Café 東京')
        with self.assertRaises(Invalid):encode_body(dict(x=float('inf')))
        with self.assertRaises(Invalid):encode_body(dict(x='a'*MAX_BYTES))
        with self.assertRaises(Invalid):strict_json(b' '* (MAX_BYTES+1))


class TransportFixture(BaseHTTPRequestHandler):
    mode='redirect'
    seen=[]
    def do_GET(self):
        self.seen.append(self.path)
        if self.mode=='redirect':
            self.send_response(302);self.send_header('Location','http://127.0.0.1:1/private');self.end_headers();return
        self.send_response(200)
        self.send_header('Content-Type','text/html' if self.mode=='html' else 'application/json');self.end_headers()
        body={'html':b'<html>secret body</html>','duplicate':b'{"csrf":"x","csrf":"y"}','session':b'{"csrf":"short"}','drop':b'{"csrf":"abcdefghijklmnopqrstuvwxyz0123456789"}'}.get(self.mode,b'{}')
        self.wfile.write(body)
    def do_POST(self):
        self.seen.append(self.path)
        self.rfile.read(int(self.headers.get('Content-Length','0')))
        self.connection.shutdown(socket.SHUT_RDWR)
        self.connection.close()
    def log_message(self,*args):pass


class OperatorTransportTests(unittest.TestCase):
    def test_redirect_invalid_content_duplicate_response_and_session_fail_closed(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),TransportFixture)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            for mode,code in [('redirect','REDIRECT_REJECTED'),('html','INVALID_RESPONSE'),('duplicate','INVALID_RESPONSE'),('session','INVALID_SESSION')]:
                TransportFixture.mode=mode;TransportFixture.seen=[]
                client=OperatorClient('http://127.0.0.1:'+str(server.server_port))
                with self.subTest(mode=mode),self.assertRaises(ClientError) as error:client.call(dict(app_id='one',operation='workspace.read',input={}))
                self.assertEqual(error.exception.code,code)
                self.assertEqual(TransportFixture.seen,['/api/bootstrap'])
                self.assertNotIn('secret body',str(error.exception))
        finally:
            server.shutdown();server.server_close();thread.join()

    def test_lost_write_response_is_not_retried_or_reported_as_definite_failure(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),TransportFixture)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        TransportFixture.mode='drop';TransportFixture.seen=[]
        try:
            client=OperatorClient('http://127.0.0.1:'+str(server.server_port))
            body=dict(id='listing-one',manifest_version=1,kind='ASO_LISTING',data=dict(release='build-1',listing=listing()))
            with self.assertRaises(ClientError) as error:client.call(dict(app_id='sample-one',operation='growth.save',input=body))
            self.assertEqual(error.exception.code,'TRANSPORT_UNAVAILABLE')
            self.assertIn('Inspect saved history',str(error.exception))
            self.assertEqual(TransportFixture.seen,['/api/bootstrap','/api/apps/sample-one/subscription-growth/entries'])
        finally:
            server.shutdown();server.server_close();thread.join()
