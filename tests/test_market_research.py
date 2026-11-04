"""Offline contracts and immutable GrowthReviews lifecycle for market research."""
import copy
import hashlib
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from mission_control.common import Invalid, digest
from mission_control.db import connection
from mission_control.growth_review_contract import context_of, entry_readout
from mission_control.growth_review_store import GrowthReviews
from mission_control.market_research import agent_contract, analyze_snapshot, validate_snapshot
from mission_control.store import Store


STAMP = "2026-10-23T12:00:00+00:00"


def fixture():
    excerpt = "Find nearby hiking trails and plan a trip"
    return {"id": "market-1", "manifest_version": 1, "kind": "MARKET_RESEARCH", "data": {
        "release": "build-1", "snapshot": {
            "platform": "iOS", "locale": "en-US", "territory": "US", "observed_at": STAMP,
            "own_listing": {"excerpt": "plan hiking trail trips", "source_id": "src-1"},
            "sources": [{"id": "src-1", "url": "https://example.com/report", "sha256": hashlib.sha256(excerpt.encode()).hexdigest(),
                "retrieved_at": STAMP, "coverage": "COMPLETE", "excerpt": excerpt}],
            "phrases": [{"id": "phrase-1", "phrase": "hiking trails", "source_ids": ["src-1"],
                "observed": {"demand_signal": "Source lists phrase", "competitor_position": None},
                "inferred": {"intent": "trip planning", "relevance": 0.8},
                "metrics": {"search_volume": None, "rank": None, "difficulty": None}}],
            "competitors": [{"id": "comp-1", "name": "TrailCo", "listing_excerpt": "Find nearby hiking trails", "source_id": "src-1"}],
        }}}


class MarketResearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "market.sqlite", seed=False)
        self.store.save_app("sample-one", dict(name="App", release="build-1", locale="en-US", currency="USD", store_app_id="123"))
        self.stamp = datetime.fromisoformat(STAMP)
        self.work = GrowthReviews(self.store, lambda: self.stamp)

    def tearDown(self):
        self.tmp.cleanup()

    def test_valid_snapshot_projects_observed_overlap_and_hypothesis_separately(self):
        body = fixture()
        row = self.work.save("sample-one", body)
        readout = self.work.list("sample-one")["history"][0]["readout"]
        analysis = readout["analysis"]
        self.assertEqual(analysis["state"], "OBSERVED")
        self.assertEqual(analysis["coverage"]["fraction"], 1.0)
        candidate = analysis["candidates"][0]
        self.assertEqual(candidate["competitor_ids"], ["comp-1"])
        self.assertIsNone(candidate["metrics"]["search_volume"])
        self.assertFalse(analysis["provider_verified"])
        self.assertFalse(analysis["paid_counts_used"])
        self.assertEqual(row["kind"], "MARKET_RESEARCH")

    def test_store_replay_is_immutable_and_context_drift_preserves_record(self):
        body = fixture()
        first = self.work.save("sample-one", body)
        self.assertEqual(self.work.save("sample-one", body), first)
        changed = copy.deepcopy(body)
        changed["data"]["snapshot"]["phrases"][0]["phrase"] = "camping"
        with self.assertRaises(Invalid):
            self.work.save("sample-one", changed)
        self.store.save_app("sample-one", dict(name="App", release="build-2", locale="en-US", currency="USD", store_app_id="123"), version=1)
        listed = self.work.list("sample-one")["history"][0]
        self.assertEqual(listed["readout"]["availability"], "STALE_APP_SCOPE")
        with connection(self.store.path) as db:
            persisted = db.execute("SELECT hash FROM growth_review_entries WHERE id='market-1'").fetchone()[0]
        self.assertEqual(persisted, first["hash"])

    def test_portable_export_restore_revalidates_market_research_as_imported_assertion(self):
        row = self.work.save("sample-one", fixture())
        snapshot = self.store.export("sample-one")
        target = Store(Path(self.tmp.name) / "restored.sqlite", seed=False)
        target.restore(snapshot)
        imported = GrowthReviews(target, lambda: self.stamp).list("sample-one")["history"][0]
        self.assertEqual(imported["hash"], row["hash"])
        self.assertEqual(imported["readout"]["availability"], "IMPORTED_ASSERTION")
        self.assertEqual(imported["readout"]["analysis"]["status"], "OBSERVED")

    def test_rejects_wrong_scope_duplicates_dates_bad_hash_unsafe_url_secrets_and_nonfinite(self):
        mutations = []
        for fn in (
            lambda b: b["data"]["snapshot"].update(locale="fr-FR"),
            lambda b: b["data"]["snapshot"].update(release="bad"),
            lambda b: b["data"]["snapshot"]["phrases"].append(copy.deepcopy(b["data"]["snapshot"]["phrases"][0])),
            lambda b: b["data"]["snapshot"]["sources"][0].update(retrieved_at="2999-01-01T00:00:00+00:00"),
            lambda b: b["data"]["snapshot"]["sources"][0].update(sha256="0" * 64),
            lambda b: b["data"]["snapshot"]["sources"][0].update(url="http://localhost/x"),
            lambda b: b["data"]["snapshot"].update(token="secret"),
            lambda b: b["data"]["snapshot"]["phrases"][0]["inferred"].update(relevance=float("nan")),
        ):
            body = fixture(); fn(body); mutations.append(body)
        for body in mutations:
            with self.subTest(body=body):
                with self.assertRaises(Invalid): self.work.save("sample-one", body)

    def test_operator_metrics_require_source_and_remain_unverified(self):
        body = fixture(); phrase = body["data"]["snapshot"]["phrases"][0]
        phrase["metrics"]["search_volume"] = {"value": 1200, "source_id": "src-1"}
        row = self.work.save("sample-one", body)
        metric = self.work.list("sample-one")["history"][0]["readout"]["analysis"]["candidates"][0]["metrics"]["search_volume"]
        self.assertEqual(metric["provenance"], "OPERATOR_ASSERTION")
        self.assertFalse(metric["provider_verified"])
        phrase["metrics"]["rank"] = {"value": 2, "source_id": "missing"}
        with self.assertRaises(Invalid): self.work.save("sample-one", dict(body, id="market-2"))

    def test_no_result_partial_and_stale_states_have_next_actions(self):
        body = fixture()["data"]["snapshot"]
        body["sources"][0]["coverage"] = "NO_RESULTS"; body["phrases"] = []
        no_result = validate_snapshot(body, {"locale": "en-US"}, STAMP)
        self.assertEqual(analyze_snapshot(no_result, STAMP)["state"], "NO_RESULTS")
        body = fixture()["data"]["snapshot"]; body["sources"][0]["coverage"] = "PARTIAL"
        partial = validate_snapshot(body, {"locale": "en-US"}, STAMP)
        self.assertEqual(analyze_snapshot(partial, STAMP)["state"], "PARTIAL")
        body = fixture()["data"]["snapshot"]
        old = (self.stamp - timedelta(days=91)).isoformat()
        body["sources"][0]["retrieved_at"] = old; body["observed_at"] = STAMP
        stale = validate_snapshot(body, {"locale": "en-US"}, STAMP)
        self.assertEqual(analyze_snapshot(stale, STAMP)["state"], "STALE")

    def test_no_network_and_contract_fixture_shape(self):
        self.assertEqual(agent_contract()["kind"], "MARKET_RESEARCH")
        with patch("socket.socket", side_effect=AssertionError("network forbidden")):
            self.work.save("sample-one", fixture())

    def test_long_listing_excerpts_and_malformed_urls_are_handled_safely(self):
        body = fixture()
        body["data"]["snapshot"]["own_listing"]["excerpt"] = "hiking " * 140
        body["data"]["snapshot"]["competitors"][0]["listing_excerpt"] = "trails " * 140
        self.work.save("sample-one", body)
        for unsafe in ("https://example.com:bad/report", "https://[broken/report", "https://example.com:65536/report"):
            invalid = fixture()
            invalid["data"]["snapshot"]["sources"][0]["url"] = unsafe
            with self.subTest(url=unsafe), self.assertRaises(Invalid):
                self.work.save("sample-one", invalid)


if __name__ == "__main__":
    unittest.main()
