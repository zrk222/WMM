"""Cross-surface extension tests against isolated real SQLite authority records."""

from datetime import datetime, timedelta, timezone
import unittest
import sqlite3
import json
from unittest.mock import patch

from mission_control.authority_expiry import AuthorityExpiry
from mission_control.common import Invalid, canonical
from mission_control.db import connection
from tests.test_complete_automation import AuthorityFixture
from tests import test_campaign_execution as campaign_fixtures
from tests import test_organic_video_policy as organic_fixtures
from tests import test_campaign_schedule as schedule_fixtures
from tests import test_campaign_monitor as monitor_fixtures
from tests import test_organic_video_schedule as video_schedule_fixtures
from tests.test_verified_review import OWNER as AUTOMATION_OWNER


def extend(store, app, owner, kind, identity, expires, clock=None):
    service = AuthorityExpiry(store, clock=clock)
    review = service.preview(app, owner, dict(kind=kind, id=identity, expires=expires))
    receipt = service.confirm(
        app, owner, dict(**review, request_id="synthetic-extension", extended_expiry_consent=True)
    )
    return review, receipt


class StandingIntegration(AuthorityFixture, unittest.TestCase):
    def setUp(self):
        self.setup_authority()

    def tearDown(self):
        self.cleanup_authority()

    def test_atomic_bundle_preserves_ids_and_usage(self):
        issued = self.activate()
        self.grants.admit(issued["token"], self.envelope())
        with connection(self.store.path) as db:
            before = dict(db.execute("SELECT * FROM agent_grants WHERE id=?", (issued["grant"]["id"],)).fetchone())
        selected = (self.observed + timedelta(days=3)).isoformat()
        review, result = extend(
            self.store,
            "sample-one",
            AUTOMATION_OWNER,
            "AUTOMATION",
            issued["policy_id"],
            selected,
            lambda: self.observed,
        )
        self.assertEqual(review["preview"]["usage"]["used"], 1)
        self.assertEqual(result["receipt"]["revision"], 1)
        with connection(self.store.path) as db:
            after = dict(db.execute("SELECT * FROM agent_grants WHERE id=?", (issued["grant"]["id"],)).fetchone())
            proofs = db.execute("SELECT kind FROM authority_expiry_consents ORDER BY kind").fetchall()
        self.assertEqual(before, after)
        self.assertEqual([row["kind"] for row in proofs], ["AGENT_GRANT", "AUTOMATION"])

    def test_fresh_test_of_unchanged_extended_scope_keeps_usage(self):
        proposal = self.proposal(expires=(self.observed + timedelta(days=3)).isoformat())
        proposal["extended_expiry_consent"] = True
        review = self.automation.preview("sample-one", AUTOMATION_OWNER, proposal)
        issued = self.automation.activate(
            "sample-one", AUTOMATION_OWNER, dict(proposal=review["proposal"], summary_hash=review["summary_hash"])
        )
        self.grants.admit(issued["token"], self.envelope())
        self.observed += timedelta(hours=25)
        with connection(self.store.path) as db:
            db.execute(
                "UPDATE agent_connections SET last_test=?,updated=?",
                (self.observed.isoformat(), self.observed.isoformat()),
            )
        self.grants.admit(issued["token"], self.envelope())
        self.assertEqual(self.grants.authority_status(issued["grant"]["id"], "sample-one")["used"], 2)
        with connection(self.store.path) as db:
            source = db.execute("SELECT data FROM agent_connections").fetchone()
            changed = json.loads(source["data"])
            changed["model"] = "different-model"
            db.execute("UPDATE agent_connections SET data=?", (canonical(changed),))
        with self.assertRaises((Invalid, PermissionError)):
            self.grants.admit(issued["token"], self.envelope())
        self.assertEqual(self.grants.authority_status(issued["grant"]["id"], "sample-one")["used"], 2)

    def test_bundle_failure_rolls_back_both_receipts(self):
        issued = self.activate()
        service = AuthorityExpiry(self.store, clock=lambda: self.observed)
        review = service.preview(
            "sample-one",
            AUTOMATION_OWNER,
            dict(kind="AUTOMATION", id=issued["policy_id"], expires=(self.observed + timedelta(days=3)).isoformat()),
        )
        with connection(self.store.path) as db:
            db.execute(
                "CREATE TRIGGER fixture_grant_failure BEFORE INSERT ON authority_expiry_consents WHEN NEW.kind='AGENT_GRANT' BEGIN SELECT RAISE(ABORT,'synthetic failure'); END"
            )
        with self.assertRaises(sqlite3.IntegrityError):
            service.confirm(
                "sample-one", AUTOMATION_OWNER, dict(**review, request_id="atomic", extended_expiry_consent=True)
            )
        with connection(self.store.path) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM authority_expiry_consents").fetchone()[0], 0)

    def test_legacy_extension_reverification_preserves_usage_and_rejects_changed_config(self):
        issued = self.activate()
        self.grants.admit(issued["token"], self.envelope())
        extend(
            self.store,
            "sample-one",
            AUTOMATION_OWNER,
            "AUTOMATION",
            issued["policy_id"],
            (self.observed + timedelta(days=3)).isoformat(),
            lambda: self.observed,
        )
        self.observed += timedelta(hours=25)
        with connection(self.store.path) as db:
            db.execute(
                "UPDATE agent_connections SET last_test=?,updated=?",
                (self.observed.isoformat(), self.observed.isoformat()),
            )
        self.grants.admit(issued["token"], self.envelope())
        self.assertEqual(self.grants.authority_status(issued["grant"]["id"], "sample-one")["used"], 2)
        with connection(self.store.path) as db:
            source = db.execute("SELECT data FROM agent_connections").fetchone()
            changed = json.loads(source["data"])
            changed["model"] = "different-model"
            db.execute("UPDATE agent_connections SET data=?", (canonical(changed),))
        with self.assertRaises((Invalid, PermissionError)):
            self.grants.admit(issued["token"], self.envelope())
        self.assertEqual(self.grants.authority_status(issued["grant"]["id"], "sample-one")["used"], 2)

    def test_standing_executions_keep_the_deadline_captured_at_admission(self):
        from mission_control.automation_execution import start, bound

        issued = self.activate()
        envelope = self.envelope()
        old = self.grants.admit(issued["token"], envelope)
        dispatched = self.grants.admit(issued["token"], envelope)
        review, _ = extend(
            self.store,
            "sample-one",
            AUTOMATION_OWNER,
            "AUTOMATION",
            issued["policy_id"],
            (self.observed + timedelta(days=3)).isoformat(),
            lambda: self.observed,
        )
        self.assertTrue(
            any(item["id"] == old["automation_execution_id"] for item in review["preview"]["dependent_deadlines"])
        )
        new = self.grants.admit(issued["token"], envelope)
        start(self.store, dispatched, envelope)
        with connection(self.store.path) as db:
            old_bound = db.execute(
                "SELECT * FROM automation_execution_authority WHERE execution_id=?", (old["automation_execution_id"],)
            ).fetchone()
            new_bound = db.execute(
                "SELECT * FROM automation_execution_authority WHERE execution_id=?", (new["automation_execution_id"],)
            ).fetchone()
        self.assertLess(old_bound["permission_expires_at"], new_bound["permission_expires_at"])
        with patch("mission_control.complete_automation.utc", return_value=self.observed + timedelta(hours=2)):
            with self.assertRaises(PermissionError):
                start(self.store, old, envelope)
            with bound(self.store, dispatched["automation_execution_id"]):
                with self.assertRaises(PermissionError):
                    with connection(self.store.path):
                        pass
            self.assertEqual(start(self.store, new, envelope), new["automation_execution_id"])

    def test_trigger_upgrade_blocks_rowid_replacement_for_both_receipt_kinds(self):
        from mission_control.db import initialize

        issued = self.activate()
        admission = self.grants.admit(issued["token"], self.envelope())
        extend(
            self.store,
            "sample-one",
            AUTOMATION_OWNER,
            "AUTOMATION",
            issued["policy_id"],
            (self.observed + timedelta(days=3)).isoformat(),
            lambda: self.observed,
        )
        with connection(self.store.path) as db:
            db.execute("DROP TRIGGER authority_expiry_no_replace")
            db.execute(
                "CREATE TRIGGER authority_expiry_no_replace BEFORE INSERT ON authority_expiry_consents WHEN EXISTS(SELECT 1 FROM authority_expiry_consents WHERE authority_id=NEW.authority_id AND revision=NEW.revision) BEGIN SELECT RAISE(ABORT,'old'); END"
            )
            db.execute("DROP TRIGGER automation_execution_authority_no_replace")
            db.execute(
                "CREATE TRIGGER automation_execution_authority_no_replace BEFORE INSERT ON automation_execution_authority WHEN EXISTS(SELECT 1 FROM automation_execution_authority WHERE execution_id=NEW.execution_id) BEGIN SELECT RAISE(ABORT,'old'); END"
            )
        initialize(self.store.path)
        with connection(self.store.path) as db:
            prior = db.execute(
                "SELECT * FROM automation_executions WHERE id=?", (admission["automation_execution_id"],)
            ).fetchone()
            values = dict(prior)
            values["id"] = "another-execution"
            db.execute(
                "INSERT INTO automation_executions ("
                + ",".join(values)
                + ") VALUES ("
                + ",".join("?" for _ in values)
                + ")",
                tuple(values.values()),
            )
            for table, key, new_value in (
                ("authority_expiry_consents", "authority_id", "different-authority"),
                ("automation_execution_authority", "execution_id", "another-execution"),
            ):
                original = db.execute("SELECT rowid,* FROM " + table + " LIMIT 1").fetchone()
                fields = dict(original)
                storage_id = fields.pop("rowid")
                fields[key] = new_value
                if table == "authority_expiry_consents":
                    fields["request_id"] = "different-request"
                sql = (
                    "INSERT OR REPLACE INTO "
                    + table
                    + " (rowid,"
                    + ",".join(fields)
                    + ") VALUES ("
                    + ",".join("?" for _ in range(len(fields) + 1))
                    + ")"
                )
                with self.assertRaises(sqlite3.IntegrityError):
                    db.execute(sql, (storage_id, *fields.values()))
                self.assertNotEqual(
                    db.execute("SELECT " + key + " FROM " + table + " WHERE rowid=?", (storage_id,)).fetchone()[0],
                    new_value,
                )

    def test_fk_upgrade_preserves_orphan_receipt_and_missing_execution_fails_closed(self):
        from mission_control.automation_execution import execution_row
        from mission_control.db import initialize

        issued = self.activate()
        admission = self.grants.admit(issued["token"], self.envelope())
        identity = admission["automation_execution_id"]
        with connection(self.store.path) as db:
            before = dict(
                db.execute("SELECT * FROM automation_execution_authority WHERE execution_id=?", (identity,)).fetchone()
            )
            for suffix in ("no_replace", "no_update", "no_delete"):
                db.execute("DROP TRIGGER automation_execution_authority_" + suffix)
            db.execute("ALTER TABLE automation_execution_authority RENAME TO authority_new_fixture")
            db.execute(
                "CREATE TABLE automation_execution_authority(execution_id TEXT PRIMARY KEY REFERENCES automation_executions(id),permission_expires_at TEXT NOT NULL,policy_revision INTEGER NOT NULL,policy_hash TEXT NOT NULL,grant_revision INTEGER NOT NULL,grant_hash TEXT NOT NULL,record_hash TEXT NOT NULL)"
            )
            db.execute("INSERT INTO automation_execution_authority SELECT * FROM authority_new_fixture")
            db.execute("DROP TABLE authority_new_fixture")
        initialize(self.store.path)
        with connection(self.store.path) as db:
            self.assertFalse(db.execute("PRAGMA foreign_key_list(automation_execution_authority)").fetchall())
            self.assertEqual(
                before,
                dict(
                    db.execute(
                        "SELECT * FROM automation_execution_authority WHERE execution_id=?", (identity,)
                    ).fetchone()
                ),
            )
            db.execute("DELETE FROM automation_executions WHERE id=?", (identity,))
            with self.assertRaises(PermissionError):
                execution_row(db, identity)
            self.assertEqual(
                before,
                dict(
                    db.execute(
                        "SELECT * FROM automation_execution_authority WHERE execution_id=?", (identity,)
                    ).fetchone()
                ),
            )
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("DELETE FROM automation_execution_authority WHERE execution_id=?", (identity,))


