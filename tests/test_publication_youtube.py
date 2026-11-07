"""Offline YouTube resumable adapter contract tests."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from mission_control import publication_youtube as yt
from mission_control.common import Invalid
from mission_control.publication_transport import Context, Response

def response(status=200, data=None, headers=None):
    return Response(status=status,data=data or {},headers=headers or {})

def fixture():
    draft={'provider':'youtube','destination_id':'UC1','title':'Title','caption':'Caption','link':None,
           'settings':{'privacy_status':'public','self_declared_made_for_kids':False,'contains_synthetic_media':False}}
    artifact={'raw':b'abc','sha256':'x','bytes':3,'duration_seconds':30,'width':720,'height':1280,'fps':30,'content_type':'video/mp4'}
    context=Context('youtube','UC1','secret',lambda:None,lambda:None)
    return draft,artifact,context

class YouTubePublicationTests(unittest.TestCase):
    def test_private_provider_result_does_not_silently_satisfy_public_request(self):
        d,a,c=fixture()
        data={'items':[{'id':'vid1','snippet':{'channelId':'UC1'},'status':{'privacyStatus':'private'},'processingDetails':{'processingStatus':'succeeded'}}]}
        with patch.object(yt.http,'request',return_value=response(data=data)):
            result=yt.read(d,{'remote_id':'vid1','session':None},c)
        self.assertEqual(result['status'],'PUBLISHED')
        self.assertTrue(result['observation']['requires_attention'])
        self.assertEqual(result['observation']['requested_privacy_status'],'public')
        self.assertIn('do not upload a duplicate',result['observation']['next_action'])

    def test_init_upload_and_read_owner_channel(self):
        d,a,c=fixture()
        with patch.object(yt.http,'request',return_value=response(headers={'location':'https://www.googleapis.com/upload/youtube/v3/videos?upload_id=secret'})) as req:
            state=yt.create(d,a,c)
        self.assertEqual(state['status'],'CREATED')
        self.assertNotIn('secret',str(state['observation']))
        self.assertEqual(req.call_args.kwargs['json_body']['status']['privacyStatus'],'public')
        with patch.object(yt.http,'upload',return_value=response(data={'id':'vid1'})):
            state=yt.upload(d,a,state,c)
        self.assertEqual(state['remote_id'],'vid1')
        data={'items':[{'id':'vid1','snippet':{'channelId':'UC1'},'status':{'privacyStatus':'public'},'processingDetails':{'processingStatus':'succeeded'}}]}
        with patch.object(yt.http,'request',return_value=response(data=data)):
            state=yt.read(d,state,c)
        self.assertEqual(state['observation']['privacy_status'],'public')

    def test_resume_query_and_mismatched_owner(self):
        d,a,c=fixture(); state={'status':'CREATED','remote_id':None,'asset_id':None,'session':{'url':'https://www.googleapis.com/upload/youtube/v3/videos?upload_id=x','bytes':3},'observation':{}}
        with patch.object(yt.http,'upload',return_value=response(status=308,headers={'range':'bytes=0-1'})):
            state=yt.read(d,state,c)
        self.assertEqual(state['session']['offset'],2)
        bad={'items':[{'id':'vid1','snippet':{'channelId':'other'}}]}
        with patch.object(yt.http,'request',return_value=response(data=bad)):
            with self.assertRaises(Invalid): yt.read(d,{**state,'remote_id':'vid1'},c)

    def test_eligibility_and_context_rejected_before_effect(self):
        d,a,c=fixture()
        with patch.object(yt.http,'request') as call:
            with self.assertRaises(Invalid): yt.create(d,{**a,'duration_seconds':181},c)
            with self.assertRaises(Invalid): yt.create(d,a,Context('youtube','other','secret',lambda:None,lambda:None))
            call.assert_not_called()

    def test_missing_session_cannot_reinitialize_and_bad_ranges_fail(self):
        d,a,c=fixture()
        with patch.object(yt.http,'request') as request:
            with self.assertRaises(Invalid): yt.read(d,{'remote_id':None,'session':None},c)
            request.assert_not_called()
        state={'remote_id':None,'session':{'url':'https://www.googleapis.com/upload/youtube/v3/videos?upload_id=x','bytes':3}}
        with patch.object(yt.http,'upload',return_value=response(status=308,headers={'range':'bytes=0-99'})):
            with self.assertRaises(Invalid): yt.read(d,state,c)

    def test_rate_limit_does_not_automatically_retry(self):
        d,a,c=fixture()
        with patch.object(yt.http,'request',side_effect=Invalid('rate limited')) as request:
            with self.assertRaises(Invalid): yt.create(d,a,c)
            self.assertEqual(request.call_count,1)

    def test_real_transport_accepts_adapter_calls_and_preserves_json_upload_response(self):
        d,a,c=fixture(); session='https://www.googleapis.com/upload/youtube/v3/videos?upload_id=test'
        with patch.object(yt.http,'_exchange',side_effect=[response(headers={'location':session}),response(data={'id':'v1'})]) as exchange:
            state=yt.create(d,a,c)
            state=yt.upload(d,a,state,c)
        self.assertEqual(state['remote_id'],'v1')
        self.assertTrue(exchange.call_args.args[7])
