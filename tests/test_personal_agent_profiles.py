"""Offline profiles plus actual local HTTP, CLI and official MCP discovery."""
import copy
import json
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit
from mission_control.agent_operations import discovery
from mission_control.common import digest
from mission_control.marketing_agent_manifest import operating_manifest
from mission_control.operation_catalog import catalog
from mission_control.personal_agent_profiles import operating_guide
from mission_control.creative_taste import guidance
from mission_control.operator_client import OperatorClient
from tests import test_agent_cli as cli_fixture
from tests import test_agent_mcp as mcp_fixture


APP=dict(id='sample-one',version=1,data=dict(name='Synthetic app',job='Evaluate current retention'))


class GuideTests(unittest.TestCase):
    def test_six_primary_documented_profiles_classify_unknown_connections(self):
        guide=discovery(APP)['personal_agent_guide'];rows=guide['profiles']
        self.assertEqual({r['id'] for r in rows},{'grok-bot','meta-muse','instinct','hark-pro','codex-dots','claude-duet'})
        self.assertEqual(len(rows),6)
        domains={'grok-bot':{'docs.x.ai','x.ai'},'meta-muse':{'research.meta.ai','introducing.muse.ai','platform.muse.ai'},
                 'instinct':{'instinct.com'},'hark-pro':{'hark.com'},
                 'codex-dots':{'learn.chatgpt.com','help.openai.com'},'claude-duet':{'claude.com'}}
        for row in rows:
            self.assertTrue(row['verified']);self.assertTrue(row['unknown'])
            self.assertTrue(row['instruction']);self.assertTrue(row['result'])
            for source in row['sources']:
                self.assertEqual(urlsplit(source).scheme,'https')
                self.assertIn(urlsplit(source).hostname,domains[row['id']])
        self.assertEqual(rows[0]['route'],'CONDITIONAL_APPROVED_LOCAL_COMMAND')
        self.assertTrue(all(r['route'].startswith('BLOCKED_') for r in rows[1:4]+rows[5:]))
        self.assertEqual(rows[4]['route'],'CONDITIONAL_CONNECTED_COMPUTER_TASK')
        self.assertFalse(guide['execution_authority']);self.assertFalse(guide['connection_verified'])
        self.assertEqual(guide['live_provider_acceptance'],'NOT_RUN')

    def test_owner_protocol_and_team_handoff_survive_real_discovery_without_authority(self):
        guide=discovery(APP)['personal_agent_guide']
        protocol=guide['owner_operating_protocol']
        self.assertEqual(protocol,operating_manifest(APP)['owner_operating_protocol'])
        viral=protocol['creative_rules']['viral_only']
        self.assertEqual((viral['minimum_views'],viral['minimum_creator_baseline_multiple'],viral['combination']),(100000,10,'AND'))
        self.assertTrue(viral['ugc_intake_exempt'])
        self.assertEqual(len({r['wmm_runbook']['first_action'] for r in guide['profiles']}),6)
        team=guide['team_operating_contract']
        self.assertEqual(team['authority'],'ADVISORY_ONLY')
        self.assertIn('distinct authenticated human',team['review'])
        self.assertIn('resource_ids_and_revisions',team['handoff_fields'])
        self.assertEqual(guide['other_hosts']['route'],'CAPABILITY_VERIFICATION_REQUIRED')
        # A consumer cannot mutate another app/agent's fresh contract in process.
        guide['profiles'][0]['wmm_runbook']['context']='tampered'
        guide['owner_operating_protocol']['creative_rules']['viral_only']['minimum_views']=1
        fresh=discovery(APP)['personal_agent_guide']
        self.assertNotEqual(fresh['profiles'][0]['wmm_runbook']['context'],'tampered')
        self.assertEqual(fresh['owner_operating_protocol']['creative_rules']['viral_only']['minimum_views'],100000)

    def test_current_app_policy_catalog_and_output_changes_invalidate_guide_hash(self):
        value=discovery(APP);guide=value['personal_agent_guide']
        self.assertEqual(guide['scope']['app_hash'],digest(APP['data']))
        self.assertEqual(guide['scope']['policy_sha256'],digest(operating_manifest(APP)))
        self.assertEqual(guide['implemented_catalog'],catalog())
        self.assertEqual(guide['unimplemented_execution'],operating_manifest(APP)['unimplemented_execution'])
        for change in (dict(APP,id='sample-two'),dict(APP,version=2),dict(APP,data=dict(APP['data'],job='Changed objective'))):
            self.assertNotEqual(discovery(change)['personal_agent_guide']['guide_sha256'],guide['guide_sha256'])
        policy=operating_manifest(APP);current_catalog=catalog()
        self.assertNotEqual(operating_guide(APP,dict(policy,policy_version=999),current_catalog)['guide_sha256'],guide['guide_sha256'])
        self.assertNotEqual(operating_guide(APP,policy,dict(current_catalog,changed=True))['guide_sha256'],guide['guide_sha256'])
        altered=copy.deepcopy(guide);del altered['guide_sha256']
        self.assertEqual(digest(altered),guide['guide_sha256'])
        guide['profiles'][0]['sources'].append('untrusted')
        self.assertNotIn('untrusted',discovery(APP)['personal_agent_guide']['profiles'][0]['sources'])

    def test_discovery_is_offline_and_instructions_do_not_expand_authority(self):
        with patch('builtins.open',side_effect=AssertionError('No private file reads')), \
             patch('socket.create_connection',side_effect=AssertionError('No network')), \
             patch('subprocess.run',side_effect=AssertionError('No agent invocation')):
            guide=discovery(APP)['personal_agent_guide']
        self.assertEqual(guide['brief']['objective'],APP['data']['job'])
        self.assertIn('at most three',guide['brief']['questions'])
        self.assertIn('current sources',guide['brief']['reasoning'])
        self.assertIn('current grants and checkpoints',guide['brief']['execution'])
        self.assertIn('UNKNOWN',json.dumps(guide['authority_rules']))
        self.assertIn('never automatically resend',json.dumps(guide['authority_rules']))
        self.assertEqual(guide['result_contract']['status'],['COMPLETE','FAILED','BLOCKED','UNKNOWN'])
        self.assertIn('source_kpis_or_unavailable_reason',guide['result_contract']['required'])
        self.assertEqual(guide['creative_handoff']['source_id'],'creative_taste')

    def test_actual_taste_policy_and_public_preferences_remain_advisory_and_app_bound(self):
        app=dict(APP,data=dict(APP['data'],brand_voice='Plain and honest',audience='Founders',private_fixture='EXCLUDED'))
        handoff=discovery(app)['personal_agent_guide']['creative_handoff']
        self.assertEqual(handoff['policy'],guidance())
        self.assertEqual(handoff['policy_sha256'],guidance()['policy_sha256'])
        self.assertEqual(len(handoff['policy']['five_laws']),5)
        self.assertEqual(handoff['public_preferences']['brand_voice'],'Plain and honest')
        self.assertNotIn('private_fixture',handoff['public_preferences'])
        self.assertEqual(handoff['authority'],'ADVISORY_ONLY')
        self.assertEqual(handoff['execution_status'],'REQUIRED_NOT_COMPLETE')
        self.assertEqual(handoff['app_hash'],digest(app['data']))


