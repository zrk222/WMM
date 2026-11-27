"""Adversarial probes for WMM's own reviewed-dispatch and approval controls.

Each case is derived from the product's own spec invariants
(specs/agent-reviewed-dispatch.md and the module contracts), not from any
external test material. Synthetic identities and isolated databases only.
"""

import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from mission_control.agent_checkpoints import Checkpoints
from mission_control.agent_review_dispatch import ReviewedDispatch
from mission_control.common import Invalid, canonical, digest, now, uid
from mission_control.db import connection
from mission_control.operation_authority import bound_owner, protected
from mission_control.operation_outcome import EffectUncertain
from mission_control.operator_client import ClientError, OperatorClient
from mission_control.publication_authority import Publications, current
from mission_control.review_access import Access
from mission_control.store import Store
from tests import test_agent_review_policy as fixture
from tests import test_verified_review as identities


class ReviewedDispatchAdversarialTests(unittest.TestCase):
    setUp_base = fixture.ReviewPolicyTests.setUp
    tearDown = fixture.ReviewPolicyTests.tearDown
    body = fixture.ReviewPolicyTests.body
    envelope = fixture.ReviewPolicyTests.envelope
    listing_body = fixture.ReviewPolicyTests.listing_body
    issue_reviewed = fixture.ReviewPolicyTests.issue_reviewed

    def setUp(self) -> None:
        self.setUp_base()
        Access(self.store).save(
            "sample-one",
            identities.OWNER,
            identities.CHECKER,
            dict(
                login=identities.CHECKER["login"],
                role="CHECKER",
                status="ACTIVE",
                version=None,
            ),
        )
        self.issued = self.issue_reviewed()
        self.token = self.issued["token"]
        self.dispatch = ReviewedDispatch(self.server.service)
        self.checkpoints = Checkpoints(self.store)
        self.input = self.envelope("growth.save", self.listing_body())

    def history(self) -> list:
        value = self.owner.call(self.envelope())
        assert isinstance(value, dict)
        return value["history"]

    def prepare(self) -> dict:
        return self.dispatch.prepare(self.token, "review-one", self.input)

    def approve(self, prepared: dict) -> dict:
        row = prepared["checkpoint"]
        return self.checkpoints.approve(
            "sample-one",
            "review-one",
            identities.CHECKER["principal"],
            row["revision"],
            row["hash"],
        )

    def resume(self, approved: dict) -> dict:
        return self.dispatch.resume(
            self.token,
            "sample-one",
            "review-one",
            approved["revision"],
            approved["hash"],
        )

    def bump_owner_role(self) -> None:
        with connection(self.store.path) as db:
            db.execute(
                "UPDATE operator_roles SET version=version+1 WHERE principal=?",
                (identities.OWNER["principal"],),
            )

    def test_stale_maker_role_version_denies_approve(self) -> None:
        waiting = self.prepare()
        row = waiting["checkpoint"]
        self.bump_owner_role()
        with self.assertRaises((Invalid, PermissionError)):
            self.checkpoints.approve(
                "sample-one",
                "review-one",
                identities.CHECKER["principal"],
                row["revision"],
                row["hash"],
            )
        self.assertEqual(self.history(), [])

    def test_stale_maker_role_version_denies_resume(self) -> None:
        waiting = self.prepare()
        approved = self.approve(waiting)
        self.bump_owner_role()
        with self.assertRaises((Invalid, PermissionError)):
            self.resume(approved)
        self.assertEqual(self.history(), [])

    def test_reprepare_after_success_never_resurrects_or_duplicates(self) -> None:
        waiting = self.prepare()
        approved = self.approve(waiting)
        done = self.resume(approved)
        self.assertEqual(done["checkpoint"]["state"], "SUCCEEDED")
        replay = self.prepare()
        self.assertEqual(replay["checkpoint"]["state"], "SUCCEEDED")
        self.assertEqual(replay["result"], done["result"])
        with self.assertRaises(Invalid):
            self.resume(approved)
        self.assertEqual(len(self.history()), 1)

    def test_reprepare_after_unknown_never_rearms_execution(self) -> None:
        def uncertain(service, envelope):
            raise EffectUncertain()

        dispatch = ReviewedDispatch(self.server.service, executor=uncertain)
        waiting = dispatch.prepare(self.token, "review-one", self.input)
        approved = self.approve(waiting)
        done = dispatch.resume(
            self.token,
            "sample-one",
            "review-one",
            approved["revision"],
            approved["hash"],
        )
        self.assertEqual(done["checkpoint"]["state"], "UNKNOWN")
        replay = dispatch.prepare(self.token, "review-one", self.input)
        self.assertEqual(replay["checkpoint"]["state"], "UNKNOWN")
        with self.assertRaises(Invalid):
            dispatch.resume(
                self.token,
                "sample-one",
                "review-one",
                approved["revision"],
                approved["hash"],
            )
        self.assertEqual(self.history(), [])

    def test_approval_replay_is_rejected(self) -> None:
        waiting = self.prepare()
        self.approve(waiting)
        row = waiting["checkpoint"]
        with self.assertRaises(Invalid):
            self.checkpoints.approve(
                "sample-one",
                "review-one",
                identities.CHECKER["principal"],
                row["revision"],
                row["hash"],
            )

    def test_expired_checkpoint_cannot_be_approved(self) -> None:
        waiting = self.prepare()
        row = waiting["checkpoint"]
        future = Checkpoints(self.store, clock=lambda: datetime.now(timezone.utc) + timedelta(hours=2))
        with self.assertRaises(Invalid):
            future.approve(
                "sample-one",
                "review-one",
                identities.CHECKER["principal"],
                row["revision"],
                row["hash"],
            )
        self.assertEqual(self.history(), [])

    def test_unrelated_maker_cannot_cancel(self) -> None:
        Access(self.store).save(
            "sample-one",
            identities.OWNER,
            identities.STRANGER,
            dict(
                login=identities.STRANGER["login"],
                role="MAKER",
                status="ACTIVE",
                version=None,
            ),
        )
        waiting = self.prepare()
        row = waiting["checkpoint"]
        with self.assertRaises(PermissionError):
            self.checkpoints.cancel(
                "sample-one",
                "review-one",
                identities.STRANGER["principal"],
                row["revision"],
            )

    def test_reconcile_requires_uncertain_state(self) -> None:
        waiting = self.prepare()
        row = waiting["checkpoint"]
        cancelled = self.checkpoints.cancel("sample-one", "review-one", identities.OWNER["principal"], row["revision"])
        self.assertEqual(cancelled["state"], "CANCELLED")
        with self.assertRaises(Invalid):
            self.checkpoints.reconcile(
                "sample-one",
                "review-one",
                identities.CHECKER["principal"],
                cancelled["revision"],
                "SUCCEEDED",
                "a" * 64,
            )

    def test_ordinary_dispatch_denial_consumes_no_quota(self) -> None:
        issued = self.issue_reviewed()
        client = OperatorClient(self.origin, grant_token=issued["token"])
        with self.assertRaises(ClientError) as error:
            client.call(self.envelope("growth.save", self.listing_body()))
        self.assertEqual(error.exception.status, 403)
        rows = self.grants.list("sample-one", identities.OWNER)["grants"]
        self.assertEqual(rows[0]["used"], 0)

    def test_reviewed_grant_requires_executable_call_ceiling(self) -> None:
        """Regression: max_calls=1 with a review policy deadlocked after preparation.

        Before the issuance guard, such a grant consumed its only attempt in
        prepare, was approved, and could never resume (quota exhausted), leaving
        a permanent unexecutable APPROVED checkpoint.
        """
        body = dict(self.body(max_calls=1), review_operations=["growth.save"])
        with self.assertRaises(ClientError) as error:
            self.owner.request("POST", "/api/apps/sample-one/agent-grants/issue", body)
        self.assertEqual(error.exception.status, 400)
        with connection(self.store.path) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM agent_grants").fetchone()[0], 1)  # only setUp's grant
        body = dict(self.body(max_calls=2), review_operations=["growth.save"])
        issued = self.owner.request("POST", "/api/apps/sample-one/agent-grants/issue", body)
        dispatch = ReviewedDispatch(self.server.service)
        waiting = dispatch.prepare(issued["token"], "review-single", self.input)
        row = waiting["checkpoint"]
        approved = self.checkpoints.approve(
            "sample-one",
            "review-single",
            identities.CHECKER["principal"],
            row["revision"],
            row["hash"],
        )
        done = dispatch.resume(
            issued["token"],
            "sample-one",
            "review-single",
            approved["revision"],
            approved["hash"],
        )
        self.assertEqual(done["checkpoint"]["state"], "SUCCEEDED")


