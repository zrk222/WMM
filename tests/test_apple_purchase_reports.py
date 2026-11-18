"""Read only exact daily app commerce files; preserve signed Apple estimates and source checks."""

import gzip
import hashlib
import json
import unittest
from typing import Any
from unittest.mock import patch

from mission_control.apple_analytics import PURCHASES, SUBSCRIPTION_STATE
from mission_control.apple_metrics_contract import complete_instance
from mission_control.common import Invalid, now
from mission_control.db import connection
from mission_control.provider_reports import prepare_analytics_metrics, report_options
from mission_control.worker import run_once
from tests import test_apple_metrics_http_route as routes
from tests import test_apple_metrics_worker as fixtures

OPTIONS = dict(
    operation="analytics_metrics",
    report_id="report-1",
    instance_id="daily-1",
    report_family=PURCHASES,
    start="2026-10-23",
    end="2026-10-23",
)
REPORT = dict(
    id="report-1",
    name=PURCHASES,
    coverage="COMPLETE",
    instances=[dict(id="daily-1", granularity="DAILY", processing_date="2026-10-25")],
)
HEADER = (
    "Date\tApp Apple Identifier\tPurchase Type\tPurchases\tProceeds in USD\tSales in USD\tPaying Users\tContent Name\n"
)


class Reader:
    hashes = ["synthetic source hash"]


def segment(lines: str) -> list[dict]:
    data = gzip.compress((HEADER + lines).encode(), mtime=0)
    return [
        dict(id="segment-1", size=len(data), checksum=hashlib.md5(data, usedforsecurity=False).hexdigest(), data=data)
    ]


def prepare(lines: str, options: dict[str, Any] | None = None) -> Any:
    actual = options or OPTIONS
    report_options("app_store", actual)
    with (
        patch(
            "mission_control.provider_reports.read_analytics", return_value=dict(coverage="COMPLETE", reports=[REPORT])
        ),
        patch("mission_control.provider_reports.read_instance_segments", return_value=segment(lines)) as download,
    ):
        reader = Reader()
        result = prepare_analytics_metrics(reader, {}, "sample-one", "123", actual, "connection-1", 1)
        download.assert_called_once_with(reader, "123", "report-1", "daily-1")
        return result