class GuideHTTPCLITests(unittest.TestCase):
    setUp=cli_fixture.AgentCLITests.setUp
    tearDown=cli_fixture.AgentCLITests.tearDown
    cli=cli_fixture.AgentCLITests.cli
    call=cli_fixture.AgentCLITests.call

    def test_actual_http_and_cli_return_same_app_scoped_guide(self):
        http=OperatorClient(self.origin).call(dict(app_id='sample-one',operation='operations.read',input={}))
        result,cli=self.call('operations.read')
        self.assertEqual(result.returncode,0)
        self.assertEqual(http['personal_agent_guide'],cli['personal_agent_guide'])
        self.assertEqual(http['personal_agent_guide']['creative_handoff']['policy_sha256'],guidance()['policy_sha256'])
        self.assertEqual(len(cli['personal_agent_guide']['creative_handoff']['policy']['five_laws']),5)
        self.assertEqual(http['personal_agent_guide']['scope']['app_id'],'sample-one')
        other=self.call('operations.read',app='sample-two')[1]
        self.assertNotEqual(other['personal_agent_guide']['guide_sha256'],http['personal_agent_guide']['guide_sha256'])


@unittest.skipUnless(mcp_fixture.HAS_MCP,'Official MCP SDK required')
class GuideMCPTests(unittest.IsolatedAsyncioTestCase):
    setUp=cli_fixture.AgentCLITests.setUp
    tearDown=cli_fixture.AgentCLITests.tearDown
    session=mcp_fixture.MCPSubprocessTests.session
    tool=mcp_fixture.MCPSubprocessTests.tool
    data=mcp_fixture.MCPSubprocessTests.data

    async def test_actual_stdio_operations_read_contains_guide(self):
        async with self.session() as client:
            guide=self.data(await self.tool(client,'operations.read'))['personal_agent_guide']
            expected=discovery(self.store.app('sample-one'))['personal_agent_guide']
            self.assertEqual(guide,expected)
            self.assertEqual(guide['creative_handoff']['policy_sha256'],guidance()['policy_sha256'])
            self.assertEqual(len(guide['creative_handoff']['policy']['five_laws']),5)
            self.assertEqual(guide['live_provider_acceptance'],'NOT_RUN')


if __name__=='__main__':unittest.main()
