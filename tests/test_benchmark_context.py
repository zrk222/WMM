"""Scope/denominator/date mismatches and truthful advisory output."""
import copy
import time
import unittest
from unittest.mock import patch
from mission_control.common import Invalid
from mission_control.benchmark_context import (benchmark_record, observed_record, compare_benchmark, numeric, scope_data)

AS_OF = "2026-10-22T12:00:00+00:00"


def records(metric="CPT_MINOR", denominator="TAPS"):
    scope = dict(metric=metric, denominator=denominator, category="Health", territory="US", platform="iOS",
                 placement="SEARCH_RESULTS", campaign_type="GENERIC", currency="USD",
                 period_start="2025-01-01T00:00:00+00:00", period_end="2026-01-01T00:00:00+00:00")
    reference = dict(scope, dataset_id="synthetic-2025", source_url="https://synthetic.example/report",
                     source_sha256="a" * 64, published_at="2026-03-01T00:00:00+00:00", retrieved_at="2026-10-01T00:00:00+00:00",
                     expires_at="2026-12-01T00:00:00+00:00", percentile=50, value=200, coverage="COMPLETE", limitations="Synthetic observations, no revenue dataset")
    observed = dict(scope, numerator=3000, denominator_count=10, source_sha256="b" * 64, coverage="COMPLETE")
    return reference, observed


class BenchmarkContextTests(unittest.TestCase):
    def test_compare_benchmark_retains_sources_and_no_economics_authority(self):
        ref, obs = records()
        result = compare_benchmark(ref, obs, AS_OF)
        self.assertEqual(result["status"], "COMPARABLE_ADVISORY")
        self.assertEqual(result["difference"], 100)
        self.assertEqual(result["reference"]["dataset_id"], "synthetic-2025")
        self.assertIsNone(result["roas"])
        self.assertIsNone(result["lifetime_value"])
        self.assertFalse(result["spend_authority"])

    def test_every_segment_period_currency_and_denominator_mismatch_blocks(self):
        ref, obs = records()
        for key, value in (("category", "Business"), ("territory", "CA"), ("platform", "Android"),
                           ("placement", "TODAY"), ("campaign_type", "BRAND"), ("currency", "CAD"),
                           ("period_start", "2025-02-01T00:00:00+00:00")):
            result = compare_benchmark(ref, dict(obs, **{key: value}), AS_OF)
            self.assertEqual(result["status"], "INCOMPATIBLE")
            self.assertIsNone(result["difference"])
        with self.assertRaises(Invalid):
            observed_record(dict(obs, denominator="INSTALLS"))

    def test_expiry_partial_and_zero_denominators_remain_unavailable(self):
        ref, obs = records()
        result = compare_benchmark(dict(ref, expires_at="2026-10-02T00:00:00+00:00"), dict(obs, denominator_count=0, coverage="PARTIAL"), AS_OF)
        self.assertEqual(len(result["reasons"]), 3)
        self.assertIsNone(result["difference"])

    def test_benchmark_record_observed_record_scope_data_numeric_boundaries(self):
        ref, obs = records()
        self.assertEqual(benchmark_record(ref, AS_OF)["value"], 200)
        self.assertEqual(observed_record(obs)["value"], 300)
        self.assertEqual(scope_data(ref)["currency"], "USD")
        self.assertEqual(numeric(0, "test"), 0)
        for value in (True, -1, float("nan"), float("inf"), "3"):
            with self.assertRaises(Invalid):
                numeric(value, "test")
        for key, value in (("source_url", "https://localhost/private"), ("source_sha256", "bad"),
                           ("percentile", 101), ("published_at", "2999-01-01T00:00:00+00:00")):
            with self.assertRaises(Invalid):
                benchmark_record(dict(ref, **{key: value}), AS_OF)

    def test_rate_counts_do_not_become_percentages_or_paid_conversion(self):
        ref, obs = records("CR", "TAPS")
        ref["value"] = .5
        obs["numerator"] = 6
        self.assertAlmostEqual(compare_benchmark(ref, obs, AS_OF)["difference"], .1)
        with self.assertRaises(Invalid):
            observed_record(dict(obs, numerator=11))
        with self.assertRaises(Invalid):
            benchmark_record(dict(ref, value=50), AS_OF)

    def test_bounded_pure_comparison_preserves_input_without_network(self):
        ref, obs = records()
        before = copy.deepcopy((ref, obs))
        started = time.perf_counter()
        with patch("socket.socket") as network:
            for _ in range(100):
                compare_benchmark(ref, obs, AS_OF)
            network.assert_not_called()
        self.assertLess(time.perf_counter() - started, 5)
        self.assertEqual((ref, obs), before)
