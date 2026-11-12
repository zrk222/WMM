"""Actual owner router, original campaign policy and Runner monitor integration.

The tests exercise retained_check through original policy_checker; direct
monitor actor forgery and unrelated campaign effects are denied.
"""

from datetime import datetime, timedelta, timezone
import json
import multiprocessing
import os
from pathlib import Path
import threading
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request

from mission_control import campaign_monitor as monitor
from mission_control.campaign_access import policy_checker
from mission_control.campaign_execution import CampaignExecutionService
from mission_control.common import canonical, now
from mission_control.db import connection
from mission_control.operator_client import OperatorClient, ClientError
from mission_control.server import Server, owner_domain_post
from mission_control.social_contract import configuration
from mission_control.store import Store
from mission_control.worker import (
    Runner,
    claim,
    failed_result,
    process_special,
    run_once,
)
from tests import test_campaign_execution as fixture


MONITOR_CRASH_EXIT = 73


def poll_monitor_process(path, provider_objects, mutations, interrupt_after_pause):
    """Child process with a synthetic provider and no access to live credentials."""
    wire = fixture.FakePaidTransport()
    wire.objects = provider_objects

    def pause(kind, identity, value, token, secret, alive):
        alive()
        wire.objects[identity]["status"] = value
        with Path(mutations).open("a", encoding="utf-8") as recorded:
            recorded.write(canonical(dict(kind=kind, identity=identity, status=value)) + "\n")
        if interrupt_after_pause:
            os._exit(MONITOR_CRASH_EXIT)
        raise AssertionError("The replacement process tried a second provider mutation")

    wire.set_paid_status = pause
    with (
        patch.object(
            CampaignExecutionService,
            "_credentials",
            return_value=({}, "fixture-secret", {"access_token": "fixture-token"}),
        ),
        patch(
            "mission_control.campaign_transport.MetaTransport.request",
            side_effect=AssertionError("Live provider forbidden"),
        ),
        patch("socket.getaddrinfo", side_effect=AssertionError("Network lookup forbidden")),
        patch("mission_control.campaign_transport.MetaTransport", return_value=wire),
    ):
        Runner(Store(path)).poll()


class CampaignMonitorIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture.PaidTests("test_paid_lifecycle_and_pause")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.store = self.fixture.store
        self.wire = self.fixture.transport
        self.scope = self.fixture.paid_scope
        self.intent = self.fixture.service.run_ad("sample", "owner", self.scope["scope_id"], self.fixture.adbody)
        with connection(self.store.path) as db:
            db.execute("UPDATE social_connections SET expires=?", (time.time() + 7200,))
        self.mocks = [
            patch(
                "mission_control.operator_identity.github_read",
                return_value=dict(
                    principal="owner",
                    login="owner",
                    provider="GITHUB",
                    verified_at=now(),
                ),
            ),
            patch.object(
                CampaignExecutionService,
                "_credentials",
                return_value=(
                    {},
                    "synthetic-secret",
                    dict(access_token="synthetic-token"),
                ),
            ),
            patch(
                "mission_control.campaign_transport.MetaTransport.request",
                side_effect=AssertionError("Live provider forbidden"),
            ),
            patch(
                "mission_control.campaign_transport.MetaTransport",
                return_value=self.wire,
            ),
        ]
        for mock in self.mocks:
            mock.start()
            self.addCleanup(mock.stop)
        self.server = Server(("127.0.0.1", 0), self.store)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)
        self.client = OperatorClient("http://127.0.0.1:" + str(self.server.server_port))
        self.client.bootstrap()
        self.client.request("POST", "/api/identity/login", dict(token="synthetic_owner_identity_token"))
        self.base = "/api/apps/sample/campaign-monitor/"

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def body(self):
        return dict(
            scope_id=self.scope["scope_id"],
            targets=[
                dict(
                    intent_id=self.intent["id"],
                    request_hash=self.intent["request_hash"],
                )
            ],
            cadence_seconds=30,
            expires_at=(datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
            max_runs=2,
            max_provider_units=30,
            max_pause_attempts=1,
            protective_conditions=["configuration_drift"],
        )

    def activate(self):
        saved = self.client.request("POST", self.base + "prepare", dict(proposal=self.body()))
        return self.client.request(
            "POST",
            self.base + "activate",
            dict(monitor_id=saved["id"], summary_hash=saved["summary_hash"]),
        )

    def job(self):
        with connection(self.store.path) as db:
            row = db.execute(
                "SELECT * FROM jobs WHERE action='campaign_monitor' ORDER BY created DESC LIMIT 1"
            ).fetchone()
            return dict(row) if row else None

    def test_real_owner_domain_post_and_protected_http_contract(self):
        self.assertEqual(
            owner_domain_post(["api", "apps", "sample", "campaign-monitor", "history"]).__module__,
            "mission_control.campaign_monitor_http",
        )
        anonymous = OperatorClient(self.client.origin)
        anonymous.bootstrap()
        with self.assertRaises(ClientError):
            anonymous.request("POST", self.base + "history", {})
        with self.assertRaises(ClientError):
            self.client.request(
                "POST",
                self.base + "prepare",
                dict(proposal=self.body(), owner="forged"),
            )
        for headers in (
            {"Origin": "http://foreign.invalid"},
            {"X-CSRF-Token": "wrong"},
        ):
            req = Request(
                self.client.origin + self.base + "history",
                data=b"",
                method="POST",
                headers={
                    "Origin": self.client.origin,
                    "X-CSRF-Token": self.client.csrf,
                    "Content-Type": "application/json",
                    **headers,
                },
            )
            with self.assertRaises(HTTPError) as denied:
                self.client.opener.open(req, timeout=10)
            self.assertEqual(denied.exception.code, 403)
        active = self.activate()
        status = self.client.request("POST", self.base + "status", dict(monitor_id=active["id"]))
        self.assertEqual(status["effective_status"], "ACTIVE")
        self.assertEqual(len(self.client.request("POST", self.base + "history", {})["monitors"]), 1)

    def test_actual_runner_poll_after_owner_session_closed_verifies_protective_pause(
        self,
    ):
        active = self.activate()
        self.client.request("POST", "/api/identity/logout", {})
        self.wire.objects[self.intent["ids"]["adset"]]["lifetime_budget"] = 999
        original_checker = policy_checker(self.store)
        with self.assertRaises(PermissionError):
            original_checker("sample", "owner", self.scope, "RECONCILE")
        actors = []
        from mission_control import campaign_monitor_authority as authority

        original = authority.check

        def record(store, app, actor, scope, action):
            actors.append((actor, action))
            return original(store, app, actor, scope, action)

        with patch.object(authority, "check", side_effect=record):
            self.assertTrue(self.server.runner.poll())
        job = self.job()
        self.assertEqual(job["status"], "SUCCEEDED")
        self.assertEqual(
            json.loads(job["result"])["observations"][0]["protective_pause"],
            "PAUSED_campaign",
        )
        self.assertTrue(actors)
        self.assertTrue(all(actor.startswith("monitor:") for actor, action in actors))
        self.assertTrue(all(action in ("RECONCILE", "PAUSE") for actor, action in actors))
        result = self.fixture.service.list_intents("sample", self.scope["scope_id"])[0]
        self.assertEqual(result["status"], "PAUSED_campaign")
        self.assertEqual(result["commitment"], 80)
        with connection(self.store.path) as db:
            row = db.execute(
                "SELECT pauses,units,status FROM campaign_monitors WHERE id=?",
                (active["id"],),
            ).fetchone()
            self.assertEqual((row["pauses"], row["units"], row["status"]), (1, 8, "ACTIVE"))
        self.assertIn("campaign_monitor", self.server.runner.health["components"])

    def test_live_background_thread_operates_without_browser_or_owner_session(self):
        self.activate()
        self.client.request("POST", "/api/identity/logout", {})
        runner = self.server.runner
        runner.start()
        try:
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                job = self.job()
                if job and job["status"] in ("SUCCEEDED", "BLOCKED"):
                    break
                time.sleep(0.03)
            self.assertEqual(self.job()["status"], "SUCCEEDED")
            self.assertEqual(self.wire.objects[self.intent["ids"]["campaign"]]["status"], "ACTIVE")
        finally:
            runner.stop()
        self.assertEqual(runner.health["status"], "STOPPED")

    def test_fresh_runner_recovers_active_monitor_and_does_not_replay_lost_pause(self):
        active = self.activate()
        self.client.request("POST", "/api/identity/logout", {})
        self.wire.objects[self.intent["ids"]["adset"]]["lifetime_budget"] = 999
        status_calls = []

        def lost(kind, identity, value, token, secret, alive):
            alive()
            status_calls.append(value)
            self.wire.objects[identity]["status"] = value
            raise TimeoutError("Synthetic lost protective pause reply")

        with patch.object(self.wire, "set_paid_status", side_effect=lost):
            restored = Runner(Store(self.store.path))
            self.assertTrue(restored.poll())
            recovered = Runner(Store(self.store.path))
            recovered.retry_failed()
            recovered.poll()
        job = self.job()
        self.assertEqual(job["status"], "BLOCKED")
        self.assertEqual(json.loads(job["result"])["status"], "BLOCKED")
        self.assertEqual(status_calls, ["PAUSED"])
        with connection(self.store.path) as db:
            saved = db.execute(
                "SELECT id,summary_hash,pauses,status FROM campaign_monitors WHERE id=?", (active["id"],)
            ).fetchone()
            self.assertEqual(
                (saved["id"], saved["summary_hash"], saved["pauses"], saved["status"]),
                (active["id"], active["summary_hash"], 1, "BLOCKED"),
            )
            events = [
                row["code"] for row in db.execute("SELECT code FROM workflow_events WHERE job_id=?", (job["id"],))
            ]
            self.assertEqual(events, ["STARTED", "BLOCKED"])
            self.assertEqual(
                db.execute("SELECT count(*) FROM jobs WHERE action='campaign_monitor'").fetchone()[0],
                1,
            )
        current = self.fixture.service.list_intents("sample", self.scope["scope_id"])[0]
        self.assertEqual((current["status"], current["commitment"]), ("UNKNOWN", 80))

    def test_expired_monitor_job_lease_and_exception_never_auto_replay(self):
        self.activate()
        monitor.tick(self.store)
        job = claim(self.store)
        with connection(self.store.path) as db:
            db.execute("UPDATE jobs SET lease=0 WHERE id=?", (job["id"],))
        self.assertIsNone(claim(self.store))
        self.assertEqual(self.job()["status"], "BLOCKED")
        self.assertEqual(json.loads(self.job()["result"]), monitor.interrupted_result())
        result, status, delay = failed_result(job, TimeoutError("Synthetic uncertain operation"))
        self.assertEqual((status, delay), ("BLOCKED", 0))
        self.assertNotIn("Synthetic uncertain operation", canonical(result))

    def test_abrupt_monitor_process_exit_after_pause_holds_effect_on_restart(self):
        active = self.activate()
        self.client.request("POST", "/api/identity/logout", {})
        self.wire.objects[self.intent["ids"]["adset"]]["lifetime_budget"] = 999
        mutations = self.store.path.parent / "synthetic-monitor-mutations.jsonl"
        spawn = multiprocessing.get_context("spawn")

        def poll_in_fresh_process(interrupt, expected_exit):
            process = spawn.Process(
                target=poll_monitor_process, args=(self.store.path, self.wire.objects, mutations, interrupt)
            )
            process.start()
            try:
                process.join(timeout=30)
                self.assertFalse(process.is_alive(), "Monitor acceptance process timed out")
                self.assertEqual(process.exitcode, expected_exit)
            finally:
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=5)
                process.close()

        poll_in_fresh_process(True, MONITOR_CRASH_EXIT)
        interrupted = self.job()
        self.assertEqual(interrupted["status"], "RUNNING")
        self.assertIsNone(interrupted["result"])
        # Advance only the isolated fixture deadlines to exercise expired recovery.
        with connection(self.store.path) as db:
            db.execute("UPDATE jobs SET lease=0 WHERE id=?", (interrupted["id"],))
            db.execute("UPDATE campaign_monitors SET due=0 WHERE id=?", (active["id"],))

        poll_in_fresh_process(False, 0)
        resumed = self.job()
        self.assertEqual((resumed["id"], resumed["status"], resumed["attempts"]), (interrupted["id"], "BLOCKED", 1))
        self.assertEqual(json.loads(resumed["result"]), monitor.interrupted_result())
        self.assertEqual(
            [json.loads(line) for line in mutations.read_text(encoding="utf-8").splitlines()],
            [dict(kind="campaign", identity=self.intent["ids"]["campaign"], status="PAUSED")],
        )
        with connection(self.store.path) as db:
            saved = db.execute(
                "SELECT summary_hash,pauses,status FROM campaign_monitors WHERE id=?", (active["id"],)
            ).fetchone()
            self.assertEqual(
                (saved["summary_hash"], saved["pauses"], saved["status"]), (active["summary_hash"], 1, "BLOCKED")
            )
            self.assertEqual(db.execute("SELECT count(*) FROM jobs WHERE action='campaign_monitor'").fetchone()[0], 1)
        intent = self.fixture.service.list_intents("sample", self.scope["scope_id"])[0]
        self.assertEqual(
            (intent["id"], intent["status"], intent["commitment"]), (self.intent["id"], "PENDING_PAUSED_campaign", 80)
        )
        self.client.request("POST", "/api/identity/login", dict(token="synthetic_owner_identity_token"))
        receipt = self.client.request("POST", self.base + "status", dict(monitor_id=active["id"]))
        self.assertEqual(
            (receipt["last_observation"]["job_id"], receipt["last_observation"]["external_execution"]),
            (interrupted["id"], "MONITOR_INTERRUPTED_UNCONFIRMED"),
        )

    def test_only_exact_monitor_action_changes_normal_return_status_mapping(self):
        self.activate()
        monitor.tick(self.store)
        with patch("mission_control.worker.process", return_value=dict(status="BLOCKED")):
            self.assertTrue(run_once(self.store))
        self.assertEqual(self.job()["status"], "BLOCKED")
        with connection(self.store.path) as db:
            db.execute(
                "INSERT INTO jobs(id,app_id,action,data,status,created,updated,request_key) VALUES(?,?,?,?,?,?,?,?)",
                (
                    "ordinary-blocked-value",
                    "sample",
                    "pipeline",
                    "{}",
                    "QUEUED",
                    now(),
                    now(),
                    "ordinary-blocked-value",
                ),
            )
        with patch("mission_control.worker.process", return_value=dict(status="BLOCKED")):
            self.assertTrue(run_once(self.store))
        with connection(self.store.path) as db:
            self.assertEqual(
                db.execute("SELECT status FROM jobs WHERE id='ordinary-blocked-value'").fetchone()[0],
                "SUCCEEDED",
            )

    def test_original_organic_preflight_identity_boundaries_charge_exact_monitor_quota(
        self,
    ):
        organic = self.fixture.service.list_intents("sample", self.fixture.scope["scope_id"])[0]
        proposal = dict(
            self.body(),
            scope_id=self.fixture.scope["scope_id"],
            targets=[dict(intent_id=organic["id"], request_hash=organic["request_hash"])],
            protective_conditions=[],
            max_pause_attempts=0,
        )
        draft = self.client.request("POST", self.base + "prepare", dict(proposal=proposal))
        active = self.client.request(
            "POST",
            self.base + "activate",
            dict(monitor_id=draft["id"], summary_hash=draft["summary_hash"]),
        )
        self.client.request("POST", "/api/identity/logout", {})
        calls = []
        permissions = [
            "public_profile",
            "pages_manage_posts",
            "pages_show_list",
            "pages_read_engagement",
        ]
        page = dict(
            id="123",
            name="Synthetic Page",
            tasks=["CREATE_CONTENT"],
            access_token="synthetic-page-token",
        )

        def social(provider, operation, fields, bearer=None, alive=lambda: None):
            alive()
            # A real concurrent write proves admission finished its transaction.
            with connection(self.store.path) as db:
                db.execute("UPDATE apps SET updated=updated WHERE id='sample'")
            calls.append(operation)
            return {
                "app_token": dict(access_token="synthetic-app-token"),
                "inspect": dict(
                    data=dict(
                        is_valid=True,
                        app_id="12345",
                        user_id="subject",
                        scopes=permissions,
                    )
                ),
                "identity": dict(id="subject", name="Synthetic owner"),
                "permissions": dict(data=[dict(permission=value, status="granted") for value in permissions]),
                "pages": dict(data=[page]),
                "page_identity": dict(id="123", name="Synthetic Page"),
            }[operation]

        config = configuration(
            dict(
                provider="facebook",
                client_id="12345",
                client_secret="synthetic-secret",
                native_enabled=False,
                redirect_uri="https://relay.example/cb/facebook",
                version=0,
                campaign_access="publish",
            )
        )
        self.assertEqual(config["campaign_access"], "publish")
        self.assertIn("pages_manage_posts", config["scopes"])
        credentials = (
            config,
            "synthetic-secret",
            dict(access_token="synthetic-user-token", page_token="synthetic-page-token"),
        )
        with (
            patch.object(CampaignExecutionService, "_credentials", return_value=credentials),
            patch("mission_control.social_profiles.request", side_effect=social),
        ):
            self.assertTrue(self.server.runner.poll())
        self.assertEqual(
            calls,
            [
                "app_token",
                "inspect",
                "identity",
                "permissions",
                "pages",
                "pages",
                "page_identity",
            ],
        )
        self.assertEqual(self.job()["status"], "SUCCEEDED")
        with connection(self.store.path) as db:
            self.assertEqual(
                db.execute("SELECT units FROM campaign_monitors WHERE id=?", (active["id"],)).fetchone()[0],
                8,
            )
        self.assertEqual(self.wire.posts, 1)

    def test_off_cancels_queued_work_and_original_policy_rejects_forged_actor(self):
        active = self.activate()
        monitor.tick(self.store)
        self.client.request(
            "POST",
            self.base + "off",
            dict(monitor_id=active["id"], version=active["version"]),
        )
        self.assertEqual(self.job()["status"], "CANCELLED")
        self.assertFalse(run_once(self.store))
        check = policy_checker(self.store)
        for actor in ("owner", "monitor:invented-job"):
            with self.assertRaises(PermissionError):
                check("sample", actor, self.scope, "PAUSE")

    def test_process_special_routes_monitor_without_changing_campaign_routes(self):
        with patch(
            "mission_control.campaign_monitor.execute",
            return_value=dict(status="OBSERVED"),
        ) as execute:
            self.assertEqual(
                process_special(self.store, dict(action="campaign_monitor"), None),
                dict(status="OBSERVED"),
            )
            execute.assert_called_once()
        with patch(
            "mission_control.campaign_schedule.execute",
            return_value=dict(status="VERIFIED"),
        ) as execute:
            self.assertEqual(
                process_special(self.store, dict(action="campaign_post"), None),
                dict(status="VERIFIED"),
            )
            execute.assert_called_once()


if __name__ == "__main__":
    unittest.main()
