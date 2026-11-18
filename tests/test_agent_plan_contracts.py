"""The owner plan and prerequisite receipts survive the existing agent routes."""

import json
import unittest
from datetime import datetime, timedelta, timezone
from typing import Any, cast

from mission_control.agent_operations import discovery
from mission_control.db import connection
from mission_control.operator_client import ClientError, OperatorClient
from mission_control.worker import enqueue
from tests import test_agent_grants as grant_fixture
from tests import test_personal_agent_profiles as profile_fixture

APP = "sample-one"


class AgentPlanContractsTests(unittest.TestCase):
    def test_discovery_exposes_dependencies_and_completion_receipts(self) -> None:
        guide = cast(dict[str, Any], discovery(profile_fixture.APP)["personal_agent_guide"])
        assert isinstance(guide, dict)
        plan = guide["owner_operating_protocol"]["action_plan"]
        self.assertTrue(
            {"step_id", "task", "assigned_agent_id", "depends_on", "completion_receipt"} <= set(plan["step_fields"])
        )
        self.assertIn("plan_steps", guide["result_contract"]["owner_summary"])

    def test_prerequisite_receipts_gate_named_continuations_across_domains(self) -> None:
        fixture = grant_fixture.GrantTests()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        store, owner = fixture.store, fixture.owner
        job = enqueue(store, APP, "pipeline", dict(stage=1), "next")
        before = [enqueue(store, APP, action, {}, action) for action in ("sync", "render")]
        dependencies = [item["id"] for item in before]
        foreign = enqueue(store, "sample-two", "pipeline", {}, "foreign")

        def create(prerequisites: list[str]) -> dict[str, Any]:
            result = owner.request(
                "POST",
                f"/api/apps/{APP}/agent-grants/handoff-create",
                dict(
                    job_id=job["id"],
                    depends_on_jobs=prerequisites,
                    recipient="replacement",
                    operations=["jobs.read"],
                    expires=(datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat(),
                ),
            )
            assert isinstance(result, dict)
            return result

        for invalid in ([job["id"]], [foreign["id"]], dependencies * 2):
            with self.assertRaises(ClientError):
                create(invalid)
        saved = create(dependencies)
        self.assertEqual(saved["effective_status"], "WAITING_FOR_DEPENDENCIES")
        target = owner.request(
            "POST",
            f"/api/apps/{APP}/agent-grants/issue",
            dict(fixture.body(["handoff.resume", "jobs.read"]), agent_id="replacement"),
        )
        assert isinstance(target, dict)
        client = OperatorClient(fixture.origin, grant_token=target["token"])
        envelope = dict(
            app_id=APP,
            operation="handoff.resume",
            resource_id=saved["id"],
            input=dict(version=saved["version"], payload_hash=saved["payload_hash"]),
        )
        with self.assertRaises(ClientError):
            client.call(envelope)
        with connection(store.path) as db:
            db.execute(
                "UPDATE jobs SET status='SUCCEEDED',result=? WHERE id=?", ('{"artifact":"private"}', dependencies[0])
            )
            db.execute("UPDATE jobs SET status='SUCCEEDED' WHERE id=?", (dependencies[1],))
        listed = owner.request("POST", f"/api/apps/{APP}/agent-grants/handoff-list", {})
        assert isinstance(listed, dict)
        self.assertEqual(listed["handoffs"][0]["effective_status"], "DEPENDENCY_NEEDS_REVIEW")
        with self.assertRaises(ClientError):
            client.call(envelope)
        with connection(store.path) as db:
            db.execute("UPDATE jobs SET result=? WHERE id=?", ('{"render":"private"}', dependencies[1]))
        resumed = client.call(envelope)
        assert isinstance(resumed, dict)
        self.assertEqual(resumed["effective_status"], "CLAIMED")
        self.assertTrue(all(len(item["result_hash"]) == 64 for item in resumed["dependencies"]))
        self.assertNotIn("private", json.dumps(resumed["dependencies"]))
        with connection(store.path) as db:
            db.execute("UPDATE jobs SET data='{}',request_key='changed' WHERE id=?", (dependencies[0],))
        with self.assertRaises(ClientError):
            client.call(envelope)
