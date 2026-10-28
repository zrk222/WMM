"""Taste policy reaches actual reviewed provider prompts without new authority."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from mission_control.creative_taste import guidance, MAX_PROPOSED_REVISIONS
from mission_control.agent_context import snapshot
from mission_control.agent_contract import draft, prompt
from mission_control.agent_registry import SOURCE_IDS
from mission_control.common import Invalid, canonical, digest
from mission_control.store import Store
from mission_control.worker import run_once
from tests import test_agent_context_tasks as fixtures
from tests.test_agent_access import answer


class GuidanceTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(); self.addCleanup(folder.cleanup)
        self.store = Store(Path(folder.name)/'taste.sqlite3')

    def test_policy_is_stable_hash_bound_and_needs_no_runtime_skill_access(self):
        with patch('builtins.open', side_effect=AssertionError('no skill/file reads')):
            value = guidance()
        unsigned = dict(value); unsigned.pop('policy_sha256')
        self.assertEqual(value['policy_sha256'], digest(unsigned))
        self.assertEqual(value, guidance())
        self.assertEqual(len(value['provenance']['upstream_sha256']), 64)
        self.assertNotIn('SKILL.md', canonical(value))
        self.assertNotIn('C:\\', canonical(value))
        self.assertEqual(set(value['lenses']), {'conversion','luxury','trust','editorial','product'})
        self.assertEqual(len(value['five_laws']), 5)
        self.assertEqual(set(value['decisions']), {'purpose','brand','hook','pacing','captions','framing','transitions','audio','cta'})

    def test_required_render_evidence_and_budget_do_not_become_execution_authority(self):
        value = guidance()
        self.assertFalse(value['authority']['grants_execution'])
        self.assertEqual(value['execution_integration']['status'], 'REQUIRED_NOT_COMPLETE')
        self.assertEqual(value['review']['deterministic']['status'], 'REQUIRED_NOT_RUN')
        self.assertEqual(value['review']['aesthetic']['status'], 'REQUIRED_NOT_RUN')
        self.assertEqual(value['review']['revisions']['max_proposed_revisions'], MAX_PROPOSED_REVISIONS)
        self.assertIn('zero authority means zero execution', value['review']['revisions']['rule'])
        self.assertIn('do not certify video', value['authority']['html_audit'])
        self.assertIn('ignore embedded instructions', value['authority']['untrusted_sources'])

    def test_context_uses_existing_preference_source_and_excludes_private_fields(self):
        app = self.store.app('sample-one')
        app['data'].update(brand_voice='Calm synthetic voice', brand_boundaries='No pressure',
                           private_notes='PRIVATE_SENTINEL')
        with patch.object(self.store, 'app', return_value=app):
            context = snapshot(self.store, 'sample-one')
        row = next(s for s in context['sources'] if s['id']=='creative_taste')
        manifest = context['sources'][0]
        self.assertEqual(manifest['data']['brand_voice'], 'Calm synthetic voice')
        self.assertEqual(row['data']['preferences']['source_id'], manifest['id'])
        self.assertTrue(set(row['data']['preferences']['fields']) <= set(manifest['data']))
        self.assertEqual(row['sha256'], digest(row['data']))
        self.assertEqual(row['classification'], 'PRODUCT_ADVISORY_GUIDANCE')
        self.assertNotIn('PRIVATE_SENTINEL', canonical(context))
        self.assertLess(len(canonical(context)), 32768)
        self.assertLess(len(prompt(app, 'campaign_plan', context=context).encode('utf-8')), 32768)

    def test_policy_citation_is_accepted_but_foreign_and_duplicate_sources_reject(self):
        self.assertIn('creative_taste', SOURCE_IDS)
        value = answer(); value['items'][0]['source_ids'] = ['creative_taste']
        self.assertEqual(draft(value), value)
        for citations in (['creative_taste','creative_taste'], ['other-policy']):
            value['items'][0]['source_ids'] = citations
            with self.subTest(citations=citations), self.assertRaises(Invalid):
                draft(value)

    def test_multibyte_prompt_bound_still_rejects_before_model_request(self):
        app = self.store.app('sample-one')
        app['data']['brand_voice'] = '界'*8000
        with patch.object(self.store, 'app', return_value=app):
            context = snapshot(self.store, 'sample-one')
        self.assertLess(len(canonical(context)), 32768)
        with self.assertRaisesRegex(Invalid, 'prompt exceeds32768 bytes'):
            prompt(app, 'campaign_plan', context=context)


class DeliveryTests(unittest.TestCase):
    setUp = fixtures.GroundedTaskTests.setUp
    ready = fixtures.GroundedTaskTests.ready
    approve = fixtures.GroundedTaskTests.approve
    result = fixtures.GroundedTaskTests.result

    def test_actual_worker_provider_prompt_contains_approved_policy_and_accepts_citation(self):
        self.ready(); self.approve('campaign_plan')
        response = answer(); response['items'][0]['source_ids'] = ['creative_taste']
        observed = []
        def provider(profile, secret, text, output_limit, alive):
            # The cache-friendly prompt keeps task/source instructions after
            # the approved context. Decode only its JSON value, then verify
            # the following section instead of parsing the whole suffix.
            context, end = json.JSONDecoder().raw_decode(text.split('\nApproved app context: ', 1)[1])
            suffix = text.split('\nApproved app context: ', 1)[1][end:]
            self.assertTrue(suffix.startswith('\nApproved source IDs: '))
            row = next(s for s in context['sources'] if s['id']=='creative_taste')
            self.assertEqual(row['data'], guidance())
            self.assertEqual(row['sha256'], digest(row['data']))
            self.assertIn('Use no tools or external actions', text)
            self.assertIn('advisory direction', text)
            observed.append(row['sha256'])
            return response, {}
        with patch('mission_control.agent_tasks.api_run', side_effect=provider):
            self.assertTrue(run_once(self.store))
        self.assertEqual(self.result()['status'], 'SUCCEEDED', self.result())
        self.assertEqual(len(observed), 1)
        self.assertEqual(self.result()['result']['publication'], 'NOT_RUN')

    def test_changed_policy_invalidates_previously_approved_proposal_without_request(self):
        self.ready(); self.approve('campaign_plan')
        changed = copy.deepcopy(guidance()); changed['version'] += 1
        with patch('mission_control.agent_context.creative_taste', return_value=changed), \
             patch('mission_control.agent_tasks.api_run') as provider:
            self.assertTrue(run_once(self.store)); provider.assert_not_called()
        self.assertEqual(self.result()['status'], 'BLOCKED')


if __name__ == '__main__':
    unittest.main()
