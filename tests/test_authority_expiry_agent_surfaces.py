"""Existing CLI/MCP inspection carries deadline metadata without owner powers."""
import io
import json
import unittest
from unittest.mock import patch

from mission_control.agent_cli import main
from mission_control.agent_mcp import execute_tool, tool_definitions
from mission_control.common import Invalid
from mission_control.operator_client import OperatorClient
from mission_control.marketing_agent_manifest import owner_operating_protocol


class ExpiryAgentSurfaceTests(unittest.TestCase):
    def setUp(self):
        self.token = 'wmmg_' + 'a' * 43
        self.envelope = dict(operation='operations.read', app_id='sample-one', input={})
        self.result = dict(agent_authority=dict(grant_id='grant-one', effective_expires='2027-01-01T00:00:00+00:00',
                                                used=4, max_calls=10, remaining_calls=6, consent_revision=2))

    def test_existing_cli_inspection_retains_current_authority_metadata(self):
        output = io.StringIO()
        with patch('mission_control.agent_cli.grant_environment', return_value=self.token), \
                patch('mission_control.agent_cli.OperatorClient') as client:
            client.return_value.call.return_value = self.result
            status = main(['call', '--origin', 'http://127.0.0.1:12345', '--use-grant'],
                          stdin=io.BytesIO(json.dumps(self.envelope).encode()), stdout=output, stderr=io.StringIO())
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(output.getvalue()), self.result)
        self.assertNotIn(self.token, output.getvalue())

    def test_existing_mcp_inspection_retains_metadata_and_never_adds_owner_confirmation(self):
        with patch('mission_control.agent_mcp.OperatorClient') as client:
            client.return_value.call.return_value = self.result
            result = execute_tool('http://127.0.0.1:12345', 'wmm_operations_read',
                                  dict(app_id='sample-one', input={}), self.token)
        self.assertEqual(result, self.result)
        self.assertFalse(any('expiry_confirm' in row['name'] for row in tool_definitions(True)))
        with self.assertRaises(Invalid):
            execute_tool('http://127.0.0.1:12345', 'wmm_authority_expiry_confirm', {}, self.token)

    def test_scoped_transport_cannot_reach_owner_extension_routes(self):
        client = OperatorClient('http://127.0.0.1:12345', self.token)
        for action in ('preview', 'confirm', 'history'):
            with self.subTest(action=action), self.assertRaises(Invalid):
                client.request('POST', '/api/apps/sample-one/authority-expiry/' + action,
                               dict(principal='owner', extended_expiry_consent=True))

    def test_manifest_distinguishes_permission_readiness_and_remaining_accounting(self):
        lifetime = owner_operating_protocol()['permission_lifetime']
        self.assertEqual(lifetime['default_hours'], 24)
        self.assertIn('remaining calls', lifetime['inspect'])
        self.assertIn('cannot consent', lifetime['proposal'])
        self.assertIn('does not reset', lifetime['accounting'])
        self.assertIn('retain their own deadlines', lifetime['independent_clocks'])


if __name__ == '__main__':
    unittest.main()
