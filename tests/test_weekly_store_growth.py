"""Exercise the owner's App Store decisions from real scoped SQLite rows."""

import tempfile
import unittest
from pathlib import Path
from typing import cast

from mission_control.apple_analytics import DISCOVERY, DOWNLOADS
from mission_control.common import canonical, now
from mission_control.db import connection
from mission_control.growth_review_store import GrowthReviews
from mission_control.service import Service
from mission_control.store import Store
from mission_control.weekly_inbox import operation_exceptions
from tests.test_market_research import intent_fixture


class WeeklyStoreGrowthTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.store = Store(Path(temporary.name) / "weekly.sqlite", seed=False)
        data = dict(name="App", release="build-1", locale="en-US", store_app_id="123")
        self.store.save_app("first-app", data)
        self.store.save_app("other", dict(data, store_app_id="999"))
        with connection(self.store.path) as db:
            for app, principal, role in (
                ("first-app", "owner", "OWNER"),
                ("first-app", "maker", "MAKER"),
                ("other", "owner", "OWNER"),
            ):
                db.execute(
                    "INSERT INTO operator_roles VALUES(?,?,?,?,?,?,?,?)",
                    (app, principal, principal, role, "ACTIVE", 1, now(), "fixture"),
                )

    def research(self, missing_demand: bool = False) -> None:
        body = cast(dict, intent_fixture())
        body["manifest_version"] = self.store.app("first-app")["version"]
        snapshot = body["data"]["snapshot"]
        snapshot["observed_at"] = now()
        for item in snapshot["sources"]:
            item["retrieved_at"] = snapshot["observed_at"]
        if missing_demand:
            for item in snapshot["intent_clusters"]:
                item["evidence"]["demand"] = []
        GrowthReviews(self.store).save("first-app", body)

    def cards(self, app_id: str = "first-app", principal: str = "owner") -> list[dict]:
        cards = operation_exceptions(self.store, self.store.app(app_id), {"principal": principal})
        return [card for card in cards if card["category"] == "store_growth"]

    def test_one_scoped_action_no_writes_or_private_query_text(self) -> None:
        self.research(missing_demand=True)
        with connection(self.store.path) as db:
            before = db.execute("SELECT count(*) FROM jobs").fetchone()[0]
        first = self.cards()
        self.assertEqual(len(first), 1)
        card = first[0]
        self.assertTrue(card["owner_only"])
        self.assertEqual(card["state"], "RESEARCH_EVIDENCE_NEEDED")
        self.assertEqual(card["evidence"]["action_code"], "COLLECT_QUERY_EVIDENCE")
        self.assertIn("Apple Ads search-term report", card["next_action"])
        self.assertNotIn("offline trail planner", str(card))
        self.assertEqual(
            (self.cards()[0]["id"], self.cards()[0]["source_receipt"]["source_hash"]),
            (card["id"], card["source_receipt"]["source_hash"]),
        )
        self.assertEqual(self.cards("other"), [])
        self.assertEqual(self.cards(principal="maker"), [])
        self.assertEqual(self.cards(principal="outsider"), [])
        with connection(self.store.path) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM jobs").fetchone()[0], before)
            self.assertEqual(db.execute("SELECT count(*) FROM growth_review_entries").fetchone()[0], 1)

    def test_report_files_change_the_action_without_claiming_a_baseline(self) -> None:
        self.research()
        self.assertEqual(self.cards()[0]["state"], "BASELINE_CONNECTION_NEEDED")
        record = Service(self.store).evidence(
            "first-app",
            dict(
                kind="connection",
                title="Apple",
                source="fixture",
                data=dict(
                    provider="app_store", store_app_id="123", env_ref="GROWTH_FIRST_APP_SYNTHETIC", account_id="0"
                ),
            ),
        )
        expected = self.cards()[0]
        self.assertEqual(expected["state"], "BASELINE_REPORTS_NEEDED")
        request = dict(
            manifest_version=1,
            connection_id=record["id"],
            connection_version=record["version"],
            connection_hash=record["hash"],
            options={"operation": "analytics_reports"},
        )
        response = dict(
            operation="analytics_reports",
            provider="app_store",
            app_id="first-app",
            store_app_id="123",
            status="METRIC_DOWNLOAD_REQUIRED",
            coverage="COMPLETE",
            observed_at=now(),
            reports=[
                dict(id=f"report-{i}", name=name, coverage="COMPLETE", instances=[{}])
                for i, name in enumerate((DISCOVERY, DOWNLOADS))
            ],
        )
        with connection(self.store.path) as db:
            db.execute(
                "INSERT INTO jobs(id,app_id,action,data,status,result,created,updated,request_key) VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    "inventory",
                    "first-app",
                    "sync",
                    canonical(request),
                    "SUCCEEDED",
                    canonical(response),
                    now(),
                    now(),
                    "inventory",
                ),
            )
        ready = self.cards()[0]
        self.assertEqual(ready["state"], "FREEZE_STORE_BASELINE")
        self.assertNotEqual(ready["id"], expected["id"])
        self.assertIn("not yet verified", ready["reason"])
        self.assertEqual(ready["resolution_route"], "connections")
        self.assertIn("before seeking approval", ready["next_action"])

    def test_changed_manifest_and_damaged_saved_research_fail_closed(self) -> None:
        self.research()
        app = self.store.app("first-app")
        self.store.save_app("first-app", dict(app["data"], release="build-2"), app["version"])
        self.assertEqual(self.cards()[0]["state"], "RESEARCH_REVIEW_NEEDED")
        with connection(self.store.path) as db:
            db.execute("UPDATE growth_review_entries SET data=? WHERE app_id=?", ("NOT-JSON-PRIVATE", "first-app"))
        result = self.cards()
        self.assertEqual(result[0]["state"], "SOURCE_UNAVAILABLE")
        self.assertNotIn("NOT-JSON-PRIVATE", str(result))

    def test_ready_research_without_store_identifier_names_the_exact_setup_gap(self) -> None:
        app = self.store.app("first-app")
        self.store.save_app("first-app", dict(app["data"], store_app_id=""), app["version"])
        self.research()
        card = self.cards()[0]
        self.assertEqual(card["state"], "STORE_IDENTITY_NEEDED")
        self.assertIn("Apple ID", card["next_action"])
