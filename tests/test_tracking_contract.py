"""Real contract and fixed-request behavior with synthetic provider responses only."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import copy,unittest
from mission_control.common import Invalid,canonical,digest
from mission_control.store import Store
from mission_control.experiments import Experiments
from mission_control import tracking_contract as contract,tracking_posthog as provider
from tests.test_experiments import prepared,REGISTER


def fixture(store):
    definition=prepared(store)
    with patch('mission_control.experiments.now',return_value=REGISTER):
        experiment=Experiments(store).create('sample-one',definition)
    data=dict(provider='posthog',project_id='123',region='us',automatic=False)
    source=dict(app_id='sample-one',id='synthetic-source',provider='posthog',data=data,hash=digest(data),
                version=1,status='CONNECTED')
    return store.app('sample-one'),experiment,source


def payload(rows=None):
    return dict(columns=contract.COLUMNS,results=rows if rows is not None else [
        ['control',contract.EVENTS[0],30,20,0],['control',contract.EVENTS[1],20,18,0],
        ['treatment',contract.EVENTS[0],24,21,0],['treatment',contract.EVENTS[1],23,19,0]])


class TrackingContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(Path(self.tmp.name)/'synthetic.sqlite3')
        self.app,self.experiment,self.source=fixture(self.store)
        self.plan=contract.proposal(self.app,self.experiment,self.source)

    def test_proposal_binds_current_source_and_immutable_experiment(self):
        plan=self.plan;value={k:v for k,v in plan.items() if k!='proposal_hash'}
        self.assertEqual(plan['proposal_hash'],digest(value))
        self.assertEqual(plan['flag_key'],'wmm-'+self.experiment['id'])
        self.assertEqual(plan['experiment_hash'],self.experiment['hash'])
        self.assertNotIn(self.experiment['data']['owner'],canonical(plan))
        self.assertFalse(plan['provider_writes']);self.assertEqual(plan['spend_minor'],0)
        self.assertEqual(plan,contract.proposal(self.app,self.experiment,self.source))

    def test_expected_flag_matches_exact_two_arm_allocation_and_release_target(self):
        expected=contract.expected_flag(self.app,self.experiment)
        self.assertTrue(expected['ensure_experience_continuity'])
        groups=expected['filters']['groups'];self.assertEqual(len(groups),1)
        self.assertEqual(groups[0]['rollout_percentage'],100)
        self.assertEqual({p['key']:p['value'] for p in groups[0]['properties']},
                         dict(wmm_app_id=self.app['id'],wmm_release=self.app['data']['release']))
        variants=expected['filters']['multivariate']['variants']
        self.assertEqual([v['key'] for v in variants],list(contract.ARMS))
        self.assertEqual(sum(v['rollout_percentage'] for v in variants),100)

    def test_proposal_rejects_foreign_tampered_disconnected_and_changed_app(self):
        for changes in ({'app_id':'sample-two'},{'provider':'clarity'},{'hash':'bad'},
                        {'status':'DISCONNECTED'},{'status':'CLEANUP_REQUIRED'}):
            with self.subTest(changes=changes),self.assertRaises(Invalid):
                contract.proposal(self.app,self.experiment,{**self.source,**changes})
        for field,value in (('region','evil.example'),('project_id','123/../other')):
            source=copy.deepcopy(self.source);source['data'][field]=value;source['hash']=digest(source['data'])
            with self.assertRaises(Invalid):contract.proposal(self.app,self.experiment,source)
        for changes in ({'app_id':'sample-two'},{'hash':'bad'},{'state':'CANCELLED'}):
            with self.assertRaises(Invalid):contract.proposal(self.app,{**self.experiment,**changes},self.source)
        for field,value in (('release','build-2'),('locale','fr-FR')):
            app=copy.deepcopy(self.app);app['data'][field]=value
            with self.assertRaises(Invalid):contract.proposal(app,self.experiment,self.source)

    def test_query_filters_exact_scope_and_exports_only_aggregates(self):
        sql=contract.query(self.plan)
        for key in ('app_id','release','locale','experiment_hash','starts_at','ends_at'):
            self.assertIn(contract.literal(self.plan[key]),sql)
        self.assertIn('uniqExact(distinct_id)',sql)
        self.assertIn('HAVING uniqExact(arm) > 1',sql)
        self.assertNotIn('SELECT distinct_id FROM events',sql)
        self.assertNotIn('email',sql)
        escaped=contract.literal("release'\\OR true")
        self.assertEqual(escaped,"'release\\'\\\\OR true'")
        for value in ('',None,'x'*201,'line\nbreak'):
            with self.assertRaises(Invalid):contract.literal(value)

    def test_shape_reports_deduplicated_subjects_and_preserves_limits(self):
        result=contract.shape(payload())
        self.assertEqual(result['status'],'OBSERVED')
        self.assertEqual(result['observed_counts'][0]['subjects'],20)
        self.assertEqual(result['cross_arm_subjects'],0)
        self.assertNotIn('distinct_id',canonical(result))
        empty=contract.shape(payload([]));self.assertEqual(empty['status'],'NO_OBSERVATIONS')
        self.assertIsNone(empty['cross_arm_subjects'])
        self.assertIn('not launch',empty['scope'])

    def test_shape_rejects_unknown_rows_bad_counts_duplicates_and_async(self):
        cases=[dict(results=None),dict(columns=['raw_subject']),dict(error='secret'),
               dict(query_status={'complete':False}),dict(query_status=True)]
        for changes in cases:
            with self.subTest(changes=changes),self.assertRaises(Invalid):contract.shape({**payload(),**changes})
        rows=[['other',contract.EVENTS[0],1,1,0],['control','raw-user',1,1,0],
              ['control',contract.EVENTS[0],1,2,0],['control',contract.EVENTS[0],1,0,0],
              ['control',contract.EVENTS[0],True,1,0],['control',contract.EVENTS[0],-1,0,0],
              ['control',contract.EVENTS[0],9007199254740992,1,0],['control',contract.EVENTS[0],1,1]]
        for row in rows:
            with self.subTest(row=row),self.assertRaises(Invalid):contract.shape(payload([row]))
        row=payload()['results'][0]
        with self.assertRaises(Invalid):contract.shape(payload([row,row]))
        with self.assertRaises(Invalid):contract.shape(payload([row,['treatment',contract.EVENTS[0],2,2,1]]))
        with self.assertRaises(Invalid):contract.shape(payload([['control',contract.EVENTS[0],1,1,1]]))
        with self.assertRaises(Invalid):contract.shape(payload([['control',contract.EVENTS[0],1,1,2],['treatment',contract.EVENTS[0],1,1,2]]))

    def test_flag_findings_do_not_return_provider_private_fields(self):
        expected=self.plan['expected_flag']
        valid=dict(expected,created_by={'email':'PRIVATE@example.test'})
        self.assertEqual(provider.flag_findings(dict(count=1,results=[valid],next=None),expected),[])
        self.assertEqual(len(provider.flag_findings(dict(count=0,results=[]),expected)),1)
        changed={**valid,'active':False,'archived':True}
        findings=provider.flag_findings(dict(count=1,results=[changed]),expected)
        self.assertEqual(len(findings),2);self.assertNotIn('PRIVATE',canonical(findings))
        for invalid in ({'results':[],'count':1},{'results':[valid,valid],'count':2},
                        {'results':[{**valid,'key':'other'}],'count':1},{'next':'https://other','results':[]}):
            with self.assertRaises(Invalid):provider.flag_findings(invalid,expected)

    def test_read_uses_fixed_project_flag_query_and_guard_before_after_each_read(self):
        expected=self.plan['expected_flag'];responses=[{'id':123},dict(count=1,results=[expected]),payload()]
        with patch.object(provider,'request',side_effect=responses) as request:
            guard=[];result=provider.read(self.plan,'SYNTHETIC_TOKEN',lambda:guard.append(True))
        self.assertEqual(len(guard),6);self.assertEqual(request.call_count,3)
        self.assertEqual(request.call_args_list[0].args[0],'https://us.posthog.com/api/projects/123/')
        self.assertIn('feature_flags/?key=wmm-',request.call_args_list[1].args[0])
        self.assertEqual(request.call_args_list[2].args[2]['query']['kind'],'HogQLQuery')
        self.assertEqual(result['flag_findings'],[]);self.assertNotIn('SYNTHETIC_TOKEN',canonical(result))

    def test_missing_flag_stops_before_query_and_names_setup_recovery(self):
        with patch.object(provider,'request',side_effect=[{'id':123},dict(count=0,results=[])]) as request:
            result=provider.read(self.plan,'SYNTHETIC',lambda:None)
        self.assertEqual(request.call_count,2);self.assertEqual(result['status'],'NEEDS_SETUP')
        self.assertIsNone(result['observed_counts']);self.assertTrue(result['next_actions'])

    def test_identity_failure_and_cancelled_authority_stop_further_provider_reads(self):
        with patch.object(provider,'request',return_value={'id':456}) as request,self.assertRaises(Invalid):
            provider.read(self.plan,'SYNTHETIC',lambda:None)
        self.assertEqual(request.call_count,1)
        def denied():raise Invalid('Synthetic cancellation')
        with patch.object(provider,'request') as request,self.assertRaises(Invalid):provider.read(self.plan,'SYNTHETIC',denied)
        request.assert_not_called()
        calls=[]
        def changed():
            calls.append(True)
            if len(calls)==2:raise Invalid('Synthetic authority changed in flight')
        with patch.object(provider,'request',return_value={'id':123}) as request,self.assertRaises(Invalid):
            provider.read(self.plan,'SYNTHETIC',changed)
        self.assertEqual(request.call_count,1)


if __name__=='__main__':unittest.main()
