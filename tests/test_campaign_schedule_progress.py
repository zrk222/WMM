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
from mission_control.service import Service
from mission_control.worker import run_once
from tests import test_campaign_schedule


class ScheduleOwnerProgressTests(TestCase):
    def fixture(self) -> Any:
        fixture = test_campaign_schedule.ScheduleTests()
        self.addCleanup(fixture.doCleanups)
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        return fixture

    def test_watch_owner_sees_expiry_without_leaking_copy_or_reclassifying_delivery(self) -> None:
        fixture = self.fixture()
        _, _, batch, due = fixture.prepare_batch()
        service = Service(fixture.store)
        owner = test_campaign_schedule.OWNER["principal"]
        expired = datetime.fromtimestamp(due + 86_400, timezone.utc)
        with patch("mission_control.campaign_schedule.datetime", wraps=datetime) as clock:
            clock.now.return_value = expired
            alerts = service.workspace("sample-one", viewer=owner)["workflow"]["exceptions"]
            self.assertEqual([card["state"] for card in alerts], ["CAMPAIGN_SCHEDULE_APPROVAL_EXPIRED"])
            self.assertEqual(alerts[0]["batch_id"], batch["id"])
            self.assertNotIn(fixture.post["message"], canonical(alerts))
            self.assertEqual(service.workspace("sample-one")["workflow"]["exceptions"], [])
            self.assertEqual(service.workspace("sample-one", viewer="other-viewer")["workflow"]["exceptions"], [])
        self.assertEqual(fixture.wire.posts, 0)
        with patch("time.time", return_value=due + 1):
            self.assertEqual(tick(fixture.store), 1)
            self.assertTrue(run_once(fixture.store))
        with patch("mission_control.campaign_schedule.datetime", wraps=datetime) as clock:
            clock.now.return_value = expired
            self.assertEqual(service.workspace("sample-one", viewer=owner)["workflow"]["exceptions"], [])
        self.assertEqual(fixture.wire.posts, 1)

    def test_watch_keeps_unconfirmed_delivery_visible_after_turning_batch_off(self) -> None:
        fixture = self.fixture()
        schedule, _, batch, due = fixture.prepare_batch()
        fixture.wire.fail = True
        with patch("time.time", return_value=due + 1):
            self.assertEqual(tick(fixture.store), 1)
            self.assertTrue(run_once(fixture.store))
        with fixture.owner_bound():
            schedule.revoke("sample-one", batch["id"], batch["version"])
            self.assertEqual(schedule.status("sample-one", batch["id"])["progress"], "NEEDS_RECONCILIATION")
        service = Service(fixture.store)
        owner = test_campaign_schedule.OWNER["principal"]
        alerts = service.workspace("sample-one", viewer=owner)["workflow"]["exceptions"]
        self.assertEqual(
            [(card["state"], card["batch_id"]) for card in alerts],
            [("CAMPAIGN_SCHEDULE_NEEDS_RECONCILIATION", batch["id"])],
        )
        self.assertIn("before retrying", alerts[0]["next_action"])
        self.assertEqual(fixture.wire.posts, 1)

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
        fixture = self.fixture()
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
