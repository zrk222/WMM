"""Bearer payload ambiguity rejects before business admission on real HTTP."""
from email.message import Message
import http.client
import io
import json
from pathlib import Path
import socket
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from mission_control import agent_grant_http
from mission_control.agent_grant_http import framing, read_body
from mission_control.agent_review_protocol import PATHS
from mission_control.common import Invalid
from mission_control.server import Server
from mission_control.store import Store

ENVELOPE=dict(app_id='sample-one',operation='studio.sessions',input={})
REQUESTS={'/api/agent-operations/call':ENVELOPE,
          PATHS['prepare']:dict(id='review-one',envelope=ENVELOPE),
          PATHS['status']:dict(app_id='sample-one',id='review-one'),
          PATHS['resume']:dict(app_id='sample-one',id='review-one',revision=1,packet_hash='a'*64)}


def headers(length='2'):
    value=Message();value['Content-Type']='application/json';value['Content-Length']=length
    return value


class FramingTests(unittest.TestCase):
    def test_singleton_decimal_bounds_and_every_transfer_encoding_reject(self):
        for values in ([''],['chunked'],['','chunked'],['identity']):
            with self.subTest(values=values):
                h=headers()
                for value in values:h['Transfer-Encoding']=value
                with self.assertRaises(Invalid):framing(SimpleNamespace(headers=h))
        for length in ('0','-1','+2',' 2','2.0','16777217','9'*100):
            with self.subTest(length=length):
                with self.assertRaises(Invalid):framing(SimpleNamespace(headers=headers(length)))
        for name in ('Content-Length','Content-Type'):
            h=headers();h[name]=h[name]
            with self.assertRaises(Invalid):framing(SimpleNamespace(headers=h))
        framing(SimpleNamespace(headers=headers('16777216')))

    def test_reader_restores_timeout_and_rejects_short_or_stalled_payload(self):
        for result in (b'{}',b'{',TimeoutError('private path'),OSError('private path')):
            with self.subTest(result=type(result).__name__):
                connection=Mock();connection.gettimeout.return_value=17
                stream=SimpleNamespace(read1=Mock(side_effect=result)) if isinstance(result,Exception) else io.BytesIO(result)
                handler=SimpleNamespace(headers=headers(),connection=connection,rfile=stream)
                if result==b'{}':self.assertEqual(read_body(handler),b'{}')
                else:
                    with self.assertRaises(Invalid) as error:read_body(handler)
                    self.assertNotIn('private path',str(error.exception))
                self.assertTrue(0<connection.settimeout.call_args_list[0].args[0]<=5)
                self.assertEqual(connection.settimeout.call_args_list[-1].args,(17,))

    def test_cumulative_budget_cannot_reset_after_each_successful_read(self):
        connection=Mock();connection.gettimeout.return_value=17
        handler=SimpleNamespace(headers=headers('3'),connection=connection,
                                rfile=SimpleNamespace(read1=Mock(side_effect=[b'{',b'}',b' '])))
        with patch('mission_control.http_body.time.monotonic',side_effect=[0,0,2,2,4,4,6]):
            with self.assertRaisesRegex(Invalid,'5 seconds'):read_body(handler)
        self.assertTrue(handler.close_connection)
        self.assertEqual(connection.settimeout.call_args_list[-1].args,(17,))


class GatewayHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.server=Server(('127.0.0.1',0),Store(Path(self.temp.name)/'state.sqlite',seed=False))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.origin='http://127.0.0.1:'+str(self.server.server_port)

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.temp.cleanup()

    def request(self,path,body,extras):
        client=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=8)
        try:
            client.putrequest('POST',path,skip_host=True,skip_accept_encoding=True)
            for name,value in [('Host',self.origin[7:]),('Origin',self.origin),('Authorization','Bearer synthetic-token'),
                               ('Content-Type','application/json'),('Content-Length',str(len(body))),*extras]:
                client.putheader(name,value)
            client.endheaders(body);response=client.getresponse();return dict(status=response.status,raw=response.read(),transport_error=None)
        except (ConnectionAbortedError,ConnectionResetError,http.client.RemoteDisconnected) as error:
            return dict(status=None,raw=b'',transport_error=type(error).__name__)
        finally:client.close()

    def assert_framing_rejection(self,path,result,events,message):
        matching=[event for event in events if event.get('event')=='FRAMING_INVALID' and event.get('path')==path]
        self.assertEqual(len(matching),1,'the same request needs one observed server framing denial before a transport abort can count')
        self.assertEqual(matching[0]['error'],'Invalid')
        self.assertEqual(matching[0]['message'],message)
        if result['status'] is None:
            self.assertIn(result['transport_error'],('ConnectionAbortedError','ConnectionResetError','RemoteDisconnected'))
        else:
            self.assertIsNone(result['transport_error'])
            self.assertEqual(result['status'],400,result['raw'])
            self.assertIn(b'content',result['raw'].lower(),result['raw'])

    @staticmethod
    def observed_framing(original,events):
        def observe(handler):
            try:return original(handler)
            except Invalid as error:
                events.append(dict(event='FRAMING_INVALID',path=handler.path,error=type(error).__name__,message=str(error)))
                raise
        return observe

    def test_actual_call_and_all_review_routes_reject_before_dispatch(self):
        targets=['mission_control.agent_grants.Grants.admit',
                 'mission_control.agent_review_http.ReviewedDispatch.prepare',
                 'mission_control.agent_review_http.ReviewedDispatch.inspect',
                 'mission_control.agent_review_http.ReviewedDispatch.resume']
        malformed=(( [('Transfer-Encoding','')], 'Use one bounded content length'),
                   ([('Transfer-Encoding',''),('Transfer-Encoding','chunked')], 'Use one bounded content length'),
                   ([('Content-Type','application/json')], 'Use exactly one application/json content type'))
        from contextlib import ExitStack
        with ExitStack() as stack:
            guards=[stack.enter_context(patch(target,side_effect=AssertionError('Must reject before admission'))) for target in targets]
            for path,value in REQUESTS.items():
                body=json.dumps(value).encode()
                cases=(*malformed,([('Content-Length',str(len(body)))], 'Use one bounded content length'))
                for extra,message in cases:
                    with self.subTest(path=path,extra=extra):
                        events=[];original=agent_grant_http.framing
                        with patch('mission_control.agent_grant_http.framing',side_effect=self.observed_framing(original,events)):
                            result=self.request(path,body,extra)
                        self.assert_framing_rejection(path,result,events,message)
            for guard in guards:guard.assert_not_called()

    def test_client_abort_without_matching_server_denial_is_not_a_rejection(self):
        with self.assertRaisesRegex(AssertionError,'same request needs one observed server framing denial'):
            self.assert_framing_rejection('/api/agent-operations/call',
                dict(status=None,raw=b'',transport_error='ConnectionAbortedError'),[],
                'Use one bounded content length')

    def test_empty_transfer_encoding_guard_removal_mutant_fails_the_request_assertion(self):
        path='/api/agent-operations/call';body=json.dumps(ENVELOPE).encode();events=[]
        original=agent_grant_http.framing
        def without_empty_encoding_guard(handler):
            encodings=handler.headers.get_all('Transfer-Encoding')
            if encodings==['']:
                del handler.headers['Transfer-Encoding']
                try:return original(handler)
                finally:handler.headers['Transfer-Encoding']=''
            return self.observed_framing(original,events)(handler)
        with patch('mission_control.agent_grant_http.framing',side_effect=without_empty_encoding_guard), \
             patch('mission_control.agent_grants.Grants.admit',side_effect=AssertionError('mutant reached admission')) as admit:
            result=self.request(path,body,[('Transfer-Encoding','')])
        admit.assert_called_once()
        with self.assertRaisesRegex(AssertionError,'same request needs one observed server framing denial'):
            self.assert_framing_rejection(path,result,events,'Use one bounded content length')

    def raw_request(self,path,stall=False):
        body=json.dumps(REQUESTS[path]).encode();client=socket.create_connection(('127.0.0.1',self.server.server_port),timeout=8)
        try:
            prefix=(f'POST {path} HTTP/1.1\r\nHost: {self.origin[7:]}\r\nOrigin: {self.origin}\r\n'
                    f'Authorization: Bearer synthetic-token\r\nContent-Type: application/json\r\n'
                    f'Content-Length: {len(body)+1}\r\nConnection: close\r\n\r\n').encode()
            client.sendall(prefix+body)
            if not stall:client.shutdown(socket.SHUT_WR)
            raw=b''
            while True:
                value=client.recv(65536)
                if not value:break
                raw+=value
            return raw
        finally:client.close()

    def test_actual_truncation_on_call_and_review_routes(self):
        for path in REQUESTS:
            with self.subTest(path=path):
                raw=self.raw_request(path);self.assertIn(b'400',raw.split(b'\r\n')[0]);self.assertIn(b'truncated',raw)

    def test_actual_stalled_call_and_resume_are_bounded(self):
        for path in ('/api/agent-operations/call',PATHS['resume']):
            with self.subTest(path=path):
                raw=self.raw_request(path,stall=True);self.assertIn(b'400',raw.split(b'\r\n')[0]);self.assertIn(b'5 seconds',raw)

    def test_actual_trickle_body_stops_before_admission_at_total_deadline(self):
        client=socket.create_connection(('127.0.0.1',self.server.server_port),timeout=8)
        prefix=(f'POST /api/agent-operations/call HTTP/1.1\r\nHost: {self.origin[7:]}\r\nOrigin: {self.origin}\r\n'
                'Authorization: Bearer synthetic-token\r\nContent-Type: application/json\r\n'
                'Content-Length: 7\r\nConnection: close\r\n\r\n').encode()
        errors=[]
        def trickle():
            try:
                for index,byte in enumerate(b'{}     '):
                    if index:time.sleep(1)
                    client.sendall(bytes([byte]))
            except OSError as error:errors.append(type(error).__name__)
        with patch('mission_control.agent_grants.Grants.admit') as admit:
            try:
                started=time.monotonic();client.sendall(prefix)
                sender=threading.Thread(target=trickle);sender.start();raw=b''
                while True:
                    value=client.recv(65536)
                    if not value:break
                    raw+=value
                elapsed=time.monotonic()-started
                self.assertIn(b'400',raw.split(b'\r\n')[0]);self.assertIn(b'5 seconds',raw)
                self.assertLess(elapsed,5.8);admit.assert_not_called()
            finally:client.close();sender.join(timeout=8)


if __name__=='__main__':unittest.main()
