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


def intent_fixture():
    body = fixture()
    snapshot = body["data"]["snapshot"]
    for name, excerpt in (("gap", "Trail reviews ask for route planning without a signal."),
                          ("proof", "Build 1 can save a route and reopen it offline.")):
        snapshot["sources"].append(dict(snapshot["sources"][0], id=name, excerpt=excerpt,
                                        sha256=hashlib.sha256(excerpt.encode()).hexdigest()))
    base = snapshot["phrases"][0]
    for name, phrase in (("offline", "offline trail planner"), ("family", "family trail maps")):
        snapshot["phrases"].append(dict(base, id=name, phrase=phrase))
    def cluster(name, pid, demand, gap, proof, test):
        return dict(id=name, intent=name + " trip planning", phrase_ids=[pid],
                    evidence=dict(demand=demand, competitive_gap=gap, app_proof=proof), test=test)
    test = dict(change="Show an offline route on the first screenshot",
                hypothesis="Visitors looking for offline routes will install more often.")
    snapshot["intent_clusters"] = [
        cluster("family", "family", [], [], [], None),
        cluster("generic", base["id"], ["src-1"], ["src-1"], ["src-1"], test),
        cluster("offline", "offline", ["src-1"], ["gap"], ["proof"], test),
    ]
    return body


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

    def test_imported_stale_scope_and_assertion_provenance_are_both_visible(self):
        row=self.work.save("sample-one",fixture())
        row=dict(row,imported=1)
        changed=dict(row['context'],manifest_version=2,app_hash='0'*64)
        value=entry_readout(row,changed,STAMP)
        self.assertEqual(value['scope_status'],'STALE_APP_SCOPE')
        self.assertEqual(value['import_provenance'],'IMPORTED_ASSERTION')
        self.assertFalse(value['provider_verified'])

    def test_mixed_source_coverage_is_partial_and_empty_source_packet_is_invalid(self):
        value=fixture()['data']['snapshot']
        value['sources'].append(dict(value['sources'][0],id='no-result-source',coverage='NO_RESULTS'))
        normalized=validate_snapshot(value,{'locale':'en-US'},STAMP)
        self.assertEqual(analyze_snapshot(normalized,STAMP)['state'],'PARTIAL')
        value['sources'][0]['coverage']='PARTIAL'
        self.assertEqual(analyze_snapshot(validate_snapshot(value,{'locale':'en-US'},STAMP),STAMP)['state'],'PARTIAL')
        value['sources']=[]
        with self.assertRaises(Invalid):validate_snapshot(value,{'locale':'en-US'},STAMP)

    def test_intent_readout_prioritizes_reviewable_test_and_keeps_unknowns(self):
        body = intent_fixture()
        row = self.work.save("sample-one", body)
        read = lambda: self.work.list("sample-one")["history"][0]["readout"]["analysis"]
        results = read()["intent_opportunities"]
        self.assertEqual([(r["id"], r["status"]) for r in results], [
            ("offline", "REVIEW_TEST"), ("generic", "COLLECT_EVIDENCE"), ("family", "COLLECT_EVIDENCE")])
        self.assertEqual(results[0]["phrases"], ["offline trail planner"])
        self.assertEqual(results[0]["evidence"]["app_proof"], ["proof"])
        self.assertFalse(results[0]["organic_demand_verified"])
        self.assertEqual(results[1]["missing"], ["distinct_evidence"])
        self.assertIn("test_hypothesis", results[2]["missing"])
        self.assertEqual(self.work.save("sample-one", body)["hash"], row["hash"])
        self.assertEqual(read()["intent_opportunities"], results)
        self.stamp += timedelta(days=91)
        stale = {r["id"]: r for r in read()["intent_opportunities"]}["offline"]
        self.assertEqual(stale["status"], "COLLECT_EVIDENCE")
        self.assertIn("current_listing", stale["missing"])
        self.assertIn("app_proof", stale["missing"])

    def test_cluster_rejects_ambiguous_or_unlinked_evidence(self):
        for field, value in (
            ("phrase_ids", ["family"]),
            ("phrase_ids", [{}]),
            ("evidence", dict(demand=["proof"], competitive_gap=["gap"], app_proof=["proof"])),
            ("evidence", dict(demand=["src-1"], competitive_gap=["other-app"], app_proof=["proof"])),
            ("test", dict(change="Replace screenshot", hypothesis="")),
        ):
            body = intent_fixture()
            body["data"]["snapshot"]["intent_clusters"][-1][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(Invalid):
                self.work.save("sample-one", body)

    def test_partial_sources_cannot_support_intent_roles(self):
        body = intent_fixture()
        body["data"]["snapshot"]["sources"][1]["coverage"] = "PARTIAL"
        self.work.save("sample-one", body)
        analysis = self.work.list("sample-one")["history"][0]["readout"]["analysis"]
        opportunity = next(row for row in analysis["intent_opportunities"] if row["id"] == "offline")
        self.assertEqual(opportunity["missing"], ["competitive_gap"])
        self.assertEqual(opportunity["status"], "COLLECT_EVIDENCE")

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
