"""Receipt-backed private reports using real SQLite and synthetic provider state."""
import json,unittest
from unittest.mock import patch
from types import SimpleNamespace
from mission_control.common import Invalid,canonical,uid
from mission_control.db import connection
from mission_control import publication_reports as reports
from tests import test_publication_execution as execution
from tests import test_publication_authority as authority
APP=authority.APP

class PublicationReportTests(unittest.TestCase):
 setUp=authority.PublicationAuthorityTests.setUp
 call=authority.PublicationAuthorityTests.call
 prepare=authority.PublicationAuthorityTests.prepare
 activate=authority.PublicationAuthorityTests.activate
 leased=execution.PublicationExecutionTests.leased
 context=execution.PublicationExecutionTests.context
 state=execution.PublicationExecutionTests.state
 run_step=execution.PublicationExecutionTests.run_step
 def read(self,item):return self.call('publication.get',{'id':item['id']},lambda:reports.report(self.store,APP,item['id']))
 def test_prepared_report_and_unknown_attribution(self):
  item=self.prepare();result=self.read(item);r=result['report']
  self.assertEqual(result['id'],item['id']);self.assertEqual(r['channel']['destination_id'],'profile1');self.assertEqual(r['content']['rights_hashes'],self.draft['rights_hashes'])
  self.assertIsNone(r['latest_metrics']);self.assertIsNone(r['attribution']['installs']);self.assertIsNone(r['attribution']['revenue']);self.assertEqual(r['events'],[])
  self.assertEqual(r['latest_metric_sample'],{'receipt_hash':None,'observed_at':None,'metrics':None,'reason':'NO_PROVIDER_READ_RECORDED'})
  self.assertNotIn('fixture-secret',canonical(result));self.assertEqual(r['public_visibility'],'NOT_INDEPENDENTLY_VERIFIED')
 def test_receipts_and_chain_tampering(self):
  item,job=self.leased();vault=execution.Vault()
  with patch('mission_control.publication_sessions.Vault',return_value=vault):
   observed=self.state('READY_TO_PUBLISH');observed['observation']['metrics']={'source':'fixture','counts':{'views':None}}
   self.run_step(job,SimpleNamespace(create=lambda *a:observed))
   result=self.read(item);r=result['report'];self.assertEqual(r['intent']['status'],'READY_TO_PUBLISH');self.assertEqual(r['events'][-1]['hash'],r['intent']['receipt_hash']);self.assertEqual(r['events'][1]['previous_hash'],r['events'][0]['hash']);self.assertIsNone(r['latest_metrics']['counts']['views']);self.assertNotIn('session',canonical(r))
  with connection(self.store.path) as db:
   db.execute('DROP TRIGGER publication_event_no_update');db.execute("UPDATE publication_events SET previous_hash='bad' WHERE intent_id=? AND sequence=2",(item['id'],))
  with self.assertRaises(Invalid):self.read(item)
 def test_source_tamper_and_foreign_scope_rejected(self):
  item=self.prepare()
  with self.assertRaises((Invalid,PermissionError)):self.call('publication.get',{'id':uid()},lambda:reports.report(self.store,APP,uid()))
  with self.assertRaises((Invalid,PermissionError)):self.call('publication.get',{'id':item['id']},lambda:reports.report(self.store,'another-app',item['id']))
  with connection(self.store.path) as db:
   db.execute('DROP TRIGGER publication_authority_no_rewrite');row=db.execute('SELECT draft FROM publication_authorities WHERE id=?',(item['id'],)).fetchone();draft=json.loads(row['draft']);draft['rights_hashes']=['a'*64];db.execute('UPDATE publication_authorities SET draft=? WHERE id=?',(canonical(draft),item['id']))
  with self.assertRaises(Invalid):self.read(item)
 def test_historical_metrics_survive_subsequent_reads_and_session_retirement(self):
  item,job=self.leased();vault=execution.Vault()
  with patch('mission_control.publication_sessions.Vault',return_value=vault):
   self.run_step(job,SimpleNamespace(create=lambda *a:self.state('READY_TO_PUBLISH')))
   self.run_step(job,SimpleNamespace(publish=lambda *a:self.state('PUBLISH_ACKNOWLEDGED','urn:li:share:123')))
   for count in (10,20):
    state=self.state('PUBLISHED','urn:li:share:123');state['observation']['metrics']={'source':'fixture.provider.read','observed_at':str(count),'counts':{'views':count,'likes':None}}
    self.run_step(job,SimpleNamespace(read=lambda *a:state))
   report=self.read(item)['report'];history=report['metric_history']
   self.assertEqual([sample['metrics']['counts']['views'] for sample in history],[10,20])
   self.assertIsNone(history[0]['metrics']['counts']['likes'])
   self.assertNotEqual(history[0]['receipt_hash'],history[1]['receipt_hash'])
   self.assertEqual(report['latest_metrics']['counts']['views'],20)
   self.assertEqual(report['latest_metric_sample'],history[-1])
   self.run_step(job,SimpleNamespace(read=lambda *a:self.state('PUBLISHED','urn:li:share:123')))
   report=self.read(item)['report'];history=report['metric_history'];event=report['events'][-1]
   self.assertEqual([sample['metrics']['counts']['views'] for sample in history[:2]],[10,20])
   self.assertIsNone(report['latest_metrics'])
   self.assertEqual(report['latest_metric_sample'],history[-1])
   self.assertEqual(history[-1],{'receipt_hash':event['hash'],'observed_at':event['observed_at'],
                                 'metrics':None,'reason':'PROVIDER_READ_RETURNED_NO_METRICS'})
   self.assertTrue(event['observed_at'])

if __name__=='__main__':unittest.main()
