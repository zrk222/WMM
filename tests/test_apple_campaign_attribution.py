"""Exercise exact Apple campaign attribution with synthetic provider report bytes."""

import gzip
import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from mission_control.aeo_transport import PublicReader, ReadError, public_url
from mission_control.apple_analytics import CAMPAIGN_DOWNLOADS, DOWNLOADS
from mission_control.apple_analytics_parser import parse_instance
from mission_control.apple_metrics_http import apple_campaign_results
from mission_control.apple_metrics_store import _reconcile
from mission_control.common import Invalid, digest
from mission_control.db import connection, initialize
from mission_control.evidence_gate import scoped_tracking_tag
from mission_control.provider_reports import report_options

LINK = "https://apps.apple.com/app/apple-store/id123456789?pt=123456&ct=Early%20Launch&mt=8"
CAMPAIGN_NAME = "Early Launch"
START = "2026-01-01"
KEY = {
    "app_id": "synthetic-app",
    "store_app_id": "123456789",
    "connection_id": "synthetic-connection",
    "connection_version": 1,
    "report_id": "synthetic-report",
    "report_family": CAMPAIGN_DOWNLOADS,
    "granularity": "DAILY",
}
COLUMNS = "Date\tApp Apple Identifier\tDownload Type\tCounts\tCampaign\tTerritory\tSource Info\n"


def segment(content: str) -> dict[str, str | int | bytes]:
    """Give the production parser a verified gzip fixture with the documented column names."""
    raw = gzip.compress(content.encode(), mtime=0)
    return dict(id="s1", data=raw, size=len(raw), checksum=hashlib.md5(raw, usedforsecurity=False).hexdigest())


