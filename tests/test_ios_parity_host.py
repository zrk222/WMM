"""Exercise fixed native host entry points; fixtures are not device evidence."""
import json
import unittest
from tests import test_ios_automation as standing
from mission_control.common import Invalid


class NativeParityHostTests(unittest.TestCase):
    setUp = standing.NativeStandingTests.setUp
    verify = standing.NativeStandingTests.verify
    creation = standing.NativeStandingTests.creation
    setup_standing = standing.NativeStandingTests.setup_standing
    proposal = standing.NativeStandingTests.proposal
    vault = standing.NativeStandingTests.vault
    def test_host_standing_queue_run_and_reopen_receipts(self):
        self.setup_standing()
        self.runtime.vault_callback = self.vault
        preview = json.loads(self.runtime.native_automation(self.session, 'new-app', 'preview',
            json.dumps(self.proposal(['pipeline_preparation'])).encode()))
        issued = json.loads(self.runtime.native_automation(self.session, 'new-app', 'activate',
            json.dumps(dict(proposal=preview['proposal'], summary_hash=preview['summary_hash'], confirm_scope=True)).encode()))
        request = json.dumps(dict(app_id='new-app', operation='pipeline.prepare',
            input=dict(action='pipeline', data=dict(stage=0), request_key='native-host-parity'))).encode()
        queued = json.loads(self.runtime.native_agent_call(self.session, issued['token'], request))
        result = json.loads(self.runtime.native_jobs(self.session, 'new-app', 'run', json.dumps(dict(id=queued['id'])).encode()))
        self.assertEqual(result['status'], 'SUCCEEDED')
        monitor = json.loads(self.runtime.native_jobs(self.session, 'new-app', 'monitor', b'{}'))
        self.assertEqual(monitor['runs'][0]['processed_stages'], 12)
        self.assertEqual(monitor['runs'][0]['status'], 'SUCCEEDED')
        self.assertNotIn(issued['token'], json.dumps(monitor))
        self.available = False
        with self.assertRaises(PermissionError):
            self.runtime.native_agent_call(self.session, issued['token'], request)

    def test_host_cannot_claim_studio_completion_from_normal_action_json(self):
        self.setup_standing()
        with self.assertRaises(Invalid):
            self.runtime.native_studio(self.session, 'new-app', 'finish',
                json.dumps(dict(job_id='made-up', packet_hash='a'*64, inspection=dict(frames=48))).encode())
