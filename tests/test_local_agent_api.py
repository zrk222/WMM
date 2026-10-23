"""Actual bounded HTTP to a synthetic loopback model server; no model download."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import threading
import unittest
from unittest.mock import patch
from mission_control.common import Invalid,canonical
from mission_control.local_agent_api import endpoint,request
from tests.test_agent_access import answer


class ModelServer:
    """Capture actual request framing and emit a selected synthetic provider response."""
    def __init__(self):
        self.calls=[];self.status=200;self.headers=[];self.raw=None
        self.value=dict(choices=[dict(finish_reason='stop',message=dict(content=canonical(answer())))],usage={'total_tokens':12})
        fixture=self
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                raw=self.rfile.read(int(self.headers['Content-Length']))
                fixture.calls.append(dict(path=self.path,headers=dict(self.headers),body=json.loads(raw)))
                payload=fixture.raw if fixture.raw is not None else canonical(fixture.value).encode()
                self.send_response(fixture.status)
                for key,value in fixture.headers:self.send_header(key,value)
                if not any(k.lower()=='content-type' for k,v in fixture.headers):self.send_header('Content-Type','application/json')
                if not any(k.lower()=='content-length' for k,v in fixture.headers):self.send_header('Content-Length',str(len(payload)))
                self.end_headers()
                try:self.wfile.write(payload)
                except (BrokenPipeError,ConnectionResetError):pass
            def log_message(self,*args):pass
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url='http://127.0.0.1:'+str(self.server.server_port)+'/v1'

    def close(self):
        self.server.shutdown();self.server.server_close();self.thread.join()


class LocalAPITests(unittest.TestCase):
    def setUp(self):
        self.model=ModelServer();self.addCleanup(self.model.close)
        self.profile=dict(provider='local_api',endpoint=self.model.url,model='synthetic-model')

    def test_endpoint_normalizes_only_explicit_loopback_authority(self):
        self.assertEqual(endpoint('http://localhost:11434/v1/'),'http://127.0.0.1:11434/v1')
        self.assertEqual(endpoint('http://[::1]:11434/v1'),'http://[::1]:11434/v1')
        invalid=['https://localhost:11434/v1','http://localhost/v1','http://127.0.0.2:11434/v1','http://0.0.0.0:11434/v1','http://192.168.0.1:11434/v1','http://example.test:11434/v1','http://localhost.example:11434/v1','http://2130706433:11434/v1','http://127.0.0.1:0/v1','http://127.0.0.1:65536/v1','http://user:secret@localhost:11434/v1','http://localhost:11434/v1?','http://localhost:11434/v1#','http://localhost:11434/../v1','http://localhost:11434/%2fadmin','http://localhost:11434/v1\\other','http://localhost:11434/\nadmin']
        for value in invalid:
            with self.subTest(value=value),self.assertRaises(Invalid):endpoint(value)

    def test_actual_loopback_chat_without_auth_or_dns(self):
        with patch('socket.getaddrinfo',side_effect=AssertionError('DNS is not allowed')):
            value,usage=request(self.profile,None,'Reviewed prompt',256)
        self.assertEqual(value,answer());self.assertEqual(usage['total_tokens'],12)
        call=self.model.calls[0];self.assertEqual(call['path'],'/v1/chat/completions')
        self.assertNotIn('Authorization',call['headers']);self.assertFalse(call['body']['stream'])
        self.assertEqual(call['body']['max_tokens'],256);self.assertNotIn('tools',call['body'])

    def test_optional_auth_and_key_echo_rejection(self):
        key='synthetic-local-key'
        request(self.profile,key,'Reviewed prompt')
        self.assertEqual(self.model.calls[0]['headers']['Authorization'],'Bearer '+key)
        self.model.value['choices'][0]['message']['content']=canonical(dict(answer(),summary=key))
        with self.assertRaises(Invalid) as caught:request(self.profile,key,'Reviewed prompt')
        self.assertNotIn(key,str(caught.exception))

    def test_redirect_and_provider_failure_do_not_follow_or_reveal_private_error(self):
        for status in (301,302,307,401,429,500):
            self.model.status=status;self.model.headers=[('Location','https://private.example/SECRET')]
            self.model.raw=b'PRIVATE_SENTINEL';before=len(self.model.calls)
            with self.assertRaises(Invalid) as caught:request(self.profile,None,'Approved')
            self.assertEqual(len(self.model.calls),before+1);self.assertNotIn('PRIVATE_SENTINEL',str(caught.exception))

    def test_non_json_compression_oversize_and_ambiguous_lengths_reject(self):
        for headers in [[('Content-Type','text/html')],[('Content-Encoding','gzip')],[('Content-Length','1048577')],[('Content-Length','1'),('Content-Length','2')]]:
            self.model.headers=headers
            with self.subTest(headers=headers),self.assertRaises(Invalid):request(self.profile,None,'Approved')

    def test_structured_final_response_is_required_without_tools(self):
        for value in [[],{},dict(choices=[dict(finish_reason='length',message=dict(content='{}'))]),dict(choices=[dict(finish_reason='stop',message=dict(content='{}',tool_calls=[{}]))]),dict(choices=[dict(finish_reason='stop',message=dict(content='not JSON'))])]:
            self.model.value=value
            with self.subTest(value=value),self.assertRaises(Invalid):request(self.profile,None,'Approved')

    def test_cancel_before_and_after_io_and_invalid_bounds(self):
        with self.assertRaises(Invalid):request(self.profile,None,'Approved',alive=lambda:(_ for _ in ()).throw(Invalid('Cancelled')))
        self.assertEqual(self.model.calls,[])
        calls=[]
        def guard():
            calls.append(True)
            if len(calls)>1:raise Invalid('Cancelled after IO')
        with self.assertRaises(Invalid):request(self.profile,None,'Approved',alive=guard)
        self.assertEqual(len(self.model.calls),1)
        for prompt,tokens,key in [('x'*32769,1,None),('valid',True,None),('valid',2049,None),('valid',1,'bad key')]:
            with self.assertRaises(Invalid):request(self.profile,key,prompt,tokens)

    def test_remote_profile_cannot_reach_transport(self):
        with patch('mission_control.local_agent_api.LocalConnection') as connect:
            with self.assertRaises(Invalid):request(dict(self.profile,endpoint='http://remote.example:8080/v1'),None,'Approved')
            connect.assert_not_called()
