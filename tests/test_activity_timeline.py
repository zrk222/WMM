"""Unified local activity chronology: exact links, filters, paging and privacy."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import tempfile
import unittest
from mission_control.common import Invalid
from mission_control.db import connection
from mission_control.store import Store
from mission_control.service import Service
from mission_control.activity_timeline import read, KINDS

APP = "sample-one"
OTHER = "sample-two"
BASE = datetime(2026, 11, 1, tzinfo=timezone.utc)


def at(seconds):
    return (BASE + timedelta(seconds=seconds)).isoformat()


class ActivityTimelineTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.store = Store(Path(self.folder.name) / "test.sqlite", seed=False)
        self.store.save_app(
            APP,
            dict(
                name="Synthetic app",
                release="build-1",
                job="Synthetic job",
                audience="Synthetic audience",
                activation="Synthetic value",
                locale="en-US",
            ),
        )
        self.store.save_app(
            OTHER,
            dict(
                name="Other app",
                release="build-2",
                job="Other job",
                audience="Other audience",
                activation="Other value",
                locale="en-US",
            ),
        )
        with connection(self.store.path) as db:
            db.execute("DELETE FROM audit")

    def execute(self, sql, values):
        with connection(self.store.path) as db:
            db.execute(sql, values)

    def audit(self, action, detail, created):
        self.execute(
            "INSERT INTO audit(app_id,action,detail,created) VALUES(?,?,?,?)",
            (APP, action, json.dumps(detail), created),
        )

    def job(self, identity, action, status, created, app=APP):
        self.execute(
            "INSERT INTO jobs(id,app_id,action,data,status,created,updated,request_key) VALUES(?,?,?,?,?,?,?,?)",
            (identity, app, action, "{}", status, created, created, "request-" + identity),
        )

    def approval(self, identity, status, created, value_hash="b" * 64):
        self.execute(
            "INSERT INTO approvals(id,app_id,packet,hash,preparer,status,expires,created) VALUES(?,?,?,?,?,?,?,?)",
            (identity, APP, "{}", value_hash, "owner", status, created, created),
        )

    def review(self, identity, status, created, value_hash="c" * 64):
        self.execute(
            "INSERT INTO verified_reviews(id,app_id,packet,hash,preparer,status,expires,created) VALUES(?,?,?,?,?,?,?,?)",
            (identity, APP, "{}", value_hash, "owner", status, created, created),
        )

    def action(self, identity, status, created, value_hash="d" * 64):
        self.execute(
            "INSERT INTO provider_actions(id,app_id,target_key,packet,hash,preparer,status,expires,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (identity, APP, "target", "{}", value_hash, "owner", status, created, created, created),
        )

    def grant(self, identity, status, created, token_hash="e" * 64):
        self.execute(
            "INSERT INTO agent_grants(id,app_id,agent_id,owner,owner_version,app_version,app_hash,operations,token_hash,expires,max_calls,used,status,version,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                identity,
                APP,
                "agent",
                "owner",
                1,
                1,
                "a" * 64,
                "[]",
                token_hash,
                created,
                20,
                0,
                status,
                1,
                created,
                created,
            ),
        )

    def source(self, identity, created, value_hash="f" * 64):
        self.execute(
            "INSERT INTO insight_sources(app_id,id,provider,data,hash,scope_key,credential_ref,version,status,lease,next_due,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (APP, "source", "posthog", "{}", "a" * 64, "scope", "credential", 1, "ACTIVE", 0, 0, created, created),
        )
        self.execute(
            "INSERT INTO insight_reports(app_id,id,source_id,provider,data,hash,created) VALUES(?,?,?,?,?,?,?)",
            (APP, identity, "source", "posthog", "{}", value_hash, created),
        )

    def events(self, **kwargs):
        return read(self.store, APP, **kwargs)["events"]

    def test_chronology_is_app_scoped_and_newest_first(self):
        self.job("job-1", "sync", "SUCCEEDED", at(10), app=OTHER)
        self.job("job-2", "sync", "SUCCEEDED", at(20))
        self.audit("workspace.saved", {"version": 2}, at(30))
        self.approval("approval-1", "PENDING", at(40))
        self.source("report-1", at(50))
        result = read(self.store, APP)
        self.assertEqual(result["schema"], "growth.activity-timeline.v1")
        self.assertEqual(result["app_id"], APP)
        self.assertEqual([item["at"] for item in result["events"]], [at(50), at(40), at(30), at(20)])
        self.assertNotIn("job-1", json.dumps(result["events"]))
        self.assertEqual(result["coverage"]["counts"]["JOB"], 1)
        self.assertEqual(result["coverage"]["counts"]["SOURCE_READ"], 1)
        self.assertTrue(result["complete"])

    def test_exact_stored_reference_links_and_absent_or_ambiguous_stays_absent(self):
        self.job("job-1", "sync", "SUCCEEDED", at(1))
        self.audit("job.succeeded", {"id": "job-1", "result_hash": "a" * 64}, at(2))
        self.audit("evidence.saved", {"id": "missing", "hash": "b" * 64}, at(3))
        events = self.events()
        linked = next(item for item in events if item["action"] == "job.succeeded")
        self.assertEqual(linked["caused_by"], ["JOB:job-1"])
        self.assertEqual(linked["receipt"]["sha256"], "a" * 64)
        absent = next(item for item in events if item["action"] == "evidence.saved")
        self.assertEqual(absent["caused_by"], [])
        self.action("job-1", "SUBMITTED", at(4))
        ambiguous = next(item for item in self.events() if item["action"] == "job.succeeded")
        self.assertEqual(ambiguous["caused_by"], [])

    def test_closed_event_schema_never_discloses_payloads(self):
        self.job("job-1", "sync", "SUCCEEDED", at(1))
        self.audit("job.succeeded", {"id": "job-1", "result_hash": "a" * 64, "secret": "do-not-leak"}, at(2))
        self.grant("grant-1", "ACTIVE", at(5), token_hash="f" * 64)
        encoded = json.dumps(self.events())
        self.assertNotIn("do-not-leak", encoded)
        self.assertNotIn("f" * 64, encoded)
        for item in self.events():
            self.assertEqual(set(item), {"id", "kind", "action", "status", "at", "receipt", "caused_by"})
            self.assertEqual(set(item["receipt"]), {"kind", "id", "sha256"})

    def test_kind_and_status_filters_reject_unknown_values(self):
        self.job("job-1", "sync", "QUEUED", at(1))
        self.approval("approval-1", "PENDING", at(2))
        self.review("review-1", "VERIFIED", at(3))
        self.assertEqual({item["kind"] for item in self.events(kind="JOB")}, {"JOB"})
        self.assertEqual({item["status"] for item in self.events(status="PENDING")}, {"PENDING"})
        self.assertEqual(self.events(kind="JOB", status="PENDING"), [])
        for kwargs in ({"kind": "NOPE"}, {"status": "pending"}, {"status": "PENDING "}, {"limit": 0}, {"limit": 201}):
            with self.subTest(kwargs=kwargs), self.assertRaises(Invalid):
                read(self.store, APP, **kwargs)
        with self.assertRaises(Invalid):
            read(self.store, APP, cursor="not-a-cursor")
        with self.assertRaises(Invalid):
            read(self.store, APP, cursor="e30")  # {}

    def test_cursor_pagination_is_stable_complete_and_lossless(self):
        for index in range(25):
            self.audit("workspace.saved", {"version": index}, at(index))
        first = read(self.store, APP, limit=10)
        self.assertEqual(len(first["events"]), 10)
        self.assertFalse(first["complete"])
        self.assertIsNotNone(first["next_cursor"])
        second = read(self.store, APP, limit=10, cursor=first["next_cursor"])
        third = read(self.store, APP, limit=10, cursor=second["next_cursor"])
        self.assertEqual(len(third["events"]), 5)
        self.assertTrue(third["complete"])
        self.assertIsNone(third["next_cursor"])
        paged = first["events"] + second["events"] + third["events"]
        self.assertEqual(
            [item["id"] for item in paged], [item["id"] for item in read(self.store, APP, limit=200)["events"]]
        )
        self.assertEqual(len({item["id"] for item in paged}), 25)
        self.assertEqual(read(self.store, APP, limit=10), read(self.store, APP, limit=10))

    def test_workspace_exposes_the_same_first_page(self):
        self.job("job-1", "sync", "SUCCEEDED", at(1))
        workspace = Service(self.store).workspace(APP)
        self.assertEqual(workspace["activity_timeline"]["schema"], "growth.activity-timeline.v1")
        self.assertEqual(
            [item["id"] for item in workspace["activity_timeline"]["events"]],
            [item["id"] for item in read(self.store, APP)["events"]],
        )

    def test_agent_catalog_exposes_one_filtered_read(self):
        from mission_control.operation_catalog import request_data, catalog

        value = request_data(
            {"app_id": APP, "operation": "activity.history", "input": {"kind": "JOB", "status": "QUEUED", "limit": 10}}
        )
        self.assertEqual(value["method"], "GET")
        self.assertEqual(value["path"], "/api/apps/" + APP + "/activity/history?kind=JOB&status=QUEUED&limit=10")
        self.assertIsNone(value["body"])
        self.assertIn("activity.history", catalog()["operations"])
        with self.assertRaises(Invalid):
            request_data({"app_id": APP, "operation": "activity.history", "input": {"offset": 1}})

    def test_mcp_tool_is_read_only_and_closed(self):
        from mission_control.agent_mcp import tool_definitions

        tool = next(item for item in tool_definitions() if item["name"] == "wmm_activity_history")
        self.assertTrue(tool["annotations"]["readOnlyHint"])
        self.assertFalse(tool["annotations"]["destructiveHint"])
        self.assertEqual(
            set(tool["inputSchema"]["properties"]["input"]["properties"]), {"kind", "status", "cursor", "limit"}
        )

    def test_unknown_app_is_denied(self):
        with self.assertRaises(KeyError):
            read(self.store, "sample-three")


if __name__ == "__main__":
    unittest.main()
