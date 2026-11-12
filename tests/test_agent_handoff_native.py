"""Embedded Python host handoffs use the same grant and job records."""

from datetime import datetime, timedelta, timezone
import json
import unittest
from mission_control.worker import enqueue
from tests import test_ios_agent_access as fixture
from tests import test_ios_host as host


class NativeHandoffTests(unittest.TestCase):
    setUp = host.NativeRuntimeTests.setUp
    verify = host.NativeRuntimeTests.verify
    creation = host.NativeRuntimeTests.creation
    manage = fixture.NativeAgentAccessTests.manage
    issue = fixture.NativeAgentAccessTests.issue

    def test_native_owner_and_scoped_agent_share_original_job(self):
        issued = self.issue(operations=["handoff.resume", "jobs.read"], agent_id="replacement")
        job = enqueue(self.runtime.service.store, "new-app", "pipeline", dict(stage=2), "private-native-key")
        saved = self.manage(
            "handoff-create",
            dict(
                job_id=job["id"],
                recipient="replacement",
                operations=["jobs.read"],
                expires=(datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat(),
            ),
        )
        self.assertEqual(self.manage("handoff-list")["handoffs"][0]["job_id"], job["id"])
        request = dict(
            app_id="new-app",
            operation="handoff.resume",
            resource_id=saved["id"],
            input=dict(version=saved["version"], payload_hash=saved["payload_hash"]),
        )
        result = json.loads(self.runtime.native_agent_call(self.session, issued["token"], json.dumps(request).encode()))
        self.assertEqual(result["resume"], "RESUME_ADMITTED")
        self.assertEqual(result["job_id"], job["id"])
        self.assertNotIn("private-native-key", json.dumps(result))
        self.available = False
        with self.assertRaises(PermissionError):
            self.runtime.native_agent_call(self.session, issued["token"], json.dumps(request).encode())


if __name__ == "__main__":
    unittest.main()
