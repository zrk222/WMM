"""Durable proposals reuse the evaluator without turning advice into work."""

import copy
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast
from unittest.mock import patch

from mission_control.automation_proposals import RuleRef, RunReceipt, dismiss, duration, inbox, run
from mission_control.automation_store import save
from mission_control.common import Invalid
from mission_control.db import connection
from mission_control.operator_client import ClientError, OperatorClient
from mission_control.review_access import Access
from mission_control.store import Store
from tests import test_agent_grants as grant_fixtures
from tests.test_automation_rules import EXAMPLE
from tests.test_verified_review import OWNER


class AutomationProposalTests(unittest.TestCase):
    def setUp(self) -> None:
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.store = Store(Path(folder.name) / "workspace.sqlite3", seed=False)
        self.app = "fixture-one"
        self.version = self.store.save_app(self.app, {"name": "Demo", "release": "stable"})["version"]
        Access(self.store).bootstrap(self.app, OWNER, {"confirm_owner": True})
        self.owner = OWNER["principal"]
        rules = copy.deepcopy(EXAMPLE)
        rules["mode"] = "AUTO_WITHIN_GRANT"
        for rule in rules["rules"]:
            rule["cooldown"] = "PT1H"
        result = save(self.store, self.app, OWNER, rules)
        assert result is not None
        self.ref: RuleRef = {"version": result["version"], "hash": result["hash"]}

    def at(self, minutes: int) -> RunReceipt:
        day, minute = divmod(minutes, 60)
        clock = datetime(2026, 11, 15, 8 + day, minute, tzinfo=timezone.utc)
        with patch("mission_control.automation_proposals.now", return_value=clock.isoformat()):
            return run(self.store, self.app, self.owner, self.version, self.ref)

    def counts(self) -> tuple[int, int, int]:
        with connection(self.store.path) as db:
            return (
                db.execute("SELECT count(*) FROM automation_rule_runs").fetchone()[0],
                db.execute("SELECT count(*) FROM automation_rule_proposals").fetchone()[0],
                db.execute("SELECT count(*) FROM jobs").fetchone()[0],
            )

    def test_exact_replay_and_dismissal_survive_reopen_without_effects(self) -> None:
        with (
            patch("mission_control.connection_setup.Connections.vault", side_effect=AssertionError("vault")),
            patch("mission_control.operator_identity.github_read", side_effect=AssertionError("provider")),
        ):
            one = self.at(0)
            self.assertEqual(self.at(0), one)
            proposal = one["proposals"][0]["id"]
            closed = dismiss(self.store, self.app, self.owner, proposal)
            self.assertEqual(dismiss(self.store, self.app, self.owner, proposal), closed)
            two = self.at(61)
            self.assertEqual(two["proposals"], [{"id": proposal, "status": "UNCHANGED"}])
            reopened = Store(self.store.path, seed=False)
            result = inbox(reopened, self.app, self.owner)
        self.assertEqual(len(result["proposals"]), 1)
        self.assertEqual(result["proposals"][0]["dismissed_at"], closed["dismissed_at"])
        self.assertEqual(result["proposals"][0]["proposal"]["mode"], "PROPOSE_ONLY")
        self.assertEqual(self.counts(), (2, 1, 0))

    def test_changed_facts_wait_for_cooldown_without_extending_it(self) -> None:
        self.at(0)
        self.store.save_record(
            self.app,
            dict(kind="retention", title="Changed facts", source="Synthetic", data={}, manifest_version=self.version),
        )
        for minute in (10, 59):
            blocked = self.at(minute)
            self.assertEqual(blocked["proposals"][0]["status"], "COOLDOWN")
        ready = self.at(60)
        self.assertEqual(ready["proposals"][0]["status"], "SAVED")
        self.assertEqual(self.at(61)["proposals"][0]["status"], "UNCHANGED")
        self.assertEqual(self.counts(), (5, 2, 0))

    def test_owner_app_version_and_commit_guard(self) -> None:
        with self.assertRaises(PermissionError):
            inbox(self.store, self.app, "github:other")
        with self.assertRaises(Invalid):
            run(self.store, self.app, self.owner, self.version + 1, self.ref)
        with self.assertRaises(Invalid):
            run(self.store, self.app, self.owner, self.version, cast(RuleRef, dict(self.ref, hash="0" * 64)))
        with self.assertRaises(PermissionError):
            run(
                self.store,
                self.app,
                self.owner,
                self.version,
                self.ref,
                commit_check=lambda: self.fail_session(),
            )
        self.assertEqual(self.counts(), (0, 0, 0))

    @staticmethod
    def fail_session() -> None:
        raise PermissionError("Synthetic session revoked")

    def test_legacy_cooldown_labels_are_not_accepted_for_durable_runs(self) -> None:
        for value in ("P8D", "PT169H", "tomorrow", "PT0M", "PT1.5H"):
            with self.subTest(value=value), self.assertRaises(Invalid):
                duration(value)


class AutomationProposalHTTPTests(unittest.TestCase):
    owner: OperatorClient
    origin: str
    store: Store
    setUp = grant_fixtures.GrantTests.setUp
    tearDown = grant_fixtures.GrantTests.tearDown
    url = "/api/apps/sample-one/automation/proposals"

    def test_owner_can_run_saved_rules_and_other_clients_cannot_read_or_dismiss(self) -> None:
        doc = self.owner.request("POST", "/api/apps/sample-one/automation/rules", {"document": EXAMPLE})
        assert doc is not None
        bound = {"version": doc["version"], "hash": doc["hash"]}
        version = self.store.app("sample-one")["version"]
        body = {"app_version": version, "saved": bound, "study": None, "request_id": "fixture-rule-request-1"}
        result = self.owner.request("POST", self.url + "/run", body)
        assert result is not None
        identity = result["proposals"][0]["id"]
        self.assertEqual(self.owner.request("POST", self.url + "/run", body), result)
        with self.assertRaises(ClientError):
            self.owner.request("POST", self.url + "/run", {**body, "study": {"study_id": "different"}})
        persisted = self.owner.request("GET", self.url)
        assert persisted is not None
        self.assertEqual(persisted["proposals"][0]["proposal"]["id"], identity)
        anonymous = OperatorClient(self.origin)
        anonymous.bootstrap()
        for client, url in [(anonymous, self.url), (self.owner, self.url.replace("sample-one", "sample-two"))]:
            with self.assertRaises(ClientError):
                client.request("GET", url)
            with self.assertRaises(ClientError):
                client.request("POST", url + "/dismiss", {"id": identity})
        result = self.owner.request("POST", self.url + "/dismiss", {"id": identity})
        assert result is not None
        self.assertIsNotNone(result["dismissed_at"])
