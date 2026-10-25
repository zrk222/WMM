"""Real immutable app/creative/cohort binding and transactional observation persistence."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from mission_control.common import Invalid,canonical,digest
from mission_control.db import connection
from mission_control.store import Store
from mission_control.ledger import Ledger
from mission_control.funnel_store import Funnels
from tests.test_creative_rendering import prepared_render
from tests.test_funnel_contract import fixture,observed
from tests.test_ledger import cohort

APP='sample-one'


class FunnelStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'state.sqlite';self.store=Store(self.path,seed=False)
        self.store.save_app('sample-two',dict(name='Other app',release='build-1',locale='en-US',currency='USD'))
        brief,_=prepared_render(self.store,APP)
        app=self.store.app(APP);self.version=app['version'];self.plan=fixture()
        for key in ('release','locale','currency'):self.plan[key]=app['data'][key]
        self.plan['creative_refs']=[dict(kind='CREATIVE_BRIEF',id=brief['id'],version=brief['version'],sha256=brief['hash'])]
        Ledger(self.path).define(APP,cohort(cohort_id=self.plan['cohort_id'],release=self.plan['release'],locale=self.plan['locale'],currency=self.plan['currency'],starts_at=self.plan['attribution']['starts_at'],ends_at=self.plan['attribution']['ends_at'],matures_at='2026-11-01T00:00:00+00:00'))
        self.flow=Funnels(self.store)

    def body(self):
        return dict(id='app-sales-one',manifest_version=self.version,data=self.plan)

    def import_body(self,saved,values):
        return dict(funnel_id=saved['id'],funnel_hash=saved['hash'],manifest_version=self.version,observations=values)

    def test_bounded_pages_preserve_all_definitions_and_report_observations_after_first_page(self):
        saved=self.flow.save(APP,self.body())
        for i in range(100):self.flow.save(APP,dict(self.body(),id='page-'+str(i).zfill(3)))
        first=self.flow.list(APP);last=self.flow.list(APP,first['next_offset'])
        self.assertEqual((len(first['items']),len(last['items']),first['total'],last['next_offset']),(100,1,101,None))
        self.assertTrue(all('data' not in row for row in first['items']))
        values=[dict(observed(self.plan),event_id='page-'+str(i).zfill(3))for i in range(101)]
        values[-1].update(count=42,observed_at='2026-10-04T00:00:00+00:00')
        self.flow.ingest(APP,self.import_body(saved,values))
        first=self.flow.observations(APP,saved['id']);last=self.flow.observations(APP,saved['id'],100)
        self.assertEqual((len(first['items']),first['next_offset'],len(last['items']),last['total']),(100,100,1,101))
        self.assertEqual(last['items'][0]['data']['observation']['count'],42)
        self.assertEqual(self.flow.report(APP,saved['id'])['stages'][0]['count'],42)
        for value in (-1,True,10001):
            with self.subTest(value=value),self.assertRaises(Invalid):self.flow.list(APP,value)

    def test_real_sources_definition_replay_observed_zero_restart_and_no_payment_duplication(self):
        saved=self.flow.save(APP,self.body())
        self.assertEqual(self.flow.save(APP,self.body()),saved)
        self.assertEqual(saved['data']['sources'],self.plan['creative_refs'])
        value=observed(self.plan)
        self.assertEqual(self.flow.ingest(APP,self.import_body(saved,[value]))['inserted'],1)
        self.assertEqual(self.flow.ingest(APP,self.import_body(saved,[value]))['duplicates'],1)
        restarted=Funnels(Store(self.path))
        self.assertEqual(restarted.list(APP)['items'][0]['source_status'],'CURRENT')
        self.assertEqual(restarted.observations(APP,saved['id'])['items'][0]['data']['observation']['count'],0)
        with connection(self.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM growth_events WHERE app_id=?',(APP,)).fetchone()[0],0)

    def test_conflicting_batch_rolls_back_and_immutable_definition_rejects_overwrite(self):
        saved=self.flow.save(APP,self.body());first=observed(self.plan)
        self.flow.ingest(APP,self.import_body(saved,[first]))
        second=dict(first,event_id='second-event',count=2)
        with self.assertRaises(Invalid):self.flow.ingest(APP,self.import_body(saved,[second,dict(first,count=1)]))
        self.assertEqual(len(self.flow.observations(APP,saved['id'])['items']),1)
        with self.assertRaises(Invalid):self.flow.save(APP,dict(self.body(),data=dict(self.plan,hook='Different hypothesis')))

    def test_foreign_app_stale_manifest_and_changed_source_hash_are_rejected(self):
        with self.assertRaises(Invalid):self.flow.save('sample-two',self.body())
        with self.assertRaises(Invalid):self.flow.save(APP,dict(self.body(),manifest_version=self.version+1))
        saved=self.flow.save(APP,self.body())
        with connection(self.path) as db:
            db.execute("UPDATE creative_briefs SET hash=? WHERE app_id=? AND id=?",('0'*64,APP,self.plan['creative_refs'][0]['id']))
        self.assertEqual(self.flow.list(APP)['items'][0]['source_status'],'SOURCE_REVIEW_NEEDED')
        with self.assertRaises(Invalid):self.flow.ingest(APP,self.import_body(saved,[observed(self.plan)]))
        with self.assertRaises(Invalid):self.flow.observations('sample-two',saved['id'])

    def test_cohort_window_and_changed_app_context_are_not_silently_rebound(self):
        wrong=deepcopy(self.plan);wrong['attribution']['ends_at']='2026-10-03T00:00:00+00:00'
        with self.assertRaises(Invalid):self.flow.save(APP,dict(self.body(),data=wrong))
        saved=self.flow.save(APP,self.body());app=self.store.app(APP)
        self.store.save_app(APP,dict(app['data'],release='changed'),app['version'])
        self.assertEqual(self.flow.list(APP)['items'][0]['source_status'],'SOURCE_REVIEW_NEEDED')
        with self.assertRaises(Invalid):self.flow.ingest(APP,self.import_body(saved,[observed(self.plan)]))

    def test_report_reuses_existing_ledger_and_preserves_missing_upstream_counts(self):
        saved=self.flow.save(APP,self.body())
        result=self.flow.report(APP,saved['id'])
        self.assertEqual(result['cohort_id'],self.plan['cohort_id'])
        self.assertEqual(result['subscription_ledger']['cohort']['cohort_id'],self.plan['cohort_id'])
        self.assertTrue(all(row['count'] is None for row in result['stages']))
        self.assertFalse(result['execution_authority'])

    def test_app_context_cohort_binding_creative_binding_and_source_bindings_use_actual_records(self):
        from mission_control.funnel_store import app_context,cohort_binding,creative_binding,source_bindings
        from datetime import datetime,timezone
        with connection(self.path) as db:
            app=app_context(db,APP,self.version)
            self.assertEqual(cohort_binding(db,APP,self.plan,app)['id'],self.plan['cohort_id'])
            self.assertEqual(creative_binding(db,self.store,APP,self.plan['creative_refs'][0]),self.plan['creative_refs'][0])
            self.assertEqual(source_bindings(db,self.store,APP,self.plan,datetime.now(timezone.utc)),self.plan['creative_refs'])
            with self.assertRaises(Invalid):app_context(db,APP,True)
            with self.assertRaises(Invalid):creative_binding(db,self.store,APP,dict(self.plan['creative_refs'][0],version=999))

    def test_research_binding_requires_current_app_and_available_customer_sources(self):
        from mission_control.funnel_store import research_binding
        from mission_control.customer_workflow_store import CustomerWorkflows
        from tests.test_customer_workflow import proposal
        from datetime import datetime,timezone
        value=proposal()
        for key in ('release','locale','currency'):value[key]=self.plan[key]
        saved=CustomerWorkflows(self.store).save(APP,dict(id='pain-evidence',manifest_version=self.version,data=value))
        ref=dict(kind='CUSTOMER_WORKFLOW',id=saved['id'],version=1,sha256=saved['hash'])
        with connection(self.path) as db:
            self.assertEqual(research_binding(db,APP,ref,datetime(2026,10,25,tzinfo=timezone.utc)),ref)
            with self.assertRaises(Invalid):research_binding(db,APP,ref,datetime(2027,1,1,tzinfo=timezone.utc))
            with self.assertRaises(Invalid):research_binding(db,APP,dict(ref,sha256='0'*64),datetime(2026,10,25,tzinfo=timezone.utc))

    def test_report_keeps_real_refund_adjusted_ledger_proceeds_without_second_subtraction(self):
        from tests.test_ledger import event
        saved=self.flow.save(APP,self.body())
        ledger=Ledger(self.path)
        ledger.ingest(APP,dict(cohort_id=self.plan['cohort_id'],events=[
            event('install','INSTALL',day='2026-10-01'),
            event('charge','PURCHASE',day='2026-10-01',amount=2000),
            event('refund','REFUND',day='2026-10-02',amount=500,related='charge')]))
        result=self.flow.report(APP,saved['id'])
        self.assertEqual(result['subscription_ledger']['net_proceeds_minor'],1500)
        self.assertEqual(result['subscription_ledger']['refunds_minor'],500)
        with connection(self.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM growth_events WHERE app_id=?',(APP,)).fetchone()[0],3)

    def test_oversized_import_and_corrupt_definition_preserve_saved_history(self):
        saved=self.flow.save(APP,self.body())
        with self.assertRaises(Invalid):self.flow.ingest(APP,self.import_body(saved,[observed(self.plan)]*501))
        self.assertEqual(self.flow.observations(APP,saved['id'])['items'],[])
        with connection(self.path) as db:
            db.execute('UPDATE growth_funnels SET hash=? WHERE app_id=? AND id=?',('0'*64,APP,saved['id']))
        with self.assertRaises(Invalid):self.flow.list(APP)
