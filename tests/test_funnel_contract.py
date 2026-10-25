"""App-sales routes and observed-zero/unknown input semantics stay explicit."""
from copy import deepcopy
from datetime import datetime,timezone
import unittest
from mission_control.common import Invalid
from mission_control.funnel_contract import definition,observation,stages,window,outcome,offer_boundary,source_ref,rows,unique


def fixture():
    source=dict(kind='CREATIVE_BRIEF',id='brief-one',version=1,sha256='a'*64)
    stage=dict(id='view',type='VIDEO_VIEW',label='Video view',parents=[],unit='VIEWS',denominator_definition='Eligible platform views')
    return dict(release='build-1',locale='en-US',currency='USD',cohort_id='cohort-one',
                outcome=dict(audience='People organizing their tasks',pain='Tasks lack one clear next action',research_refs=[],milestone='Complete first saved action',metric='Activated users',target=100,due_at='2026-11-01T00:00:00+00:00'),
                creative_refs=[source],hook='Choose the next useful action.',cta='Try the app',destination='https://example.com/app',route='APP_DOWNLOAD',
                stages=[stage,dict(stage,id='install',type='INSTALL',label='App install',parents=['view'],unit='UNIQUE_SUBJECTS',denominator_definition='Attributed install identities')],
                attribution=dict(method='Supplied platform observation',identity_scope='platform-app-campaign-one',starts_at='2026-10-01T00:00:00+00:00',ends_at='2026-10-02T00:00:00+00:00',conversion_window_seconds=86400),
                offer_boundary=dict(free_deliverables=['First action'],paid_deliverables=['Additional app workflows']))


def observed(plan):
    return dict(event_id='event-one',stage_id='view',source_ref='platform-export-one',source_sha256='b'*64,cohort_id=plan['cohort_id'],starts_at=plan['attribution']['starts_at'],ends_at=plan['attribution']['ends_at'],observed_at='2026-10-03T00:00:00+00:00',coverage='OBSERVED',count=0,unit='VIEWS',denominator_definition=plan['stages'][0]['denominator_definition'],identity_scope=plan['attribution']['identity_scope'])


class FunnelContractTests(unittest.TestCase):
    def setUp(self):
        self.plan=fixture();self.clock=datetime(2026,10,4,tzinfo=timezone.utc)

    def test_definition_preserves_app_outcome_free_paid_boundary_and_current_source_inputs(self):
        result=definition(self.plan)
        self.assertEqual(result,self.plan)
        result['stages'][0]['label']='Changed copy'
        self.assertEqual(self.plan['stages'][0]['label'],'Video view')
        for route in ('APP_DOWNLOAD','RESOURCE','APP_DEMO'):
            self.assertEqual(definition(dict(self.plan,route=route))['route'],route)
        for route in ('WEBINAR','COACHING','GUARANTEED_INCOME'):
            with self.assertRaises(Invalid):definition(dict(self.plan,route=route))

    def test_stage_graph_rejects_cycles_unknown_parents_duplicates_and_oversized_plans(self):
        for rows in ([dict(self.plan['stages'][0],parents=['install']),self.plan['stages'][1]],
                     [dict(self.plan['stages'][0],parents=['missing'])],
                     [self.plan['stages'][0]]*2,[],[self.plan['stages'][0]]*33):
            with self.subTest(rows=rows),self.assertRaises(Invalid):stages(rows)
        bad=deepcopy(self.plan['stages']);bad[1]['parents']=['view','view']
        with self.assertRaises(Invalid):stages(bad)

    def test_observation_keeps_zero_partial_and_unknown_distinct(self):
        plan=definition(self.plan);value=observed(plan)
        self.assertEqual(observation(value,plan,self.clock)['count'],0)
        self.assertEqual(observation(dict(value,coverage='PARTIAL',count=7),plan,self.clock)['coverage'],'PARTIAL')
        self.assertIsNone(observation(dict(value,coverage='UNKNOWN',count=None),plan,self.clock)['count'])
        for change in (dict(coverage='UNKNOWN',count=0),dict(count=True),dict(count=-1),dict(count=1.2),dict(count=10**12+1),dict(coverage='VERIFIED')):
            with self.subTest(change=change),self.assertRaises(Invalid):observation(dict(value,**change),plan,self.clock)

    def test_observation_rejects_scope_population_window_and_future_mismatches(self):
        plan=definition(self.plan);value=observed(plan)
        for change in (dict(cohort_id='foreign'),dict(identity_scope='foreign'),dict(stage_id='foreign'),dict(unit='UNIQUE_SUBJECTS'),dict(denominator_definition='Different population'),dict(source_sha256='bad'),dict(observed_at='2027-01-01T00:00:00+00:00'),dict(ends_at='2026-10-03T00:00:00+00:00'),dict(starts_at='2026-09-30T00:00:00+00:00')):
            with self.subTest(change=change),self.assertRaises(Invalid):observation(dict(value,**change),plan,self.clock)

    def test_contract_rejects_hidden_fields_unbounded_sources_and_untyped_targets(self):
        for change in (dict(shell='exec'),dict(currency='usd'),dict(destination='http://127.0.0.1/private'),dict(creative_refs=[]),dict(creative_refs=self.plan['creative_refs']*21),dict(outcome=dict(self.plan['outcome'],target=True))):
            with self.subTest(change=change),self.assertRaises(Invalid):definition(dict(self.plan,**change))
        with self.assertRaises(Invalid):source_ref(dict(self.plan['creative_refs'][0],id='../private'))
        with self.assertRaises(Invalid):window(dict(self.plan['attribution'],ends_at=self.plan['attribution']['starts_at']))
        with self.assertRaises(Invalid):offer_boundary(dict(free_deliverables=['item']*21,paid_deliverables=[]))
        with self.assertRaises(Invalid):unique([{'id':'same'},{'id':'same'}],'id','sources')

    def test_observation_window_rejects_end_after_evidence_and_reversed_range(self):
        from mission_control.funnel_contract import observation_window
        value=observed(self.plan)
        self.assertEqual(observation_window(value,self.plan,self.clock)['observed_at'],value['observed_at'])
        with self.assertRaises(Invalid):observation_window(dict(value,observed_at=value['starts_at']),self.plan,self.clock)
