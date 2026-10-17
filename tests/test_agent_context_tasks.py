"""Approved evidence must remain unchanged before and after model inference."""
from unittest.mock import patch
import unittest
from tests import test_agent_tasks as fixtures
from tests.test_agent_access import answer
from mission_control.agent_tasks import proposal
from mission_control.common import canonical,digest
from mission_control.db import connection
from mission_control.worker import run_once


class GroundedTaskTests(unittest.TestCase):
    setUp=fixtures.AgentTaskTests.setUp
    approve=fixtures.AgentTaskTests.approve
    result=fixtures.AgentTaskTests.result
    def ready(self):
        with connection(self.store.path) as db:
            db.execute("UPDATE agent_connections SET status='TESTED' WHERE id=?",(self.identity,))
        self.access.routes('sample-one',dict(version=0,mode='byok',routes={'campaign_plan':self.identity}))

    def change(self):
        self.store.save_record('sample-one',dict(kind='claim',title='Synthetic failure',source='Synthetic',data=dict(result='FAIL')))

    def test_guard_and_guard_context_block_new_evidence_before_request(self):
        self.ready();self.approve('campaign_plan');self.change()
        with patch('mission_control.agent_tasks.api_run') as run:
            run_once(self.store);run.assert_not_called()
        self.assertEqual(self.result()['status'],'BLOCKED')

    def test_live_guard_rejects_new_evidence_during_request(self):
        self.ready();self.approve('campaign_plan')
        def provider(*args):self.change();return answer(),{}
        with patch('mission_control.agent_tasks.api_run',side_effect=provider):run_once(self.store)
        self.assertEqual(self.result()['status'],'BLOCKED')
        self.assertNotIn('draft',self.result()['result'])

    def test_connection_test_transmits_no_campaign_sources(self):
        value=proposal(self.store,'sample-one',dict(task='connection_test',focus='',connection_id=self.identity))['proposal']
        self.assertIsNone(value['context']);self.assertEqual(value['source_ids'],[])
        self.assertNotIn('stage_2',value['prompt'])

    def test_missing_approved_context_rejects_even_rehashed_envelope(self):
        self.ready();queued=self.approve('campaign_plan');data=queued['data']
        del data['envelope']['context'];data['envelope_hash']=digest(data['envelope'])
        with connection(self.store.path) as db:db.execute('UPDATE jobs SET data=? WHERE id=?',(canonical(data),queued['id']))
        with patch('mission_control.agent_tasks.api_run') as run:
            run_once(self.store);run.assert_not_called()
        self.assertEqual(self.result()['status'],'BLOCKED')

    def test_current_stage_citation_is_accepted_and_other_app_rejected(self):
        self.ready();self.approve('campaign_plan');response=answer();response['items'][0]['source_ids']=['stage_2']
        with patch('mission_control.agent_tasks.api_run',return_value=(response,{})):run_once(self.store)
        self.assertEqual(self.result()['status'],'SUCCEEDED')
        self.approve('campaign_plan');response['items'][0]['source_ids']=['sample-two']
        with patch('mission_control.agent_tasks.api_run',return_value=(response,{})):run_once(self.store)
        self.assertEqual(self.result()['status'],'BLOCKED')
