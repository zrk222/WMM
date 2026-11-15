"""Discovery-bound briefs use real isolated history and existing production gates."""

from datetime import datetime, timedelta, timezone
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from mission_control.common import Invalid, digest
from mission_control.db import connection
from mission_control.store import Store
from mission_control.service import Service
from mission_control.creative_library import Library, append_capture
from mission_control.creative_analysis import Analyses
from mission_control.creative_briefs import Briefs
from mission_control.creative_rendering import render_request, current_request
from mission_control.discovery_store import Discovery
from tests.test_creative_library import reference
from tests.test_creative_production import ready_production, inspection
from tests.test_discovery_intelligence import filters, reviewed
from tests.test_viral_policy import history
from tests.production_fixtures import ready_capabilities


class DiscoveryBriefTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "state.sqlite")
        self.app = "production-test"
        _, self.legacy_analysis, self.records, self.data = ready_production(self.store, self.app)
        self.library = Library(self.store)
        self.briefs = Briefs(self.store)
        self.discovery = Discovery(self.store)
        stamp = datetime.now(timezone.utc) - timedelta(seconds=5)
        self.stamp = stamp.isoformat()
        source_data = reference(
            platform="tiktok",
            post_id="candidate",
            creator_id="creator",
            format="short",
            url="https://www.tiktok.com/@creator/video/123",
            metric_kind="VIEWS",
            metric_value=100000,
            metric_at=self.stamp,
            captured_at=self.stamp,
            published_at=(stamp - timedelta(days=1)).isoformat(),
        )
        saved = self.library.save(self.app, {"data": source_data})
        self.source = next(row for row in self.library.list(self.app) if row["id"] == saved["id"])
        self.analysis = Analyses(self.store).save(self.app, {"data": inspection(self.source)})
        ready_capabilities(self.store, self.app, [self.source])
        self.data.update(analysis_id=self.analysis["id"], analysis_hash=self.analysis["hash"])
        baseline = history()
        for index, row in enumerate(baseline):
            row.update(observed_at=self.stamp, published_at=(stamp - timedelta(days=index + 2)).isoformat())
        self.value = reviewed(baseline=baseline)
        self.value["card"]["authentic_evidence_ids"] = [self.records["asset"]["id"]]
        self.review = self.save_review(self.value)
        query = filters(
            published_after=(stamp - timedelta(days=3)).isoformat(),
            published_before=(stamp + timedelta(seconds=2)).isoformat(),
        )
        self.collection = self.discovery.collect(
            self.app,
            dict(
                id="collection",
                version=0,
                manifest_version=self.store.app(self.app)["version"],
                query=query,
                attempted_sources=1,
                failed_sources=0,
            ),
        )
        self.binding = dict(
            schema="wmm.brief-discovery.v1",
            mode="ORIGINAL_RECREATION",
            manifest_version=self.store.app(self.app)["version"],
            collection_id=self.collection["id"],
            collection_hash=self.collection["hash"],
            reference_id=self.source["id"],
            review_hash=self.review["hash"],
        )

    def tearDown(self):
        self.tmp.cleanup()

    def save_review(self, value, version=0):
        return self.discovery.save_review(
            self.app,
            dict(
                id="review",
                version=version,
                manifest_version=self.store.app(self.app)["version"],
                reference_id=self.source["id"],
                source_hash=self.source["current"]["hash"],
                data=value,
            ),
        )

    def prepare(self, **changes):
        return self.briefs.save(self.app, {"data": dict(self.data, discovery=dict(self.binding, **changes))})

    def test_legacy_unchanged_and_original_binds_only_authentic_app_assets(self):
        legacy = self.briefs.save(self.app, {"data": self.data})
        self.assertNotIn("discovery", legacy["data"])
        row = self.prepare()
        proof = row["data"]["discovery"]
        self.assertEqual(proof["card"]["rights_status"], "UNKNOWN")
        self.assertEqual(proof["foreign_bytes"], "NOT_AUTHORIZED")
        self.assertEqual(proof["collection_provenance"], "OPERATOR_REPORTED_READ_COVERAGE")
        self.assertEqual(proof["authentic_proofs"][0]["hash"], self.records["asset"]["hash"])
        self.assertEqual(row["data"]["publication"], "NOT_RUN")
        self.assertEqual(self.briefs.list(self.app)[0]["evidence_status"], "CURRENT")
        with self.assertRaises(Invalid):
            self.prepare(mode="LICENSED_EDIT")

    def test_licensed_requires_current_explicit_attestation(self):
        self.value["card"].update(
            rights_status="ALLOWED_BY_ATTESTATION", rights_evidence="Synthetic fixture attestation"
        )
        self.review = self.save_review(self.value, 1)
        self.collection = self.discovery.collect(
            self.app,
            dict(
                id="collection",
                version=1,
                manifest_version=self.binding["manifest_version"],
                query=self.collection["data"]["query"],
                attempted_sources=1,
                failed_sources=0,
            ),
        )
        self.binding.update(review_hash=self.review["hash"], collection_hash=self.collection["hash"])
        self.assertEqual(self.prepare(mode="LICENSED_EDIT")["data"]["discovery"]["foreign_bytes"], "NOT_AUTHORIZED")

    def test_unqualified_missing_baseline_or_unselected_app_proof_rejected(self):
        self.value["baseline"] = []
        self.review = self.save_review(self.value, 1)
        query = dict(self.collection["data"]["query"], viral_only=False)
        self.collection = self.discovery.collect(
            self.app,
            dict(
                id="collection",
                version=1,
                manifest_version=self.binding["manifest_version"],
                query=query,
                attempted_sources=1,
                failed_sources=0,
            ),
        )
        self.binding.update(collection_hash=self.collection["hash"], review_hash=self.review["hash"])
        self.assertTrue(self.collection["data"]["results"][0]["included"])
        with self.assertRaisesRegex(Invalid, "qualified"):
            self.prepare()

    def test_hash_app_source_review_and_analysis_mismatch_rejected(self):
        for changes in (
            dict(collection_hash="0" * 64),
            dict(review_hash="0" * 64),
            dict(manifest_version=999),
            dict(reference_id="invalid"),
        ):
            with self.subTest(changes=changes), self.assertRaises(Invalid):
                self.prepare(**changes)
        with self.assertRaises(Invalid):
            self.briefs.save(self.app, {"data": dict(self.data, channel="X", discovery=self.binding)})
        other = dict(
            self.data,
            analysis_id=self.legacy_analysis["id"],
            analysis_hash=self.legacy_analysis["hash"],
            discovery=self.binding,
        )
        with self.assertRaisesRegex(Invalid, "same current source"):
            self.briefs.save(self.app, {"data": other})
        self.save_review(self.value, 1)
        with self.assertRaisesRegex(Invalid, "Review changed"):
            self.prepare()

    def test_render_request_rechecks_revision_and_asset_bytes(self):
        saved = self.prepare()
        with connection(self.store.path) as db:
            request = render_request(
                db, self.store, self.app, dict(brief_id=saved["id"], brief_hash=saved["hash"], shape="PORTRAIT")
            )
            current_request(db, self.store, self.app, request)
        path = self.store.path.parent / "files" / self.app / self.records["asset"]["data"]["file_id"]
        raw = path.read_bytes()
        path.write_bytes(b"changed")
        with connection(self.store.path) as db, self.assertRaises(Invalid):
            current_request(db, self.store, self.app, request)
        path.write_bytes(raw)
        self.save_review(self.value, 1)
        with connection(self.store.path) as db, self.assertRaisesRegex(Invalid, "Repair current brief proof"):
            current_request(db, self.store, self.app, request)
        self.assertEqual(self.briefs.list(self.app)[0]["evidence_status"], "STALE_EVIDENCE")

    def test_source_and_app_changes_stale_prepared_brief(self):
        self.prepare()
        self.library.save(
            self.app,
            dict(
                id=self.source["id"],
                version=self.source["current"]["version"],
                data=dict(self.source["current"]["data"], title="Changed synthetic source"),
            ),
        )
        self.assertEqual(self.briefs.list(self.app)[0]["evidence_status"], "STALE_EVIDENCE")
        with self.assertRaises(Invalid):
            self.prepare()

    def test_same_hash_source_revision_stales_existing_binding(self):
        saved = self.prepare()
        with connection(self.store.path) as db:
            append_capture(
                db, self.app, self.source["id"], self.source["current"]["data"], self.source["current"]["version"] + 1
            )
        self.assertEqual(self.briefs.list(self.app)[0]["evidence_status"], "STALE_EVIDENCE")
        with self.assertRaisesRegex(Invalid, "version changed"):
            self.prepare()
        with connection(self.store.path) as db, self.assertRaises(Invalid):
            render_request(
                db, self.store, self.app, dict(brief_id=saved["id"], brief_hash=saved["hash"], shape="PORTRAIT")
            )

    def test_fresh_same_hash_revision_roundtrips_exact_source_version(self):
        with connection(self.store.path) as db:
            append_capture(
                db, self.app, self.source["id"], self.source["current"]["data"], self.source["current"]["version"] + 1
            )
        self.review = self.save_review(self.value, 1)
        self.collection = self.discovery.collect(
            self.app,
            dict(
                id="collection",
                version=1,
                manifest_version=self.binding["manifest_version"],
                query=self.collection["data"]["query"],
                attempted_sources=1,
                failed_sources=0,
            ),
        )
        self.binding.update(review_hash=self.review["hash"], collection_hash=self.collection["hash"])
        saved = self.prepare()
        self.assertEqual(saved["data"]["source"]["version"], 2)
        restored = Store(Path(self.tmp.name) / "same-hash-restored/state.sqlite")
        restored.restore(self.store.export(self.app))
        self.assertEqual(Briefs(restored).list(self.app)[0]["current"]["data"]["source"]["version"], 2)

    def test_app_context_change_stales_prepared_brief(self):
        self.prepare()
        app = self.store.app(self.app)
        self.store.save_app(self.app, dict(app["data"], name="Changed app"), app["version"])
        self.assertEqual(self.briefs.list(self.app)[0]["evidence_status"], "STALE_EVIDENCE")
        with self.assertRaises(Invalid):
            self.prepare()

    def test_freshness_and_app_proof_are_required(self):
        with patch(
            "mission_control.creative_briefs.now",
            return_value=(datetime.now(timezone.utc) + timedelta(hours=25)).isoformat(),
        ):
            with self.assertRaisesRegex(Invalid, "fresh"):
                self.prepare()
        self.value["card"]["authentic_evidence_ids"] = []
        self.review = self.save_review(self.value, 1)
        self.collection = self.discovery.collect(
            self.app,
            dict(
                id="collection",
                version=1,
                manifest_version=self.binding["manifest_version"],
                query=self.collection["data"]["query"],
                attempted_sources=1,
                failed_sources=0,
            ),
        )
        self.binding.update(review_hash=self.review["hash"], collection_hash=self.collection["hash"])
        with self.assertRaisesRegex(Invalid, "authentic app proof"):
            self.prepare()

    def test_card_proofs_must_be_selected_in_brief(self):
        asset = self.records["asset"]
        other = Service(self.store).evidence(
            self.app,
            dict(kind="asset", title="Second synthetic asset", source="Synthetic local fixture", data=asset["data"]),
        )
        with self.assertRaisesRegex(Invalid, "card.s authentic app assets"):
            self.briefs.save(self.app, {"data": dict(self.data, asset_ids=[other["id"]], discovery=self.binding)})

    def test_oversized_frozen_collection_is_rejected(self):
        oversized = deepcopy(self.collection)
        oversized["data"]["synthetic_padding"] = "x" * 1048576
        with patch("mission_control.discovery_store.latest", return_value=oversized):
            with self.assertRaisesRegex(Invalid, "1 MiB"):
                self.prepare()

    def test_snapshot_roundtrip_displays_frozen_proof_but_stays_stale_and_rejects_tampering(self):
        saved = self.prepare()
        snapshot = self.store.export(self.app)
        restored = Store(Path(self.tmp.name) / "restored/state.sqlite")
        restored.restore(snapshot)
        item = self.briefs.list(self.app)[0]
        other = Briefs(restored).list(self.app)[0]
        self.assertEqual(other["current"]["data"]["discovery"], item["current"]["data"]["discovery"])
        self.assertEqual(other["evidence_status"], "STALE_EVIDENCE")
        with connection(restored.path) as db, self.assertRaises(Invalid):
            render_request(
                db, restored, self.app, dict(brief_id=saved["id"], brief_hash=saved["hash"], shape="PORTRAIT")
            )
        bad = deepcopy(snapshot)
        row = bad["payload"]["production"]["briefs"][0]["versions"][0]
        row["data"]["discovery"]["card"]["interpreted_mechanism"] = "Tampered mechanism"
        row["hash"] = digest(row["data"])
        bad["payload"]["production"]["briefs"][0]["current"] = deepcopy(row)
        bad["sha256"] = digest(bad["payload"])
        target = Store(Path(self.tmp.name) / "tampered/state.sqlite")
        with self.assertRaises(Invalid):
            target.restore(bad)

    def test_discovery_snapshot_rejects_rehashed_invalid_historical_product_evidence(self):
        self.prepare()
        snapshot = self.store.export(self.app)
        cases = [
            ("claim", {"result": "FAIL"}),
            ("claim", {"checked_at": "2020-01-01T00:00:00+00:00"}),
            ("claim", {"release": "another-build"}),
            ("store", {"locale": "fr-CA"}),
            ("asset", {"authentic": False}),
            ("asset", {"rights_cleared": False}),
            ("asset", {"locale": "fr-CA"}),
        ]
        for index, (kind, changes) in enumerate(cases):
            with self.subTest(kind=kind, changes=changes):
                bad = deepcopy(snapshot)
                item = bad["payload"]["production"]["briefs"][0]
                row = item["versions"][0]
                record = next(r for r in row["data"]["records"] if r["kind"] == kind)
                record["data"].update(changes)
                record["hash"] = digest({key: record[key] for key in ("kind", "data", "source")})
                if kind == "asset":
                    row["data"]["discovery"]["authentic_proofs"][0]["hash"] = record["hash"]
                row["hash"] = digest(row["data"])
                item["current"] = deepcopy(row)
                bad["sha256"] = digest(bad["payload"])
                target = Store(Path(self.tmp.name) / ("tampered-product-" + str(index)) / "state.sqlite")
                with self.assertRaises(Invalid):
                    target.restore(bad)

    def test_legacy_snapshot_valid_and_rehashed_invalid_product_evidence_rejected(self):
        self.briefs.save(self.app, {"data": self.data})
        snapshot = self.store.export(self.app)
        restored = Store(Path(self.tmp.name) / "legacy-restored/state.sqlite")
        restored.restore(snapshot)
        self.assertEqual(Briefs(restored).list(self.app)[0]["evidence_status"], "CURRENT")
        cases = [
            ("claim", {"result": "FAIL"}),
            ("readiness", {"checked_at": "2020-01-01T00:00:00+00:00"}),
            ("route", {"release": "wrong"}),
            ("store", {"locale": "fr-CA"}),
            ("asset", {"authentic": False}),
            ("asset", {"rights_cleared": False}),
        ]
        for index, (kind, changes) in enumerate(cases):
            with self.subTest(kind=kind, changes=changes):
                bad = deepcopy(snapshot)
                item = bad["payload"]["production"]["briefs"][0]
                row = item["versions"][0]
                record = next(r for r in row["data"]["records"] if r["kind"] == kind)
                record["data"].update(changes)
                record["hash"] = digest({key: record[key] for key in ("kind", "data", "source")})
                row["hash"] = digest(row["data"])
                item["current"] = deepcopy(row)
                bad["sha256"] = digest(bad["payload"])
                target = Store(Path(self.tmp.name) / ("legacy-bad-" + str(index)) / "state.sqlite")
                with self.assertRaises(Invalid):
                    target.restore(bad)

    def test_legacy_same_hash_source_revision_restores_history_and_stales_current(self):
        saved = self.briefs.save(self.app, {"data": self.data})
        with connection(self.store.path) as db:
            append_capture(db, self.app, self.source["id"], self.source["current"]["data"], 2)
        self.assertEqual(self.briefs.list(self.app)[0]["evidence_status"], "STALE_EVIDENCE")
        restored = Store(Path(self.tmp.name) / "legacy-same-hash/state.sqlite")
        restored.restore(self.store.export(self.app))
        item = Briefs(restored).list(self.app)[0]
        self.assertEqual(item["current"]["data"]["source"]["version"], saved["data"]["source"]["version"])
        self.assertEqual(item["evidence_status"], "STALE_EVIDENCE")
        with connection(restored.path) as db, self.assertRaises(Invalid):
            render_request(
                db, restored, self.app, dict(brief_id=saved["id"], brief_hash=saved["hash"], shape="PORTRAIT")
            )


if __name__ == "__main__":
    unittest.main()
