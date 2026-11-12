"""Real existing queue retention of goal drafts; synthetic apps, no provider calls."""

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from mission_control.automatic_preparation import GOAL_STAGES, goal_request
from mission_control.common import Invalid, digest
from mission_control.service import Service
from mission_control.store import Store
from mission_control.worker import jobs, run_once


class GoalPacketHistoryTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / "state.sqlite"
        self.store = Store(self.path)
        self.service = Service(self.store)

    def request(self, goal="research", app="sample-one"):
        view = self.service.workspace(app)
        value = dict(goal=goal, manifest_version=view["app"]["version"], source_hash=view["preparation"]["source_hash"])
        return dict(
            action="pipeline",
            data=dict(stage=0, goal_packet=value),
            request_key="goal-packet-" + goal + "-" + value["source_hash"],
        )

    def test_all_goal_subsets_persist_after_store_restart_and_duplicate_save(self):
        for goal, stages in GOAL_STAGES.items():
            body = self.request(goal)
            job = self.service.queue("sample-one", body)
            self.assertEqual(job["id"], self.service.queue("sample-one", body)["id"])
            with patch("urllib.request.urlopen", side_effect=AssertionError("No provider calls")):
                run_once(self.store)
            restarted = Store(self.path)
            saved = next(row for row in jobs(restarted, "sample-one") if row["id"] == job["id"])
            self.assertEqual(saved["status"], "SUCCEEDED", saved["result"])
            packet = saved["result"]["goal_packet"]
            self.assertEqual(tuple(row["stage"] for row in packet["outputs"]), stages)
            self.assertEqual(packet["source_hash"], body["data"]["goal_packet"]["source_hash"])
            self.assertEqual(saved["result"]["goal_packet_hash"], digest(packet))
            self.assertTrue(packet["created_at"])
            self.assertEqual(packet["classification"], "LOCAL_DRAFT_NO_AUTHORITY")
            self.assertEqual(saved["result"]["external_execution"], "NOT_RUN")
            self.assertEqual(saved["result"]["spend_minor"], 0)
            self.assertEqual(len(saved["result"]["outputs"]), 12)
        self.assertEqual(len(jobs(self.store, "sample-one")), 4)
        self.assertEqual(jobs(self.store, "sample-two"), [])

    def test_changed_app_or_evidence_blocks_saved_output_without_retry(self):
        for change in ("app", "evidence"):
            with self.subTest(change=change):
                body = self.request()
                job = self.service.queue("sample-one", body)
                if change == "app":
                    app = self.store.app("sample-one")
                    self.store.save_app("sample-one", dict(app["data"], name="Changed synthetic app"), app["version"])
                else:
                    self.service.evidence(
                        "sample-one",
                        dict(
                            kind="learning",
                            title="New synthetic observation",
                            source="Synthetic",
                            data=dict(
                                change="Changed", heldout_test="Synthetic", rollback="Synthetic", result="NOT_RUN"
                            ),
                        ),
                    )
                run_once(self.store)
                saved = next(row for row in jobs(self.store, "sample-one") if row["id"] == job["id"])
                self.assertEqual(saved["status"], "BLOCKED")
                self.assertNotIn("goal_packet", saved["result"])
                self.assertIn("App or evidence changed", saved["result"]["error"])
                self.assertEqual(saved["attempts"], 1)

    def test_closed_inputs_reject_forged_outputs_and_invalid_bindings_before_queue(self):
        base = self.request()
        for field, invalid in [
            ("goal", "unknown"),
            ("goal", []),
            ("manifest_version", True),
            ("manifest_version", 0),
            ("source_hash", "A" * 64),
            ("source_hash", ""),
        ]:
            body = deepcopy(base)
            body["data"]["goal_packet"][field] = invalid
            with self.subTest(field=field, invalid=invalid), self.assertRaises(Invalid):
                self.service.queue("sample-one", body)
        for extra in (
            {"goal_packet": dict(base["data"]["goal_packet"], outputs=[])},
            {"stage": 6},
            {"stage": True},
            {"unexpected": True},
        ):
            data = dict(base["data"], **extra)
            with self.assertRaises(Invalid):
                goal_request(data)
        self.assertEqual(jobs(self.store, "sample-one"), [])

    def test_foreign_app_hash_cannot_be_saved_as_its_packet(self):
        job = self.service.queue("sample-two", self.request())
        run_once(self.store)
        row = next(x for x in jobs(self.store, "sample-two") if x["id"] == job["id"])
        self.assertEqual(row["status"], "BLOCKED")
        self.assertEqual(jobs(self.store, "sample-one"), [])


if __name__ == "__main__":
    unittest.main()
