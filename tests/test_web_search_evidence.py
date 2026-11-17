"""Offline acceptance of the OpenSEO evidence import and its authority boundary."""

import copy
import unittest
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

from mission_control.common import Invalid, iso_time
from mission_control.growth_review_store import GrowthReviews
from mission_control.store import Store
from mission_control.subscription_review import recovery_issues
from mission_control.web_search_evidence import OWNED_TOOLS, TOOLS, WINDOWED_TOOLS

STAMP = "2026-11-16T12:00:00Z"
APP = {"name": "Sample", "website": "https://sample.example/", "release": "r1", "locale": "en-US"}


def observation(tool: str = "get_search_console_performance", **values: int | float | str | bool | None) -> dict:
    excerpt = "Selected synthetic response fields."
    return {
        "tool": tool,
        "subject": "time planning app",
        "page_url": "https://sample.example/guide" if tool in OWNED_TOOLS else None,
        "period": {"start": "2026-11-01", "end": "2026-11-14", "device": "MOBILE"} if tool in WINDOWED_TOOLS else None,
        "coverage": "COMPLETE",
        "retrieved_at": STAMP,
        "reference_url": "https://openseo.example/research",
        "excerpt": excerpt,
        "sha256": sha256(excerpt.encode()).hexdigest(),
        "values": {field: values.get(field) for field in TOOLS[tool]["fields"]},
    }


def packet(*observations: dict) -> dict:
    return {
        "id": "test-research",
        "kind": "WEB_SEO_EVIDENCE",
        "manifest_version": 1,
        "data": {
            "provider": "openseo",
            "release": "r1",
            "locale": "en-US",
            "territory": "US",
            "website": "https://sample.example",
            "observations": list(observations),
        },
    }


class OpenSEOTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.store = Store(self.root / "app.sqlite", seed=False)
        self.store.save_app("main-app", APP)
        self.store.save_app("other-app", dict(APP, website="https://other.example"))
        self.review = GrowthReviews(self.store, lambda: iso_time(STAMP))

    def readout(self) -> dict:
        return self.review.list("main-app")["history"][0]["readout"]

    def test_saved_recommendation_and_immutable_app_isolation(self) -> None:
        body = packet(
            observation("research_keywords", volume=140, difficulty=32),
            observation(clicks=4, impressions=110, ctr=4 / 110, position=8.5),
        )
        saved = self.review.save("main-app", body)
        self.assertEqual(self.review.save("main-app", body), saved)
        self.assertFalse(self.review.list("other-app")["history"])
        with self.assertRaisesRegex(Invalid, "website configured"):
            self.review.save("other-app", body)
        changed = copy.deepcopy(body)
        changed["data"]["observations"][0]["values"]["volume"] = 222
        with self.assertRaisesRegex(Invalid, "immutable"):
            self.review.save("main-app", changed)
        state = self.readout()
        self.assertEqual(state["analysis"]["recommendation"]["tool"], "get_search_console_performance")
        self.assertEqual(state["analysis"]["scope"], "WEB_SEARCH_ONLY")
        for claim in ("provider_verified", "external_writes", "execution_authority", "outcomes_verified"):
            self.assertFalse(state[claim])
        self.assertFalse(state["analysis"]["store_rank_verified"])

    def test_partial_missing_and_stale_never_become_outcomes(self) -> None:
        source = observation("get_serp_results", best_position=5)
        source["coverage"] = "PARTIAL"
        self.review.save("main-app", packet(source))
        self.assertEqual(self.readout()["analysis"]["status"], "COLLECT_EVIDENCE")
        self.review.clock = lambda: iso_time("2026-12-17T12:00:00Z")
        analysis = self.readout()["analysis"]
        self.assertEqual(analysis["status"], "RECHECK_SOURCE")
        self.assertIsNone(analysis["recommendation"]["measure"])
        self.assertIsNone(analysis["test_brief"])
        self.assertEqual(analysis["observations"][0]["values"]["best_position"], 5)

    def test_export_restore_retains_hash_and_requires_recheck(self) -> None:
        saved = self.review.save("main-app", packet(observation(clicks=2, impressions=70)))
        restored = Store(self.root / "other.sqlite", seed=False)
        restored.restore(self.store.export("main-app"))
        row = GrowthReviews(restored, lambda: iso_time(STAMP)).list("main-app")["history"][0]
        self.assertEqual(saved["hash"], row["hash"])
        self.assertEqual(row["readout"]["analysis"]["status"], "RECHECK_SOURCE")

    def test_reject_malformed_or_misleading_sources(self) -> None:
        for replacement in (
            {"sha256": "0" * 64},
            {"coverage": "NO_RESULTS"},
            {"reference_url": "https://example.com/report?authorization=hidden"},
            {"retrieved_at": "2035-11-16T12:00:00Z"},
            {"values": {"clicks": True, "impressions": 40, "ctr": None, "position": None}},
            {"values": {"clicks": 1, "impressions": 40, "ctr": 3.2, "position": None}},
            {"tool": "set_report_sharing"},
            {"page_url": "https://other.example/guide"},
            {"values": {"clicks": 5, "impressions": 0, "ctr": None, "position": None}},
        ):
            with self.subTest(replacement=replacement):
                source = observation(clicks=2, impressions=70)
                source.update(replacement)
                with self.assertRaises(Invalid):
                    self.review.save("main-app", packet(source))
        self.assertEqual(self.review.list("main-app")["history"], [])

    def test_repeat_exports_and_comparable_exposure(self) -> None:
        small = observation(clicks=2, impressions=70)
        large = dict(observation(clicks=30, impressions=700), subject="best time planner")
        repeated = dict(small, retrieved_at="2026-11-16T11:00:00Z")
        with self.assertRaisesRegex(Invalid, "distinct"):
            self.review.save("main-app", packet(small, repeated))
        self.review.save("main-app", packet(small, large))
        recommendation = self.readout()["analysis"]["recommendation"]
        self.assertEqual(recommendation["subject"], "best time planner")
        self.assertAlmostEqual(recommendation["observed_rate"]["value"], 30 / 700)
        brief = self.readout()["analysis"]["test_brief"]
        self.assertEqual((brief["page"], brief["territory"], brief["device"]), (large["page_url"], "US", "MOBILE"))
        self.assertEqual(brief["source_sha256"], large["sha256"])
        self.assertEqual(brief["baseline"], recommendation["observed_rate"])
        self.assertEqual(brief["comparison_days"], 14)
        self.assertIn("search title", brief["change"])
        self.assertIn("cannot establish causal lift", brief["comparison"])

    def test_default_page_total_needs_query_before_a_title_test(self) -> None:
        row = observation(clicks=0, impressions=250)
        row["subject"] = row["page_url"]
        self.review.save("main-app", packet(row))
        analysis = self.readout()["analysis"]
        self.assertIsNone(analysis["test_brief"])
        self.assertIn("queries", analysis["next_action"])

    def test_generic_ga4_events_are_not_store_clicks(self) -> None:
        tool = "get_google_analytics_organic_landing_pages"
        body = packet(observation(tool, sessions=70, key_events=20))
        self.review.save("main-app", body)
        missing = self.readout()["analysis"]["recommendation"]
        self.assertEqual(missing["status"], "COLLECT_EVIDENCE")
        self.assertIn("Generic GA4 key events", missing["next_action"])
        self.assertIsNone(missing["observed_rate"])
        body["id"] = "with-store-link-event"
        body["data"]["observations"][0]["values"]["store_bound_sessions"] = 7
        self.review.save("main-app", body)
        row = self.review.list("main-app")["history"][1]["readout"]["analysis"]["recommendation"]
        self.assertEqual(row["observed_rate"]["value"], 0.1)

    def test_mixed_same_page_indexing_state_blocks_copy_test_and_surfaces_all_repairs(self) -> None:
        index = observation("inspect_urls", canonical_match=None, indexing_state=None)
        index["coverage"] = "PARTIAL"
        self.review.save("main-app", packet(observation(clicks=2, impressions=70), index))
        analysis = self.readout()["analysis"]
        self.assertEqual(len(analysis["repairs"]), 2)
        self.assertIsNone(analysis["test_brief"])
        self.assertFalse(any(row["status"] == "REVIEW_ACTION" for row in analysis["observations"]))
        issues = recovery_issues(self.review.list("main-app"), [])
        self.assertEqual(len(issues), 2)
        self.assertTrue(any("indexing" in item["next_action"] for item in issues))

    def test_exact_whitespace_excerpt_hash_and_healthy_page(self) -> None:
        index = observation("inspect_urls", canonical_match=True, indexing_state="INDEXED")
        index["excerpt"] = "  exact evidence with spaces \n"
        index["sha256"] = sha256(index["excerpt"].encode()).hexdigest()
        self.review.save("main-app", packet(index))
        analysis = self.readout()["analysis"]
        self.assertEqual(analysis["status"], "NO_ACTION")
        self.assertEqual(analysis["observations"][0]["excerpt"], index["excerpt"])
        self.assertEqual(analysis["repairs"], [])

    def test_unknown_report_window_cannot_masquerade_as_fresh_evidence(self) -> None:
        row = observation(clicks=2, impressions=70)
        row["period"] = {"start": "2026-01-01", "end": "2026-01-05", "device": "MOBILE"}
        self.review.save("main-app", packet(row))
        self.assertEqual(self.readout()["analysis"]["status"], "RECHECK_SOURCE")
