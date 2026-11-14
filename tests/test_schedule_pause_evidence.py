"""The schedule label must follow retained provider evidence."""

import json
import unittest
from typing import Any
from unittest.mock import patch

from mission_control.campaign_schedule import tick
from mission_control.common import canonical, digest
from mission_control.db import connection
from mission_control.worker import run_once
from tests import test_campaign_schedule


class SchedulePauseEvidenceTests(unittest.TestCase):
    def test_pause_label_requires_an_intact_provider_receipt(self) -> None:
        fixture: Any = test_campaign_schedule.ScheduleTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        scope, due, request = fixture.paid_fixture()
        service, batch = fixture.paid_batch(scope, due, [request])
        with patch("time.time", return_value=due.timestamp() + 1):
            tick(fixture.store)
            run_once(fixture.store)
        fixture.owner_call("revoke", {"scope_id": scope["scope_id"]})
        with fixture.owner_bound():
            stopped = service.status("sample-one", batch["id"])["items"][0]
        self.assertEqual(stopped["effective_status"], "PAUSED_VERIFIED")
        self.assertNotIn("account_id", stopped["intent"])
        key = (stopped["intent"]["id"],)
        with connection(fixture.store.path) as db:
            original = db.execute("SELECT data FROM campaign_pause_receipts WHERE intent_id=?", key).fetchone()
            receipt = json.loads(original["data"])
            receipt["effective_status"] = "ACTIVE"
            db.execute(
                "UPDATE campaign_pause_receipts SET hash=?,data=? WHERE intent_id=?",
                (digest(receipt), canonical(receipt), *key),
            )
        with fixture.owner_bound():
            delivery_active = service.status("sample-one", batch["id"])["items"][0]
        self.assertEqual(delivery_active["effective_status"], "NEEDS_RECONCILIATION")
        self.assertEqual(delivery_active["intent"]["commitment"], stopped["intent"]["commitment"])
        with connection(fixture.store.path) as db:
            db.execute("UPDATE campaign_pause_receipts SET hash='invalid' WHERE intent_id=?", key)
        with fixture.owner_bound():
            self.assertTrue(service.status("sample-one", batch["id"])["evidence_unavailable"])
        with connection(fixture.store.path) as db:
            db.execute("DELETE FROM campaign_pause_receipts WHERE intent_id=?", key)
        with fixture.owner_bound():
            unverified = service.status("sample-one", batch["id"])["items"][0]
        self.assertEqual(unverified["effective_status"], "NEEDS_RECONCILIATION")
        self.assertEqual(unverified["intent"]["commitment"], stopped["intent"]["commitment"])
