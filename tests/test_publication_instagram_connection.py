import unittest
from types import SimpleNamespace
from unittest.mock import patch
from mission_control.common import Invalid
from mission_control import publication_instagram_connection as ig

class InstagramConnectionTests(unittest.TestCase):
 def setUp(self):
  self.draft={'app_id':'app','connection_id':'id','connection_version':2,'provider':'instagram','destination_id':'456'}
  self.row={'app_id':'app','id':'id','version':2,'provider':'facebook','status':'CONNECTED_READ_TESTED','lease':None,'expires':None,'data':{'destination':{'id':'123','kind':'PAGE'},'identity':{'permissions':['instagram_basic','instagram_content_publish']}}}
 def test_local_binding(self):
  self.assertEqual(ig.assert_saved_connection(self.row,self.draft),'123')
  for change in ({'version':3},{'provider':'instagram'},{'status':'DISCONNECTED'}):
   with self.assertRaises(Invalid):ig.assert_saved_connection({**self.row,**change},self.draft)
  with self.assertRaises(Invalid):ig.assert_saved_connection(self.row,{**self.draft,'connection_version':3})
 def test_live_read_fixtures(self):
  cfg={'provider':'facebook','scopes':['instagram_basic','instagram_content_publish']}; creds={'access_token':'user-token','page_token':'page-token'}
  ident=SimpleNamespace(permissions=['instagram_basic','instagram_content_publish'],destinations=[{'id':'123'}])
  with patch.object(ig,'facebook',return_value=ident),patch.object(ig,'selected_page',return_value=({'id':'123'},'page-token')),patch.object(ig,'request',return_value={'id':'123','instagram_business_account':{'id':'456','username':'example'}}) as call:
   result,token=ig.inspect(cfg,'client-secret',creds,'123','456'); self.assertEqual(result,{'id':'456','username':'example','page_id':'123'});self.assertEqual(token,'page-token')
   self.assertEqual(call.call_args.args[:2],('facebook','instagram_account'))
   with self.assertRaises(Invalid):ig.inspect(cfg,'client-secret',creds,'123','999')
   with self.assertRaises(Invalid):ig.inspect(cfg,'client-secret',creds,'../123','456')

if __name__=='__main__':unittest.main()
