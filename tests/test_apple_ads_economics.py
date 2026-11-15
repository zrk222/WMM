"""Fixed, app-scoped campaign economics from a synthetic native report read."""

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from mission_control.apple_ads_economics import row_cost
from mission_control.common import Invalid, digest
from mission_control.provider_reports import read_report

BINDING = {"provider": "apple_ads", "store_app_id": "123", "account_id": "456"}
IDENTITY = {"id": 42, "promotedObjectType": "APPSTORE_APP", "promotedObjectId": "123", "adAccountId": "456"}


def report_options(days_ago: int = 1) -> dict[str, object]:
    end = datetime.now(timezone.utc).date() - timedelta(days=days_ago)
    return {
        "operation": "campaign_report",
        "campaign_ids": ["42"],
        "start": (end - timedelta(days=1)).isoformat(),
        "end": end.isoformat(),
    }


def page(rows: list[dict], *, total: int | None = None, offset: int = 0) -> dict:
    return {
        "result": {"rows": rows},
        "pagination": {"offset": offset, "pageSize": 100, "totalCount": len(rows) if total is None else total},
    }


class NativeAppleAcquisitionTests(unittest.TestCase):
    def read(self, report: dict, days_ago: int = 1) -> dict:
        with (
            patch("mission_control.provider_reports.credential", return_value="fixture-token"),
            patch(
                "mission_control.provider_reports.report_request",
                side_effect=[{"result": [IDENTITY]}, report],
            ) as transport,
        ):
            result = read_report(BINDING, "demo-app", report_options(days_ago))
        self.assertEqual(transport.call_count, 2)
        assert isinstance(result, dict)
        return result

    def test_retained_same_report_covers_exact_app_account_and_source(self) -> None:
        row = {
            "metadata": IDENTITY,
            "totalMetrics": {
                "localSpend": {"amount": "9.1203", "currency": "USD"},
                "totalInstalls": 7,
                "totalNewDownloads": 3,
                "totalRedownloads": 4,
            },
        }
        report = self.read(page([row]))
        evidence = report["campaign_acquisition"]
        self.assertFalse(report["external_writes"])
        self.assertFalse(evidence["revenue_source_joined"])
        self.assertEqual(
            (evidence["app_id"], evidence["store_app_id"], evidence["ad_account_id"]), ("demo-app", "123", "456")
        )
        self.assertEqual(evidence["provider_source_sha256"], report["source_hash"])
        self.assertEqual(evidence["observed_at"], report["observed_at"])
        self.assertEqual(evidence["reporting_timezone"], "UTC")
        self.assertEqual(evidence["ends_at_exclusive"].split("T")[0], datetime.now(timezone.utc).date().isoformat())
        self.assertEqual(
            evidence["rows"],
            [
                {
                    "campaign_id": "42",
                    "status": "AVAILABLE",
                    "billing_currency": "USD",
                    "spend_minor_exact": "912.03",
                    "first_time_downloads": 3,
                    "cost_per_new_download_minor": "304.0100",
                }
            ],
        )
        frozen = {key: value for key, value in evidence.items() if key != "receipt_sha256"}
        self.assertEqual(evidence["receipt_sha256"], digest(frozen))

    def test_unavailable_rows_never_count_redownloads_or_become_zero_cost(self) -> None:
        spend = {"localSpend": {"amount": "12", "currency": "JPY"}}
        cases = (
            ({**spend, "totalInstalls": 100}, "", "MISSING_FIRST_DOWNLOADS", None),
            ({**spend, "totalNewDownloads": 0}, "", "NO_FIRST_DOWNLOADS", 0),
            ({**spend, "totalNewDownloads": True}, "", "MISSING_FIRST_DOWNLOADS", None),
            ({"totalNewDownloads": 5, "localSpend": {"amount": "NaN", "currency": "USD"}}, "", "MISSING_SPEND", 5),
            ({"totalNewDownloads": 1, "localSpend": {"amount": "0", "currency": "USD"}}, "", "NO_REPORTED_SPEND", 1),
            ({**spend, "totalNewDownloads": 9}, "INCOMPLETE_REPORT", "INCOMPLETE_REPORT", 9),
        )
        for metrics, report_state, expected, count in cases:
            with self.subTest(status=expected):
                cost = row_cost("42", metrics, report_state)
                self.assertEqual(cost["status"], expected)
                self.assertEqual(cost["first_time_downloads"], count)
                self.assertIsNone(cost["cost_per_new_download_minor"])
        self.assertEqual(self.read(page([]))["campaign_acquisition"]["rows"][0]["status"], "NO_CAMPAIGN_ROW")

    def test_open_day_and_duplicate_campaign_are_not_comparable(self) -> None:
        row = {"metadata": IDENTITY, "totalMetrics": {"totalNewDownloads": 1}}
        result = self.read(page([row]), days_ago=0)["campaign_acquisition"]["rows"][0]
        self.assertEqual(result["status"], "OPEN_REPORT_WINDOW")
        self.assertIsNone(result["cost_per_new_download_minor"])
        with self.assertRaisesRegex(Invalid, "repeats an entity"):
            self.read(page([row, row]))
