"""Evidence boundaries for a campaign-scoped Meta Insights spend read."""

import json
import unittest
from datetime import date
from unittest.mock import patch

from mission_control.campaign_transport import META_VERSION, MetaTransport, Unconfirmed
from mission_control.common import Invalid


class MetaWindowedSpendTests(unittest.TestCase):
    since = date(2026, 10, 1)
    until = date(2026, 10, 31)

    def read(self):
        return MetaTransport().campaign_spend_window(
            "123", "456", "CAD", self.since, self.until, "fixture-token", "fixture-secret", lambda: None
        )

    def test_exact_read_preserves_amount_and_lag(self):
        row = dict(
            campaign_id="123",
            account_id="456",
            account_currency="CAD",
            date_start="2026-10-01",
            date_stop="2026-10-31",
            spend="6.005",
        )
        with patch.object(MetaTransport, "request", return_value={"data": [row]}) as request:
            result = self.read()
        method, path, fields, *_ = request.call_args.args
        self.assertEqual((method, path), ("GET", f"/{META_VERSION}/123/insights"))
        self.assertEqual(json.loads(fields["time_range"]), {"since": "2026-10-01", "until": "2026-10-31"})
        self.assertEqual(fields["level"], "campaign")
        self.assertNotIn("date_preset", fields)
        self.assertEqual(result["reported_spend"], "6.005")
        self.assertEqual(result["reporting"], "PROVIDER_REPORTED_MAY_LAG")

    def test_mismatched_scope_or_incomplete_results_are_not_spend(self):
        row = dict(
            campaign_id="123",
            account_id="456",
            account_currency="CAD",
            date_start="2026-10-01",
            date_stop="2026-10-31",
            spend="0",
        )
        for key, value in (
            ("campaign_id", "124"),
            ("account_id", "457"),
            ("account_currency", "USD"),
            ("date_start", "2026-10-02"),
            ("date_stop", "2026-10-30"),
            ("spend", "-0.1"),
        ):
            with (
                self.subTest(field=key),
                patch.object(MetaTransport, "request", return_value={"data": [dict(row, **{key: value})]}),
                self.assertRaises(Unconfirmed),
            ):
                self.read()
        for payload in ({"data": [row, row]}, {"data": [row], "paging": {"next": "https://example.invalid"}}):
            with patch.object(MetaTransport, "request", return_value=payload), self.assertRaises(Unconfirmed):
                self.read()
        with patch.object(MetaTransport, "request", return_value={"data": []}):
            self.assertIsNone(self.read()["reported_spend"])

    def test_oversize_and_inverted_windows_never_call_provider(self):
        with patch.object(MetaTransport, "request") as request:
            for since, until in ((self.until, self.since), (self.since, date(2026, 11, 1))):
                with self.assertRaises(Invalid):
                    MetaTransport().campaign_spend_window(
                        "123", "456", "CAD", since, until, "fixture-token", "fixture-secret", lambda: None
                    )
            request.assert_not_called()
