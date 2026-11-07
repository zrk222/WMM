"""Offline TikTok creator, transfer and status tests."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from mission_control import publication_tiktok as tt
from mission_control.common import Invalid
from mission_control.publication_transport import Context, Response

def response(status=200,data=None,headers=None): return Response(status=status,data=data or {},headers=headers or {})
def ok(data): return response(data={'error':{'code':'ok'},'data':data})
def fixture():
    d={'provider':'tiktok','destination_id':'open1','title':'','caption':'Caption','link':None,
       'settings':{'privacy_level':'SELF_ONLY','disable_duet':True,'disable_comment':True,'disable_stitch':True,
                   'brand_content_toggle':False,'brand_organic_toggle':True,'is_aigc':False}}
    a={'raw':b'abc','sha256':'x','bytes':3,'duration_seconds':30,'width':720,'height':1280,'fps':30,'content_type':'video/mp4'}
    a['approved_creator_info']={'creator_username':'creator','creator_nickname':'Creator','privacy_level_options':['SELF_ONLY'],'max_video_post_duration_sec':60,'comment_disabled':False,'duet_disabled':False,'stitch_disabled':False}
    return d,a,Context('tiktok','open1','secret',lambda:None,lambda:None)

class TikTokPublicationTests(unittest.TestCase):
    def test_changed_creator_snapshot_stops_before_upload_initialization(self):
        d,a,c=fixture();changed={**a['approved_creator_info'],'creator_username':'different'}
        with patch.object(tt.http,'request',return_value=ok(changed)) as send:
            with self.assertRaisesRegex(Invalid,'creator options changed'):tt.create(d,a,c)
        self.assertEqual(send.call_count,1)
        self.assertIn('creator_info',send.call_args.args[2])

    def test_create_upload_status_and_private_visibility(self):
        d,a,c=fixture(); info={'creator_username':'creator','creator_nickname':'Creator','privacy_level_options':['SELF_ONLY'],'max_video_post_duration_sec':60,'comment_disabled':False,'duet_disabled':False,'stitch_disabled':False}
        init={'publish_id':'v_pub_file~1','upload_url':'https://open-upload.tiktokapis.com/video/?upload_id=secret'}
        with patch.object(tt.http,'request',side_effect=[ok(info),ok(init)]): state=tt.create(d,a,c)
        self.assertEqual(state['status'],'CREATED')
        with patch.object(tt.http,'upload',return_value=response(status=201)) as send: state=tt.upload(d,a,state,c)
        self.assertEqual(send.call_args.kwargs['content_range'],'bytes 0-2/3')
        with patch.object(tt.http,'request',return_value=ok({'status':'PUBLISH_COMPLETE','publicaly_available_post_id':[]})):
            state=tt.read(d,state,c)
        self.assertEqual(state['observation']['visibility'],'NOT_PUBLICLY_CONFIRMED')

    def test_unauthorized_privacy_or_duration_stops_before_init(self):
        d,a,c=fixture(); info={'creator_username':'creator','creator_nickname':'Creator','privacy_level_options':['SELF_ONLY'],'max_video_post_duration_sec':20,'comment_disabled':False,'duet_disabled':False,'stitch_disabled':False}
        with patch.object(tt.http,'request',return_value=ok(info)) as call:
            with self.assertRaises(Invalid): tt.create(d,a,c)
        self.assertEqual(call.call_count,1)

    def test_chunk_plan_bounds(self):
        self.assertEqual(tt.chunk_plan(4_000_000),(4_000_000,1))
        size,count=tt.chunk_plan(70_000_000)
        self.assertGreaterEqual(size,5_000_000); self.assertLessEqual(size,64_000_000)
        self.assertEqual(count,70_000_000//size)
        with self.assertRaises(Invalid): tt.chunk_plan(4_000_000_001)

    def test_public_post_id_and_ambiguous_status(self):
        d,a,c=fixture(); state={'asset_id':'v_pub_file~1','session':{'bytes':3,'offset':0},'remote_id':None}
        with patch.object(tt.http,'request',return_value=ok({'status':'PUBLISH_COMPLETE','publicaly_available_post_id':[987654321012345678]})):
            result=tt.read(d,state,c)
        self.assertEqual(result['remote_id'],'987654321012345678')
        self.assertEqual(result['observation']['visibility'],'PUBLIC_CONFIRMED')
        with patch.object(tt.http,'request',return_value=ok({'status':'UNRECOGNIZED'})):
            with self.assertRaises(Invalid): tt.read(d,state,c)

    def test_missing_id_or_destination_prevents_provider_call(self):
        d,a,c=fixture()
        with patch.object(tt.http,'request') as call:
            with self.assertRaises(Invalid): tt.read(d,{'asset_id':None},c)
            with self.assertRaises(Invalid): tt.create(d,a,Context('tiktok','other','secret',lambda:None,lambda:None))
            call.assert_not_called()

    def test_only_one_chunk_sent_and_lost_response_requires_status_read(self):
        d,a,c=fixture(); total=20_000_001; a={**a,'raw':b'x'*total,'bytes':total}
        state={'asset_id':'v_pub_file~1','session':{'url':'https://open-upload.tiktokapis.com/video/?upload_id=x',
               'bytes':total,'chunk_size':10_000_000,'count':2,'offset':0}}
        with patch.object(tt.http,'upload',return_value=response(status=206)) as send:
            result=tt.upload(d,a,state,c)
        self.assertEqual(send.call_count,1)
        self.assertEqual(result['session']['offset'],10_000_000)
        self.assertEqual(send.call_args.kwargs['content_range'],f'bytes 0-9999999/{total}')
        with patch.object(tt.http,'request',return_value=ok({'status':'PROCESSING_UPLOAD','uploaded_bytes':10_000_000})):
            result=tt.read(d,state,c)
        self.assertEqual(result['session']['offset'],10_000_000)

    def test_real_transport_accepts_fixed_urls_and_no_upload_bearer(self):
        d,a,c=fixture(); info={'creator_username':'creator','creator_nickname':'Creator','privacy_level_options':['SELF_ONLY'],
          'max_video_post_duration_sec':60,'comment_disabled':False,'duet_disabled':False,'stitch_disabled':False}
        init={'publish_id':'v_pub_file~1','upload_url':'https://open-upload.tiktokapis.com/video/?upload_id=test'}
        with patch.object(tt.http,'_exchange',side_effect=[ok(info),ok(init),response(status=201)]) as exchange:
            state=tt.create(d,a,c); tt.upload(d,a,state,c)
        self.assertNotIn('Authorization',exchange.call_args.args[5])
