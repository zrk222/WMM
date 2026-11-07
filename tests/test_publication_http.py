import contextlib,unittest,uuid
from types import SimpleNamespace
from unittest.mock import patch
from mission_control.common import Invalid
from mission_control import publication_http as http,publication_service as service

class Headers:
 def __init__(self,values):self.values=values
 def get_all(self,key):return self.values.get(key)
class Handler:
 def __init__(self,method,path,origin=True,auth=False):
  self.command=method;self.path=path;self.server=SimpleNamespace(server_port=8765,service=SimpleNamespace(store=object()),identities=SimpleNamespace(fresh=lambda s:{'principal':'owner'}))
  self.headers=Headers({'Host':['127.0.0.1:8765'],'Origin':['http://127.0.0.1:8765'] if origin else None,'Authorization':['Bearer agent'] if auth else None})
 def session(self):return 'session'
 def send(self,status,result):return status,result

@contextlib.contextmanager
def bound(*args):yield

class PublicationHttpTests(unittest.TestCase):
 def test_owner_get_report_uses_canonical_read_only_publication_get_envelope(self):
  identity=str(uuid.uuid4());path='/api/apps/app/publications/'+identity;seen=[]
  def binding(store,envelope,*args):seen.append(envelope);return bound()
  with patch.object(http,'singleton',side_effect=AssertionError('GET must not check POST CSRF')),\
       patch.object(http,'bound_owner',side_effect=binding),patch.object(http,'protected',side_effect=lambda *args:bound()),\
       patch('mission_control.publication_reports.report',return_value={'id':identity,'app_id':'app','report':{}}):
   result=http.route(Handler('GET',path),path.strip('/').split('/'))
  self.assertEqual(result,(200,{'id':identity,'app_id':'app','report':{}}))
  self.assertEqual(seen,[{'app_id':'app','operation':'publication.get','input':{'id':identity}}])

 def test_publication_list_keeps_worker_queue_and_provider_phase_separate(self):
  authority_row={'id':'authority-one'};schedule_row={'schedule_status':'QUEUED','job_id':'job-one','job_status':'QUEUED','due':1790000000.0,'next_due':1790003600.0}
  class DB:
   query=''
   def execute(self,query,*args):self.query=query;return self
   def fetchall(self):return [authority_row] if 'publication_authorities' in self.query else []
   def fetchone(self):return schedule_row if 'publication_schedules' in self.query else None
  @contextlib.contextmanager
  def db(*args):yield DB()
  class Saved:
   def __init__(self,*args):pass
   def view(self,app):return {'accounts':[]}
  class Renders:
   def __init__(self,*args):pass
   def list(self,app):return {'items':[]}
  intent={'authority_id':'authority-one','status':'CREATED'}
  with patch.object(service,'_owner',return_value=(None,'owner')),patch.object(service,'connection',db),\
       patch('mission_control.social_connections.Connections',Saved),patch('mission_control.hypit_jobs.HypitRenders',Renders),\
       patch.object(service,'Publications'),patch('mission_control.publication_schedule.initialize'),\
       patch.object(service,'_row',return_value=({'id':'authority-one','status':'APPROVED'}, {'provider':'linkedin'},None)),\
       patch.object(service,'_view',return_value={'id':'authority-one','status':'APPROVED'}),\
       patch('mission_control.publication_execution.list_intents',return_value=[intent]):
   result=service.list_publications(SimpleNamespace(path='fake'),'app')
  item=result['authorities'][0]
  self.assertEqual(item['status'],'APPROVED')
  self.assertEqual(item['schedule'],{'status':'QUEUED','job_id':'job-one','job_status':'QUEUED','due':1790000000.0,'next_due':1790003600.0,'provider_status':'CREATED'})

 def test_publication_list_separates_channel_catalog_from_saved_accounts(self):
  class DB:
   def execute(self,*args):return self
   def fetchall(self):return []
  @contextlib.contextmanager
  def db(*args):yield DB()
  class Saved:
   def __init__(self,*args):pass
   def view(self,app):return {'accounts':[{'id':'connection','provider':'youtube','version':2,'status':'CONNECTED_READ_TESTED','data':{}}]}
  class Renders:
   def __init__(self,*args):pass
   def list(self,app):return {'items':[]}
  with patch.object(service,'_owner',return_value=(None,'owner')),patch.object(service,'connection',db),\
       patch('mission_control.social_connections.Connections',Saved),patch('mission_control.hypit_jobs.HypitRenders',Renders),\
       patch.object(service,'Publications'),patch('mission_control.publication_schedule.initialize'),patch('mission_control.publication_execution.list_intents',return_value=[]):
   result=service.list_publications(SimpleNamespace(path='fake'),'app')
  self.assertEqual({row['provider'] for row in result['channels']},{'instagram','tiktok','youtube','linkedin'})
  self.assertTrue(all('name' in row and 'kinds' in row for row in result['channels']))
  self.assertEqual(result['accounts'][0]['id'],'connection')

 def test_preflight_closed_payload_no_forged_info(self):
  with self.assertRaises(Invalid):service.dispatch(object(),'app','preflight',{'connection_id':'x','connection_version':1,'destination_id':'y','info':{'privacy_level_options':['PUBLIC_TO_EVERYONE']}})
 def test_exact_owner_admission_and_agent_denial(self):
  body={'connection_id':'id','connection_version':1,'destination_id':'ig'};seen=[]
  def binding(store,envelope,*args):seen.append(envelope);return bound()
  path='/api/apps/app/publications/preflight';h=Handler('POST',path)
  with patch.object(http,'json_body',return_value=body),patch.object(http,'singleton',return_value='session'),patch.object(http,'bound_owner',side_effect=binding),patch.object(http,'protected',side_effect=lambda *a:bound()),patch.object(http,'dispatch',return_value={'ok':True}):
   self.assertEqual(http.route(h,path.strip('/').split('/')),(200,{'ok':True}))
   self.assertEqual(seen[0],{'app_id':'app','operation':'publication.preflight','input':body})
   with self.assertRaises(PermissionError):http.route(Handler('POST',path,auth=True),path.strip('/').split('/'))
   with self.assertRaises(PermissionError):http.route(Handler('POST',path,origin=False),path.strip('/').split('/'))
   with self.assertRaises(Invalid):http.route(Handler('POST',path+'?x=1'),path.strip('/').split('/'))
 def test_activate_and_reconcile_binding(self):
  identity=str(uuid.uuid4());path='/api/apps/app/publications/'+identity+'/activate';body={'review_hash':'h'};seen=[]
  def binding(store,envelope,*args):seen.append(envelope);return bound()
  with patch.object(http,'json_body',return_value=body),patch.object(http,'singleton',return_value='session'),patch.object(http,'bound_owner',side_effect=binding),patch.object(http,'protected',side_effect=lambda *a:bound()),patch.object(http,'dispatch',return_value={}):
   http.route(Handler('POST',path),path.strip('/').split('/'))
  self.assertEqual(seen[0]['input'],{'id':identity,'body':body})
 def test_draft_server_supplies_binding(self):
  class DB:
   def execute(self,*args):return self
   def fetchone(self):return {'version':7}
  @contextlib.contextmanager
  def db(*a):yield DB()
  body={'provider':'linkedin','kind':'linkedin_text','connection_id':str(uuid.uuid4()),'connection_version':1,'destination_id':'person','title':'','caption':'Hello','link':None,'artifact_id':None,'settings':{'visibility':'PUBLIC'}}
  with patch.object(service,'_owner'),patch.object(service,'connection',db):
   draft=service.draft(SimpleNamespace(path='fake'),'app',body)['draft']
  self.assertEqual(draft['manifest_version'],7);self.assertEqual(draft['app_id'],'app');self.assertIsNone(draft['artifact']);self.assertEqual(len(draft['rights_hashes']),1)
  with patch.object(service,'_owner'),self.assertRaises(Invalid):service.draft(object(),'app',{**body,'rights_hashes':['forged']})

if __name__=='__main__':unittest.main()
