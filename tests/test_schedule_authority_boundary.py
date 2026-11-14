"""Regression witnesses for retained schedule authority identity."""

import unittest

from mission_control.campaign_schedule_authority import check_scope


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