class CampaignIntegration(unittest.TestCase):
    def setUp(self):
        self.fixture = campaign_fixtures.CampaignTests("test_publish_is_exact_durable_and_not_replayed")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def test_campaign_extension_retains_scope_and_blocks_uncertain(self):
        f = self.fixture
        f.service.run_post("sample", "grant:example", f.scope["scope_id"], f.post)
        with connection(f.store.path) as db:
            before = dict(db.execute("SELECT * FROM campaign_scopes").fetchone())
        review, _ = extend(
            f.store,
            "sample",
            dict(principal="owner"),
            "CAMPAIGN",
            f.scope["scope_id"],
            (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
        )
        self.assertEqual(review["preview"]["usage"]["posts"][0]["status"], "VERIFIED")
        with connection(f.store.path) as db:
            self.assertEqual(before, dict(db.execute("SELECT * FROM campaign_scopes").fetchone()))
            db.execute("UPDATE campaign_intents SET status='UNKNOWN'")
        with self.assertRaises(Invalid):
            AuthorityExpiry(f.store).preview(
                "sample",
                dict(principal="owner"),
                dict(
                    kind="CAMPAIGN",
                    id=f.scope["scope_id"],
                    expires=(datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
                ),
            )


class OrganicIntegration(unittest.TestCase):
    def setUp(self):
        self.fixture = organic_fixtures.OrganicPolicyTests(
            "test_policy_limits_and_external_or_unknown_cost_are_rejected"
        )
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def test_organic_extension_preserves_policy_and_reservations(self):
        f = self.fixture
        policy = f.create()
        original = f.call("reserve", f.reservation_body(policy))
        with connection(f.store.path) as db:
            before = dict(db.execute("SELECT * FROM organic_video_policies").fetchone())
        review, _ = extend(
            f.store,
            organic_fixtures.APP,
            organic_fixtures.OWNER,
            "ORGANIC_POLICY",
            policy["id"],
            (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
        )
        self.assertEqual(review["preview"]["usage"]["generations"], 1)
        later = f.call("reserve", f.reservation_body(policy))
        self.assertEqual(original["data"]["permission_expires_at"], f.policy["expires_at"])
        self.assertEqual(later["data"]["permission_expires_at"], review["preview"]["new_expiry"])
        from mission_control.organic_video_policy import child_deadline

        with patch("mission_control.organic_video_policy.datetime") as clock:
            clock.now.return_value = datetime.now(timezone.utc) + timedelta(hours=2)
            with self.assertRaises(PermissionError):
                child_deadline(original["data"], f.policy["expires_at"])
            child_deadline(later["data"], f.policy["expires_at"])
        with connection(f.store.path) as db:
            self.assertEqual(before, dict(db.execute("SELECT * FROM organic_video_policies").fetchone()))

    def test_new_organic_long_approval_requires_explicit_consent(self):
        f = self.fixture
        selected = dict(f.policy, expires_at=(datetime.now(timezone.utc) + timedelta(days=2)).isoformat())
        with self.assertRaises(Invalid):
            f.create(selected)
        selected["extended_expiry_consent"] = True
        policy = f.create(selected)
        receipts = AuthorityExpiry(f.store).history(
            organic_fixtures.APP, organic_fixtures.OWNER, "ORGANIC_POLICY", policy["id"]
        )["receipts"]
        self.assertEqual(len(receipts), 1)

    def test_schedule_due_date_respects_original_admission_deadline(self):
        from mission_control.organic_video_schedule import due_authority

        f = self.fixture
        policy = f.create()
        admission = f.call("admit", f.admission(policy))
        extend(
            f.store,
            organic_fixtures.APP,
            organic_fixtures.OWNER,
            "ORGANIC_POLICY",
            policy["id"],
            (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
        )
        intent = dict(
            data=canonical(dict(request=dict(admission_id=admission["id"], admission_hash=admission["hash"])))
        )
        with connection(f.store.path) as db:
            row = db.execute("SELECT * FROM organic_video_policies WHERE id=?", (policy["id"],)).fetchone()
            current = f.policies._current(db, row)
            due_authority(db, organic_fixtures.APP, current, intent, datetime.now(timezone.utc) + timedelta(minutes=10))
            with self.assertRaises(Invalid):
                due_authority(
                    db, organic_fixtures.APP, current, intent, datetime.now(timezone.utc) + timedelta(hours=2)
                )


class DependentDisclosure(unittest.TestCase):
    def test_actual_campaign_schedule_item_is_reviewed(self):
        fixture = schedule_fixtures.ScheduleTests("test_off_cancels_queued_and_blocks_dispatch")
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        self.addCleanup(fixture.doCleanups)
        (
            _,
            draft,
            _,
            _,
        ) = fixture.prepare_batch()
        review = AuthorityExpiry(fixture.store).preview(
            "sample-one",
            AUTOMATION_OWNER,
            dict(
                kind="CAMPAIGN",
                id=draft["summary"]["scope_id"],
                expires=(datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
            ),
        )
        item = draft["summary"]["items"][0]
        disclosed = next(row for row in review["preview"]["dependent_deadlines"] if row["kind"] == "CAMPAIGN_SCHEDULE")
        self.assertEqual(
            (disclosed["id"], disclosed["due_at"], disclosed["expires"]),
            (item["item_id"], item["due_at"], draft["summary"]["permission_expires_at"]),
        )

    def test_actual_campaign_monitor_is_reviewed(self):
        fixture = monitor_fixtures.CampaignMonitorTests(
            "test_prepare_activate_exact_hash_owner_selection_and_finite_plan"
        )
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        monitor = fixture.activate()
        review = AuthorityExpiry(fixture.store).preview(
            "sample",
            dict(principal="owner"),
            dict(
                kind="CAMPAIGN",
                id=fixture.scope["scope_id"],
                expires=(datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
            ),
        )
        disclosed = next(row for row in review["preview"]["dependent_deadlines"] if row["kind"] == "CAMPAIGN_MONITOR")
        self.assertEqual(
            (disclosed["id"], disclosed["expires"]), (monitor["id"], monitor["summary"]["proposal"]["expires_at"])
        )

    def test_actual_reel_schedule_item_is_reviewed(self):
        fixture = video_schedule_fixtures.VideoScheduleTests(
            "test_off_cancels_shared_queue_and_prevents_provider_calls"
        )
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        self.addCleanup(fixture.doCleanups)
        _, active, _, _, _ = fixture.scheduled()
        review = AuthorityExpiry(fixture.store).preview(
            organic_fixtures.APP,
            organic_fixtures.OWNER,
            dict(
                kind="ORGANIC_POLICY",
                id=fixture.policy["id"],
                expires=(datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
            ),
        )
        disclosed = next(row for row in review["preview"]["dependent_deadlines"] if row["kind"] == "REEL_SCHEDULE")
        item = active["summary"]["items"][0]
        self.assertEqual(
            (disclosed["id"], disclosed["due_at"], disclosed["expires"]),
            (item["item_id"], item["due_at"], item["permission_expires_at"]),
        )


if __name__ == "__main__":
    unittest.main()
