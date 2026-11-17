"""Private report HTTP and real background worker retain owner authority."""

import json
import unittest
from datetime import timedelta
from sqlite3 import Connection
from unittest.mock import patch

from mission_control import campaign_owner_reports as reports
from mission_control.apple_analytics import CAMPAIGN_DOWNLOADS
from mission_control.apple_analytics_parser import parse_instance
from mission_control.apple_metrics_store import _reconcile
from mission_control.common import canonical, digest
from mission_control.db import connection
from mission_control.operator_client import ClientError, OperatorClient
from mission_control.server import owner_domain_post
from mission_control.store import Store
from mission_control.worker import Runner
from tests import test_campaign_owner_reports as report_fixtures
from tests import test_campaign_schedule as schedule_fixtures
from tests.test_apple_campaign_attribution import COLUMNS, segment
from tests.test_verified_review import OWNER_TOKEN


class ScheduledCampaignJourneyTests(unittest.TestCase):
    def test_scheduled_launch_restart_pause_and_owner_report_share_the_same_intent(self) -> None:
        """Run the three independent approvals against one durable synthetic campaign."""
        fixture = schedule_fixtures.ScheduleTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.addCleanup(fixture.tearDown)
        # The reused gateway setup installs these on its unittest instance.
        store, client = (vars(fixture)[name] for name in ("store", "owner"))
        assert isinstance(store, Store) and isinstance(client, OperatorClient)
        app = "sample-one"
        monitor_base = f"/api/apps/{app}/campaign-monitor/"
        report_base = f"/api/apps/{app}/campaign-owner-reports/"
        scope, due, request = fixture.paid_fixture()
        with connection(store.path) as db:
            db.execute(
                "UPDATE social_connections SET expires=? WHERE app_id=? AND id=?",
                ((due + timedelta(hours=2)).timestamp(), app, scope["connection_id"]),
            )
        scope_id = scope["scope_id"]
        draft = fixture.owner_call(
            "schedule-prepare",
            {
                "scope_id": scope_id,
                "items": [{"due_at": due.isoformat(), "operation": "campaign.ad-launch", "request": request}],
            },
        )
        batch_id = draft["summary"]["batch_id"]
        fixture.owner_call("schedule-activate", {"batch_id": batch_id, "summary_hash": draft["summary_hash"]})
        agreement = client.request(
            "POST",
            f"/api/apps/{app}/agent-grants/agreement-preview",
            {
                "manifest_version": store.app(app)["version"],
                "workflow_policy_id": None,
                "campaign_scope_id": scope_id,
                "schedule_batch_id": batch_id,
            },
        )
        assert isinstance(agreement, dict)
        self.assertFalse(agreement["summary"]["execution_authority"])
        self.assertEqual(agreement["summary"]["schedule"]["id"], batch_id)
        client.request("POST", "/api/identity/logout", {})
        self.assertEqual(fixture.wire.objects, {})

        with patch("time.time", return_value=due.timestamp() + 1):
            self.assertTrue(Runner(Store(store.path)).poll())
            self.assertFalse(Runner(Store(store.path)).poll())
        self.assertEqual(len(fixture.wire.objects), 4)
        self.assertEqual(fixture.wire.counter, 1004)
        client.request("POST", "/api/identity/login", {"token": OWNER_TOKEN})
        item = fixture.owner_call("schedule-status", {"batch_id": batch_id})["items"][0]
        self.assertEqual(item["effective_status"], "ACTIVE_VERIFIED")
        intent_id = item["intent"]["id"]
        current = fixture.owner_call("status", {"scope_id": scope_id})
        intent = next(row for row in current["intents"] if row["id"] == intent_id)
        campaign_id = intent["ids"]["campaign"]
        monitor = client.request(
            "POST",
            monitor_base + "prepare",
            {
                "proposal": {
                    "scope_id": scope_id,
                    "targets": [{"intent_id": intent["id"], "request_hash": intent["request_hash"]}],
                    "cadence_seconds": 30,
                    "expires_at": (due + timedelta(minutes=10)).isoformat(),
                    "max_runs": 1,
                    "max_provider_units": 30,
                    "max_pause_attempts": 1,
                    "protective_conditions": ["configuration_drift"],
                }
            },
        )
        assert isinstance(monitor, dict)
        client.request(
            "POST",
            monitor_base + "activate",
            {"monitor_id": monitor["id"], "summary_hash": monitor["summary_hash"]},
        )
        client.request("POST", "/api/identity/logout", {})
        fixture.wire.objects[intent["ids"]["adset"]]["lifetime_budget"] += 1
        with (
            patch("mission_control.campaign_transport.MetaTransport", return_value=fixture.wire),
            patch.object(fixture.wire, "set_paid_status", wraps=fixture.wire.set_paid_status) as provider_status,
        ):
            self.assertTrue(Runner(Store(store.path)).poll())
            self.assertFalse(Runner(Store(store.path)).poll())
        with connection(store.path) as db:
            monitor_job = db.execute(
                "SELECT status,result FROM jobs WHERE app_id=? AND action='campaign_monitor'", (app,)
            ).fetchone()
        self.assertEqual(monitor_job["status"], "SUCCEEDED", monitor_job["result"])
        self.assertEqual(
            [call.args[:3] for call in provider_status.call_args_list], [("campaign", campaign_id, "PAUSED")]
        )

        client.request("POST", "/api/identity/login", {"token": OWNER_TOKEN})
        plan = client.request(
            "POST",
            report_base + "prepare",
            {
                "proposal": {
                    "selection": {
                        "scope_id": scope_id,
                        "monitor_id": monitor["id"],
                        "experiment_id": None,
                        "measurement_window": {
                            "starts_at": (due - timedelta(days=1)).isoformat(),
                            "ends_at": (due + timedelta(days=1)).isoformat(),
                        },
                    },
                    "cadence_seconds": 30,
                    "expires_at": (due + timedelta(minutes=10)).isoformat(),
                    "max_reports": 1,
                }
            },
        )
        assert isinstance(plan, dict)
        client.request("POST", report_base + "activate", {"plan_id": plan["id"], "summary_hash": plan["summary_hash"]})
        client.request("POST", "/api/identity/logout", {})
        self.assertTrue(Runner(Store(store.path)).poll())
        self.assertFalse(Runner(Store(store.path)).poll())
        with connection(store.path) as db:
            jobs_seen = {
                action: (count, status)
                for action, count, status in db.execute(
                    "SELECT action,count(*),min(status) FROM jobs WHERE app_id=? GROUP BY action", (app,)
                )
            }
            stored = db.execute("SELECT * FROM campaign_owner_reports WHERE app_id=?", (app,)).fetchall()
        for action in ("campaign_ad", "campaign_monitor", "campaign_owner_report"):
            self.assertEqual(jobs_seen[action], (1, "SUCCEEDED"))
        self.assertEqual(len(stored), 1)
        with self.assertRaises(ClientError):
            client.request("POST", report_base + "history", {})
        saved = reports.report_view(stored[0])
        client.request("POST", "/api/identity/login", {"token": OWNER_TOKEN})
        reread = client.request("POST", report_base + "read", {"report_id": saved["id"]})
        assert isinstance(reread, dict)
        self.assertEqual(reread["hash"], saved["hash"])
        self.assertEqual(saved["plan_id"], plan["id"])
        report = saved["report"]
        ad = next(row for row in report["campaign"]["receipts"] if row["kind"] == "AD")
        self.assertEqual(ad["id"], intent["id"])
        self.assertEqual(ad["pause_readback"]["effective_status"], "PAUSED")
        self.assertEqual(report["campaign"]["retained_commitment_minor"], 80)
        self.assertEqual(report["campaign"]["outcome_attribution"], "NOT_ESTABLISHED")
        self.assertFalse(report["authority_issued"])
        for private in ("synthetic-token", "synthetic-secret", "credential_ref"):
            self.assertNotIn(private, canonical(reread))


class ReportIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.f = report_fixtures.CampaignOwnerReportsTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.store = self.f.store
        self.client = self.f.fixture.client
        self.base = "/api/apps/sample/campaign-owner-reports/"

    def test_actual_owner_router_and_logged_out_worker_report(self) -> None:
        self.assertEqual(
            owner_domain_post(["api", "apps", "sample", "campaign-owner-reports", "history"]).__module__,
            "mission_control.campaign_owner_reports",
        )
        plan = self.f.plan()
        # Isolate local report generation from the separately approved provider monitor.
        with connection(self.store.path) as db:
            db.execute("UPDATE campaign_monitors SET status='OFF'")
        self.client.request("POST", "/api/identity/logout", {})
        self.assertTrue(self.f.fixture.server.runner.poll())
        with connection(self.store.path) as db:
            job = db.execute("SELECT * FROM jobs WHERE action='campaign_owner_report'").fetchone()
            self.assertEqual(job["status"], "SUCCEEDED")
            self.assertEqual(json.loads(job["result"]), {"status": "PRIVATE_REPORT_SAVED"})
            retained = db.execute("SELECT * FROM campaign_owner_reports WHERE app_id=?", ("sample",)).fetchall()
        self.assertEqual(len(retained), 1)
        saved = reports.report_view(retained[0])
        self.assertEqual(saved["report"]["visibility"], "PRIVATE_OWNER_ONLY")
        self.assertFalse(saved["report"]["authority_issued"])
        self.assertEqual(saved["plan_id"], plan["id"])
        self.assertIn("owner_reports", self.f.fixture.server.runner.health["components"])

    def test_real_http_capture_read_and_off_report_plan(self) -> None:
        body = {"selection": self.f.chosen(), "request_key": "88888888-8888-4888-8888-888888888888"}
        saved = self.client.request("POST", self.base + "capture", body)
        assert isinstance(saved, dict)
        reread = self.client.request("POST", self.base + "read", {"report_id": saved["id"]})
        assert isinstance(reread, dict)
        self.assertEqual(saved["hash"], reread["hash"])
        plan = self.f.plan()
        off = self.client.request("POST", self.base + "off", {"plan_id": plan["id"], "version": plan["version"]})
        assert isinstance(off, dict)
        self.assertEqual(off["status"], "OFF")
        self.assertEqual(reports.tick(self.store), 0)

    def test_owner_can_capture_receipts_without_a_monitor(self) -> None:
        chosen = self.f.chosen(monitor_id=None)
        with connection(self.store.path) as db:
            db.execute("DELETE FROM campaign_monitors")
        body = {"selection": chosen, "request_key": "99999999-9999-4999-8999-999999999999"}
        with patch.object(reports, "last_observation", side_effect=AssertionError("No monitor selected")):
            saved = self.client.request("POST", self.base + "capture", body)
            replay = self.client.request("POST", self.base + "capture", body)
        assert isinstance(saved, dict) and isinstance(replay, dict)
        self.assertEqual(saved["hash"], replay["hash"])
        report = saved["report"]
        self.assertEqual(report["monitor"]["status"], "NOT_SELECTED")
        self.assertIsNone(report["monitor"]["last_observation"])
        self.assertIsNone(report["source"]["monitor_hash"])
        self.assertTrue(report["campaign"]["receipts"])
        self.assertEqual(report["campaign"]["provider_readback"], "NOT_PERFORMED")
        self.assertFalse(report["authority_issued"])
        with connection(self.store.path) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM campaign_monitors").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT count(*) FROM campaign_owner_reports").fetchone()[0], 1)

    def test_apple_report_uses_the_exact_saved_post_and_mature_rows(self) -> None:
        link = "https://apps.apple.com/app/apple-store/id123456789?pt=123456&ct=apple-owner-fixture&mt=8"
        dates = dict(starts_at="2026-01-01T00:00:00+00:00", ends_at="2026-01-03T00:00:00+00:00")
        plan = dict(
            dates,
            link=link,
            campaign_tag="apple-owner-fixture",
            measurement_source="APPLE_APP_DOWNLOADS",
            primary_metric="apple_first_time_downloads",
            denominator="none",
            hypothesis="The exact tested campaign supplies a reported count.",
            decision_rule="Use two mature US rows.",
        )
        selection = self.f.chosen(monitor_id=None, measurement_window=dates, apple_storefront="US")
        scope_id = selection["scope_id"]
        key = dict(
            app_id="sample",
            store_app_id="123456789",
            connection_id="synthetic-connection",
            connection_version=1,
            report_id="synthetic-report",
            report_family=CAMPAIGN_DOWNLOADS,
            granularity="DAILY",
        )
        with connection(self.store.path) as db:
            scope = db.execute(
                "SELECT summary FROM campaign_scopes WHERE app_id=? AND id=?", ("sample", scope_id)
            ).fetchone()
            summary = json.loads(scope["summary"])
            summary.update(measurement_plan=plan, ad_account_id=None)
            db.execute(
                "UPDATE campaign_scopes SET summary=?,summary_hash=? WHERE app_id=? AND id=?",
                (canonical(summary), digest(summary), "sample", scope_id),
            )
            db.execute("DELETE FROM campaign_paid_intents WHERE app_id=?", ("sample",))
            db.execute("DELETE FROM campaign_intents WHERE app_id=?", ("sample",))
            self.add_apple_fixture(db, key, "2026-01-01", "2026-01-03", 0)
            self.add_apple_fixture(db, key, "2026-01-02", "2026-01-03", 8)

        with (
            patch(
                "mission_control.apple_owner_outcome.source",
                return_value=(1, "123456789", {"id": "synthetic-connection", "version": 1}),
            ),
            patch(
                "mission_control.apple_owner_outcome.inventory",
                return_value=(
                    {"coverage": "COMPLETE"},
                    [{"name": CAMPAIGN_DOWNLOADS, "coverage": "COMPLETE", "id": "synthetic-report"}],
                ),
            ),
        ):
            without_post = self.f.capture(selection)["report"]["apple_downloads"]
            self.assertEqual(without_post["status"], "DELIVERY_UNVERIFIED")
            self.assertIsNone(without_post["first_time_downloads"])
            with connection(self.store.path) as db:
                db.execute(
                    "INSERT INTO campaign_intents VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        "sample",
                        "synthetic-post",
                        scope_id,
                        "synthetic-request",
                        digest("request"),
                        summary["approved_content_hashes"][0],
                        summary["approved_rights_hashes"][0],
                        summary["page_id"],
                        "VERIFIED",
                        "123_456",
                        canonical(dict(id="123_456", destination_check={"approved_link_sha256": digest(link)})),
                        "2026-01-01T17:00:00+00:00",
                        "2026-01-01T17:01:00+00:00",
                    ),
                )
            incomplete = self.f.capture(selection)["report"]["apple_downloads"]
            self.assertEqual(incomplete["status"], "INCOMPLETE")
            self.assertIsNone(incomplete["first_time_downloads"])
            self.assertEqual([row["evidence_status"] for row in incomplete["rows"]], ["READY_TO_REVIEW", "PROVISIONAL"])
            with connection(self.store.path) as db:
                db.execute("BEGIN IMMEDIATE")
                self.add_apple_fixture(db, key, "2026-01-02", "2026-01-04", 5)
            observed = self.f.capture(selection)["report"]["apple_downloads"]
            self.assertEqual(observed["status"], "REPORTED")
            self.assertEqual(observed["first_time_downloads"], 5)
            self.assertEqual([row["first_time_downloads"] for row in observed["rows"]], [0, 5])
            self.assertTrue(all(row["source_sha256"] for row in observed["rows"]))
            self.assertEqual(observed["delivery"]["status"], "EXACT_TAGGED_POST_READBACK")
            other_store = self.f.capture(dict(selection, apple_storefront="CA"))["report"]["apple_downloads"]
            self.assertIsNone(other_store["first_time_downloads"])
            self.assertTrue(all(row["evidence_status"] == "NO_MATCH" for row in other_store["rows"]))
            wrong_dates = dict(dates, ends_at="2026-01-04T00:00:00+00:00")
            wrong = self.f.capture(dict(selection, measurement_window=wrong_dates))["report"]["apple_downloads"]
            self.assertIsNone(wrong["first_time_downloads"])
            self.assertEqual(wrong["status"], "WINDOW_MISMATCH")

    @staticmethod
    def add_apple_fixture(db: Connection, key: dict[str, str | int], event: str, processing: str, count: int) -> None:
        fixture = COLUMNS + f"{event}\t123456789\tFirst-time Download\t{count}\tapple-owner-fixture\tUS\tfixture\n"
        parsed = parse_instance("123456789", processing, [segment(fixture)], True, CAMPAIGN_DOWNLOADS)
        _reconcile(db, dict(key, event_date=event), parsed)


if __name__ == "__main__":
    unittest.main()