class PurchaseReportTests(unittest.TestCase):
    def test_exact_date_filters_corrections_and_keeps_fractional_dollars_signed(self) -> None:
        data = (
            "2026-10-22\t123\tApp purchase\t1\t7.00\t8.00\t1\toutside-window\n"
            "2026-10-23\t123\tIn-app purchases\t1\t1.234500\t1.99\t1\tprivate-plan-name\n"
            "2026-10-23\t123\tIn-app purchases\t-1\t-0.75\t-0.98\t1\tprivate-plan-name\n"
            "2026-10-23\t123\tIn-app purchases\t0\t-0.00001\t-0.01\t1\tprivate-plan-name\n"
        )
        result = prepare(data)
        self.assertEqual(len(result.partitions), 1)
        part = result.partitions[0]
        rows = part["instance"]["rows"]
        self.assertEqual([row["count"] for row in rows], [1, -1, 0])
        self.assertEqual([row["proceeds_usd"] for row in rows], ["1.2345", "-0.75", "-0.00001"])
        self.assertEqual({row["date"] for row in rows}, {"2026-10-23"})
        self.assertEqual(len({row["source_sha256"] for row in rows}), 1)
        self.assertNotIn("private-plan-name", json.dumps(part))
        self.assertNotIn("paying users", json.dumps(part))
        self.assertEqual(result.summary(["INSERTED"])["partitions"][0]["observation_count"], 3)
        for bad in ("NaN", "1e50", "01.2345000"):
            altered = dict(part["instance"], rows=[dict(rows[0], proceeds_usd=bad)])
            with self.subTest(bad=bad), self.assertRaises(Invalid):
                complete_instance(part["partition"], altered)

    def test_missing_mixed_app_malformed_or_unscoped_commerce_fails_closed(self) -> None:
        for line in (
            "",
            "2026-10-23\t999\tApp purchase\t1\t5\t6\t1\tforeign\n",
            "2026-10-23\t123\tApp purchase\t1\t\t6\t1\tempty\n",
            "2026-10-23\t123\tApp purchase\t1\tNaN\t6\t1\tinvalid\n",
            "2026-10-22\t123\tApp purchase\t1\t5\t6\t1\tstale\n",
        ):
            with self.subTest(line=line), self.assertRaises(Invalid):
                prepare(line)
        for invalid in (
            {k: v for k, v in OPTIONS.items() if k != "start"},
            dict(OPTIONS, end="2026-12-23"),
            dict(OPTIONS, operation="analytics_metrics_latest"),
            dict(OPTIONS, vendorNumber="unsolicited"),
        ):
            with self.subTest(invalid=invalid), self.assertRaises(Invalid):
                report_options("app_store", invalid)

    def test_generic_queue_cannot_use_owner_commerce_authority(self) -> None:
        case = fixtures.AppleMetricsWorkerTests("test_complete_instance_is_committed_with_job_and_source_readback")
        self.addCleanup(case.doCleanups)
        case.setUp()
        with self.assertRaisesRegex(Invalid, "owner performance"):
            case.queue(OPTIONS)

    def test_owner_reads_retained_commerce_after_dated_private_file_jobs(self) -> None:
        case = routes.AppleMetricsRouteTests("test_owner_can_queue_observe_and_pause_without_provider_calls")
        self.addCleanup(case.doCleanups)
        case.setUp()
        window = dict(manifest_version=case.app["version"], start=OPTIONS["start"], end=OPTIONS["end"])
        reports = [
            REPORT,
            dict(
                id="states",
                name=SUBSCRIPTION_STATE,
                coverage="COMPLETE",
                instances=[dict(id="states-day", granularity="DAILY", processing_date="2026-10-26")],
            ),
        ]
        inventory = dict(
            provider="app_store",
            operation="analytics_reports",
            app_id=routes.APP,
            store_app_id="123",
            status="METRIC_DOWNLOAD_REQUIRED",
            coverage="COMPLETE",
            observed_at=now(),
            reports=reports,
        )
        job = case.post(routes.BASE + "inventory", case.inventory_body())
        with patch("mission_control.worker.read_report", return_value=inventory):
            self.assertTrue(run_once(case.store))
        queued = case.post(routes.BASE + "performance-collect", dict(window, inventory_id=job["job_id"]))
        self.assertEqual(len(queued["jobs"]), 2)

        def files(_reader: Any, app_id: str, report_id: str, instance_id: str) -> list[dict]:
            self.assertEqual(app_id, "123")
            if (report_id, instance_id) == ("report-1", "daily-1"):
                return segment(
                    "2026-10-22\t123\tApp purchase\t1\t10\t11\t1\tother-date\n"
                    "2026-10-23\t123\tIn-app purchases\t2\t1.234\t3\t1\tprivate-content\n"
                    "2026-10-23\t123\tIn-app purchases\t0\t-0.123\t-0.130\t1\tprivate-content\n"
                )
            self.assertEqual((report_id, instance_id), ("states", "states-day"))
            raw = gzip.compress(
                b"Date\tApp Apple Identifier\tState Metric\tState Metric Grouping\tCounts\n"
                b"2026-10-23\t123\tFull price\tPaid plans\t3\n"
                b"2026-10-23\t123\tFree trials\tSubscription offers\t10\n",
                mtime=0,
            )
            return [
                dict(
                    id="states-segment",
                    size=len(raw),
                    data=raw,
                    checksum=hashlib.md5(raw, usedforsecurity=False).hexdigest(),
                )
            ]

        with (
            patch("mission_control.provider_reports.credential", return_value="owner-only-synthetic"),
            patch("mission_control.provider_reports.read_analytics", return_value=inventory),
            patch("mission_control.provider_reports.read_instance_segments", side_effect=files) as read,
        ):
            self.assertTrue(run_once(case.store))
            self.assertTrue(run_once(case.store))
            self.assertEqual(read.call_count, 2)
        result = case.post(routes.BASE + "performance", window)
        values = {r["label"]: r for r in result["outcome_coverage"]["metrics"]}
        self.assertEqual(values["Apple estimated proceeds"]["value"], "1.111 USD")
        self.assertEqual(values["Active paid subscriptions"]["value"], "3")
        combined = case.post(routes.BASE + "search-review", window)
        self.assertEqual(combined["outcome_coverage"]["metrics"], result["outcome_coverage"]["metrics"])
        self.assertEqual(len(values["Apple estimated proceeds"]["source_sha256"]), 64)
        self.assertNotIn("owner-only-synthetic", json.dumps(result))
        with connection(case.store.path) as db:
            self.assertEqual(
                {r[0] for r in db.execute("SELECT event_date FROM apple_metric_partitions")}, {OPTIONS["start"]}
            )
