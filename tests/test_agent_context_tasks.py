"""Approved evidence must remain unchanged before and after model inference."""

import unittest
from typing import Any, cast
from unittest.mock import patch

from mission_control.agent_access import AgentAccess
from mission_control.agent_tasks import proposal
from mission_control.common import Invalid, canonical, digest
from mission_control.db import connection
from mission_control.store import Store
from mission_control.worker import run_once
from tests import test_agent_tasks as fixtures
from tests.test_agent_access import answer


class GroundedTaskTests(unittest.TestCase):
    store: Store
    access: AgentAccess
    identity: str
    setUp = fixtures.AgentTaskTests.setUp
    approve = fixtures.AgentTaskTests.approve
    result = fixtures.AgentTaskTests.result

    def ready(self):
        with connection(self.store.path) as db:
            db.execute("UPDATE agent_connections SET status='TESTED' WHERE id=?", (self.identity,))
        self.access.routes("sample-one", dict(version=0, mode="byok", routes={"campaign_plan": self.identity}))

    def change(self):
        self.store.save_record(
            "sample-one", dict(kind="claim", title="Synthetic failure", source="Synthetic", data=dict(result="FAIL"))
        )

    def test_guard_and_guard_context_block_new_evidence_before_request(self):
        self.ready()
        self.approve("campaign_plan")
        self.change()
        with patch("mission_control.agent_tasks.api_run") as run:
            run_once(self.store)
            run.assert_not_called()
        self.assertEqual(self.result()["status"], "BLOCKED")

    def test_live_guard_rejects_new_evidence_during_request(self):
        self.ready()
        self.approve("campaign_plan")

        def provider(*args):
            self.change()
            return answer(), {}

        with patch("mission_control.agent_tasks.api_run", side_effect=provider):
            run_once(self.store)
        self.assertEqual(self.result()["status"], "BLOCKED")
        self.assertNotIn("draft", self.result()["result"])

    def test_connection_test_transmits_no_campaign_sources(self):
        value = cast(
            dict[str, Any],
            proposal(self.store, "sample-one", dict(task="connection_test", focus="", connection_id=self.identity))[
                "proposal"
            ],
        )
        self.assertIsNone(value["context"])
        self.assertEqual(value["source_ids"], [])
        self.assertNotIn("stage_2", value["prompt"])

    def test_missing_approved_context_rejects_even_rehashed_envelope(self):
        self.ready()
        queued = self.approve("campaign_plan")
        data = queued["data"]
        del data["envelope"]["context"]
        data["envelope_hash"] = digest(data["envelope"])
        with connection(self.store.path) as db:
            db.execute("UPDATE jobs SET data=? WHERE id=?", (canonical(data), queued["id"]))
        with patch("mission_control.agent_tasks.api_run") as run:
            run_once(self.store)
            run.assert_not_called()
        self.assertEqual(self.result()["status"], "BLOCKED")

    def test_current_stage_citation_is_accepted_and_other_app_rejected(self):
        self.ready()
        self.approve("campaign_plan")
        response: dict[str, Any] = answer()
        response["items"][0]["source_ids"] = ["stage_2"]
        with patch("mission_control.agent_tasks.api_run", return_value=(response, {})):
            run_once(self.store)
        self.assertEqual(self.result()["status"], "SUCCEEDED")
        self.approve("campaign_plan")
        response["items"][0]["source_ids"] = ["sample-two"]
        with patch("mission_control.agent_tasks.api_run", return_value=(response, {})):
            run_once(self.store)
        self.assertEqual(self.result()["status"], "BLOCKED")

    def test_changed_evidence_keeps_previously_tested_connection_usable(self):
        self.ready()
        self.approve("campaign_plan")
        self.change()
        with patch("mission_control.agent_tasks.api_run") as run:
            run_once(self.store)
            run.assert_not_called()
        self.assertEqual(self.result()["status"], "BLOCKED")
        self.assertEqual(self.access.get("sample-one", self.identity)["status"], "TESTED")
        self.approve("campaign_plan")

    def test_expired_task_does_not_mark_healthy_connection_broken(self):
        self.ready()
        queued = self.approve("campaign_plan")
        data = queued["data"]
        data["envelope"]["expires_at"] = "2020-01-01T00:00:00+00:00"
        data["envelope_hash"] = digest(data["envelope"])
        with connection(self.store.path) as db:
            db.execute("UPDATE jobs SET data=? WHERE id=?", (canonical(data), queued["id"]))
        with patch("mission_control.agent_tasks.api_run") as run:
            run_once(self.store)
            run.assert_not_called()
        self.assertEqual(self.result()["status"], "BLOCKED")
        self.assertEqual(self.access.get("sample-one", self.identity)["status"], "TESTED")

    def test_provider_permission_failure_still_requires_connection_retest(self):
        self.ready()
        self.approve("campaign_plan")
        with patch("mission_control.agent_tasks.api_run", side_effect=Invalid("Provider permission denied")):
            run_once(self.store)
        self.assertEqual(self.result()["status"], "BLOCKED")
        self.assertEqual(self.access.get("sample-one", self.identity)["status"], "NEEDS_ATTENTION")
