"""Finite local rule schedules commit receipts and advance together."""

import copy
import sqlite3
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from mission_control import automation_proposal_schedule as schedules
from mission_control.automation_proposals import inbox
from mission_control.automation_store import save
from mission_control.common import Invalid
from mission_control.db import connection
from mission_control.review_access import Access
from mission_control.store import Store
from tests.test_automation_rules import EXAMPLE
from tests.test_verified_review import OWNER

START = datetime(2026, 11, 15, 7, tzinfo=timezone.utc)


class RuleScheduleTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store = Store(Path(tmp.name) / "workspace.sqlite3", seed=False)
        self.app = "fixture-one"
        self.owner = OWNER["principal"]
        self.version = self.store.save_app(self.app, {"name": "Demo", "release": "stable"})["version"]
        Access(self.store).bootstrap(self.app, OWNER, {"confirm_owner": True})
        rules = copy.deepcopy(EXAMPLE)
        rules["mode"] = "AUTO_WITHIN_GRANT"
        saved = save(self.store, self.app, OWNER, rules)
        assert saved is not None
        self.body = {
            "enabled": True,
            "version": None,
            "app_version": self.version,
            "saved": {"version": saved["version"], "hash": saved["hash"]},
            "study": None,
            "interval_hours": 1,
            "expires_at": (START + timedelta(days=3)).isoformat(),
            "max_runs": 2,
        }

    def enable(self, **changes: object) -> dict:
        with patch.object(schedules, "now", return_value=START.isoformat()):
            return schedules.configure(self.store, self.app, self.owner, {**self.body, **changes})

    def read(self) -> dict | None:
        return schedules.read(self.store, self.app, self.owner)

    def required(self) -> dict:
        value = self.read()
        assert value is not None
        return value

    def jobs(self) -> int:
        with connection(self.store.path) as db:
            return db.execute("SELECT count(*) FROM jobs").fetchone()[0]

    def test_concurrent_workers_retain_single_due_slot_then_skip_missed_slots(self) -> None:
        self.enable()
        delayed = START + timedelta(hours=10)
        save(self.store, self.app, OWNER, {**EXAMPLE, "mode": "PROPOSE_ONLY"})
        with (
            patch("mission_control.connection_setup.Connections.vault", side_effect=AssertionError("vault")),
            patch("mission_control.operator_identity.github_read", side_effect=AssertionError("provider")),
            ThreadPoolExecutor(max_workers=2) as pool,
        ):
            list(pool.map(lambda _: schedules.evaluate_due(self.store, self.app, delayed), range(2)))
        first = self.required()
        self.assertEqual(first["run_count"], 1)
        self.assertEqual(first["next_due"], (delayed + timedelta(hours=1)).isoformat(timespec="microseconds"))
        self.assertEqual(first["binding"]["saved"], self.body["saved"])
        reopened = Store(self.store.path, seed=False)
        schedules.evaluate_due(reopened, self.app, delayed + timedelta(hours=1))
        self.assertEqual(self.required()["status"], "EXHAUSTED")
        self.assertEqual(self.required()["run_count"], 2)
        items = inbox(reopened, self.app, self.owner)
        self.assertEqual(len(items["proposals"]), 1)
        assert items["latest_run"] is not None
        self.assertEqual(items["latest_run"]["proposals"][0]["status"], "UNCHANGED")
        self.assertEqual(self.jobs(), 0)

    def test_fault_after_insert_rolls_back_and_restart_can_retry_exact_slot(self) -> None:
        self.enable()
        real = schedules.evaluate_in_snapshot

        def interrupted(*args, **kwargs):
            real(*args, **kwargs)
            raise sqlite3.OperationalError("simulated process interruption")

        due = START + timedelta(hours=1)
        with (
            patch.object(schedules, "evaluate_in_snapshot", side_effect=interrupted),
            self.assertRaises(sqlite3.OperationalError),
        ):
            schedules.evaluate_due(self.store, self.app, due)
        self.assertEqual(self.required()["run_count"], 0)
        self.assertIsNone(inbox(self.store, self.app, self.owner)["latest_run"])
        reopened = Store(self.store.path, seed=False)
        schedules.evaluate_due(reopened, self.app, due)
        self.assertEqual(self.required()["run_count"], 1)
        self.assertEqual(len(inbox(reopened, self.app, self.owner)["proposals"]), 1)

    def test_off_expiry_app_and_role_drift_block_future_evaluations(self) -> None:
        for case in ("OFF", "EXPIRED", "app revision", "owner revision"):
            with self.subTest(case=case):
                current = self.read()
                self.enable(version=current["version"] if current else None)
                due = START + timedelta(hours=1)
                if case == "OFF":
                    schedules.configure(
                        self.store, self.app, self.owner, {"enabled": False, "version": self.required()["version"]}
                    )
                elif case == "EXPIRED":
                    due = START + timedelta(days=3)
                elif case == "app revision":
                    with connection(self.store.path, write=True) as db:
                        db.execute("UPDATE apps SET version=version+1 WHERE id=?", (self.app,))
                elif case == "owner revision":
                    with connection(self.store.path, write=True) as db:
                        db.execute(
                            "UPDATE operator_roles SET version=version+1 WHERE app_id=? AND principal=?",
                            (self.app, self.owner),
                        )
                schedules.evaluate_due(self.store, self.app, due)
                row = self.required()
                self.assertEqual(row["status"], case if case in {"OFF", "EXPIRED"} else "BLOCKED")
                self.assertEqual(row["run_count"], 0)
                self.assertIsNone(inbox(self.store, self.app, self.owner)["latest_run"])
                if case == "app revision":
                    self.body["app_version"] = self.version + 1

    def test_tick_rechecks_utc_expiry_under_lock_and_before_retaining_run(self) -> None:
        limit = START + timedelta(hours=3)
        before = limit - timedelta(milliseconds=1)
        for clock in ((before, limit), (before, before, limit)):
            current = self.read()
            self.enable(
                version=current["version"] if current else None,
                expires_at=limit.astimezone(timezone(timedelta(hours=14))).isoformat(),
            )
            self.assertEqual(self.required()["expires_at"], limit.isoformat(timespec="microseconds"))
            with patch.object(schedules, "now", side_effect=[stamp.isoformat() for stamp in clock]):
                self.assertEqual(schedules.tick(self.store), 1)
            self.assertEqual(self.required()["status"], "EXPIRED")
            self.assertEqual(self.required()["run_count"], 0)
            self.assertIsNone(inbox(self.store, self.app, self.owner)["latest_run"])

    def test_rejects_stale_or_unbounded_consent(self) -> None:
        for change in (
            {"interval_hours": 0},
            {"max_runs": True},
            {"max_runs": 31},
            {"version": 1},
            {"expires_at": START.isoformat()},
            {"app_version": 0},
        ):
            with self.subTest(change=change), self.assertRaises(Invalid):
                self.enable(**change)
        self.assertIsNone(self.read())
