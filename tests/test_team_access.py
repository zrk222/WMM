"""Single-use app invitations for MAKER/CHECKER; no public signup or OWNER grant."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from mission_control.common import Invalid
from mission_control.db import connection
from mission_control.review_access import Access
from mission_control.store import Store
from mission_control.team_access import accept, issue, list_invitations, revoke

APP = "sample-one"
OWNER = {"principal": "github:1", "login": "owner"}
INVITEE = {"principal": "github:2", "login": "maker-one"}


class TeamInvitationTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.store = Store(Path(self.folder.name) / "state.sqlite", seed=False)
        for app in (APP, "sample-two"):
            self.store.save_app(
                app,
                dict(
                    name="Synthetic " + app,
                    release="build-1",
                    job="Synthetic job",
                    audience="Synthetic audience",
                    activation="Synthetic value",
                    locale="en-US",
                ),
            )
        Access(self.store).bootstrap(APP, OWNER, {"confirm_owner": True})

    def body(self, login="maker-one", role="MAKER", hours=24):
        return dict(login=login, role=role, expires=(datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat())

    def test_owner_issues_once_only_invitation_and_accepts_maker(self):
        issued = issue(self.store, APP, OWNER, self.body())
        self.assertEqual(issued["token_delivery"], "ONCE_ONLY")
        self.assertNotIn("token_hash", issued["invitation"])
        self.assertNotIn(issued["token"], str(list_invitations(self.store, APP, OWNER)))
        with connection(self.store.path) as db:
            self.assertNotIn(issued["token"], "\n".join(db.iterdump()))
        accepted = accept(self.store, issued["token"], INVITEE)
        self.assertEqual((accepted["role"], accepted["status"]), ("MAKER", "ACTIVE"))
        members = Access(self.store).list(APP)["members"]
        self.assertTrue(any(row["principal"] == INVITEE["principal"] and row["role"] == "MAKER" for row in members))
        with self.assertRaises(Invalid):
            accept(self.store, issued["token"], INVITEE)

    def test_wrong_login_expiry_revocation_and_owner_assignment_are_rejected(self):
        issued = issue(self.store, APP, OWNER, self.body())
        with self.assertRaises(PermissionError):
            accept(self.store, issued["token"], dict(INVITEE, login="other"))
        with self.assertRaises(Invalid):
            issue(self.store, APP, OWNER, self.body(role="OWNER"))
        with self.assertRaises(PermissionError):
            issue(self.store, APP, INVITEE, self.body())
        with self.assertRaises(Invalid):
            issue(self.store, APP, OWNER, self.body(login="owner"))
        pending = list_invitations(self.store, APP, OWNER)["invitations"][0]
        revoke(self.store, APP, OWNER, dict(id=pending["id"], version=pending["version"]))
        with self.assertRaises(Invalid):
            accept(self.store, issued["token"], INVITEE)

    def test_expired_invitation_and_list_status(self):
        issued = issue(self.store, APP, OWNER, self.body())
        row = list_invitations(self.store, APP, OWNER)["invitations"][0]
        with connection(self.store.path) as db:
            db.execute(
                "UPDATE team_invitations SET expires=? WHERE app_id=? AND id=?",
                ((datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(), APP, row["id"]),
            )
        self.assertEqual(list_invitations(self.store, APP, OWNER)["invitations"][0]["status"], "EXPIRED")
        with self.assertRaises(Invalid):
            accept(self.store, issued["token"], INVITEE)

    def test_cross_app_access_and_owner_cannot_reaccept(self):
        issued = issue(self.store, APP, OWNER, self.body())
        with self.assertRaises(PermissionError):
            list_invitations(self.store, APP, INVITEE)
        with self.assertRaises(PermissionError):
            list_invitations(self.store, "sample-two", OWNER)
        with self.assertRaises(PermissionError):
            accept(self.store, issued["token"], dict(OWNER))


if __name__ == "__main__":
    unittest.main()
