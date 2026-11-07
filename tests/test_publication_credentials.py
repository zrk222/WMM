import unittest
from types import SimpleNamespace
from unittest.mock import patch
from mission_control.common import Invalid
from mission_control import publication_credentials as pc
from mission_control.publication_transport import Context
from mission_control.social_profiles import Identity


class MeterResponse:
 def __init__(self,raw=b'{"sub":"person","name":"Person"}'):
  self.raw=raw;self.status=200
 def getheaders(self):return [('Content-Length',str(len(self.raw))),('Content-Type','application/json')]
 def read1(self,size):part=self.raw[:size];self.raw=self.raw[size:];return part


class MeterWire:
 def __init__(self,*args):self.stream_socket=self;self.response=MeterResponse()
 def settimeout(self,value):pass
 def request(self,*args,**kwargs):pass
 def getresponse(self):return self.response
 def close(self):pass

class FakeConnections:
 def __init__(self,store):self.row=store.row;self.setup=store.setup;self.secrets=store.secrets;self.expired=store.expired
 def get(self,app,identity):
  if app!=self.row['app_id'] or identity!=self.row['id']:raise Invalid('missing')
  return self.row
 def alive(self,row):
  if self.expired or row['status']!='CONNECTED_READ_TESTED':raise Invalid('expired')

class CredentialsTests(unittest.TestCase):
 def setUp(self):
  self.required='w_member_social';self.cfg={'provider':'linkedin','scopes':['openid','profile',self.required],'campaign_access':'publish'}
  self.row={'app_id':'app','id':'connection','provider':'linkedin','version':3,'config_version':2,'status':'CONNECTED_READ_TESTED','subject_id':'person','secret_ref':'grant','data':{'facts':{'reported_scopes':['openid','profile',self.required]},'identity':{'permissions':['openid','profile',self.required]},'destination':{'id':'person'}}}
  self.configrow={'version':2,'status':'CONFIGURED_UNTESTED','data':self.cfg,'secret_ref':'client'}
  self.setup=SimpleNamespace(get=lambda a,p:self.configrow);self.secrets=SimpleNamespace(load=lambda a,p,r:{'client_secret':'client-secret'} if r=='client' else {'access_token':'private-token'})
  self.store=SimpleNamespace(row=self.row,setup=self.setup,secrets=self.secrets,expired=False)
  self.draft={'app_id':'app','connection_id':'connection','connection_version':3,'provider':'linkedin','destination_id':'person'}
  self.charges=0;self.beats=0
  self.p=patch.object(pc,'Connections',FakeConnections);self.p.start();self.addCleanup(self.p.stop)
 def charge(self):self.charges+=1
 def beat(self):self.beats+=1
 def verify(self,config,secret,grant,alive):
  alive();return SimpleNamespace(subject_id='person',destinations=[{'id':'person'}],permissions=['openid','profile',self.required])
 def test_linkedin_fresh_identity_and_private_context(self):
  with patch.object(pc,'verify',side_effect=self.verify) as verify:
   ctx=pc.context(self.store,'app',self.draft,self.charge,self.beat)
  self.assertIsInstance(ctx,Context);self.assertEqual(self.charges,0);self.assertEqual(verify.call_count,1);self.assertGreaterEqual(self.beats,1);self.assertNotIn('private-token',repr(ctx))
 def test_local_and_foreign_rejections(self):
  for change in ({'provider':'youtube'},{'destination_id':'other'},{'connection_version':2}):
   with self.assertRaises(Invalid):pc.context(self.store,'app',{**self.draft,**change},self.charge,self.beat)
  self.store.expired=True
  with self.assertRaises(Invalid):pc.context(self.store,'app',self.draft,self.charge,self.beat)
  self.assertEqual(self.charges,0)
 def test_partial_scope_and_changed_subject(self):
  self.row['data']['facts']['reported_scopes']=['openid']
  with self.assertRaises(Invalid):pc.context(self.store,'app',self.draft,self.charge,self.beat)
  self.row['data']['facts']['reported_scopes']=['openid','profile',self.required]
  with patch.object(pc,'verify',return_value=SimpleNamespace(subject_id='foreign',destinations=[{'id':'person'}],permissions=[self.required])):
   with self.assertRaises(Invalid):pc.context(self.store,'app',self.draft,self.charge,self.beat)
  self.assertEqual(self.charges,0)
 def test_instagram_link_and_public_inspect(self):
  self.row.update(provider='facebook',subject_id='user');self.row['data']={'identity':{'permissions':['instagram_basic','instagram_content_publish']},'destination':{'id':'123','kind':'PAGE'}}
  self.cfg={'provider':'facebook','scopes':['public_profile','pages_show_list','pages_read_engagement','instagram_basic','instagram_content_publish'],'campaign_access':'instagram_publish'};self.configrow['data']=self.cfg
  self.secrets.load=lambda a,p,r:{'client_secret':'client-secret'} if r=='client' else {'page_token':'page-secret'}
  d={**self.draft,'provider':'instagram','destination_id':'456'}
  def read(provider,operation,values,bearer,alive):
   alive();self.assertEqual((provider,operation,values['account'],bearer),('facebook','instagram_account','123','page-secret'));return {'id':'123','instagram_business_account':{'id':'456','username':'creator'}}
  with patch.object(pc,'request',side_effect=read) as read_mock:
   ctx=pc.context(self.store,'app',d,self.charge,self.beat);self.assertEqual(ctx.login_family,'facebook');self.assertNotIn('page-secret',repr(ctx))
   info=pc.inspect_instagram(self.store,'app','connection',3,self.charge,self.beat)
  self.assertEqual(info['destination_id'],'456');self.assertNotIn('page-secret',str(info));self.assertEqual(read_mock.call_count,2);self.assertEqual(self.charges,0)
  self.row['data']['identity']['permissions']=['instagram_basic']
  with self.assertRaises(Invalid):pc.context(self.store,'app',d,self.charge,self.beat)
  self.row['data']['identity']['permissions']=['instagram_basic','instagram_content_publish']
  with patch.object(pc,'request',return_value={'id':'123','instagram_business_account':{'id':'999','username':'x'}}):
   with self.assertRaises(Invalid):pc.context(self.store,'app',d,self.charge,self.beat)

 def test_two_provider_reads_charge_twice_but_heartbeats_do_not(self):
  from mission_control import social_transport
  def verify_two_reads(config,secret,grant,alive):
   first=pc.request('linkedin','identity',bearer='synthetic-access',alive=alive)
   alive()
   second=pc.request('linkedin','identity',bearer='synthetic-access',alive=alive)
   return Identity(first['sub'],first['name'],[{'id':second['sub']}],['w_member_social'])
  with patch('mission_control.social_transport.PinnedHTTPS',MeterWire), \
       patch('mission_control.social_transport.address',return_value='203.0.113.9'), \
       patch('mission_control.social_transport.trust_context',return_value=object()), \
       patch.object(pc,'verify',side_effect=verify_two_reads):
   pc.context(self.store,'app',self.draft,self.charge,self.beat)
  self.assertEqual(self.charges,2)
  self.assertGreater(self.beats,2)

if __name__=='__main__':unittest.main()
