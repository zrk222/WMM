"""Negative validation fixtures and actual isolated loopback adapter probes."""

import importlib.util
import math
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "http_benchmark", Path(__file__).resolve().parents[1] / "tools/benchmark_http.py"
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
benchmark, parity, summarize = MODULE.benchmark, MODULE.parity, MODULE.summarize


class BenchmarkTests(unittest.TestCase):
    def test_percentiles_and_malformed_samples(self) -> None:
        self.assertEqual(summarize([4.0, 1.0, 3.0, 2.0])["p50_ms"], 2.0)
        self.assertEqual(summarize([4.0, 1.0, 3.0, 2.0])["p95_ms"], 4.0)
        for samples in ([], [0.0], [-1.0], [math.nan], [math.inf], [True]):
            with self.subTest(samples=samples), self.assertRaises(ValueError):
                summarize(samples)

    def test_mismatch_and_identical_failure_rejected(self) -> None:
        valid = [{"actual": 200, "expected": 200}]
        parity(valid, valid)
        with self.assertRaises(ValueError):
            parity(valid, [{"actual": 403, "expected": 200}])
        with self.assertRaises(ValueError):
            parity([{"actual": 403, "expected": 200}], [{"actual": 403, "expected": 200}])
        with self.assertRaises(ValueError):
            parity([], [])

    def test_actual_network_both_adapters(self) -> None:
        receipt = benchmark(10, 1)
        self.assertTrue(receipt["parity_pass"])
        for result in receipt["results"]:
            self.assertEqual(result["measurement"]["count"], 10)
            self.assertGreater(result["memory_after_requests"]["resident_bytes"], 0)
            self.assertEqual(len(result["parity"]), 12)
        self.assertIn("tools/benchmark_http.py", receipt["source_sha256"])

    def test_invalid_counts(self) -> None:
        for count, warmup in ((0, 1), (10001, 1), (1, -1), (1, 101)):
            with self.assertRaises(ValueError):
                benchmark(count, warmup)
