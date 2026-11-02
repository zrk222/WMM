"""Bounded copy packs use real approvals/jobs, not a second agent executor."""
import copy
import unittest
from unittest.mock import patch

from mission_control.agent_contract import draft,output_contract,prompt
from mission_control.agent_operations import discovery
from mission_control.agent_tasks import AgentWork
from mission_control.common import Invalid,canonical,digest
from mission_control.draft_recipes import CONTENT_PACK_FOCUS,CONTENT_PACK_TITLES,catalog,recipe,validate
from mission_control.store import Store
from mission_control.worker import run_once,jobs
from tests import test_agent_tasks as fixture
from tests.test_agent_access import connection_test_fixture


def pack():
    return dict(summary='Synthetic text pack; owner review required',
                items=[dict(title=title,detail='Explain the approved app benefit. Try the first task.',
                            source_ids=['app_manifest']) for title in CONTENT_PACK_TITLES],
                unknowns=['No campaign, render, publication or measured outcome'])


class ContractTests(unittest.TestCase):
    def test_runtime_limits_match_acceptance_and_are_not_shared_mutable_state(self):
        limits=output_contract()
        value=dict(summary='s'*limits['summary_chars'],
                   items=[dict(title='t'*limits['title_chars'],detail='d'*limits['detail_chars'],source_ids=['app_manifest'])]*limits['max_items'],
                   unknowns=['u'*limits['unknown_chars']]*limits['max_unknowns'])
        self.assertEqual(draft(value,['app_manifest']),value)
        for change in ('summary','title','detail','unknown','items','unknowns'):
            bad=copy.deepcopy(value)
            if change=='summary':bad['summary']+='x'
            elif change in ('title','detail'):bad['items'][0][change]+='x'
            elif change=='unknown':bad['unknowns'][0]+='x'
            elif change=='items':bad['items'].append(copy.deepcopy(bad['items'][0]))
            else:bad['unknowns'].append('x')
            with self.subTest(change=change),self.assertRaises(Invalid):draft(bad,['app_manifest'])
        limits['summary_chars']=1
        self.assertEqual(output_contract()['summary_chars'],1200)
        text=prompt({'data':{}},'original_copy')
        self.assertIn('Character limits: summary 1200',text)
        self.assertIn('Cite only unique approved source IDs',text)

    def test_recipe_requires_exact_complete_order_and_real_source_references(self):
        selected=recipe('original_copy',CONTENT_PACK_FOCUS)
        self.assertLessEqual(len(CONTENT_PACK_FOCUS),1000)
        self.assertIsNone(recipe('campaign_plan',CONTENT_PACK_FOCUS))
        self.assertIsNone(recipe('original_copy',CONTENT_PACK_FOCUS+' edited'))
        self.assertEqual(validate(draft(pack(),['app_manifest']),selected)['status'],'TEXT_DRAFT_PACK_READY')
        for change in ('missing','duplicate','order','blank','unsourced','foreign'):
            bad=pack()
            if change=='missing':bad['items'].pop()
            elif change=='duplicate':bad['items'][1]['title']=bad['items'][0]['title']
            elif change=='order':bad['items'].reverse()
            elif change=='blank':bad['items'][0]['detail']='  '
            elif change=='unsourced':bad['items'][0]['source_ids']=[]
            else:bad['items'][0]['source_ids']=['other-app']
            with self.subTest(change=change),self.assertRaises(Invalid):validate(draft(bad,['app_manifest']),selected)
        selected['version']=2
        with self.assertRaises(Invalid):validate(pack(),selected)
        self.assertEqual(catalog()[0]['version'],1)

    def test_recipe_is_in_hash_bound_existing_agent_discovery_without_new_authority(self):
        app=dict(id='synthetic-app',version=1,data=dict(name='Synthetic',release='1'))
        guide=discovery(app)['personal_agent_guide']
        protocol=guide['owner_operating_protocol']
        self.assertEqual(protocol['draft_recipes'][0],catalog()[0])
        self.assertEqual(protocol['draft_output_contract'],output_contract())
        original=guide['guide_sha256'];protocol['draft_recipes'][0]['item_titles'].clear()
        changed=copy.deepcopy(guide);changed.pop('guide_sha256')
        self.assertNotEqual(digest(changed),original)
        fresh=discovery(app)['personal_agent_guide']
        self.assertEqual(fresh['guide_sha256'],original)
        self.assertFalse(fresh['execution_authority'])

    def test_model_scores_reasoning_and_approval_fields_are_not_authority(self):
        for field in ('confidence_score','reasoning_chain','auto_approved','commands'):
            with self.subTest(field=field),self.assertRaises(Invalid):
                draft(dict(pack(),**{field:'not permitted'}),['app_manifest'])


class WorkerTests(unittest.TestCase):
    setUp=fixture.AgentTaskTests.setUp
    approve=fixture.AgentTaskTests.approve
    result=fixture.AgentTaskTests.result

    def ready(self):
        self.approve()
        with patch('mission_control.agent_tasks.api_run',return_value=(connection_test_fixture(),None)):
            self.assertTrue(run_once(self.store))
        self.access.routes('sample-one',dict(version=0,mode='byok',routes={'original_copy':self.identity}))

    def test_approved_pack_survives_restart_without_replay_or_claiming_rendering(self):
        self.ready();job=self.approve('original_copy',CONTENT_PACK_FOCUS)
        self.assertEqual(job['data']['envelope']['draft_recipe'],catalog()[0])
        with patch('mission_control.agent_tasks.api_run',return_value=(pack(),None)) as model:
            self.assertTrue(run_once(self.store));self.assertEqual(model.call_count,1)
        saved=self.result();self.assertEqual(saved['status'],'SUCCEEDED',saved['result'])
        self.assertEqual(saved['result']['draft_recipe']['rendering'],'NOT_RUN')
        self.assertEqual(saved['result']['draft_recipe']['factual_verification'],'OWNER_REVIEW_REQUIRED')
        self.assertFalse(saved['result']['automatically_verified'])
        self.assertEqual(saved['result']['cost'],'UNKNOWN')
        reopened=Store(self.store.path)
        with patch('mission_control.agent_tasks.api_run') as model:
            replay=AgentWork(reopened).start('sample-one',job['data']['original_request'])
            self.assertEqual(replay['id'],job['id']);self.assertFalse(run_once(reopened));model.assert_not_called()
        self.assertEqual(jobs(reopened,'sample-one')[0]['result'],saved['result'])
        self.assertEqual(jobs(reopened,'sample-two'),[])

    def test_partial_pack_is_not_success_and_never_retries_the_model(self):
        self.ready();self.approve('original_copy',CONTENT_PACK_FOCUS);partial=pack();partial['items'].pop()
        with patch('mission_control.agent_tasks.api_run',return_value=(partial,None)) as model:
            self.assertTrue(run_once(self.store));self.assertFalse(run_once(self.store));self.assertEqual(model.call_count,1)
        saved=self.result();self.assertEqual(saved['status'],'BLOCKED')
        self.assertNotIn('draft',saved['result']);self.assertIn('every requested item',canonical(saved['result']))

    def test_changed_output_contract_stops_before_provider_transmission(self):
        self.ready();self.approve('original_copy',CONTENT_PACK_FOCUS)
        changed=output_contract();changed['max_items']=7
        with patch('mission_control.agent_tasks.output_contract',return_value=changed),patch('mission_control.agent_tasks.api_run') as model:
            self.assertTrue(run_once(self.store));model.assert_not_called()
        self.assertEqual(self.result()['status'],'BLOCKED')
