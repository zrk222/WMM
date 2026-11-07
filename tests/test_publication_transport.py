"""Fixed destinations, private capabilities and authority boundaries for publishing."""
import json
import unittest
from unittest.mock import Mock, patch

from mission_control.common import Invalid
from mission_control import publication_transport as transport


class PublicationTransportTests(unittest.TestCase):
    def context(self, provider='youtube', family='default'):
        return transport.Context(provider, 'selected-account', 'synthetic-private-token',
                                 Mock(), Mock(), login_family=family)

    def response(self, status=200, data=None, headers=()):
        conn=Mock()
        response=conn.getresponse.return_value
        response.status=status
        response.getheaders.return_value=list(headers)
        return conn, json.dumps(data or {}).encode()

    def test_fixed_api_host_and_private_token_never_enter_repr(self):
        context=self.context()
        conn, raw=self.response(data={'items':[]})
        with patch.object(transport,'PinnedHTTPS',return_value=conn), \
             patch.object(transport,'address',return_value='93.184.216.34'), \
             patch.object(transport,'response_headers',return_value={}), \
             patch.object(transport,'response_body',return_value=raw):
            result=transport.request(context,'GET','/youtube/v3/channels',query={'mine':'true'})
        self.assertEqual(result.data,{'items':[]})
        self.assertNotIn(context.token,repr(context))
        self.assertEqual(conn.request.call_args.args[:2],('GET','/youtube/v3/channels?mine=true'))
        self.assertEqual(conn.request.call_args.kwargs['headers']['Authorization'],'Bearer '+context.token)
        context.before_call.assert_called_once()
        conn.close.assert_called_once()

    def test_rejects_untrusted_hosts_and_paths_before_authority_or_network(self):
        context=self.context()
        with patch.object(transport,'PinnedHTTPS') as network:
            for url in ('https://127.0.0.1/upload','https://www.googleapis.com.evil.test/upload',
                        'https://user:pass@www.googleapis.com/upload/youtube/v3/videos',
                        'http://www.googleapis.com/upload/youtube/v3/videos'):
                with self.subTest(url=url),self.assertRaises(Invalid):
                    transport.upload(context,url,b'x')
            for path in ('//other.test/x','/../private','/x/%2e%2e/private','/x%2fprivate','/x?token=bad'):
                with self.subTest(path=path),self.assertRaises(Invalid):
                    transport.request(context,'GET',path)
        network.assert_not_called()
        context.before_call.assert_not_called()

    def test_upload_status_probe_and_encoded_linkedin_urn_are_supported(self):
        context=self.context()
        conn, raw=self.response(308,headers=[('Range','bytes=0-1023')])
        with patch.object(transport,'PinnedHTTPS',return_value=conn), \
             patch.object(transport,'address',return_value='93.184.216.34'), \
             patch.object(transport,'response_headers',return_value={}), \
             patch.object(transport,'response_body',return_value=b''):
            result=transport.upload(context,'https://www.googleapis.com/upload/youtube/v3/videos?upload_id=private',
                                    b'',content_range='bytes */2048',expected=(200,201,308),bearer=True)
        self.assertEqual(result.status,308)
        self.assertEqual(result.headers['range'],'bytes=0-1023')
        headers=conn.request.call_args.kwargs['headers']
        self.assertEqual(headers['Content-Length'],'0')
        self.assertEqual(headers['Content-Range'],'bytes */2048')
        self.assertEqual(transport.api_url(self.context('linkedin'),'/rest/videos/urn%3Ali%3Avideo%3Aabc'),
                         'https://api.linkedin.com/rest/videos/urn%3Ali%3Avideo%3Aabc')

    def test_redirect_or_network_failure_is_sanitized_without_retry(self):
        context=self.context()
        conn, raw=self.response(302,headers=[('Location','https://evil.test/private-token')])
        for failure in (None,OSError('private-token and upload_id=secret')):
            with self.subTest(failure=type(failure).__name__), \
                 patch.object(transport,'PinnedHTTPS',return_value=conn), \
                 patch.object(transport,'address',return_value='93.184.216.34'), \
                 patch.object(transport,'response_headers',return_value={}), \
                 patch.object(transport,'response_body',return_value=raw):
                conn.request.side_effect=failure
                with self.assertRaises(transport.PublicationError) as caught:
                    transport.request(context,'POST','/upload/youtube/v3/videos',json_body={})
                self.assertNotIn('private-token',str(caught.exception))
                self.assertNotIn('secret',str(caught.exception))

    def test_meta_upload_oauth_and_linkedin_upload_host_do_not_cross_channels(self):
        ig=self.context('instagram','facebook')
        self.assertEqual(transport.api_url(ig,'/v26.0/123/media'),'https://graph.facebook.com/v26.0/123/media')
        with self.assertRaises(Invalid):
            transport.upload(self.context('linkedin'),'https://rupload.facebook.com/ig-api-upload/v26.0/123',b'x')
        with self.assertRaises(Invalid):
            transport.upload(self.context(),'https://www.googleapis.com/upload/youtube/v3/videos',b'x',
                             headers={'Authorization':'Bearer injected'})


if __name__=='__main__':
    unittest.main()
