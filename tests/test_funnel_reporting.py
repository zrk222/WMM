"""Comparable aggregate edges preserve uncertainty, source conflicts and ledger separation."""
from copy import deepcopy
from datetime import datetime,timezone
import unittest
from mission_control.funnel_reporting import calculate,selected_snapshot,edge_rate
from mission_control.common import digest
from tests.test_funnel_contract import fixture,observed


class FunnelReportTests(unittest.TestCase):
    def setUp(self):
        self.plan=fixture();self.plan['stages'][1].update(unit='VIEWS',denominator_definition=self.plan['stages'][0]['denominator_definition'])
        self.saved=dict(id='funnel-one',app_id='sample-one',hash='c'*64,data=dict(definition=self.plan))
        self.value=observed(self.plan);self.asof='2026-10-04T00:00:00+00:00'

    def report(self,values,ledger=None):
        return calculate(self.saved,[dict(data=dict(observation=v))for v in values],ledger,self.asof)

    def test_observed_edges_use_eligible_counts_and_keep_payment_ledger_separate(self):
        parent=dict(self.value,count=100);child=dict(self.value,event_id='child',stage_id='install',count=20)
        ledger=dict(source_hash='d'*64,net_proceeds_minor=2000,refunds_minor=500)
        result=self.report([parent,child],ledger)
        self.assertEqual(result['edges'][0]['rate'],.2)
        self.assertEqual(result['edges'][0]['drop_off_count'],80)
        self.assertFalse(result['edges'][0]['subject_transition_verified'])
        self.assertEqual(result['subscription_ledger'],ledger)
        self.assertEqual(result['subscription_ledger']['net_proceeds_minor'],2000)
        self.assertEqual(result['source_hash'],digest({k:v for k,v in result.items()if k!='source_hash'}))

    def test_missing_unknown_partial_zero_and_mismatched_populations_do_not_invent_rates(self):
        for parent,child,code in [(dict(self.value,count=0),dict(self.value,event_id='child',stage_id='install',count=0),'ZERO_DENOMINATOR'),
            (dict(self.value,count=5),dict(self.value,event_id='child',stage_id='install',count=6),'NUMERATOR_EXCEEDS_DENOMINATOR'),
            (dict(self.value,count=5,coverage='PARTIAL'),dict(self.value,event_id='child',stage_id='install',count=2),'INCOMPLETE_OBSERVATION')]:
            result=self.report([parent,child]);self.assertIsNone(result['edges'][0]['rate']);self.assertEqual(result['edges'][0]['status'],code)
        result=self.report([]);self.assertTrue(all(s['count']is None for s in result['stages']))
        self.assertIn('LEDGER_UNAVAILABLE',[r['code']for r in result['findings']])
        self.plan['stages'][1]['unit']='UNIQUE_SUBJECTS'
        result=self.report([dict(self.value,count=100),dict(self.value,event_id='child',stage_id='install',count=2)])
        self.assertEqual(result['edges'][0]['status'],'POPULATION_OR_UNIT_MISMATCH')

    def test_snapshots_are_not_summed_and_conflicting_sources_or_equal_time_counts_remain_unknown(self):
        original=dict(self.value,count=100)
        newer=dict(original,event_id='newer',count=150,observed_at='2026-10-04T00:00:00+00:00')
        self.assertEqual(self.report([original,newer])['stages'][0]['count'],150)
        conflict=dict(newer,event_id='conflict',count=160)
        result=self.report([newer,conflict]);self.assertEqual(result['stages'][0]['status'],'CONFLICTING_SNAPSHOTS');self.assertIsNone(result['stages'][0]['count'])
        foreign=dict(original,event_id='other',source_ref='different-source')
        result=self.report([original,foreign]);self.assertEqual(result['stages'][0]['status'],'AMBIGUOUS_SOURCES')
        partial=dict(original,ends_at='2026-10-01T12:00:00+00:00')
        self.assertEqual(self.report([partial])['stages'][0]['status'],'PARTIAL_WINDOW')
        future=dict(original,observed_at='2026-10-05T00:00:00+00:00')
        self.assertEqual(self.report([future])['stages'][0]['status'],'MISSING')