class AppleCampaignAttributionTests(unittest.TestCase):
    def test_only_official_product_links_carry_apple_parameters(self) -> None:
        self.assertEqual(public_url(LINK, allow_tracking=True), LINK)
        self.assertEqual(
            public_url("https://example.com/?utm_campaign=test", allow_tracking=True),
            "https://example.com/?utm_campaign=test",
        )
        for link in (
            LINK.replace("apps.apple.com", "apps.apple.com.example.org"),
            LINK.replace("/app/apple-store/", "/unrelated/"),
            LINK + "&ct=another",
            LINK.replace("mt=8", "mt=1"),
            LINK.replace("123456&", "secret&"),
            LINK.replace("Early%20Launch", "%0d%0aonly"),
        ):
            with self.subTest(link=link), self.assertRaises(ReadError):
                public_url(link, allow_tracking=True)

    def test_redirect_preserves_product_and_exact_approved_query(self) -> None:
        def redirect(location: str) -> str:
            return PublicReader(allow_tracking=True).redirect(
                dict(url=LINK, headers={"location": [location]}), "https://apps.apple.com"
            )

        localized = LINK.replace("/app/apple-store/", "/ca/app/example/")
        self.assertEqual(redirect(localized), localized)
        with self.assertRaisesRegex(ReadError, "REDIRECT_PRODUCT"):
            redirect(localized.replace("id123456789", "id999"))
        with self.assertRaisesRegex(ReadError, "REDIRECT_QUERY"):
            redirect(localized.split("?")[0])

    def test_exact_apple_download_rows_keep_zero_distinct_from_no_data(self) -> None:
        fixture = (
            COLUMNS
            + "2026-01-01\t123456789\tFirst-time Download\t2\tEarly Launch\tCA\tprivate-referrer\n"
            + "2026-01-01\t123456789\tFirst-time Download\t13\tEarly Launch\tUS\tprivate-referrer\n"
            + "2026-01-01\t123456789\tRedownload\t10\tEarly Launch\tCA\tprivate-referrer\n"
            + "2026-01-01\t123456789\tFirst-time Download\t21\tOther Campaign\tCA\tprivate-referrer\n"
            + "2026-01-01\t123456789\tFirst-time Download\t22\t\tCA\tprivate-referrer\n"
            + "2026-01-02\t123456789\tFirst-time Download\t0\tEarly Launch\tCA\tprivate-referrer\n"
        )
        parsed = parse_instance("123456789", "2026-01-04", [segment(fixture)], True, CAMPAIGN_DOWNLOADS)
        self.assertNotIn(CAMPAIGN_NAME, json.dumps(parsed))
        self.assertNotIn("private-referrer", json.dumps(parsed))
        with self.assertRaisesRegex(Invalid, "another app"):
            parse_instance("999", "2026-01-04", [segment(fixture)], True, CAMPAIGN_DOWNLOADS)

        with TemporaryDirectory() as temp:
            path = Path(temp) / "fixture.sqlite"
            initialize(path)
            with connection(path) as db:
                db.execute("BEGIN IMMEDIATE")
                for app, store_id in (("synthetic-app", "123456789"), ("another-app", "999")):
                    db.execute(
                        "INSERT INTO apps(id,data,updated) VALUES(?,?,?)",
                        (app, json.dumps({"store_app_id": store_id}), "fixture"),
                    )
                self.assertEqual(scoped_tracking_tag(db, "synthetic-app", LINK), "early launch")
                with self.assertRaisesRegex(Invalid, "must target this app"):
                    scoped_tracking_tag(db, "another-app", LINK)
                rows = parsed["rows"]
                assert isinstance(rows, list)
                for day in (START, "2026-01-02"):
                    instance = dict(parsed, rows=[row for row in rows if row["date"] == day])
                    self.assertEqual(_reconcile(db, dict(KEY, event_date=day), instance), "INSERTED")
                window = dict(territory="CA", start=START, end="2026-01-03")
                actual = apple_campaign_results(db, KEY, CAMPAIGN_NAME, window)
                self.assertEqual(actual["status"], "APPLE_REPORTED_ROWS")
                self.assertEqual([row["first_time_downloads"] for row in actual["rows"]], [2, 0, None])
                self.assertEqual(
                    [row["evidence_status"] for row in actual["rows"]],
                    ["READY_TO_REVIEW", "READY_TO_REVIEW", "NO_FILE"],
                )
                self.assertEqual([row["processing_date"] for row in actual["rows"]], ["2026-01-04", "2026-01-04", None])
                self.assertEqual(actual["campaign_sha256"], digest(CAMPAIGN_NAME))
                self.assertIsNotNone(actual["rows"][0]["source_sha256"])
                self.assertIsNone(actual["rows"][2]["source_sha256"])
                self.assertFalse(actual["external_writes"])
                for wrong in (dict(KEY, app_id="another-app"), dict(KEY, report_family=DOWNLOADS)):
                    unavailable = apple_campaign_results(db, wrong, CAMPAIGN_NAME, window)
                    self.assertEqual(unavailable["status"], "UNAVAILABLE_OR_SUPPRESSED")
                    self.assertTrue(all(row["first_time_downloads"] is None for row in unavailable["rows"]))

    def test_provisional_result_and_missing_match_are_distinct_until_apple_revises(self) -> None:
        day = "2026-01-02"
        key = dict(KEY, event_date=day)
        row = f"{day}\t123456789\tFirst-time Download\t{{count}}\tEarly Launch\tUS\tprivate-referrer\n"
        with TemporaryDirectory() as temp:
            path = Path(temp) / "fixture.sqlite"
            initialize(path)
            with connection(path) as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute(
                    "INSERT INTO apps(id,data,updated) VALUES(?,?,?)",
                    (KEY["app_id"], json.dumps({"store_app_id": KEY["store_app_id"]}), "fixture"),
                )
                window = dict(territory="US", start=day, end=day)

                for processing, count in (("2026-01-03", 2), ("2026-01-04", 1)):
                    fixture = segment(COLUMNS + row.format(count=count))
                    instance = parse_instance("123456789", processing, [fixture], True, CAMPAIGN_DOWNLOADS)
                    _reconcile(db, key, instance)
                    result = apple_campaign_results(db, KEY, CAMPAIGN_NAME, window)
                    observation = result["rows"][0]
                    self.assertEqual(observation["processing_date"], processing)
                    self.assertEqual(observation["first_time_downloads"], count)
                    if count == 2:
                        self.assertEqual(observation["evidence_status"], "PROVISIONAL")
                        self.assertIn("Keep the existing review window", result["next_action"])
                    else:
                        self.assertEqual(observation["evidence_status"], "READY_TO_REVIEW")
                        self.assertIn("Apple can still issue corrections", result["next_action"])

                no_match = apple_campaign_results(db, KEY, CAMPAIGN_NAME, dict(window, territory="CA"))["rows"][0]
                self.assertEqual(no_match["evidence_status"], "NO_MATCH")
                self.assertEqual(no_match["processing_date"], "2026-01-04")
                self.assertIsNone(no_match["first_time_downloads"])
                self.assertIsNotNone(no_match["source_sha256"])

    def test_provider_collection_requires_explicit_detailed_report_and_instance(self) -> None:
        options = dict(operation="analytics_metrics", report_id="report-1", instance_id="instance-1")
        detailed = dict(options, report_family=CAMPAIGN_DOWNLOADS)
        self.assertEqual(report_options("app_store", detailed), detailed)
        with self.assertRaises(Invalid):
            report_options("app_store", dict(options, report_family="Not permitted"))
        with self.assertRaises(Invalid):
            report_options("app_store", dict(detailed, instance_id="../another-instance"))
