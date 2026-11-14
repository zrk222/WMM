"""Regression witnesses for retained schedule authority identity."""

import unittest
from unittest.mock import patch

from mission_control.campaign_schedule_authority import check_deadline, check_lease, check_scope


class ScheduleAuthorityBoundaryTests(unittest.TestCase):
    def test_a_matching_scope_cannot_authorize_a_different_batch(self) -> None:
        scope = {
            "scope_id": "scope",
            "approval_hash": "hash",
            "owner_principal": "owner",
            "expires_at": "2099-01-01T00:00:00+00:00",
        }
        summary = {"batch_id": "approved", "app_id": "app", "scope_id": "scope", "scope_hash": "hash", "owner": "owner"}
        check_scope({"batch_id": "approved"}, summary, "app", scope)
        with self.assertRaisesRegex(PermissionError, "Scheduled campaign batch changed"):
            check_scope({"batch_id": "other"}, summary, "app", scope)

    def test_a_matching_batch_cannot_replace_scope_approval(self) -> None:
        scope = {
            "scope_id": "scope",
            "approval_hash": "reviewed",
            "owner_principal": "owner",
            "expires_at": "2099-01-01T00:00:00+00:00",
        }
        summary = {
            "batch_id": "approved",
            "app_id": "app",
            "scope_id": "scope",
            "scope_hash": "other",
            "owner": "owner",
        }
        with self.assertRaisesRegex(PermissionError, "Scheduled campaign scope changed"):
            check_scope({"batch_id": "approved"}, summary, "app", scope)

    def test_reviewed_deadline_denies_at_equality(self) -> None:
        expiry = "2030-01-01T00:00:00+00:00"
        with (
            patch("mission_control.campaign_schedule_authority.time.time", return_value=1893456000),
            self.assertRaisesRegex(PermissionError, "Scheduled campaign approval expired"),
        ):
            check_deadline({"permission_expires_at": expiry}, "2099-01-01T00:00:00+00:00")

    def test_worker_lease_denies_at_equality(self) -> None:
        row = {
            "app_id": "app",
            "action": "campaign_post",
            "batch_status": "ACTIVE",
            "item_status": "QUEUED",
            "job_status": "RUNNING",
            "attempts": 1,
            "lease": 100,
            "due": 99,
        }
        with patch("mission_control.campaign_schedule_authority.time.time", return_value=100):
            check_lease(dict(row, lease=101), "app", ("workspace", "job", 1))
            with self.assertRaisesRegex(PermissionError, "Scheduled campaign worker lease changed"):
                check_lease(row, "app", ("workspace", "job", 1))
