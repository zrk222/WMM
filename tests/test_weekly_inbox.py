"""Portfolio coverage, source failures, app lineage and authority denial."""
import unittest
from types import SimpleNamespace
from mission_control.common import Invalid
from mission_control.weekly_inbox import review


class InboxTests(unittest.TestCase):
    def service(self, count=2, failed=None):
        apps=[dict(id='app-'+str(i),version=1,data=dict(name='App '+str(i))) for i in range(count)]
        def workspace(identity):
            if identity==failed:raise RuntimeError('SECRET MUST NEVER APPEAR')
            app=next(a for a in apps if a['id']==identity)
            return dict(app=app,records=[],stages=[dict(id=i,title=str(i),status='BLOCKED',missing=['Collect evidence']) for i in range(1,13)])
        return SimpleNamespace(store=SimpleNamespace(apps=lambda:apps),workspace=workspace)

    def test_separate_sources_and_no_authority(self):
        result=review(self.service())
        self.assertEqual(len(result['exceptions']),8)
        for card in result['exceptions']:
            self.assertEqual(card['app_id'],card['source_receipt']['app_id'])
            self.assertTrue(card['source_receipt']['source_hash'])
            self.assertTrue(card['resolution_route']);self.assertIsNone(card['cost_minor'])
        self.assertEqual(result['authority'],'NO_EXECUTION_AUTHORITY')
        for key in ('spend_allowed','scale_allowed','learning_pilot_allowed'):self.assertIs(result[key],False)

    def test_source_failure_is_redacted_and_other_apps_continue(self):
        result=review(self.service(failed='app-0'))
        self.assertEqual(result['exceptions'][0]['state'],'UNAVAILABLE')
        self.assertEqual(len(result['exceptions']),5)
        self.assertNotIn('SECRET',str(result))

    def test_explicit_pagination_and_empty_portfolio(self):
        service=self.service(7)
        self.assertEqual(review(service)['coverage'],dict(offset=0,evaluated=5,total_apps=7,next_offset=5))
        self.assertEqual(review(service,5)['coverage']['evaluated'],2)
        self.assertEqual(review(self.service(0))['exceptions'],[])
        for offset in (-1,True,8):
            with self.assertRaises(Invalid):review(service,offset)

    def test_critical_first_and_local_ready_digest(self):
        service=self.service(1);original=service.workspace
        def workspace(identity):
            w=original(identity)
            w['stages']=[dict(id=i,title=str(i),status='READY') for i in range(1,13)]
            w['records']=[dict(id='r1',app_id=identity,version=1,hash='a'*64,kind='review',title='Broken checkout',data=dict(confirmed=True,severity='P0'))]
            return w
        service.workspace=workspace
        result=review(service)
        self.assertEqual(result['exceptions'][0]['priority'],0)
        self.assertEqual(len(result['apps'][0]['local_ready']),4)
