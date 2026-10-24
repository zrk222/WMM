"""Actual lost-token regression, closed telemetry and durable selected-agent parity."""
import json
import unittest
from unittest.mock import patch
from mission_control.agent_usage import observation, MAX_TOKENS
from mission_control.agent_commands import output
from mission_control.agent_access import AgentAccess
from mission_control.agent_tasks import AgentWork
from mission_control.common import canonical
from mission_control.store import Store
from mission_control.worker import jobs, run_once
from tests import test_agent_tasks
from tests.test_agent_access import connection_test_fixture
from tests.test_local_agent_access import local_body
from tests.test_local_agent_api import ModelServer


class UsageTests(unittest.TestCase):
    def test_compatible_aliases_preserve_exact_reported_counts_without_totals_inference(self):
        value = observation(dict(prompt_tokens=11, completion_tokens=4, total_tokens=18))
        self.assertEqual(value, dict(usage=dict(input_tokens=11, output_tokens=4, total_tokens=18), usage_status='REPORTED', usage_issues=[]))
        self.assertEqual(observation(dict(input_tokens=11, prompt_tokens=11))['usage'], dict(input_tokens=11))
        missing = observation(dict(prompt_tokens=11, completion_tokens=4))
        self.assertEqual(missing['usage'], dict(input_tokens=11, output_tokens=4))
        self.assertEqual(missing['usage_status'], 'PARTIAL')

    def test_invalid_counts_and_conflicting_aliases_do_not_replace_draft_or_choose_a_value(self):
        for invalid in (True, False, -1, 1.5, '12', None, [], {}, MAX_TOKENS + 1):
            with self.subTest(invalid=invalid):
                value = observation(dict(input_tokens=12, prompt_tokens=invalid, output_tokens=0))
                self.assertEqual(value['usage'], dict(output_tokens=0))
                self.assertEqual(value['usage_issues'], ['INVALID_INPUT_TOKENS'])
                self.assertEqual(value['usage_status'], 'PARTIAL')
        conflict = observation(dict(input_tokens=12, prompt_tokens=13))
        self.assertEqual(conflict, dict(usage={}, usage_status='INVALID', usage_issues=['CONFLICT_INPUT_TOKENS']))
        self.assertEqual(observation(dict(total_tokens=MAX_TOKENS))['usage'], dict(total_tokens=MAX_TOKENS))

    def test_cache_and_reasoning_subsets_are_retained_without_inflating_total(self):
        raw = dict(prompt_tokens=100, completion_tokens=20, total_tokens=120,
                   prompt_tokens_details=dict(cached_tokens=80), completion_tokens_details=dict(reasoning_tokens=10))
        self.assertEqual(observation(raw)['usage'], dict(input_tokens=100, output_tokens=20, total_tokens=120, cache_read_tokens=80, reasoning_tokens=10))
        native = dict(input_tokens=10, output_tokens=3, cache_read_input_tokens=8, cache_creation_input_tokens=2)
        result = observation(native)
        self.assertEqual(result['usage'], dict(input_tokens=10, output_tokens=3, cache_read_tokens=8, cache_write_tokens=2))
        self.assertNotIn('total_tokens', result['usage'])
        self.assertEqual(observation(dict(cached_input_tokens=8, cache_read_input_tokens=9))['usage_issues'], ['CONFLICT_CACHE_READ_TOKENS'])

    def test_absent_zero_malformed_details_and_private_strings_remain_distinct(self):
        for raw in (None, {}, dict(secret='SYNTHETIC_PRIVATE_USAGE')):
            self.assertEqual(observation(raw), dict(usage={}, usage_status='UNAVAILABLE', usage_issues=[]))
        for raw in ('SYNTHETIC_PRIVATE_USAGE', [], 42):
            result = observation(raw)
            self.assertEqual(result['usage_status'], 'INVALID')
            self.assertNotIn('SYNTHETIC_PRIVATE_USAGE', canonical(result))
        zero = observation(dict(prompt_tokens=0, completion_tokens=0, total_tokens=0))
        self.assertEqual(zero['usage'], dict(input_tokens=0, output_tokens=0, total_tokens=0))
        self.assertEqual(zero['usage_status'], 'REPORTED')
        details = observation(dict(prompt_tokens_details='SYNTHETIC_PRIVATE_USAGE'))
        self.assertEqual(details['usage_issues'], ['INVALID_CACHE_READ_TOKENS'])
        self.assertNotIn('SYNTHETIC_PRIVATE_USAGE', canonical(details))

    def test_native_codex_and_claude_usage_maps_through_the_same_contract(self):
        draft = connection_test_fixture()
        events = [dict(type='item.completed', item=dict(type='agent_message', text=canonical(draft))),
                  dict(type='turn.completed', usage=dict(input_tokens=20, output_tokens=4, cached_input_tokens=12))]
        _, usage = output('codex', dict(code=0, stdout='\n'.join(map(json.dumps, events)), stderr=''))
        self.assertEqual(observation(usage)['usage'], dict(input_tokens=20, output_tokens=4, cache_read_tokens=12))
        _, usage = output('claude', dict(code=0, stdout=canonical(dict(subtype='success', structured_output=draft,
            usage=dict(input_tokens=20, output_tokens=4, cache_read_input_tokens=12, cache_creation_input_tokens=2))), stderr=''))
        self.assertEqual(observation(usage)['usage'], dict(input_tokens=20, output_tokens=4, cache_read_tokens=12, cache_write_tokens=2))


