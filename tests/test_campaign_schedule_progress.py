import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest import TestCase
from unittest.mock import patch

from mission_control.campaign_execution import SCHEMA
from mission_control.campaign_schedule import CampaignSchedules, batch_progress, tick
from mission_control.common import Invalid, canonical, digest
from mission_control.db import SCHEMA as DB_SCHEMA
from mission_control.worker import run_once
from tests import test_campaign_schedule


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

    def test_duplicate_tag_activation_keeps_the_first_schedule_dispatchable(self) -> None:
        # Reuse the real owner/gateway fixture and fake provider from the schedule integration suite.
        fixture: Any = test_campaign_schedule.ScheduleTests()
        self.addCleanup(fixture.doCleanups)
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        service = CampaignSchedules(fixture.store)
        due = datetime.now(timezone.utc) + timedelta(seconds=30)
        drafts: list[tuple[str, str]] = []
        with fixture.owner_bound():
            for index, request_id in enumerate(
                ("44444444-4444-4444-8444-444444444444", "55555555-5555-4555-8555-555555555555")
            ):
                link = f"https://example.test/page?utm_source={index}&utm_campaign=shared-tag"
                post = dict(
                    fixture.post,
                    request_id=request_id,
                    link=link,
                    content_hash=digest({"message": fixture.post["message"], "link": link}),
                )
                fixture.scope["approved_content_hashes"] = [post["content_hash"]]
                scope = fixture.activate()
                draft = service.prepare(
                    "sample-one",
                    dict(scope_id=scope["scope_id"], items=[dict(due_at=due.isoformat(), request=post)]),
                )
                summary, summary_hash = draft["summary"], draft["summary_hash"]
                assert isinstance(summary, dict) and isinstance(summary_hash, str)
                batch_id = summary["batch_id"]
                assert isinstance(batch_id, str)
                drafts.append((batch_id, summary_hash))
            (first_id, first_hash), (second_id, second_hash) = drafts
            service.activate("sample-one", first_id, first_hash)
            with self.assertRaisesRegex(Invalid, "tracking tag belongs to an earlier campaign"):
                service.activate("sample-one", second_id, second_hash)

        with (
            patch("time.time", return_value=due.timestamp() + 1),
            patch("mission_control.campaign_execution.check_destination", return_value={"status": "REACHABLE"}),
        ):
            self.assertEqual(tick(fixture.store), 1)
            self.assertTrue(run_once(fixture.store))
            self.assertEqual(tick(fixture.store), 0)

        with fixture.owner_bound():
            first_status = service.status("sample-one", first_id)
            second_status = service.status("sample-one", second_id)
        items = first_status["items"]
        assert isinstance(items, list)
        self.assertEqual(items[0]["intent"]["status"], "VERIFIED")
        self.assertEqual(second_status["status"], "DRAFT")
        self.assertEqual(fixture.wire.posts, 1)
