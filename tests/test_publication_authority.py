"""Publication approvals bind owner, app, connection and exact review."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile, unittest
from unittest.mock import patch
from mission_control.common import Invalid, canonical, digest, now, uid
from mission_control.db import connection
from mission_control.operation_authority import bound_owner, protected
from mission_control.publication_authority import Publications, current, record_preflight
from mission_control.review_access import Access
from mission_control.store import Store
from mission_control import publication_artifacts

APP = "authority-test"
OWNER = {"principal": "github:1", "login": "owner"}


class Sessions:
    def local(self, session, principal, generation=None):
        return {"session_generation": 1}


class PublicationAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name) / "data.sqlite")
        with connection(self.store.path) as db:
            db.execute("INSERT INTO apps(id,data,updated) VALUES(?,?,?)", (APP, canonical({"name": "Fixture"}), now()))
        Access(self.store).bootstrap(APP, OWNER, {"confirm_owner": True})
        self.connection = uid()
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
            data = {"destination": {"id": "profile1"}, "facts": {"reported_scopes": ["w_member_social"]}}
            db.execute(
                "INSERT INTO social_connections VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    APP,
                    self.connection,
                    "linkedin",
                    1,
                    1,
                    "profile1",
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
        self.svc = Publications(self.store)
        self.sessions = Sessions()
        self.draft = {
            "schema": "wmm.organic-publication.v1",
            "request_id": uid(),
            "app_id": APP,
            "manifest_version": 1,
            "provider": "linkedin",
            "connection_id": self.connection,
            "connection_version": 1,
            "destination_id": "profile1",
            "kind": "linkedin_text",
            "title": "",
            "caption": "Hello",
            "link": None,
            "artifact": None,
            "rights_hashes": [digest({"kind": "OWNER_ORIGINAL_COPY", "title": "", "caption": "Hello", "link": None})],
            "source_hashes": [],
            "settings": {"visibility": "PUBLIC"},
        }

    def call(self, operation, body, fn):
        envelope = {"app_id": APP, "operation": operation, "input": body}
        with bound_owner(self.store, envelope, self.sessions, "s", OWNER):
            with protected(self.store, envelope):
                return fn()

    def prepare(self):
        body = {"draft": self.draft, "preflight_id": None}
        return self.call("publication.prepare", body, lambda: self.svc.prepare(APP, self.draft))

    def activate(self, item, **extra):
        body = {
            "review_hash": item["review_hash"],
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            "max_calls": 3,
            "extended_expiry_consent": False,
            "confirm_publish": True,
            "confirm_rights": True,
        }
        body.update(extra)
        return self.call(
            "publication.activate", {"id": item["id"], "body": body}, lambda: self.svc.activate(APP, item["id"], body)
        )

    def test_review_approval_charge_and_revocation(self):
        item = self.prepare()
        self.assertEqual(item["status"], "PREPARED")
        approved = self.activate(item)
        self.assertEqual(approved["status"], "APPROVED")

        def charge():
            with connection(self.store.path) as db:
                db.execute("BEGIN IMMEDIATE")
                return current(db, self.store, APP, item["id"], charge=True)

        value = self.call("publication.execute", {"id": item["id"]}, charge)
        self.assertEqual(value["authority"]["calls_used"], 1)
        revoked = self.call(
            "publication.revoke",
            {"id": item["id"], "version": approved["version"]},
            lambda: self.svc.revoke(APP, item["id"], approved["version"]),
        )
        self.assertEqual(revoked["status"], "REVOKED")

        def check_current():
            with connection(self.store.path) as db:
                return current(db, self.store, APP, item["id"])

        with self.assertRaises((Invalid, PermissionError)):
            self.call("publication.execute", {"id": item["id"]}, check_current)

    def test_stale_approval_and_connection_fail_closed(self):
        item = self.prepare()
        with self.assertRaises((Invalid, PermissionError)):
            self.activate(item, review_hash="0" * 64)
        with connection(self.store.path) as db:
            db.execute("UPDATE social_connections SET version=2 WHERE app_id=? AND id=?", (APP, self.connection))
        with self.assertRaises((Invalid, PermissionError)):
            self.activate(item)

    def test_extended_expiry_requires_explicit_consent(self):
        item = self.prepare()
        future = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
        with self.assertRaises(Invalid):
            self.activate(item, expires_at=future)
        result = self.activate(item, expires_at=future, extended_expiry_consent=True)
        self.assertEqual(result["status"], "APPROVED")

    def test_tiktok_preflight_owner_and_staleness(self):
        stamp = now()
        identity = uid()
        with connection(self.store.path) as db:
            db.execute(
                "INSERT INTO social_configs VALUES(?,?,?,?,?,?,?,?)",
                (APP, "tiktok", 1, canonical({"provider": "tiktok"}), "fixture", "CONFIGURED_UNTESTED", stamp, stamp),
            )
            data = {"destination": {"id": "tt1"}, "facts": {"reported_scopes": ["video.publish"]}}
            db.execute(
                "INSERT INTO social_connections VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    APP,
                    identity,
                    "tiktok",
                    1,
                    1,
                    "tt1",
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
        info = {
            "creator_username": "creator",
            "creator_nickname": "Creator",
            "privacy_level_options": ["SELF_ONLY"],
            "max_video_post_duration_sec": 60,
            "comment_disabled": False,
            "duet_disabled": False,
            "stitch_disabled": False,
        }
        body = {"connection_id": identity, "connection_version": 1, "destination_id": "tt1"}
        with (
            patch("mission_control.publication_authority.time.time", return_value=1000),
            patch("mission_control.publication_credentials.context", return_value=object()),
            patch("mission_control.publication_tiktok.creator_info", return_value=info),
        ):
            pre = self.call(
                "publication.preflight", body, lambda: record_preflight(self.store, APP, identity, 1, "tt1")
            )
            with self.assertRaises(TypeError):
                record_preflight(self.store, APP, identity, 1, "tt1", info)
        with connection(self.store.path) as db:
            with self.assertRaises(Exception):
                db.execute("UPDATE publication_preflights SET info=? WHERE id=?", ("{}", pre["id"]))
        from mission_control.publication_authority import _preflight

        draft = {
            "provider": "tiktok",
            **body,
            "settings": {
                "privacy_level": "SELF_ONLY",
                "disable_comment": True,
                "disable_duet": True,
                "disable_stitch": True,
            },
        }
        with (
            connection(self.store.path) as db,
            patch("mission_control.publication_authority.time.time", return_value=1301),
        ):
            with self.assertRaises(Invalid):
                _preflight(db, APP, OWNER["principal"], pre["id"], draft, fresh=True)

    def test_stale_app_and_replaced_owner_role_invalidate_approval(self):
        item = self.prepare()
        self.activate(item)

        def check_current():
            with connection(self.store.path) as db:
                return current(db, self.store, APP, item["id"])

        with connection(self.store.path) as db:
            db.execute("UPDATE apps SET version=version+1 WHERE id=?", (APP,))
        with self.assertRaises((Invalid, PermissionError)):
            self.call("publication.execute", {"id": item["id"]}, check_current)
        with connection(self.store.path) as db:
            db.execute("UPDATE apps SET version=version-1 WHERE id=?", (APP,))
            db.execute(
                "UPDATE operator_roles SET version=version+1 WHERE app_id=? AND principal=?", (APP, OWNER["principal"])
            )
        with self.assertRaises((Invalid, PermissionError)):
            self.call("publication.execute", {"id": item["id"]}, check_current)

    def test_budget_and_review_are_enforced_atomically(self):
        item = self.prepare()
        self.activate(item, max_calls=1)

        def charge():
            with connection(self.store.path) as db:
                db.execute("BEGIN IMMEDIATE")
                return current(db, self.store, APP, item["id"], charge=True)

        self.call("publication.execute", {"id": item["id"]}, charge)
        with self.assertRaises(PermissionError):
            self.call("publication.execute", {"id": item["id"]}, charge)
        with connection(self.store.path) as db:
            with self.assertRaises(Exception):
                db.execute("UPDATE publication_authorities SET draft=? WHERE id=?", ("{}", item["id"]))

    def test_nonmatching_protected_envelope_is_rejected(self):
        envelope = {
            "app_id": APP,
            "operation": "publication.prepare",
            "input": {"draft": self.draft, "preflight_id": None},
        }
        changed = {**self.draft, "caption": "Altered"}
        with bound_owner(self.store, envelope, self.sessions, "s", OWNER):
            with protected(self.store, envelope):
                with self.assertRaises(PermissionError):
                    self.svc.prepare(APP, changed)

    def test_effect_boundary_rechecks_proof_without_rereading_media(self):
        item = self.prepare()
        self.activate(item)

        def check_current():
            with connection(self.store.path) as db:
                return current(db, self.store, APP, item["id"])

        with patch("mission_control.publication_artifacts.verify", wraps=publication_artifacts.verify) as verify:
            self.call("publication.execute", {"id": item["id"]}, check_current)
        self.assertIs(verify.call_args.kwargs["verify_bytes"], False)

    def test_due_time_is_approved_and_bounded(self):
        item = self.prepare()
        due = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()
        approved = self.activate(item, due_at=due)
        self.assertEqual(approved["due_at"], due)
        with connection(self.store.path) as db:
            approval = db.execute("SELECT approval FROM publication_authorities WHERE id=?", (item["id"],)).fetchone()[
                "approval"
            ]
        self.assertIn(due, approval)

    def test_due_time_rejects_past_naive_and_after_expiry(self):
        for due in (
            (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
            "2026-01-01T00:00:00",
            "invalid",
            (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(),
        ):
            with self.subTest(due=due):
                item = self.prepare()
                with self.assertRaises(Invalid):
                    self.activate(item, due_at=due)
                self.draft = {**self.draft, "request_id": uid()}