class DurableUsageTests(unittest.TestCase):
    setUp = test_agent_tasks.AgentTaskTests.setUp
    approve = test_agent_tasks.AgentTaskTests.approve

    def saved(self, identity):
        return next(job for job in jobs(self.store, 'sample-one') if job['id'] == identity)

    def test_api_aliases_persist_on_owned_job_and_replay_does_not_repeat_inference(self):
        queued = self.approve()
        raw = dict(prompt_tokens=14, completion_tokens=3, total_tokens=17, secret='SYNTHETIC_PRIVATE_USAGE')
        with patch('mission_control.agent_tasks.api_run', return_value=(connection_test_fixture(), raw)) as inference:
            self.assertTrue(run_once(self.store))
            inference.assert_called_once()
        saved = self.saved(queued['id'])
        self.assertEqual(saved['status'], 'SUCCEEDED', saved['result'])
        self.assertEqual(saved['result']['usage'], dict(input_tokens=14, output_tokens=3, total_tokens=17))
        self.assertEqual(saved['result']['usage_status'], 'REPORTED')
        self.assertEqual(saved['result']['cost'], 'UNKNOWN')
        self.assertEqual(saved['result']['quota'], 'UNKNOWN')
        self.assertNotIn('SYNTHETIC_PRIVATE_USAGE', canonical(saved))
        self.store = Store(self.store.path)
        with patch('mission_control.agent_tasks.api_run') as inference:
            replay = AgentWork(self.store).start('sample-one', queued['data']['original_request'])
            self.assertEqual(replay['id'], queued['id'])
            self.assertFalse(run_once(self.store))
            inference.assert_not_called()
        self.assertEqual(self.saved(queued['id'])['result'], saved['result'])
        self.assertEqual(jobs(self.store, 'sample-two'), [])

    def test_actual_local_model_response_retains_aliases_before_worker_storage(self):
        model = ModelServer()
        self.addCleanup(model.close)
        model.value['choices'][0]['message']['content'] = canonical(connection_test_fixture())
        model.value['usage'] = dict(prompt_tokens=9, completion_tokens=2, total_tokens=11)
        self.identity = self.access.save('sample-one', local_body(model.url))['connection']
        queued = self.approve()
        self.assertTrue(run_once(self.store))
        saved = self.saved(queued['id'])
        self.assertEqual(saved['status'], 'SUCCEEDED', saved['result'])
        self.assertEqual(saved['result']['usage'], dict(input_tokens=9, output_tokens=2, total_tokens=11))
        self.assertEqual(len(model.calls), 1)

    def test_missing_and_invalid_telemetry_do_not_discard_successful_drafts(self):
        for raw, status in ((None, 'UNAVAILABLE'), ({'input_tokens': True}, 'INVALID')):
            queued = self.approve()
            with patch('mission_control.agent_tasks.api_run', return_value=(connection_test_fixture(), raw)):
                self.assertTrue(run_once(self.store))
            saved = self.saved(queued['id'])
            self.assertEqual(saved['status'], 'SUCCEEDED', saved['result'])
            self.assertEqual(saved['result']['draft'], connection_test_fixture())
            self.assertEqual(saved['result']['usage_status'], status)
            self.assertEqual(saved['result']['usage'], {})
