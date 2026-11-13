"""Exact finite monitor authority over real SQLite and synthetic provider effects.

API tests exercise check_connection, target_row, eligible and protect through
actual saved source revisions, queue admission and provider guards. Static
Forge name routing is supplemented by executable assertions, not claimed as
behavioral coverage.
"""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import time
import unittest
from unittest.mock import patch

from mission_control import campaign_monitor as core
from mission_control import campaign_monitor_authority as authority
from mission_control.campaign_execution import CampaignExecutionService
from mission_control.common import Invalid, canonical, digest, now
from mission_control.db import connection
from mission_control.operation_authority import bound_owner, protected
from mission_control.worker import claim
from tests import test_campaign_execution as fixtures


class LocalIdentity:
    def local(self, session, principal, generation=None):
        if principal != "owner" or generation not in (None, "fixture-generation"):
            raise PermissionError("Synthetic owner changed")
        return dict(principal="owner", session_generation="fixture-generation")


class CampaignMonitorTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.PaidTests("test_paid_lifecycle_and_pause")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.store = self.fixture.store
        self.wire = self.fixture.transport
        self.scope = self.fixture.paid_scope
        self.intent = self.fixture.service.run_ad("sample", "owner", self.scope["scope_id"], self.fixture.adbody)
        with connection(self.store.path) as db:
            db.execute("UPDATE social_connections SET expires=?", (time.time() + 7200,))
        self.monitors = core.Monitors(self.store)

        # Same narrow check hook root installs in campaign_access.policy_checker.
        def checker(store):
            def verify(app, actor, scope, action):
                if not authority.check(store, app, actor, scope, action):
                    raise PermissionError("Missing retained monitor capability")

            return verify

        mocks = [
            patch("mission_control.campaign_access.policy_checker", side_effect=checker),
            patch.object(
                CampaignExecutionService,
                "_credentials",
                return_value=(
                    {},
                    "synthetic-secret",
                    {"access_token": "synthetic-token"},
                ),
            ),
            patch(
                "mission_control.campaign_transport.MetaTransport.request",
                side_effect=AssertionError("Live provider forbidden"),
            ),
        ]
        for mock in mocks:
            mock.start()
            self.addCleanup(mock.stop)
        self.identities = LocalIdentity()

    @contextmanager
    def owner(self):
        envelope = dict(app_id="sample", operation="campaign.monitor.owner.fixture", input={})
        with bound_owner(self.store, envelope, self.identities, "session", dict(principal="owner")):
            with protected(self.store, envelope):
                yield

    def body(self, **changes):
        return dict(
            dict(
                scope_id=self.scope["scope_id"],
                targets=[
                    dict(
                        intent_id=self.intent["id"],
                        request_hash=self.intent["request_hash"],
                    )
                ],
                cadence_seconds=30,
                expires_at=(datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
                max_runs=3,
                max_provider_units=40,
                max_pause_attempts=1,
                protective_conditions=["configuration_drift"],
            ),
            **changes,
        )

    def activate(self, **changes):
        with self.owner():
            saved = self.monitors.prepare("sample", self.body(**changes))
            return self.monitors.activate("sample", saved["id"], saved["summary_hash"])

    def job(self, **changes):
        monitor = self.activate(**changes)
        self.assertEqual(core.tick(self.store), 1)
        job = claim(self.store)
        self.assertEqual(job["action"], "campaign_monitor")
        return monitor, job

    def status(self, monitor):
        with self.owner():
            return self.monitors.status("sample", monitor["id"])

    def test_prepare_activate_exact_hash_owner_selection_and_finite_plan(self):
        with self.assertRaises(PermissionError):
            self.monitors.prepare("sample", self.body())
        with self.owner():
            saved = self.monitors.prepare("sample", self.body())
            self.assertEqual(saved["status"], "DRAFT")
            with self.assertRaises(Invalid):
                self.monitors.activate("sample", saved["id"], "0" * 64)
            for changes in (
                dict(cadence_seconds=29),
                dict(cadence_seconds=3601),
                dict(max_runs=True),
                dict(max_provider_units=161),
                dict(max_pause_attempts=0),
                dict(protective_conditions=["spend_threshold"]),
                dict(expires_at=(datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()),
                dict(targets=[dict(intent_id=self.intent["id"], request_hash="a" * 64)]),
            ):
                with (
                    self.subTest(changes=changes),
                    self.assertRaises((Invalid, PermissionError)),
                ):
                    self.monitors.prepare("sample", self.body(**changes))
            active = self.monitors.activate("sample", saved["id"], saved["summary_hash"])
            self.assertEqual(active["status"], "ACTIVE")
            self.assertEqual(len(self.monitors.history("sample")["monitors"]), 1)
        with connection(self.store.path) as db:
            row = db.execute(
                "SELECT status FROM campaign_paid_intents WHERE id=?",
                (self.intent["id"],),
            ).fetchone()
        self.assertEqual(row["status"], "ACTIVE_campaign")

    def test_tick_atomic_unique_pending_and_twenty_limit(self):
        monitors = [self.activate() for _ in range(21)]
        with ThreadPoolExecutor(max_workers=2) as pool:
            queued = list(pool.map(lambda _: core.tick(self.store), range(2)))
        self.assertEqual(sum(queued), 21)
        self.assertTrue(all(value <= 20 for value in queued))
        self.assertEqual(core.tick(self.store), 0)
        with connection(self.store.path) as db:
            self.assertEqual(
                db.execute("SELECT count(*) FROM jobs WHERE action='campaign_monitor'").fetchone()[0],
                21,
            )
        self.assertEqual(len(monitors), 21)

    def test_read_reconcile_keeps_hold_and_never_creates_or_activates(self):
        monitor, job = self.job(protective_conditions=[], max_pause_attempts=0)
        before = len(self.wire.objects)
        with (
            patch.object(self.wire, "create_paid", side_effect=AssertionError("No creation")),
            patch.object(
                self.wire,
                "set_paid_status",
                side_effect=AssertionError("No status mutation"),
            ),
        ):
            result = core.execute(self.store, job, self.wire)
        self.assertEqual(result["status"], "OBSERVED")
        self.assertEqual(self.status(monitor)["provider_units"], 5)
        self.assertEqual(self.status(monitor)["pause_attempts"], 0)
        self.assertEqual(len(self.wire.objects), before)
        self.assertEqual(
            self.fixture.service.list_intents("sample", self.scope["scope_id"])[0]["commitment"],
            80,
        )

    def test_fresh_configuration_drift_causes_only_verified_pause_retains_hold(self):
        monitor, job = self.job()
        adset = self.intent["ids"]["adset"]
        self.wire.objects[adset]["lifetime_budget"] = 999
        statuses = []
        original = self.wire.set_paid_status

        def status(kind, identity, value, token, secret, alive):
            statuses.append((kind, value))
            return original(kind, identity, value, token, secret, alive)

        with patch.object(self.wire, "set_paid_status", side_effect=status):
            result = core.execute(self.store, job, self.wire)
        self.assertEqual(result["status"], "OBSERVED")
        self.assertEqual(statuses, [("campaign", "PAUSED")])
        self.assertEqual(result["observations"][0]["protective_pause"], "PAUSED_campaign")
        current = self.fixture.service.list_intents("sample", self.scope["scope_id"])[0]
        self.assertEqual(current["status"], "PAUSED_campaign")
        self.assertEqual(current["commitment"], 80)
        self.assertEqual(self.status(monitor)["pause_attempts"], 1)
        self.assertEqual(self.status(monitor)["provider_units"], 8)

    def test_active_after_end_requires_selected_condition(self):
        monitor, job = self.job(protective_conditions=["active_after_end"])
        with connection(self.store.path) as db:
            row = db.execute(
                "SELECT data FROM campaign_paid_intents WHERE id=?",
                (self.intent["id"],),
            ).fetchone()
            data = json.loads(row["data"])
            data["end_time"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
            # The request hash is immutable; a changed approved request denies
            # admission instead of manufacturing an expired owner approval.
            db.execute(
                "UPDATE campaign_paid_intents SET data=?,request_hash=? WHERE id=?",
                (canonical(data), digest(data), self.intent["id"]),
            )
        with self.assertRaises(PermissionError):
            core.execute(self.store, job, self.wire)
        result = dict(
            self.intent,
            result=dict(
                observed_at=(datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
                objects=dict(campaign=dict(status="ACTIVE")),
            ),
            data=data,
        )
        self.assertEqual(core.pause_reason(result, ["active_after_end"]), "active_after_end")
        self.assertIsNone(core.pause_reason(result, ["configuration_drift"]))

    def test_off_and_lease_and_cross_target_are_rechecked_at_boundary(self):
        monitor, job = self.job()
        with authority.bound(self.store, job) as cap:
            cap.update(action="RECONCILE", intent_id=self.intent["id"])
            self.assertTrue(
                authority.check(
                    self.store,
                    "sample",
                    "monitor:" + job["id"],
                    dict(self.scope),
                    "RECONCILE",
                )
            )
            with self.assertRaises(PermissionError):
                authority.check(self.store, "sample", "owner", dict(self.scope), "RECONCILE")
            cap["intent_id"] = "99999999-9999-4999-8999-999999999999"
            with self.assertRaises(PermissionError):
                authority.admit(self.store)
            cap["intent_id"] = self.intent["id"]
            with connection(self.store.path) as db:
                db.execute("UPDATE jobs SET lease=0 WHERE id=?", (job["id"],))
            with self.assertRaises(PermissionError):
                authority.admit(self.store)
        with self.owner():
            self.monitors.off("sample", monitor["id"], monitor["version"])
        self.assertEqual(self.status(monitor)["status"], "OFF")
        with self.assertRaises(PermissionError):
            core.execute(self.store, job, self.wire)

    def test_account_drift_inflight_denies_following_boundary(self):
        monitor, job = self.job()
        original = self.wire.read_paid
        count = 0

        def drift(kind, identity, token, secret, alive):
            nonlocal count
            value = original(kind, identity, token, secret, alive)
            count += 1
            if count == 1:
                with connection(self.store.path) as db:
                    db.execute("UPDATE social_connections SET version=version+1")
            return value

        with patch.object(self.wire, "read_paid", side_effect=drift):
            result = core.execute(self.store, job, self.wire)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(count, 1)
        self.assertEqual(self.status(monitor)["status"], "BLOCKED")

    def test_quota_independent_of_emergency_allowance_and_no_provider_transaction(self):
        monitor, job = self.job(max_provider_units=1)
        original = self.wire.read_paid

        def write_during_provider(*args):
            with connection(self.store.path) as db:
                db.execute("UPDATE apps SET updated=updated WHERE id='sample'")
            return original(*args)

        with patch.object(self.wire, "read_paid", side_effect=write_during_provider):
            result = core.execute(self.store, job, self.wire)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(self.status(monitor)["provider_units"], 1)
        with connection(self.store.path) as db:
            self.assertIsNone(db.execute("SELECT * FROM campaign_safety_calls WHERE category='PAUSE'").fetchone())

    def test_lost_pause_reply_blocks_restart_and_retains_hold(self):
        monitor, job = self.job()
        self.wire.objects[self.intent["ids"]["adset"]]["lifetime_budget"] = 999
        calls = []

        def lost(kind, identity, status, token, secret, alive):
            alive()
            calls.append(status)
            self.wire.objects[identity]["status"] = status
            raise TimeoutError("Synthetic lost pause reply")

        with patch.object(self.wire, "set_paid_status", side_effect=lost):
            result = core.execute(self.store, job, self.wire)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(calls, ["PAUSED"])
        self.assertEqual(self.status(monitor)["status"], "BLOCKED")
        self.assertEqual(core.tick(self.store), 0)
        self.assertEqual(
            self.fixture.service.list_intents("sample", self.scope["scope_id"])[0]["commitment"],
            80,
        )
        with self.assertRaises(PermissionError):
            core.execute(self.store, job, self.wire)

    def test_interrupted_running_job_is_stopped_without_reclaim(self):
        monitor, job = self.job()
        with connection(self.store.path) as db:
            db.execute("UPDATE jobs SET lease=0 WHERE id=?", (job["id"],))
            db.execute("UPDATE campaign_monitors SET due=0 WHERE id=?", (monitor["id"],))
        self.assertEqual(core.tick(self.store), 0)
        self.assertEqual(self.status(monitor)["status"], "BLOCKED")
        with connection(self.store.path) as db:
            self.assertEqual(
                db.execute("SELECT status FROM jobs WHERE id=?", (job["id"],)).fetchone()[0],
                "BLOCKED",
            )

    def test_pending_with_unknown_owner_does_not_pause_or_replay(self):
        monitor, job = self.job()
        with connection(self.store.path) as db:
            db.execute(
                "UPDATE campaign_paid_intents SET status='PENDING_ACTIVE_campaign' WHERE id=?",
                (self.intent["id"],),
            )
        with patch.object(self.wire, "set_paid_status", side_effect=AssertionError("No replay")):
            result = core.execute(self.store, job, self.wire)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(self.status(monitor)["provider_units"], 0)

    def test_authority_blocks_unsupported_effect_and_changed_job_bytes(self):
        monitor, job = self.job()
        with authority.bound(self.store, job) as cap:
            cap.update(action="RECONCILE", intent_id=self.intent["id"])
            with self.assertRaises(PermissionError):
                authority.check(self.store, "sample", "monitor:" + job["id"], self.scope, "RUN_AD")
            with self.assertRaises(PermissionError):
                authority.BoundaryTransport(self.store, self.wire).set_paid_status(
                    "campaign", "1", "ACTIVE", "token", "secret", lambda: None
                )
            with connection(self.store.path) as db:
                db.execute("UPDATE jobs SET data='{}' WHERE id=?", (job["id"],))
            with self.assertRaises(PermissionError):
                authority.admit(self.store)

    def test_expired_plan_owner_drift_and_max_runs_stop(self):
        monitor, job = self.job(max_runs=1)
        with connection(self.store.path) as db:
            db.execute("UPDATE jobs SET status='SUCCEEDED' WHERE id=?", (job["id"],))
            db.execute("UPDATE campaign_monitors SET due=0 WHERE id=?", (monitor["id"],))
        self.assertEqual(core.tick(self.store), 0)
        self.assertEqual(self.status(monitor)["status"], "BLOCKED")
        another = self.activate()
        with connection(self.store.path) as db:
            db.execute("UPDATE operator_roles SET version=version+1 WHERE app_id='sample'")
        self.assertEqual(core.tick(self.store), 0)
        self.assertEqual(self.status(another)["effective_status"], "BLOCKED")

    def test_unknown_pending_recovery_reads_only_and_retains_hold(self):
        monitor, job = self.job(protective_conditions=[], max_pause_attempts=0)
        with connection(self.store.path) as db:
            db.execute(
                "UPDATE campaign_paid_intents SET status='PENDING_ACTIVE_campaign' WHERE id=?",
                (self.intent["id"],),
            )
            db.execute(
                "INSERT INTO campaign_paid_leases VALUES(?,?,?,?,?)",
                (
                    "sample",
                    self.intent["id"],
                    "ACTIVE_campaign",
                    "abandoned-token",
                    now(),
                ),
            )
        with patch.object(self.wire, "set_paid_status", side_effect=AssertionError("No status replay")):
            result = core.execute(self.store, job, self.wire)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(
            self.fixture.service.list_intents("sample", self.scope["scope_id"])[0]["status"],
            "UNKNOWN",
        )
        self.assertEqual(
            self.fixture.service.list_intents("sample", self.scope["scope_id"])[0]["commitment"],
            80,
        )

    def test_active_after_approved_end_full_execution_and_remote_target_guard(self):
        monitor, job = self.job(
            protective_conditions=["active_after_end"],
            expires_at=self.scope["expires_at"],
        )
        future = datetime.fromisoformat(self.fixture.adbody["end_time"]).timestamp() + 1
        with connection(self.store.path) as db:
            db.execute("UPDATE jobs SET lease=? WHERE id=?", (future + 60, job["id"]))
        with (
            patch("time.time", return_value=future),
            patch(
                "mission_control.campaign_execution.now",
                return_value=datetime.fromtimestamp(future, timezone.utc).isoformat(),
            ),
        ):
            result = core.execute(self.store, job, self.wire)
        self.assertEqual(result["status"], "OBSERVED")
        self.assertEqual(
            self.fixture.service.list_intents("sample", self.scope["scope_id"])[0]["status"],
            "PAUSED_campaign",
        )
        with authority.bound(self.store, job) as cap:
            cap.update(action="RECONCILE", intent_id=self.intent["id"])
            with self.assertRaises(PermissionError):
                authority.BoundaryTransport(self.store, self.wire).read_paid(
                    "campaign", "999999", "token", "secret", lambda: None
                )

    def test_expiry_wrong_host_and_exhausted_pause_reservation_deny(self):
        monitor, job = self.job()
        with authority.bound(self.store, job) as cap:
            cap.update(action="RECONCILE", intent_id=self.intent["id"])
            cap["store"] = "another-host-datastore"
            with self.assertRaises(PermissionError):
                authority.admit(self.store)
        with patch(
            "time.time",
            return_value=datetime.fromisoformat(self.body()["expires_at"]).timestamp() + 1,
        ):
            with self.assertRaises(PermissionError):
                core.execute(self.store, job, self.wire)
        with connection(self.store.path) as db:
            db.execute("UPDATE campaign_monitors SET pauses=1 WHERE id=?", (monitor["id"],))
        self.wire.objects[self.intent["ids"]["adset"]]["lifetime_budget"] = 999
        with patch.object(
            self.wire,
            "set_paid_status",
            side_effect=AssertionError("No additional pause"),
        ):
            result = core.execute(self.store, job, self.wire)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(self.status(monitor)["pause_attempts"], 1)
        self.assertEqual(
            self.fixture.service.list_intents("sample", self.scope["scope_id"])[0]["commitment"],
            80,
        )

    def test_stopped_monitor_next_step_keeps_uncertainty_ahead_of_allowance_and_expiry(self):
        monitor, job = self.job()
        with connection(self.store.path) as db:
            db.execute("UPDATE campaign_monitors SET status='BLOCKED',units=160 WHERE id=?", (monitor["id"],))
            db.execute(
                "UPDATE jobs SET status='SUCCEEDED',result=? WHERE id=?",
                (
                    canonical({"observations": [{"intent_id": self.intent["id"], "status": "PAUSED_campaign"}]}),
                    job["id"],
                ),
            )
        self.assertEqual(self.status(monitor)["attention"], "REVIEW_ALLOWANCE")
        with patch("time.time", return_value=datetime.fromisoformat(self.body()["expires_at"]).timestamp() + 1):
            self.assertEqual(self.status(monitor)["attention"], "REVIEW_EXPIRY")
        with connection(self.store.path) as db:
            db.execute(
                "UPDATE jobs SET result=? WHERE id=?",
                (
                    canonical({"observations": [{"intent_id": self.intent["id"], "status": "ACK_PAUSED_campaign"}]}),
                    job["id"],
                ),
            )
        self.assertEqual(self.status(monitor)["attention"], "VERIFY_PROVIDER")

    def test_last_observation_projects_exact_historical_owned_job_and_omits_raw_secrets(
        self,
    ):
        monitor, job = self.job()
        result = dict(
            status="BLOCKED",
            error="PRIVATE_RAW_ERROR",
            token="PRIVATE_TOKEN",
            observations=[
                dict(
                    intent_id=self.intent["id"],
                    status="UNKNOWN",
                    recovery="ABANDONED_UNKNOWN",
                    protective_pause="PAUSED_campaign",
                    commitment_held_minor=80,
                    private="PRIVATE_OBSERVATION",
                ),
                dict(
                    intent_id="foreign-intent",
                    status="VERIFIED",
                    private="PRIVATE_FOREIGN",
                ),
                dict(intent_id=self.intent["id"], status="PRIVATE_INVALID_STATUS"),
                dict(intent_id=[], status={}),
            ],
        )
        with connection(self.store.path) as db:
            db.execute(
                "UPDATE jobs SET status='BLOCKED',result=? WHERE id=?",
                (canonical(result), job["id"]),
            )
        shown = self.status(monitor)["last_observation"]
        self.assertEqual(shown["status"], "BLOCKED")
        self.assertEqual(
            shown["observations"],
            [
                dict(
                    intent_id=self.intent["id"],
                    status="UNKNOWN",
                    recovery="ABANDONED_UNKNOWN",
                    protective_pause="PAUSED_campaign",
                    commitment_held_minor=80,
                )
            ],
        )
        self.assertNotIn("PRIVATE", canonical(shown))
        with self.owner():
            off = self.monitors.off("sample", monitor["id"], monitor["version"])
        self.assertEqual(off["last_observation"], shown)
        with connection(self.store.path) as db:
            db.execute(
                "UPDATE jobs SET result=? WHERE id=?",
                (canonical(dict(observations=[], secret="X" * 70000)), job["id"]),
            )
        self.assertEqual(self.status(monitor)["last_observation"]["observations"], [])
        self.store.save_app("foreign-app", {"name": "Synthetic foreign app"})
        with connection(self.store.path) as db:
            db.execute("UPDATE jobs SET app_id='foreign-app' WHERE id=?", (job["id"],))
        self.assertIsNone(self.status(monitor)["last_observation"])

    def test_organic_identity_preflight_and_post_read_each_charge_monitor_units(self):
        post = self.fixture.service.list_intents("sample", self.fixture.scope["scope_id"])[0]
        body = self.body(
            scope_id=self.fixture.scope["scope_id"],
            targets=[dict(intent_id=post["id"], request_hash=post["request_hash"])],
            protective_conditions=[],
            max_pause_attempts=0,
        )
        with self.owner():
            draft = self.monitors.prepare("sample", body)
            active = self.monitors.activate("sample", draft["id"], draft["summary_hash"])
        core.tick(self.store)
        job = claim(self.store)

        def preflight(service, app, actor, scope_id, action, active=True):
            service._alive(app, actor, scope_id, action, active)
            return (
                service.get_scope(app, scope_id),
                "synthetic-secret",
                "synthetic-token",
            )

        with patch.object(CampaignExecutionService, "_preflight", preflight):
            result = core.execute(self.store, job, self.wire)
        self.assertEqual(result["status"], "OBSERVED")
        self.assertEqual(self.status(active)["provider_units"], 2)

    def test_actual_http_adapter_requires_fresh_owner_origin_csrf_and_closed_body(self):
        import threading
        from urllib.request import Request
        from urllib.error import HTTPError
        from mission_control.server import Server
        from mission_control.operator_client import OperatorClient, ClientError
        from mission_control import server as http_server
        from mission_control import campaign_monitor_http as http

        original = http_server.owner_domain_post

        def route(parts):
            if len(parts) > 3 and parts[3] == "campaign-monitor":
                return http.post
            return original(parts)

        server = Server(("127.0.0.1", 0), self.store)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with (
                patch.object(http_server, "owner_domain_post", side_effect=route),
                patch(
                    "mission_control.operator_identity.github_read",
                    return_value=dict(
                        principal="owner",
                        login="owner",
                        provider="GITHUB",
                        verified_at=now(),
                    ),
                ),
            ):
                client = OperatorClient("http://127.0.0.1:" + str(server.server_port))
                client.bootstrap()
                base = "/api/apps/sample/campaign-monitor/"
                with self.assertRaises(ClientError):
                    client.request("POST", base + "history", {})
                client.request(
                    "POST",
                    "/api/identity/login",
                    dict(token="synthetic_identity_token"),
                )
                saved = client.request("POST", base + "prepare", dict(proposal=self.body()))
                active = client.request(
                    "POST",
                    base + "activate",
                    dict(monitor_id=saved["id"], summary_hash=saved["summary_hash"]),
                )
                self.assertEqual(active["status"], "ACTIVE")
                self.assertEqual(len(client.request("POST", base + "history", {})["monitors"]), 1)
                with self.assertRaises(ClientError):
                    client.request(
                        "POST",
                        base + "status",
                        dict(monitor_id=saved["id"], owner="forged"),
                    )
                for headers in (
                    {"Origin": "http://foreign.invalid"},
                    {"X-CSRF-Token": "wrong"},
                ):
                    request = Request(
                        client.origin + base + "history",
                        data=b"",
                        method="POST",
                        headers={
                            "Origin": client.origin,
                            "X-CSRF-Token": client.csrf,
                            "Content-Type": "application/json",
                            **headers,
                        },
                    )
                    with self.assertRaises(HTTPError) as denied:
                        client.opener.open(request, timeout=10)
                    self.assertEqual(denied.exception.code, 403)
                off = client.request(
                    "POST",
                    base + "off",
                    dict(monitor_id=saved["id"], version=active["version"]),
                )
                self.assertEqual(off["status"], "OFF")
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
