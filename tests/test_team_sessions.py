"""Durable app-scoped team sessions bound to verified GitHub identity."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from mission_control.common import Invalid
from mission_control.db import connection
from mission_control.review_access import Access
from mission_control.store import Store
from mission_control.team_sessions import list_sessions, login, open_session, revoke, verify

APP = "sample-one"
OWNER = {"principal": "github:1", "login": "owner"}
MEMBER = {"principal": "github:2", "login": "member-one"}


class TeamSessionTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.store = Store(Path(self.folder.name) / "state.sqlite", seed=False)
        for app in (APP, "sample-two"):
            self.store.save_app(app, dict(name="Synthetic " + app, release="build-1", job="Synthetic job",
                                         audience="Synthetic audience", activation="Synthetic value", locale="en-US"))
        Access(self.store).bootstrap(APP, OWNER, {"confirm_owner": True})
        from mission_control.team_access import accept, issue
        invitation = issue(self.store, APP, OWNER, dict(login=MEMBER["login"], role="MAKER",
            expires=(datetime.now(timezone.utc) + timedelta(hours=4)).isoformat()))
        accept(self.store, invitation["token"], MEMBER)

    def test_login_stores_only_a_hash_and_verify_returns_identity(self):
        with patch("mission_control.team_sessions.github_read", return_value=MEMBER):
            issued = login(self.store, APP, "g" * 30, 4)
        self.assertEqual(issued["token_delivery"], "ONCE_ONLY")
        self.assertNotIn("token_hash", issued["session"])
        with connection(self.store.path) as db:
            self.assertNotIn(issued["token"], "\n".join(db.iterdump()))
        value = verify(self.store, issued["token"])
        self.assertEqual((value["principal"], value["login"], value["app_id"]), (MEMBER["principal"], MEMBER["login"], APP))
        self.assertNotIn(issued["token"], str(list_sessions(self.store, APP, OWNER)))

    def test_expired_and_revoked_sessions_are_denied(self):
        issued = open_session(self.store, APP, MEMBER)
        with connection(self.store.path) as db:
            db.execute("UPDATE team_sessions SET expires=? WHERE id=?",
                       ((datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(), issued["session"]["id"]))
        with self.assertRaises(PermissionError):
            verify(self.store, issued["token"])
        second = open_session(self.store, APP, MEMBER)
        listed = list_sessions(self.store, APP, OWNER)["sessions"][0]
        revoke(self.store, APP, OWNER, listed["id"], listed["version"])
        with self.assertRaises(PermissionError):
            verify(self.store, second["token"])
        with self.assertRaises(PermissionError):
            revoke(self.store, APP, MEMBER, listed["id"], listed["version"])

    def test_current_active_membership_is_required_to_open_and_verify(self):
        with self.assertRaises(PermissionError):
            open_session(self.store, APP, {"principal": "github:3", "login": "outsider"})
        issued = open_session(self.store, APP, MEMBER)
        with connection(self.store.path) as db:
            db.execute("UPDATE operator_roles SET status='REVOKED',version=version+1 WHERE app_id=? AND principal=?",
                       (APP, MEMBER["principal"]))
        with self.assertRaises(PermissionError):
            verify(self.store, issued["token"])

    def test_scope_validation_and_hostile_inputs(self):
        for hours in (0, 721, True):
            with self.subTest(hours=hours), self.assertRaises(Invalid):
                open_session(self.store, APP, MEMBER, hours)
        with self.assertRaises(Invalid):
            login(self.store, APP, "short")
        with self.assertRaises(PermissionError):
            verify(self.store, "wmms_" + "x" * 43)
        with self.assertRaises(PermissionError):
            open_session(self.store, APP, {"principal": "", "login": "member"})
        with self.assertRaises(PermissionError):
            list_sessions(self.store, "sample-two", OWNER)


if __name__ == "__main__":
    unittest.main()
