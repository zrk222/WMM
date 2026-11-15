"""Real scoped grants exercise publication operations without provider calls."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from mission_control.agent_grants import Grants
from mission_control.common import Invalid, canonical, digest, now, uid
from mission_control.db import connection
from mission_control.operation_authority import bound_agent, bound_owner, protected
from mission_control.operation_catalog import OPERATIONS, request_data
from mission_control.operation_runtime import execute
from mission_control.publication_authority import Publications
from mission_control.review_access import Access
from mission_control.store import Store

APP = "publication-agent-app"
OTHER_APP = "publication-agent-other"
OWNER = {"principal": "github:701", "login": "owner"}
AGENT_OPS = ["publication.list", "publication.get", "publication.draft", "publication.prepare", "publication.execute"]


class Identities:
    def local(self, session, principal, generation=None):
        return {"session_generation": 1}


class PublicationAgentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name) / "agent.sqlite", seed=False)
        for app_id in (APP, OTHER_APP):
            self.store.save_app(
                app_id, dict(name="Synthetic publication app", release="build-1", locale="en-US", currency="USD")
            )
        Access(self.store).bootstrap(APP, OWNER, {"confirm_owner": True})
        Access(self.store).bootstrap(OTHER_APP, OWNER, {"confirm_owner": True})
        self.connection_id = uid()
        stamp = now()
        with connection(self.store.path) as db:
            db.execute(
                "INSERT INTO social_configs VALUES(?,?,?,?,?,?,?,?)",
                (
                    APP,
                    "linkedin",
                    1,
                    canonical({"provider": "linkedin"}),
                    "fixture",
                    "CONFIGURED_UNTESTED",
                    stamp,
                    stamp,
                ),
            )
            data = {"destination": {"id": "profile-1"}, "facts": {"reported_scopes": ["w_member_social"]}}
            db.execute(
                "INSERT INTO social_connections VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    APP,
                    self.connection_id,
                    "linkedin",
                    1,
                    1,
                    "profile-1",
                    canonical(data),
                    "fixture",
                    "CONNECTED_READ_TESTED",
                    None,
                    None,
                    0,
                    None,
                    0,
                    stamp,
                    stamp,
                ),
            )
        self.grants = Grants(self.store)
        body = dict(
            agent_id="marketing-agent",
            manifest_version=1,
            operations=AGENT_OPS,
            expires=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            max_calls=20,
        )
        self.token = self.grants.issue(APP, OWNER, body)["token"]
        self.service = SimpleNamespace(store=self.store)

    def agent(self, envelope):
        admission = self.grants.admit(self.token, envelope)
        with bound_agent(self.store, envelope, admission), protected(self.store, envelope):
            return execute(self.service, envelope, caller="SCOPED_AGENT")

    def owner(self, envelope, fn):
        with bound_owner(self.store, envelope, Identities(), "session", OWNER), protected(self.store, envelope):
            return fn()

    def draft_body(self):
        return dict(
            provider="linkedin",
            kind="linkedin_text",
            connection_id=self.connection_id,
            connection_version=1,
            destination_id="profile-1",
            title="",
            caption="Synthetic draft",
            link=None,
            artifact_id=None,
            settings={"visibility": "PUBLIC"},
        )

    def test_catalog_exposes_only_scoped_read_prepare_and_enqueue_operations(self):
        expected = set(AGENT_OPS)
        self.assertTrue(expected.issubset(OPERATIONS))
        forbidden = {
            "publication.preflight",
            "publication.instagram-account",
            "publication.activate",
            "publication.revoke",
            "publication.reconcile",
            "publication.credentials",
        }
        self.assertFalse(forbidden & set(OPERATIONS))
        for operation in forbidden:
            with self.assertRaises(Invalid):
                request_data(dict(app_id=APP, operation=operation, input={}))
        self.assertEqual(
            request_data(dict(app_id=APP, operation="publication.execute", input={"id": "authority-1"}))["path"],
            "/api/apps/" + APP + "/publications/execute",
        )

    def test_agent_prepare_stays_prepared_and_cannot_publish_or_widen_approval(self):
        draft = self.agent(dict(app_id=APP, operation="publication.draft", input=self.draft_body()))["draft"]
        prepared = self.agent(
            dict(app_id=APP, operation="publication.prepare", input={"draft": draft, "preflight_id": None})
        )
        self.assertEqual(prepared["status"], "PREPARED")
        with self.assertRaises((PermissionError, Invalid)):
            self.agent(dict(app_id=APP, operation="publication.execute", input={"id": prepared["id"]}))
        with connection(self.store.path) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM publication_schedules").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT count(*) FROM jobs").fetchone()[0], 0)
        with self.assertRaises(Invalid):
            self.grants.issue(
                APP,
                OWNER,
                dict(
                    agent_id="widening-agent",
                    manifest_version=1,
                    operations=["publication.activate"],
                    expires=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
                    max_calls=1,
                ),
            )

    def test_agent_can_only_enqueue_the_exact_current_owner_approval(self):
        draft = self._draft()
        prepared = self.owner(
            dict(app_id=APP, operation="publication.prepare", input={"draft": draft, "preflight_id": None}),
            lambda: Publications(self.store).prepare(APP, draft),
        )
        approval = dict(
            review_hash=prepared["review_hash"],
            expires_at=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            max_calls=3,
            extended_expiry_consent=False,
            confirm_publish=True,
            confirm_rights=True,
        )
        approved = self.owner(
            dict(app_id=APP, operation="publication.activate", input={"id": prepared["id"], "body": approval}),
            lambda: Publications(self.store).activate(APP, prepared["id"], approval),
        )
        queued = self.agent(dict(app_id=APP, operation="publication.execute", input={"id": approved["id"]}))
        self.assertEqual(queued["status"], "QUEUED")
        with connection(self.store.path) as db:
            job = db.execute("SELECT action,status,data FROM jobs WHERE id=?", (queued["job_id"],)).fetchone()
            self.assertEqual((job["action"], job["status"]), ("social_publication", "QUEUED"))
            self.assertEqual(job["data"], canonical({"publication_id": approved["id"]}))

    def test_grant_cannot_cross_apps_and_status_is_owner_scoped(self):
        with self.assertRaises(PermissionError):
            self.agent(dict(app_id=OTHER_APP, operation="publication.list", input={}))
        listing = self.agent(dict(app_id=APP, operation="publication.list", input={}))
        self.assertEqual(
            {row["provider"] for row in listing["channels"]}, {"instagram", "tiktok", "youtube", "linkedin"}
        )
        draft = self._draft()
        envelope = dict(app_id=APP, operation="publication.prepare", input={"draft": draft, "preflight_id": None})
        prepared = self.owner(envelope, lambda: Publications(self.store).prepare(APP, draft))
        result = self.agent(dict(app_id=APP, operation="publication.get", input={"id": prepared["id"]}))
        self.assertEqual(result["owner"], OWNER["principal"])
        with self.assertRaises((Invalid, PermissionError)):
            self.agent(dict(app_id=APP, operation="publication.get", input={"id": uid()}))

    def _draft(self):
        from mission_control.publication_service import draft

        return self.owner(
            dict(app_id=APP, operation="publication.draft", input=self.draft_body()),
            lambda: draft(self.store, APP, self.draft_body()),
        )["draft"]


if __name__ == "__main__":
    unittest.main()
