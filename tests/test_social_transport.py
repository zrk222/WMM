"""Fixed hosts, secret forwarding, documented form framing and closed failures."""
import json,unittest
from unittest.mock import patch
from mission_control.common import Invalid
from mission_control.social_transport import request,SocialError,form_body
from mission_control.aeo_transport import ReadError


class Response:
    def __init__(self,status=200,raw=b'{"id":"synthetic-account"}'):self.status=status;self.raw=raw
    def getheaders(self):return [('Content-Length',str(len(self.raw))),('Content-Type','application/json')]
    def read1(self,size):part=self.raw[:size];self.raw=self.raw[size:];return part


class Wire:
    response=Response()
    calls=[]
    closed=0
    def __init__(self,host,ip,context,deadline):self.stream_socket=self;type(self).calls.append(('destination',host,ip))
    def settimeout(self,value):pass
    def request(self,*args,**kwargs):type(self).calls.append((args,kwargs))
    def getresponse(self):return type(self).response
    def close(self):type(self).closed+=1


class SocialTransportTests(unittest.TestCase):
    def setUp(self):
        Wire.calls=[];Wire.closed=0;Wire.response=Response()
        for name,value in (('PinnedHTTPS',Wire),('address',lambda *a:'203.0.113.1'),('trust_context',lambda:object())):
            mocked=patch('mission_control.social_transport.'+name,value);mocked.start();self.addCleanup(mocked.stop)

    def test_fixed_identity_read_pins_host_and_keeps_bearer_out_of_url(self):
        self.assertEqual(request('tiktok','identity',bearer='synthetic-access')['id'],'synthetic-account')
        self.assertEqual(Wire.calls[0],('destination','open.tiktokapis.com','203.0.113.1'))
        args,kwargs=Wire.calls[1];self.assertEqual(args[0],'GET')
        self.assertIn('fields=open_id%2Cdisplay_name',args[1]);self.assertNotIn('synthetic-access',args[1])
        self.assertEqual(kwargs['headers']['Authorization'],'Bearer synthetic-access');self.assertEqual(Wire.closed,1)

    def test_documented_token_form_and_no_override_of_grant_or_host(self):
        fields=dict(client_key='synthetic-client',client_secret='synthetic-secret',redirect_uri='http://127.0.0.1:8765/social/callback/tiktok',code='synthetic-code',code_verifier='V'*64)
        request('tiktok','code',fields)
        args,kwargs=Wire.calls[1];self.assertEqual(args[0],'POST');self.assertIn(b'grant_type=authorization_code',kwargs['body'])
        self.assertNotIn('synthetic-secret',args[1]);self.assertNotIn('synthetic-code',args[1])
        for extra in ({'url':'https://private.example'},{'grant_type':'client_credentials'}):
            with self.assertRaises(Invalid):request('tiktok','code',{**fields,**extra})
        with self.assertRaises(Invalid):request('tiktok','publish',{})

    def test_instagram_multipart_is_bounded_and_contains_only_fixed_fields(self):
        request('instagram','code',dict(client_id='123456',client_secret='synthetic-secret',redirect_uri='https://relay.example/cb/instagram',code='synthetic-code'))
        args,kwargs=Wire.calls[1];self.assertEqual(args[1],'/oauth/access_token')
        self.assertIn('multipart/form-data; boundary=',kwargs['headers']['Content-Type'])
        self.assertIn(b'name="grant_type"\r\n\r\nauthorization_code',kwargs['body'])
        self.assertIn(b'name="client_secret"',kwargs['body'])
        with self.assertRaises(Invalid):request('instagram','code',dict(client_id='123456',client_secret='synthetic-secret\r\nforged',redirect_uri='https://relay.example/cb/instagram',code='synthetic-code'))

    def test_redirect_auth_rate_and_network_failures_never_reflect_credentials(self):
        for code,expected in ((302,'REDIRECT_REJECTED'),(401,'ACCESS_DENIED'),(403,'ACCESS_DENIED'),(429,'RATE_LIMITED'),(400,'AUTHORIZATION_REJECTED'),(500,'UNCONFIRMED')):
            with self.subTest(code=code):
                Wire.response=Response(code,b'{"error":"SYNTHETIC_PRIVATE_ERROR"}')
                with self.assertRaises(SocialError) as error:request('linkedin','identity',bearer='synthetic-secret')
                self.assertEqual(error.exception.code,expected);self.assertNotIn('PRIVATE',str(error.exception))
        with patch.object(Wire,'request',side_effect=OSError('SYNTHETIC_PRIVATE_SECRET')):
            with self.assertRaises(SocialError) as error:request('linkedin','identity',bearer='synthetic-secret')
            self.assertNotIn('PRIVATE',str(error.exception))

    def test_private_dns_or_invalid_json_fails_closed_before_reuse(self):
        with patch('mission_control.social_transport.address',side_effect=ReadError('ADDRESS_BLOCKED')):
            with self.assertRaises(SocialError):request('linkedin','identity',bearer='synthetic-secret')
            self.assertEqual(Wire.calls,[])
        for raw in (b'{"id":1,"id":2}',b'[]',b'{"bad":NaN}',b'not JSON'):
            with self.subTest(raw=raw):
                Wire.response=Response(raw=raw)
                with self.assertRaises(SocialError):request('linkedin','identity',bearer='synthetic-secret')


if __name__=='__main__':unittest.main()
