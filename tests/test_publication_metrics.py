import unittest
from unittest.mock import patch
from mission_control.common import Invalid
from mission_control.publication_transport import Context,Response
from mission_control import publication_youtube as yt,publication_meta as ig,publication_tiktok as tt

class MetricReadTests(unittest.TestCase):
 def setUp(self):
  self.yc=Context('youtube','channel','token',lambda:None,lambda:None)
  self.ic=Context('instagram','123','token',lambda:None,lambda:None,login_family='facebook')
  self.tc=Context('tiktok','creator','token',lambda:None,lambda:None)
  self.yd={'provider':'youtube','destination_id':'channel','settings':{'privacy_status':'private'}};self.id={'provider':'instagram','kind':'instagram_reel','destination_id':'123','link':None};self.td={'provider':'tiktok','destination_id':'creator'}
 def test_youtube_counts_and_null(self):
  item={'id':'abc','snippet':{'channelId':'channel'},'status':{'privacyStatus':'private'},'processingDetails':{'processingStatus':'succeeded'},'statistics':{'viewCount':'10','likeCount':'0','description':'secret should not leak'}}
  with patch.object(yt.http,'request',return_value=Response(200,{}, {'items':[item]})) as call:
   r=yt.read(self.yd,{'remote_id':'abc'},self.yc); m=r['observation']['metrics']
   self.assertEqual(m['counts'],{'views':10,'likes':0,'comments':None});self.assertNotIn('secret',str(r));self.assertIn('statistics',call.call_args.kwargs['query']['part']);self.assertEqual(r['observation']['privacy_status'],'private')
  for bad in (True,-1,'-1','999999999999999999999','x'):
   item['statistics']['viewCount']=bad
   with patch.object(yt.http,'request',return_value=Response(200,{}, {'items':[item]})),self.assertRaises(Invalid):yt.read(self.yd,{'remote_id':'abc'},self.yc)
 def test_instagram_counts_and_foreign_id(self):
  data={'id':'789','media_type':'VIDEO','like_count':3,'comments_count':0,'unrelated':'private'}
  with patch.object(ig.http,'request',return_value=Response(200,{},data)) as call:
   r=ig.read(self.id,{'asset_id':'456','remote_id':'789','status':'PUBLISHED'},self.ic)
   self.assertEqual(r['observation']['metrics']['counts'],{'views':None,'likes':3,'comments':0});self.assertNotIn('private',str(r));self.assertIn('like_count',call.call_args.kwargs['query']['fields'])
  for bad in (True,-1,'1',2**53):
   with patch.object(ig.http,'request',return_value=Response(200,{}, {**data,'like_count':bad})),self.assertRaises(Invalid):ig.read(self.id,{'asset_id':'456','remote_id':'789'},self.ic)
  with patch.object(ig.http,'request',return_value=Response(200,{}, {**data,'id':'999'})),self.assertRaises(Invalid):ig.read(self.id,{'asset_id':'456','remote_id':'789'},self.ic)
 def test_tiktok_one_query_and_unknown_counts(self):
  data={'error':{'code':'ok'},'data':{'videos':[{'id':'1234','view_count':20,'like_count':2,'share_count':0,'unused':'private'}]}}
  with patch.object(tt.http,'request',return_value=Response(200,{},data)) as call:
   r=tt.read(self.td,{'asset_id':'publish-id','remote_id':'1234','status':'PUBLISHED'},self.tc)
   self.assertEqual(r['observation']['metrics']['counts'],{'views':20,'likes':2,'comments':None,'shares':0});self.assertNotIn('private',str(r));self.assertEqual(call.call_count,1);self.assertEqual(call.call_args.args[2],'/v2/video/query/')
  for bad in (True,-1,'1',2**53):
   bad_response={'error':{'code':'ok'},'data':{'videos':[{'id':'1234','view_count':bad}]}}
   with patch.object(tt.http,'request',return_value=Response(200,{},bad_response)),self.assertRaises(Invalid):tt.read(self.td,{'asset_id':'publish-id','remote_id':'1234','status':'PUBLISHED'},self.tc)
  foreign={'error':{'code':'ok'},'data':{'videos':[{'id':'999','view_count':10}]}}
  with patch.object(tt.http,'request',return_value=Response(200,{},foreign)),self.assertRaises(Invalid):tt.read(self.td,{'asset_id':'publish-id','remote_id':'1234','status':'PUBLISHED'},self.tc)
  status={'error':{'code':'ok'},'data':{'status':'PUBLISH_COMPLETE','publicaly_available_post_id':[]}}
  with patch.object(tt.http,'request',return_value=Response(200,{},status)):
   r=tt.read(self.td,{'asset_id':'publish-id','status':'PROCESSING'},self.tc)
   self.assertIsNone(r['observation']['metrics']['counts']['views']);self.assertEqual(r['observation']['metrics']['missing'],'VIDEO_QUERY_REQUIRES_ONE_PUBLIC_ID')
  with self.assertRaises(Invalid):tt.read(self.td,{'asset_id':'publish-id','remote_id':'../../secret','status':'PUBLISHED'},self.tc)

if __name__=='__main__':unittest.main()
