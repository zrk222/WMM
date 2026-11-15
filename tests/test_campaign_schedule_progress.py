import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from unittest import TestCase

from mission_control.campaign_execution import SCHEMA
from mission_control.campaign_schedule import batch_progress
from mission_control.common import canonical, digest
from mission_control.db import SCHEMA as DB_SCHEMA


class ScheduleOwnerProgressTests(TestCase):
    def test_retained_state_separates_verified_history_expiry_and_uncertainty(self) -> None:
        starts = "2026-11-14T11:00:00+00:00"
        observed = datetime(2026, 11, 14, 14, tzinfo=timezone.utc)
        scope = {"expires_at": "2026-11-14T13:00:00+00:00"}
        stamp = digest(scope)
        summary = {"app_id": "app", "owner": "owner", "scope_id": "scope", "batch_id": "batch", "scope_hash": stamp}
        with closing(sqlite3.connect(":memory:")) as db:
            db.row_factory = sqlite3.Row
            db.executescript(DB_SCHEMA + SCHEMA)
            db.execute(
                "INSERT INTO campaign_scopes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ("app", "scope", "owner", 1, canonical(scope), stamp, "ACTIVE", 0, starts, starts),
            )
            batch = db.execute(
                "SELECT 'app' AS app_id, 'scope' AS scope_id, 'owner' AS owner, 'batch' AS id, 'ACTIVE' AS status"
            ).fetchone()
            self.assertIsNotNone(batch)
            assert batch is not None
            for state, expected in (
                ("READY", "APPROVAL_EXPIRED"),
                ("VERIFIED", "DELIVERY_VERIFIED"),
                ("NEEDS_RECONCILIATION", "NEEDS_RECONCILIATION"),
            ):
                with self.subTest(state=state):
                    self.assertEqual(
                        batch_progress(db, batch, summary, [{"effective_status": state}], observed), expected
                    )
            off = db.execute(
                "SELECT 'app' AS app_id, 'scope' AS scope_id, 'owner' AS owner, 'batch' AS id, 'OFF' AS status"
            ).fetchone()
            assert off is not None
            self.assertEqual(
                batch_progress(db, off, summary, [{"effective_status": "VERIFIED"}], observed), "DELIVERY_VERIFIED"
            )
            self.assertEqual(db.execute("SELECT status FROM campaign_scopes").fetchone()[0], "ACTIVE")
