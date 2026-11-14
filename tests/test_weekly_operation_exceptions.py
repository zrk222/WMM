"""Owner-private bounded weekly operational exceptions over real saved SQLite state."""

import json
import time
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from mission_control.common import canonical, digest, now
from mission_control.db import connection
from mission_control.weekly_inbox import operation_exceptions, review, trusted_principal
from tests import test_campaign_owner_reports as report_fixture


class WeeklyOperationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = report_fixture.CampaignOwnerReportsTests(
            "test_private_report_immutable_hash_missing_kpis_and_no_effects"
        )
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.store = self.fixture.store
        self.server = self.fixture.fixture.server
        self.owner = dict(principal="owner")

    def cards(self, user=None):
        return operation_exceptions(self.store, self.store.app("sample"), self.owner if user is None else user)

    def active(self, user=()):
        from mission_control.weekly_inbox import active_work

        return active_work(self.store, self.store.app("sample"), self.owner if user == () else user)

    def test_active_work_lists_jobs_sequences_and_expiring_authority(self):
        from mission_control.worker import enqueue

        job = enqueue(self.store, "sample", "pipeline", dict(stage=1), "active-work-key")
        stamp = now()
        expires = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
        with connection(self.store.path) as db:
            db.execute(
                "INSERT INTO campaign_sequences VALUES(?,?,?,?,?,?,?,?,?,?)",
                ("sequence-1", "sample", "{}", digest({}), "{}", "sequence-request", "WAITING", "{}", stamp, stamp),
            )
            db.execute(
                "INSERT INTO agent_grants VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    "grant-soon",
                    "sample",
                    "agent",
                    "owner",
                    1,
                    1,
                    "a" * 64,
                    '["workspace.read"]',
                    "b" * 64,
                    expires,
                    5,
                    0,
                    "ACTIVE",
                    1,
                    stamp,
                    stamp,
                ),
            )
            summary = dict(stops_at=(datetime.now(timezone.utc) + timedelta(days=3)).isoformat())
            db.execute(
                "INSERT INTO automation_policies VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    "policy-soon",
                    "sample",
                    "grant-soon",
                    "owner",
                    1,
                    "ACTIVE",
                    "{}",
                    canonical(summary),
                    digest(summary),
                    stamp,
                    stamp,
                ),
            )
        items = self.active()
        job_id = digest(["sample", "JOB", job["id"]])
        queued = next(item for item in items if item["id"] == job_id)
        self.assertEqual(queued["state"], "QUEUED")
        self.assertEqual(queued["resolution_route"], "activity")
        self.assertEqual(queued["source_receipt"]["manifest_version"], self.store.app("sample")["version"])
        self.assertEqual(next(item for item in items if item["kind"] == "SEQUENCE")["state"], "WAITING")
        for kind in ("AGENT_GRANT", "AUTOMATION"):
            item = next(card for card in items if card["kind"] == kind)
            self.assertEqual(item["state"], "EXPIRING")
            self.assertIsNotNone(item["expires_at"])
        self.assertNotIn("active-work-key", canonical(items))
        with connection(self.store.path) as db:
            db.execute("UPDATE jobs SET status='SUCCEEDED' WHERE id=?", (job["id"],))
            db.execute("UPDATE campaign_sequences SET state='CANCELLED'")
            db.execute(
                "UPDATE agent_grants SET expires=?", ((datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),)
            )
            db.execute("UPDATE automation_policies SET status='OFF'")
        remaining = {item["id"] for item in self.active()}
        for kind, identity in (
            ("JOB", job["id"]),
            ("SEQUENCE", "sequence-1"),
            ("AGENT_GRANT", "grant-soon"),
            ("AUTOMATION", "policy-soon"),
        ):
            self.assertNotIn(digest(["sample", kind, identity]), remaining)

    def test_active_work_is_owner_only_bounded_and_never_exports_results(self):
        stamp = now()
        with connection(self.store.path) as db:
            for ordinal in range(60):
                db.execute(
                    "INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        "active-%03d" % ordinal,
                        "sample",
                        "pipeline",
                        "{}",
                        "RUNNING",
                        0,
                        0,
                        canonical(dict(secret="PRIVATE_JOB_RESULT")),  # noqa: S106 - synthetic redaction fixture
                        stamp,
                        stamp,
                        "active-request-%03d" % ordinal,
                    ),
                )
        items = self.active()
        self.assertLessEqual(sum(item["kind"] == "JOB" for item in items), 50)
        self.assertNotIn("PRIVATE_JOB_RESULT", canonical(items))
        self.assertEqual(self.active(None), [])
        self.assertEqual(self.active(dict(principal="maker")), [])
        value = review(self.server.service, user=self.owner)
        self.assertTrue(any(item["kind"] == "JOB" for item in value["active_work"]))
        self.assertIn("next_offset", value["coverage"])

    def handoff(self):
        from mission_control.agent_handoffs import Handoffs
        from mission_control.worker import enqueue

        job = enqueue(self.store, "sample", "pipeline", dict(stage=1), "private-handoff-key")
        handoff = Handoffs(self.store).create(
            "sample",
            self.owner,
            dict(
                job_id=job["id"],
                recipient="replacement",
                operations=["jobs.read"],
                expires=(datetime.now(timezone.utc) + timedelta(minutes=20)).isoformat(),
            ),
        )
        return handoff, job

    def test_handoff_expiry_stale_resolution_and_revocation_are_read_only(self):
        handoff, job = self.handoff()
        self.assertEqual(self.cards(), [])
        with connection(self.store.path) as db:
            row = db.execute("SELECT expires FROM agent_handoffs WHERE id=?", (handoff["id"],)).fetchone()
            assert row is not None
            future = row[0]
            db.execute(
                "UPDATE agent_handoffs SET expires=? WHERE id=?",
                ((datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(), handoff["id"]),
            )
            jobs = canonical([dict(r) for r in db.execute("SELECT * FROM jobs")])
        effects = canonical(self.fixture.fixture.wire.objects)
        first, second = self.cards(), self.cards()
        self.assertEqual(len(first), 1)
        self.assertEqual(first[0]["state"], "EXPIRED")
        self.assertEqual(first[0]["id"], second[0]["id"])
        self.assertEqual(first[0]["source_receipt"]["source_hash"], second[0]["source_receipt"]["source_hash"])
        self.assertIn("Handoffs", first[0]["next_action"])
        self.assertNotIn("private-handoff-key", canonical(first))
        with connection(self.store.path) as db:
            self.assertEqual(canonical([dict(r) for r in db.execute("SELECT * FROM jobs")]), jobs)
            db.execute("UPDATE agent_handoffs SET expires=? WHERE id=?", (future, handoff["id"]))
        self.assertEqual(self.cards(), [])
        app = self.store.app("sample")
        self.store.save_app("sample", dict(app["data"], name="Changed"), app["version"])
        self.assertEqual(self.cards()[0]["state"], "CONTEXT_CHANGED")
        with connection(self.store.path) as db:
            db.execute("UPDATE agent_handoffs SET status='REVOKED' WHERE id=?", (handoff["id"],))
        self.assertEqual(self.cards(), [])
        self.assertEqual(canonical(self.fixture.fixture.wire.objects), effects)

    def test_handoff_failed_job_surfaces_even_when_revoked_and_resolves_on_success(self):
        handoff, job = self.handoff()
        with connection(self.store.path) as db:
            db.execute(
                "UPDATE jobs SET status='FAILED',result=? WHERE id=?",
                (canonical({"secret": "PRIVATE_ERROR"}), job["id"]),
            )
        card = self.cards()[0]
        self.assertEqual(card["state"], "JOB_FAILED")
        self.assertEqual(card["evidence"]["job_id"], job["id"])
        self.assertFalse(card["evidence"]["authority_issued"])
        self.assertNotIn("PRIVATE_ERROR", canonical(card))
        with connection(self.store.path) as db:
            db.execute("UPDATE agent_handoffs SET status='REVOKED' WHERE id=?", (handoff["id"],))
        revoked = self.cards()[0]
        self.assertEqual(revoked["id"], card["id"])
        self.assertIn("remains revoked", revoked["next_action"])
        with connection(self.store.path) as db:
            db.execute("UPDATE jobs SET status='SUCCEEDED' WHERE id=?", (job["id"],))
        self.assertEqual(self.cards(), [])

    def test_handoff_exceptions_do_not_leak_to_another_app_owner(self):
        handoff, job = self.handoff()
        with connection(self.store.path) as db:
            db.execute("UPDATE jobs SET status='BLOCKED' WHERE id=?", (job["id"],))
            db.execute(
                "INSERT INTO operator_roles VALUES(?,?,?,?,?,?,?,?)",
                ("sample", "other", "other", "OWNER", "ACTIVE", 1, now(), "owner"),
            )
        self.assertEqual(self.cards(dict(principal="other")), [])
        self.assertEqual(len(self.cards()), 1)

    def test_claimed_handoff_with_current_recipient_stays_quiet(self):
        from mission_control.operator_client import OperatorClient

        handoff, job = self.handoff()
        issued = self.fixture.fixture.client.request(
            "POST",
            "/api/apps/sample/agent-grants/issue",
            dict(
                agent_id="replacement",
                manifest_version=self.store.app("sample")["version"],
                operations=["handoff.resume", "jobs.read"],
                max_calls=5,
                expires=(datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat(),
            ),
        )
        assert isinstance(issued, dict)
        client = OperatorClient(self.fixture.fixture.client.origin, grant_token=issued["token"])
        resumed = client.call(
            dict(
                app_id="sample",
                operation="handoff.resume",
                resource_id=handoff["id"],
                input=dict(version=handoff["version"], payload_hash=handoff["payload_hash"]),
            )
        )
        assert isinstance(resumed, dict)
        self.assertEqual(resumed["effective_status"], "CLAIMED")
        self.assertEqual(resumed["job_id"], job["id"])
        self.assertEqual(self.cards(), [])

    def test_handoff_projection_is_bounded_deterministic_and_corruption_is_visible(self):
        handoff, _ = self.handoff()
        with connection(self.store.path) as db:
            row = db.execute("SELECT * FROM agent_handoffs WHERE id=?", (handoff["id"],)).fetchone()
            assert row is not None
            original = dict(row)
            expired = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
            db.execute("UPDATE agent_handoffs SET expires=?", (expired,))
            for ordinal in range(105):
                clone = dict(original, id="bounded-handoff-%03d" % ordinal, expires=expired)
                columns = tuple(clone)
                db.execute(
                    "INSERT INTO agent_handoffs ("  # noqa: S608 - columns come from the fixture table
                    + ",".join(columns)
                    + ") VALUES ("
                    + ",".join("?" for _ in columns)
                    + ")",
                    tuple(clone.values()),
                )
        first, second = self.cards(), self.cards()
        self.assertEqual(len(first), 100)
        self.assertTrue(all(card["category"] == "handoff" and card["state"] == "EXPIRED" for card in first))
        self.assertEqual([card["id"] for card in first], [card["id"] for card in second])
        self.assertEqual(
            [card["source_receipt"]["source_hash"] for card in first],
            [card["source_receipt"]["source_hash"] for card in second],
        )
        with connection(self.store.path) as db:
            # Corrupt a row inside the selected bound while another domain needs action.
            row = db.execute("SELECT id FROM agent_handoffs ORDER BY created DESC,id LIMIT 1").fetchone()
            assert row is not None
            selected = row[0]
            db.execute("UPDATE agent_handoffs SET payload=? WHERE id=?", ("PRIVATE_CORRUPTED_PAYLOAD", selected))
            db.execute("UPDATE campaign_paid_intents SET status='UNKNOWN'")
        unavailable = self.cards()
        self.assertEqual(len(unavailable), 1)
        self.assertEqual(unavailable[0]["state"], "UNAVAILABLE")
        self.assertEqual(unavailable[0]["category"], "operation_source")
        self.assertIn("inspect", unavailable[0]["next_action"])
        self.assertNotIn("PRIVATE_CORRUPTED_PAYLOAD", canonical(unavailable))

    def test_owner_only_no_anonymous_or_maker_private_refs(self):
        with connection(self.store.path) as db:
            db.execute("UPDATE campaign_paid_intents SET status='UNKNOWN'")
        app = self.store.app("sample")
        self.assertEqual(operation_exceptions(self.store, app, None), [])
        self.assertEqual(operation_exceptions(self.store, app, dict(principal="maker")), [])
        with connection(self.store.path) as db:
            db.execute(
                "INSERT INTO operator_roles VALUES(?,?,?,?,?,?,?,?)",
                ("sample", "maker", "maker", "MAKER", "ACTIVE", 1, now(), "owner"),
            )
        self.assertEqual(operation_exceptions(self.store, app, dict(principal="maker")), [])
        cards = self.cards()
        self.assertEqual(len(cards), 1)
        self.assertTrue(cards[0]["owner_only"])
        self.assertEqual(cards[0]["owner_principal"], "owner")
        with connection(self.store.path) as db:
            db.execute("UPDATE operator_roles SET status='REVOKED' WHERE app_id='sample' AND principal='owner'")
        self.assertEqual(self.cards(), [])

    def test_unknown_pending_deduped_stable_ids_safe_receipts_and_no_provider(self):
        with connection(self.store.path) as db:
            db.execute(
                "UPDATE campaign_paid_intents SET status='PENDING_ACTIVE_campaign',result=?",
                (canonical({"secret": "PRIVATE_RAW", "error": "PRIVATE_ERROR"}),),
            )
            db.execute("UPDATE campaign_monitors SET status='BLOCKED'")
        first = self.cards()
        second = self.cards()
        self.assertEqual(len(first), 1)
        card = first[0]
        self.assertEqual(card["category"], "delivery")
        self.assertEqual(card["id"], second[0]["id"])
        self.assertEqual(
            card["source_receipt"]["source_hash"],
            second[0]["source_receipt"]["source_hash"],
        )
        self.assertEqual(card["evidence"]["retained_commitment_minor"], 80)
        self.assertEqual(card["evidence"]["provider_ids"]["campaign"], "1001")
        self.assertEqual(card["action"]["tool"], "campaign")
        for private in (
            "PRIVATE_RAW",
            "PRIVATE_ERROR",
            "synthetic-secret",
            "synthetic-token",
            "credential_ref",
        ):
            self.assertNotIn(private, canonical(first))
        with connection(self.store.path) as db:
            db.execute("UPDATE campaign_paid_intents SET status='UNKNOWN'")
        changed = self.cards()[0]
        self.assertEqual(changed["id"], card["id"])
        self.assertNotEqual(
            changed["source_receipt"]["source_hash"],
            card["source_receipt"]["source_hash"],
        )

    def test_off_normal_and_completed_finite_work_quiet_but_unknown_stays_actionable(
        self,
    ):
        with connection(self.store.path) as db:
            db.execute("UPDATE campaign_monitors SET status='OFF'")
        self.assertEqual(self.cards(), [])
        with connection(self.store.path) as db:
            db.execute("UPDATE campaign_paid_intents SET status='UNKNOWN'")
        self.assertEqual(len(self.cards()), 1)

    def test_blocked_and_expired_active_monitor_reportplans_need_action(self):
        plan = self.fixture.plan()
        with connection(self.store.path) as db:
            db.execute("UPDATE campaign_monitors SET status='BLOCKED'")
            db.execute("UPDATE campaign_report_plans SET status='BLOCKED'")
        cards = self.cards()
        self.assertEqual({c["resolution_route"] for c in cards}, {"monitor", "owner_reports"})
        self.assertTrue(all(c["state"] == "BLOCKED" for c in cards))
        with connection(self.store.path) as db:
            db.execute("UPDATE campaign_monitors SET status='ACTIVE'")
            db.execute("UPDATE campaign_report_plans SET status='ACTIVE'")
        future = time.time() + 8 * 86400
        with patch(
            "mission_control.weekly_inbox.now",
            return_value=datetime.fromtimestamp(future, timezone.utc).isoformat(),
        ):
            expired = self.cards()
        self.assertEqual({c["state"] for c in expired}, {"EXPIRED"})
        with connection(self.store.path) as db:
            db.execute("UPDATE campaign_monitors SET runs=3")
            db.execute("UPDATE campaign_report_plans SET runs=2")
        with patch(
            "mission_control.weekly_inbox.now",
            return_value=datetime.fromtimestamp(future, timezone.utc).isoformat(),
        ):
            self.assertEqual(self.cards(), [])
        self.assertIsNotNone(plan)

    def test_failed_job_projection_checks_exact_owner_plan_binding(self):
        monitor = self.fixture.monitor
        assert monitor is not None
        stamp = now()
        data = dict(
            monitor_id=monitor["id"],
            monitor_version=2,
            summary_hash=monitor["summary_hash"],
            run=1,
        )
        with connection(self.store.path) as db:
            db.execute(
                "INSERT INTO jobs(id,app_id,action,data,status,result,created,updated,request_key) VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    "failed-private",
                    "sample",
                    "campaign_monitor",
                    canonical(data),
                    "FAILED",
                    canonical(dict(error="PRIVATE_FAILURE")),
                    stamp,
                    stamp,
                    "failed-private",
                ),
            )
            db.execute("UPDATE campaign_monitors SET last_job='failed-private'")
        cards = self.cards()
        self.assertEqual(cards[0]["state"], "BLOCKED")
        self.assertNotIn("PRIVATE_FAILURE", canonical(cards))
        with connection(self.store.path) as db:
            db.execute("UPDATE jobs SET status='PRIVATE_JOB_STATUS' WHERE id='failed-private'")
        self.assertEqual(self.cards(), [])
        with connection(self.store.path) as db:
            db.execute("UPDATE jobs SET status='FAILED',data='{}' WHERE id='failed-private'")
        self.assertEqual(self.cards(), [])

    def test_operation_source_failure_retains_legacy_gates_without_raw_errors(self):
        with patch(
            "mission_control.weekly_inbox._operation_rows",
            side_effect=RuntimeError("PRIVATE_SQL_ERROR"),
        ):
            value = review(self.server.service, user=self.owner)
        self.assertTrue(any(c["category"] == "operation_source" for c in value["exceptions"]))
        self.assertTrue(any(not c.get("owner_only") for c in value["exceptions"]))
        self.assertNotIn("PRIVATE_SQL_ERROR", canonical(value))

    def test_portfolio_status_projects_stage_gaps_and_active_sequences(self):
        from mission_control.weekly_inbox import project

        workspace = self.server.service.workspace("sample")
        workspace["sequences"] = {"history": [dict(state="WAITING"), dict(state="QUEUED"), dict(state="CANCELLED")]}
        workspace["workflow"] = dict(
            workspace["workflow"],
            next_action={"title": "Review the next stage"},
            steps=[dict(critical_findings=["One confirmed P0"]), dict(critical_findings=[])],
        )
        value = project(workspace)
        self.assertEqual(value["active_sequences"], 2)
        self.assertEqual(value["high_priority_gaps"], 1)
        self.assertEqual(value["current_stage"]["next_action"], "Review the next stage")
        with patch("mission_control.weekly_inbox.project", side_effect=RuntimeError("PRIVATE_SQL_ERROR")):
            broken = review(self.server.service, user=self.owner)
        for row in broken["apps"]:
            self.assertIsNone(row["current_stage"]["id"])
            self.assertIsNone(row["high_priority_gaps"])
            self.assertIsNone(row["active_sequences"])
            self.assertEqual(row["active_work"], [])
        self.assertNotIn("PRIVATE_SQL_ERROR", canonical(broken))
        self.assertEqual(set(broken["coverage"]), {"offset", "evaluated", "total_apps", "next_offset"})

    def test_trusted_principal_rejects_untrusted_shapes(self):
        for value in (
            None,
            "owner",
            {},
            {"principal": ""},
            {"principal": 3},
            {"principal": "x" * 201},
        ):
            self.assertIsNone(trusted_principal(value))
        self.assertEqual(trusted_principal(self.owner), "owner")

    def test_schedule_deadline_uses_renewal_without_extending_saved_batch(self):
        from mission_control.authority_expiry import record_initial
        from mission_control.campaign_schedule import initialize

        initialize(self.store)
        observed = datetime.now(timezone.utc)
        past = (observed - timedelta(minutes=20)).isoformat()
        first = (observed - timedelta(minutes=5)).isoformat()
        later = (observed + timedelta(hours=1)).isoformat()
        stamp = observed.isoformat()
        scope_id = self.fixture.fixture.scope["scope_id"]
        with connection(self.store.path) as db:
            db.execute("UPDATE campaign_monitors SET status='OFF'")
            scope = db.execute("SELECT * FROM campaign_scopes WHERE id=?", (scope_id,)).fetchone()
            summary = json.loads(scope["summary"])
            summary["expires_at"] = past
            db.execute(
                "UPDATE campaign_scopes SET summary=?,summary_hash=? WHERE id=?",
                (canonical(summary), digest(summary), scope_id),
            )
            scope = db.execute("SELECT * FROM campaign_scopes WHERE id=?", (scope_id,)).fetchone()
            record_initial(db, "CAMPAIGN", scope, past, later, "owner", scope["owner_version"], {}, observed)
            for name, deadline in (
                ("old-batch", first),
                ("new-batch", later),
                ("legacy-batch", None),
                ("tampered-batch", later),
                ("stale-binding", later),
            ):
                batch = dict(
                    batch_id=name,
                    app_id="sample",
                    owner="owner",
                    scope_id=scope_id,
                    scope_hash=digest({}) if name == "stale-binding" else scope["summary_hash"],
                )
                if deadline:
                    batch["permission_expires_at"] = deadline
                pinned = digest({}) if name == "tampered-batch" else digest(batch)
                db.execute(
                    "INSERT INTO campaign_schedule_batches VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (name, "sample", "owner", scope_id, canonical(batch), pinned, "ACTIVE", 2, stamp, stamp),
                )
                db.execute(
                    "INSERT INTO campaign_schedule_items VALUES(?,?,?,?,?,?,?,?,?)",
                    (name + "-item", name, observed.timestamp(), "{}", digest({}), "READY", None, stamp, stamp),
                )
        by_batch = {c["action"]["batch_id"]: c["state"] for c in self.cards()}
        self.assertEqual(
            by_batch,
            {
                "old-batch": "EXPIRED_PENDING_WORK",
                "legacy-batch": "EXPIRED_PENDING_WORK",
                "tampered-batch": "NEEDS_REPAIR",
                "stale-binding": "NEEDS_REPAIR",
            },
        )

        with connection(self.store.path) as db:
            db.execute("UPDATE campaign_scopes SET status='REVOKED' WHERE id=?", (scope_id,))
        by_batch = {c["action"]["batch_id"]: c["state"] for c in self.cards()}
        self.assertEqual(by_batch["new-batch"], "NEEDS_REPAIR")

    def test_expired_pending_schedule_owned_refs_and_uncertainty_dedup(self):
        from mission_control.campaign_schedule import initialize

        initialize(self.store)
        stamp = now()
        with connection(self.store.path) as db:
            db.execute("UPDATE campaign_monitors SET status='OFF'")
            scope = db.execute(
                "SELECT * FROM campaign_scopes WHERE app_id='sample' AND id=?",
                (self.fixture.fixture.scope["scope_id"],),
            ).fetchone()
            import json

            summary = json.loads(scope["summary"])
            summary["expires_at"] = "2020-01-01T00:00:00+00:00"
            db.execute(
                "UPDATE campaign_scopes SET summary=?,summary_hash=? WHERE id=?",
                (canonical(summary), digest(summary), scope["id"]),
            )
            batch = dict(
                batch_id="saved-batch",
                app_id="sample",
                owner="owner",
                scope_id=scope["id"],
                scope_hash=digest(summary),
            )
            db.execute(
                "INSERT INTO campaign_schedule_batches VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    "saved-batch",
                    "sample",
                    "owner",
                    scope["id"],
                    canonical(batch),
                    digest(batch),
                    "ACTIVE",
                    2,
                    stamp,
                    stamp,
                ),
            )
            db.execute(
                "INSERT INTO campaign_schedule_items VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    "saved-item",
                    "saved-batch",
                    time.time(),
                    "{}",
                    digest({}),
                    "READY",
                    None,
                    stamp,
                    stamp,
                ),
            )
        cards = self.cards()
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["state"], "EXPIRED_PENDING_WORK")
        self.assertEqual(cards[0]["action"]["batch_id"], "saved-batch")
        with connection(self.store.path) as db:
            db.execute("UPDATE campaign_paid_intents SET status='UNKNOWN'")
        cards = self.cards()
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["category"], "delivery")
        with connection(self.store.path) as db:
            db.execute("UPDATE campaign_paid_intents SET status='ACTIVE_VERIFIED'")
            db.execute("UPDATE campaign_schedule_batches SET status='OFF'")
        self.assertEqual(self.cards(), [])

    def test_closed_states_foreign_owned_rows_and_payloads_never_exported(self):
        with connection(self.store.path) as db:
            db.execute(
                "UPDATE campaign_paid_intents SET status='PENDING_PRIVATE_SECRET',ids=?",
                (canonical({"campaign": "SECRET_TOKEN", "unexpected": "PRIVATE"}),),
            )
        self.assertEqual(self.cards(), [])
        with connection(self.store.path) as db:
            db.execute("UPDATE campaign_paid_intents SET status='UNKNOWN'")
        self.assertEqual(self.cards()[0]["evidence"]["provider_ids"], {})
        with connection(self.store.path) as db:
            db.execute("UPDATE campaign_scopes SET owner='different-owner'")
        self.assertEqual(self.cards(), [])

    def test_review_preserves_p0_five_app_and_response_principal_boundary(self):
        with connection(self.store.path) as db:
            db.execute("UPDATE campaign_paid_intents SET status='UNKNOWN'")
        anonymous = review(self.server.service)
        self.assertIsNone(anonymous["owner_operations_principal"])
        self.assertFalse(any(c.get("owner_only") for c in anonymous["exceptions"]))
        owned = review(self.server.service, user=self.owner)
        self.assertEqual(owned["owner_operations_principal"], "owner")
        private = [c for c in owned["exceptions"] if c.get("owner_only")]
        self.assertEqual(len(private), 1)
        self.assertEqual(private[0]["app_id"], "sample")
        self.assertEqual(owned["authority"], "NO_EXECUTION_AUTHORITY")
        self.assertFalse(owned["spend_allowed"])
        self.assertLessEqual(owned["coverage"]["evaluated"], 5)


if __name__ == "__main__":
    unittest.main()