APP = "adversarial-pub"
PUB_OWNER = {"principal": "github:1", "login": "owner"}


class Sessions:
    def local(self, session: Any, principal: Any, generation: Any = None) -> dict:
        return {"session_generation": 1}


class PublicationAdversarialTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name) / "data.sqlite")
        with connection(self.store.path) as db:
            db.execute(
                "INSERT INTO apps(id,data,updated) VALUES(?,?,?)",
                (APP, canonical({"name": "Fixture"}), now()),
            )
        Access(self.store).bootstrap(APP, PUB_OWNER, {"confirm_owner": True})
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
            data = {
                "destination": {"id": "profile1"},
                "facts": {"reported_scopes": ["w_member_social"]},
            }
            db.execute(
                "INSERT INTO social_connections VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    APP,
                    self.connection_id,
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
            "connection_id": self.connection_id,
            "connection_version": 1,
            "destination_id": "profile1",
            "kind": "linkedin_text",
            "title": "",
            "caption": "Hello",
            "link": None,
            "artifact": None,
            "rights_hashes": [
                digest(
                    {
                        "kind": "OWNER_ORIGINAL_COPY",
                        "title": "",
                        "caption": "Hello",
                        "link": None,
                    }
                )
            ],
            "source_hashes": [],
            "settings": {"visibility": "PUBLIC"},
        }

    def call(self, operation: str, body: dict, fn: Callable[[], Any]) -> Any:
        envelope = {"app_id": APP, "operation": operation, "input": body}
        with bound_owner(self.store, envelope, self.sessions, "s", PUB_OWNER), protected(self.store, envelope):
            return fn()

    def prepare(self) -> Any:
        return self.call(
            "publication.prepare",
            {"draft": self.draft, "preflight_id": None},
            lambda: self.svc.prepare(APP, self.draft),
        )

    def activate(self, item: dict, **extra: Any) -> Any:
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
            "publication.activate",
            {"id": item["id"], "body": body},
            lambda: self.svc.activate(APP, item["id"], body),
        )

    def test_direct_status_flip_is_caught_at_read(self) -> None:
        item = self.prepare()
        with connection(self.store.path) as db:
            # The state-guard trigger permits PREPARED->APPROVED as a transition;
            # the read path must still reject the missing approval receipt.
            db.execute(
                "UPDATE publication_authorities SET status='APPROVED' WHERE id=?",
                (item["id"],),
            )
        with self.assertRaises(Invalid):
            self.call(
                "publication.get",
                {"id": item["id"]},
                lambda: self.svc.get(APP, item["id"]),
            )

    def test_approval_tamper_is_blocked_and_original_intact(self) -> None:
        item = self.prepare()
        approved = self.activate(item)
        with connection(self.store.path) as db, self.assertRaises(sqlite3.IntegrityError):
            db.execute(
                "UPDATE publication_authorities SET approval=? WHERE id=?",
                (canonical({"forged": True}), item["id"]),
            )
        value = self.call("publication.get", {"id": item["id"]}, lambda: self.svc.get(APP, item["id"]))
        self.assertEqual(value["approval_hash"], approved["approval_hash"])

    def test_revoked_approval_cannot_be_charged(self) -> None:
        item = self.prepare()
        approved = self.activate(item)
        self.call(
            "publication.revoke",
            {"id": item["id"], "version": approved["version"]},
            lambda: self.svc.revoke(APP, item["id"], approved["version"]),
        )

        def charge():
            with connection(self.store.path) as db:
                db.execute("BEGIN IMMEDIATE")
                return current(db, self.store, APP, item["id"], charge=True)

        with self.assertRaises((Invalid, PermissionError)):
            self.call("publication.execute", {"id": item["id"]}, charge)

    def test_due_time_equal_to_expiry_is_rejected(self) -> None:
        item = self.prepare()
        expiry = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        with self.assertRaises(Invalid):
            self.activate(item, expires_at=expiry, due_at=expiry)


if __name__ == "__main__":
    unittest.main()
