"""Actual source joins, bounded coverage, unavailable evidence and restart semantics."""
from datetime import datetime,timezone
from unittest.mock import patch
import unittest
from mission_control.common import Invalid,digest
from mission_control.db import connection
from mission_control.store import Store
from mission_control.funnel_store import Funnels
from mission_control import funnel_founder_review as founder
from tests import test_funnel_store as fixture
from tests.test_funnel_contract import observed

APP='sample-one'


class FunnelFounderTests(unittest.TestCase):
    setUp=fixture.FunnelStoreTests.setUp
    body=fixture.FunnelStoreTests.body
    import_body=fixture.FunnelStoreTests.import_body

    def test_absent_plan_and_existing_review_receipt_are_explicit_without_private_raw_data(self):
        value=founder.review(self.store,APP)
        self.assertEqual(value['coverage'],dict(offset=0,limit=5,evaluated=0,total=0,next_offset=None))
        self.assertEqual(value['findings'][0]['code'],'NO_APP_SALES_PLAN')
        self.assertTrue(value['subscription_review']['source_hash'])
        self.assertFalse(value['execution_authority'])
        self.assertEqual(value['status_scope'],'DISPLAYED_FUNNEL_PAGE_AND_CURRENT_SUBSCRIPTION_REVIEW')
        self.assertEqual(value['source_hash'],digest({k:v for k,v in value.items()if k!='source_hash'}))
        self.assertNotIn('history',value['subscription_review'])
        self.assertNotIn('customer_workflows',value['subscription_review'])

    def test_pages_read_only_selected_five_reports_and_restart_retains_sources(self):
        for i in range(7):self.flow.save(APP,dict(self.body(),id='plan-'+str(i)))
        stamp=datetime.now(timezone.utc)
        # Count actual domain reads, without replacing their results.
        original=Funnels.report
        with patch.object(Funnels,'report',autospec=True,side_effect=lambda obj,*a,**kw:original(obj,*a,**kw))as calls:
            first=founder.review(self.store,APP,clock=lambda:stamp)
            self.assertEqual(calls.call_count,5)
        self.assertEqual([r['id']for r in first['funnels']],['plan-'+str(i)for i in range(5)])
        self.assertEqual(first['coverage']['next_offset'],5)
        last=founder.review(Store(self.path),APP,5,clock=lambda:stamp)
        self.assertEqual([r['id']for r in last['funnels']],['plan-5','plan-6'])
        self.assertEqual(last['coverage']['total'],7)
        self.assertIsNone(last['coverage']['next_offset'])
        self.assertNotIn('net_proceeds_minor',first)
        with connection(self.path)as db:self.assertEqual(db.execute('SELECT count(*) FROM growth_events').fetchone()[0],0)
        for value in (-1,True,10001,8):
            with self.subTest(value=value),self.assertRaises(Invalid):founder.review(self.store,APP,value)

    def test_zero_partial_unknown_and_withheld_comparisons_remain_separate(self):
        saved=self.flow.save(APP,self.body());one=observed(self.plan)
        other=dict(one,event_id='unknown-install',stage_id='install',coverage='UNKNOWN',count=None,unit=self.plan['stages'][1]['unit'],denominator_definition=self.plan['stages'][1]['denominator_definition'])
        self.flow.ingest(APP,self.import_body(saved,[one,other]))
        value=founder.review(self.store,APP)['funnels'][0]
        self.assertEqual([r['count']for r in value['stages']],[0,None])
        self.assertEqual(value['stage_coverage'],dict(OBSERVED=1,UNKNOWN=1))
        self.assertEqual(value['comparisons'],dict(total=1,comparable=0,withheld=1))
        self.assertEqual(value['cohort_id'],self.plan['cohort_id'])
        self.assertEqual(value['currency'],self.plan['currency'])
        self.assertEqual(value['definition_hash'],saved['hash'])

    def test_finding_caps_disclose_remainder_and_never_copy_unreviewed_extra_fields(self):
        values=[dict(id=str(i),area='stage',code='MISSING',next_action='Collect evidence',raw='PRIVATE_EXCERPT')for i in range(101)]
        value=founder.findings(values,100)
        self.assertEqual((value['shown'],value['total'],value['has_more']),(100,101,True))
        self.assertNotIn('PRIVATE',str(value))
        plan=dict(self.plan,stages=[dict(self.plan['stages'][0],id='stage-'+str(i),parents=['stage-'+str(n)for n in range(i)])for i in range(32)])
        self.flow.save(APP,dict(self.body(),data=plan))
        finding=founder.review(self.store,APP)['funnels'][0]['findings']
        self.assertEqual(finding['shown'],20)
        self.assertGreater(finding['total'],20)
        self.assertTrue(finding['has_more'])

    def test_corrupt_source_remains_unavailable_and_stale_app_is_not_silently_rebound(self):
        saved=self.flow.save(APP,self.body())
        with connection(self.path)as db:db.execute('UPDATE growth_funnels SET hash=? WHERE id=?',('0'*64,saved['id']))
        value=founder.review(self.store,APP)
        self.assertEqual(value['status'],'NEEDS_REPAIR')
        self.assertEqual(value['funnels'][0]['state'],'UNAVAILABLE')
        self.assertIsNone(value['funnels'][0]['stages'])
        with connection(self.path)as db:db.execute('UPDATE growth_funnels SET hash=? WHERE id=?',(saved['hash'],saved['id']))
        app=self.store.app(APP);self.store.save_app(APP,dict(app['data'],release='changed'),app['version'])
        row=founder.review(self.store,APP)['funnels'][0]
        self.assertEqual(row['state'],'SOURCE_REVIEW_NEEDED')
        self.assertTrue(any(r['code']=='SOURCE_REVIEW_NEEDED'for r in row['findings']['items']))

    def test_changed_app_during_source_reads_rejects_review_and_permission_errors_propagate(self):
        self.flow.save(APP,self.body());original=founder.entry
        def change(*args):
            row=original(*args);app=self.store.app(APP)
            self.store.save_app(APP,dict(app['data'],job='Changed during review'),app['version']);return row
        with patch.object(founder,'entry',side_effect=change),self.assertRaises(Invalid):founder.review(self.store,APP)
        with patch.object(Funnels,'report',side_effect=PermissionError('Revoked owner')),self.assertRaises(PermissionError):founder.review(self.store,APP)

    def test_unavailable_base_is_named_without_discarding_readable_funnels(self):
        self.flow.save(APP,self.body())
        with patch.object(founder,'review_status',side_effect=Invalid('PRIVATE_DIAGNOSTIC')):value=founder.review(self.store,APP)
        self.assertEqual(value['status'],'NEEDS_REPAIR')
        self.assertEqual(value['subscription_review']['findings']['items'][0]['code'],'BASE_REVIEW_UNAVAILABLE')
        self.assertNotIn('PRIVATE',str(value))
        self.assertEqual(value['funnels'][0]['state'],'CURRENT')

    def test_base_review_and_stage_projection_keep_only_declared_receipts_and_populations(self):
        saved=self.flow.save(APP,self.body());stamp=datetime.now(timezone.utc)
        base=founder.base_review(self.store,self.store.app(APP),stamp)
        self.assertTrue(base['source_hash'])
        self.assertEqual(set(base),{'status','source_hash','observed_at','evidence_states','findings'})
        report=self.flow.report(APP,saved['id']);report['stages'][0]['private_raw']='PRIVATE_EXCERPT'
        projected=founder.stage_projection(report)
        self.assertNotIn('PRIVATE',str(projected))
        self.assertEqual(projected[0]['unit'],'VIEWS')
        self.assertEqual(projected[0]['denominator_definition'],self.plan['stages'][0]['denominator_definition'])
        self.assertIsNone(projected[0]['count'])
