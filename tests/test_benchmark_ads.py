"""Synthetic saved provider jobs exercise lineage, arithmetic and unavailable data."""
import copy
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from mission_control.common import Invalid, canonical, digest
from mission_control.db import connection
from mission_control.store import Store
from mission_control.benchmark_ads import source_connection, source_report, report_identity, report_rows, report_window, count_value, report_currency, spend_minor, aggregate_metric, project_saved_ads
from mission_control.benchmark_context import compare_benchmark
from mission_control.currency_units import minor_units, SOURCE_SHA256
from tests.test_benchmark_context import records

AS_OF = "2026-10-23T12:00:00+00:00"
SEGMENT = dict(category="Health", territory="US", placement="SEARCH_RESULTS", campaign_type="GENERIC")


def saved_report(store):
    """Insert isolated synthetic history; this fixture does not claim provider acceptance."""
    record = store.save_record("sample-one", dict(kind="connection", title="Synthetic Ads source", source="Test fixture only", manifest_version=store.app("sample-one")["version"],
        data=dict(provider="apple_ads", account_id="456", store_app_id="123", env_ref="GROWTH_SAMPLE_ONE_SYNTHETIC")))
    options = dict(operation="campaign_report", start="2026-10-01", end="2026-10-07", campaign_ids=["42"])
    row = dict(metadata=dict(id=42, promotedObjectType="APPSTORE_APP", promotedObjectId="123", adAccountId="456"),
               totalMetrics=dict(taps=10, impressions=100, totalInstalls=2, localSpend=dict(amount="30.00", currency="USD")))
    report = dict(provider="apple_ads", app_id="sample-one", store_app_id="123", operation="campaign_report", observed_at="2026-10-08T00:00:00+00:00", source_hash="b" * 64,
                  request=options, external_writes=False, rows=[row], declared_rows=1, coverage="COMPLETE")
    job_data = dict(connection_id=record["id"], connection_version=record["version"], options=options)
    with connection(store.path) as db:
        db.execute("INSERT INTO jobs(id,app_id,action,data,status,result,created,updated,request_key) VALUES(?,?,?,?,?,?,?,?,?)",
                   ("job-one", "sample-one", "sync", canonical(job_data), "SUCCEEDED", canonical(report), report["observed_at"], report["observed_at"], "synthetic-report-one"))
    return record, report


class BenchmarkAdsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "ads.sqlite", seed=False)
        for identity in ("sample-one", "sample-two"):
            self.store.save_app(identity, dict(name="Synthetic", release="build-1", locale="en-US", currency="USD", store_app_id="123"))
        self.record, self.report = saved_report(self.store)

    def tearDown(self):
        self.tmp.cleanup()

    def project(self, metric="CPT_MINOR", app_id="sample-one", source_hash="b" * 64):
        with connection(self.store.path) as db:
            return project_saved_ads(db, app_id, "job-one", source_hash, metric, SEGMENT, AS_OF)

    def change_report(self, report):
        with connection(self.store.path) as db:
            db.execute("UPDATE jobs SET result=? WHERE id='job-one'", (canonical(report),))

    def test_report_identity_checks_provider_app_hash_and_timeline(self):
        report = dict(provider="apple_ads", app_id="sample-one", source_hash="a" * 64,
                      observed_at="2026-10-23T11:00:00+00:00")
        job = dict(created="2026-10-23T10:00:00+00:00", updated="2026-10-23T11:30:00+00:00")
        self.assertIsNone(report_identity(report, job, "sample-one", "a" * 64, "2026-10-23T12:00:00+00:00"))
        for changed_report, changed_job, app_id, source_hash, as_of in (
            (dict(report, provider="other"), job, "sample-one", "a" * 64, "2026-10-23T12:00:00+00:00"),
            (dict(report, app_id="sample-two"), job, "sample-one", "a" * 64, "2026-10-23T12:00:00+00:00"),
            (report, job, "sample-one", "b" * 64, "2026-10-23T12:00:00+00:00"),
            (dict(report, observed_at="2026-10-23T12:01:00+00:00"), job, "sample-one", "a" * 64, "2026-10-23T12:00:00+00:00"),
            (report, dict(created="2026-10-23T11:01:00+00:00", updated="2026-10-23T11:30:00+00:00"), "sample-one", "a" * 64, "2026-10-23T12:00:00+00:00"),
        ):
            with self.subTest(report=changed_report, job=changed_job), self.assertRaises(Invalid):
                report_identity(changed_report, changed_job, app_id, source_hash, as_of)

    def test_ads_projection_uses_real_saved_totals_and_retains_operator_classification(self):
        value = self.project()
        self.assertEqual(value["observed"]["numerator"], 3000)
        self.assertEqual(value["observed"]["denominator_count"], 10)
        self.assertEqual(value["binding"]["result_hash"], digest(self.report))
        self.assertEqual(value["unit_source_sha256"], SOURCE_SHA256)
        self.assertEqual(value["classification_provenance"], "OPERATOR_DECLARED")
        self.assertFalse(value["classification_provider_verified"])
        reference, _ = records()
        reference.update(period_start="2026-10-01T00:00:00+00:00", period_end="2026-10-08T00:00:00+00:00", published_at="2026-10-10T00:00:00+00:00", retrieved_at="2026-10-22T00:00:00+00:00")
        compared = compare_benchmark(reference, value["observed"], AS_OF)
        self.assertEqual(compared["status"], "COMPARABLE_ADVISORY")
        self.assertEqual(compared["difference"], 100)
        self.assertFalse(compared["spend_authority"])

    def test_aggregate_metric_preserves_actual_rate_denominators(self):
        self.assertEqual(self.project("CR")["observed"]["numerator"], 2)
        self.assertEqual(self.project("CR")["observed"]["denominator_count"], 10)
        self.assertEqual(self.project("TTR")["observed"]["denominator_count"], 100)
        self.assertEqual(aggregate_metric(self.report["rows"], "CPI_MINOR", "USD"), (3000, 2))

    def test_missing_metrics_are_unavailable_not_zero(self):
        value = copy.deepcopy(self.report)
        value["rows"][0]["totalMetrics"]["totalInstalls"] = None
        self.change_report(value)
        self.assertIsNone(self.project("CR")["observed"])
        self.assertEqual(self.project("CR")["status"], "SOURCE_METRICS_UNAVAILABLE")
        self.assertEqual(self.project()["observed"]["numerator"], 3000)
        value["rows"][0]["totalMetrics"]["taps"] = 0
        self.change_report(value)
        self.assertEqual(self.project()["observed"]["denominator_count"], 0)

    def test_source_report_and_source_connection_reject_cross_app_hash_and_rotation(self):
        with connection(self.store.path) as db:
            report, binding, options, frozen = source_report(db, "sample-one", "job-one", "b" * 64, AS_OF)
            self.assertEqual(report, self.report)
            self.assertEqual(report_rows(report, binding, options), report["rows"])
            self.assertEqual(source_connection(db, self.store.app("sample-one"), {"data":dict(connection_id=self.record["id"], connection_version=1)}, report)[0]["id"], self.record["id"])
        for app_id, hashed in (("sample-two", "b" * 64), ("sample-one", "a" * 64)):
            with self.assertRaises(Invalid):
                self.project(app_id=app_id, source_hash=hashed)
        self.store.save_record("sample-one", dict(self.record, manifest_version=1, data=dict(self.record["data"], account_id="999")))
        with self.assertRaises(Invalid):
            self.project()

    def test_report_rows_rejects_duplicates_and_out_of_scope_metadata(self):
        for mutate in ("duplicate", "other-account", "contradictory-coverage"):
            value = copy.deepcopy(self.report)
            if mutate == "duplicate":
                value["rows"] *= 2
                value["declared_rows"] = 2
            elif mutate == "other-account":
                value["rows"][0]["metadata"]["adAccountId"] = "999"
            else:
                value["declared_rows"] = 2
            self.change_report(value)
            with self.assertRaises(Invalid):
                self.project()

    def test_report_window_timezone_and_changed_request_fail_closed(self):
        self.assertEqual(report_window(self.report["request"]), ("2026-10-01T00:00:00+00:00", "2026-10-08T00:00:00+00:00"))
        with self.assertRaises(Invalid):
            report_window(dict(start="2026-10-08", end="2026-10-07"))
        for change in (dict(reporting_timezone="ORTZ"), dict(observed_at="2999-01-01T00:00:00+00:00"), dict(request=dict(self.report["request"], start="2026-10-02"))):
            self.change_report(dict(self.report, **change))
            with self.assertRaises(Invalid):
                self.project()

    def test_minor_units_and_spend_minor_use_sourced_exponents_without_rounding(self):
        self.assertEqual(minor_units("USD"), 2)
        self.assertEqual(minor_units("JPY"), 0)
        self.assertEqual(minor_units("KWD"), 3)
        self.assertEqual(spend_minor(dict(amount="1.234", currency="KWD"), "KWD"), Decimal(1234))
        self.assertEqual(spend_minor(dict(amount="1.235", currency="USD"), "USD"), Decimal("123.500"))
        self.assertEqual(spend_minor(dict(amount="123", currency="JPY"), "JPY"), Decimal(123))
        for value in (dict(amount=True, currency="USD"), dict(amount="NaN", currency="USD"), dict(amount="1", currency="EUR")):
            with self.assertRaises(Invalid):
                spend_minor(value, "USD")
        with self.assertRaises(Invalid):
            minor_units("XXX")

    def test_report_currency_and_count_value_do_not_invent_missing_data(self):
        self.assertEqual(report_currency(self.report["rows"]), "USD")
        self.assertEqual(count_value("10"), 10)
        for value in (None, True, -1, 1.5, "unknown"):
            with self.assertRaises(Invalid):
                count_value(value)
        value = copy.deepcopy(self.report)
        value["rows"][0]["totalMetrics"]["localSpend"]["currency"] = "XXX"
        self.change_report(value)
        self.assertIsNone(self.project()["observed"])

    def test_projection_is_local_and_partial_coverage_cannot_compare(self):
        value = dict(self.report, coverage="PARTIAL", declared_rows=2)
        self.change_report(value)
        with patch("socket.socket", side_effect=AssertionError("Network forbidden")):
            result = self.project()
        self.assertEqual(result["observed"]["coverage"], "PARTIAL")
        self.assertFalse(result["external_writes"])
        with self.assertRaises(Invalid):
            self.project(metric="REVENUE")
