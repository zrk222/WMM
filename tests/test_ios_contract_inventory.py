"""Shared framing checks; these are not simulator or device acceptance."""
import json
import subprocess
import sys
import unittest

from mission_control.common import Invalid
from mission_control.ios_bridge import DomainBridge, decode_request, encode_response, MAX_REQUEST_BYTES
from mission_control.ios_capabilities import inventory
from mission_control.operation_catalog import OPERATIONS


class IOSBridgeTests(unittest.TestCase):
    def test_inventory_tracks_all_operations_and_never_claims_native_support(self):
        value = inventory()
        self.assertEqual(value['operations'], OPERATIONS)
        self.assertGreaterEqual(value['operation_count'], 53)
        self.assertFalse(value['full_parity'])
        self.assertEqual(value['native_acceptance'], 'NOT_RUN')
        value['operations'].clear()
        self.assertTrue(inventory()['operations'])

    def test_import_does_not_load_desktop_services(self):
        command = 'import sys; import mission_control.ios_bridge, mission_control.ios_capabilities; assert not ({"mission_control.service", "mission_control.server", "mission_control.credential_vault", "mission_control.agent_native"} & set(sys.modules))'
        subprocess.run([sys.executable, '-c', command], check=True)

    def test_fixed_envelope_round_trip(self):
        seen = []
        bridge = DomainBridge(lambda envelope: seen.append(envelope) or {'queued': False})
        envelope = {'app_id': 'sample-app', 'operation': 'workspace.read', 'input': {}}
        self.assertEqual(json.loads(bridge.call(json.dumps(envelope).encode())), {'queued': False})
        self.assertEqual(seen, [envelope])

    def test_invalid_input_never_reaches_dispatch(self):
        seen = []
        bridge = DomainBridge(lambda envelope: seen.append(envelope))
        invalid = [b'', b'\xff', b'{}', b'{"app_id":"sample","app_id":"foreign"}',
                   b'{"app_id":"sample","operation":"shell","input":{}}',
                   b'{"app_id":"sample","operation":"workspace.read","input":{},"role":"OWNER"}',
                   b'{"app_id":"sample","operation":"workspace.read","input":{"x":NaN}}',
                   b' ' * (MAX_REQUEST_BYTES + 1)]
        for payload in invalid:
            with self.subTest(payload=payload[:100]), self.assertRaises(Invalid):
                bridge.call(payload)
        self.assertEqual(seen, [])

    def test_authority_denial_is_preserved(self):
        def deny(envelope):
            raise PermissionError('No current native identity')
        with self.assertRaises(PermissionError):
            DomainBridge(deny).call(b'{"app_id":"sample","operation":"workspace.read","input":{}}')

    def test_results_are_finite_json(self):
        for value in (float('nan'), object()):
            with self.assertRaises(Invalid):
                encode_response(value)
        with self.assertRaises(TypeError):
            DomainBridge(None)


if __name__ == '__main__':
    unittest.main()
