"""Operational recovery reports exceptions from the exact saved rule schedule."""

import sqlite3
import unittest
from datetime import timedelta
from unittest.mock import patch

from mission_control.automation_proposal_schedule import evaluate_due
from mission_control.db import connection
from mission_control.weekly_inbox import operation_exceptions
from tests import test_automation_proposal_schedule as fixtures


class WeeklyRuleExceptionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = fixtures.RuleScheduleTests("test_rejects_stale_or_unbounded_consent")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.store = self.fixture.store
        self.app = self.fixture.app
        self.owner = self.fixture.owner
        self.fixture.enable()

    def cards(self, principal: str | None) -> list[dict]:
        with patch("mission_control.weekly_rule_exception.now", return_value=fixtures.START.isoformat()):
            cards = operation_exceptions(self.store, self.store.app(self.app), {"principal": principal})
        return [card for card in cards if card["category"] == "rule_schedule"]

    def test_stale_then_blocked_schedule_surfaces_one_safe_read_only_repair(self) -> None:
        self.assertEqual(self.cards(self.owner), [])
        with connection(self.store.path, write=True) as db:
            db.execute("UPDATE apps SET version=version+1 WHERE id=?", (self.app,))
        before = self.fixture.required()
        (issue,) = self.cards(self.owner)
        self.assertEqual(issue["resolution_route"], "results")
        self.assertEqual(issue["action"]["resource_id"], str(before["version"]))
        self.assertIn("changed", issue["reason"])
        self.assertEqual(self.fixture.required(), before)
        evaluate_due(self.store, self.app, fixtures.START + timedelta(hours=1))
        (issue,) = self.cards(self.owner)
        self.assertEqual(issue["state"], "BLOCKED")
        self.assertIn("start a new schedule", issue["next_action"])
        self.assertEqual(self.cards(None), [])
        self.assertEqual(self.cards("another-owner"), [])

    def test_corrupt_active_definition_does_not_expose_saved_fields(self) -> None:
        with connection(self.store.path, write=True) as db:
            db.execute(
                "UPDATE automation_rule_schedules SET definition=?,stopped_reason=? WHERE app_id=?",
                ("PRIVATE_RULE_TEXT", "PRIVATE_ERROR_TEXT", self.app),
            )
        (issue,) = self.cards(self.owner)
        self.assertNotIn("PRIVATE_", str(issue))
        self.assertIn("cannot verify", issue["reason"])
        self.assertTrue(issue["owner_only"])
        self.assertEqual(set(issue["evidence"]), {"status", "schedule_version", "app_version"})

    def test_terminal_normal_states_do_not_interrupt_owner(self) -> None:
        for status in ("OFF", "EXPIRED", "EXHAUSTED"):
            with self.subTest(status=status), connection(self.store.path, write=True) as db:
                db.execute(
                    "UPDATE automation_rule_schedules SET status=?,owner_version=owner_version+1 WHERE app_id=?",
                    (status, self.app),
                )
            self.assertEqual(self.cards(self.owner), [])

    def test_active_owner_revision_is_checked_before_the_next_run(self) -> None:
        with connection(self.store.path, write=True) as db:
            db.execute(
                "UPDATE operator_roles SET version=version+1 WHERE app_id=? AND principal=?",
                (self.app, self.owner),
            )
        (issue,) = self.cards(self.owner)
        self.assertIn("owner access changed", issue["reason"])
        self.assertEqual(self.fixture.required()["status"], "ACTIVE")

    def test_expired_and_exhausted_active_rows_stay_quiet_even_with_corrupt_definition(self) -> None:
        expired = (fixtures.START - timedelta(days=1)).isoformat()
        active = (fixtures.START + timedelta(days=1)).isoformat()
        for expiry, count in ((expired, 0), (active, self.fixture.body["max_runs"])):
            with self.subTest(expiry=expiry, count=count), connection(self.store.path, write=True) as db:
                db.execute(
                    "UPDATE automation_rule_schedules SET expires=?,run_count=?,definition=? WHERE app_id=?",
                    (expiry, count, "PRIVATE_RULE_TEXT", self.app),
                )
                self.assertEqual(
                    db.execute("SELECT status FROM automation_rule_schedules WHERE app_id=?", (self.app,)).fetchone()[
                        0
                    ],
                    "ACTIVE",
                )
            self.assertEqual(self.cards(self.owner), [])

    def test_rule_source_failure_preserves_other_cards_and_redacts_details(self) -> None:
        app = self.store.app(self.app)
        other_card = {"category": "agent_review"}
        with (
            patch("mission_control.weekly_inbox._agent_review_cards", return_value=[other_card]),
            patch(
                "mission_control.weekly_rule_exception.schedule_row",
                side_effect=sqlite3.OperationalError("PRIVATE_TABLE_DETAILS"),
            ) as schedule_read,
        ):
            cards = operation_exceptions(self.store, app, {"principal": self.owner})
            self.assertIn(other_card, cards)
            (issue,) = [card for card in cards if card["category"] == "rule_schedule"]
            self.assertEqual(issue["state"], "SOURCE_UNAVAILABLE")
            self.assertEqual(issue["evidence"], {"status": "SOURCE_UNAVAILABLE"})
            self.assertTrue(issue["owner_only"])
            self.assertEqual(issue["owner_principal"], self.owner)
            self.assertNotIn("PRIVATE_", str(issue))
            self.assertEqual(self.cards("another-owner"), [])
            schedule_read.assert_called_once()
