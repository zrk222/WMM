"""Actual Store snapshots preserve growth history, authority boundaries and atomicity."""
import copy
from datetime import datetime, timezone, timedelta
from pathlib import Path
import tempfile
import unittest
from mission_control.common import Invalid, digest, canonical
from mission_control.db import connection
from mission_control.store import Store
from mission_control.growth_review_store import GrowthReviews
from mission_control.growth_review_portable import context_data, projection_data, projection_truth, projection_state, projection_numerator, projection_observation, stored_data, row_data, linked_data, linked_reference, restore
from tests.test_aso_validation import listing
from tests.test_benchmark_context import records
from tests.test_benchmark_ads import saved_report, SEGMENT


class GrowthReviewPortableTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "source.sqlite", seed=False)
        self.store.save_app("sample-one", dict(name="Synthetic app", release="build-1", locale="en-US", currency="USD", store_app_id="123"))
        self.stamp = datetime.fromisoformat("2026-10-22T12:00:00+00:00")
        self.work = GrowthReviews(self.store, lambda: self.stamp)
        self.record, self.report = saved_report(self.store)
        self.listing = self.work.save("sample-one", dict(id="listing-one", kind="ASO_LISTING", manifest_version=1, data=dict(release="build-1", listing=listing())))
        ref, _ = records()
        ref.update(period_start="2026-10-01T00:00:00+00:00", period_end="2026-10-08T00:00:00+00:00", published_at="2026-10-10T00:00:00+00:00", retrieved_at="2026-10-22T00:00:00+00:00")
        self.reference = self.work.save("sample-one", dict(id="reference-one", kind="BENCHMARK_REFERENCE", manifest_version=1, data=dict(release="build-1", reference=ref)))
        self.comparison = self.work.save("sample-one", dict(id="comparison-one", kind="BENCHMARK_COMPARISON", manifest_version=1,
            data=dict(reference_id="reference-one", reference_hash=self.reference["hash"], job_id="job-one", report_hash=self.report["source_hash"], metric="CPT_MINOR", segment=SEGMENT)))
        self.work.save("sample-one", dict(id="note-one", kind="EDITORIAL_NOTE", manifest_version=1, data=dict(target_id="listing-one", target_hash=self.listing["hash"], decision="REVISE", rationale="Keep the original and prepare a shorter title")))
        self.snapshot = self.store.export("sample-one")

    def tearDown(self):
        self.tmp.cleanup()

    def test_projection_state_rejects_contradictory_status_scope_and_reasons(self):
        projection = copy.deepcopy(self.comparison["data"]["projection"])
        self.assertIsNone(projection_state(projection))
        invalid_states = (
            dict(projection, status="SOURCE_METRICS_UNAVAILABLE"),
            dict(projection, reasons="missing"),
            dict(projection, reasons=[1]),
            dict(projection, scope=1),
            dict(projection, observed=None),
        )
        for value in invalid_states:
            with self.subTest(value=value), self.assertRaises(Invalid):
                projection_state(value)

    def test_projection_numerator_keeps_only_bounded_exact_source_text(self):
        valid = dict(self.comparison["data"]["projection"], numerator_exact="12.50")
        self.assertIsNone(projection_numerator(valid))
        for numerator in (12.5, "x" * 101):
            with self.subTest(numerator=str(numerator)[:12]), self.assertRaises(Invalid):
                projection_numerator(dict(valid, numerator_exact=numerator))

    def test_linked_reference_resolves_exact_hash_kind_and_app_scope(self):
        entries = {row["id"]: row for row in self.snapshot["payload"]["growth_reviews"]}
        self.assertIsNone(linked_reference(self.comparison, entries))
        wrong_hash = copy.deepcopy(self.comparison)
        wrong_hash["data"]["reference_hash"] = "c" * 64
        with self.assertRaises(Invalid):
            linked_reference(wrong_hash, entries)
        wrong_kind = copy.deepcopy(self.comparison)
        wrong_kind["data"]["reference_id"] = "listing-one"
        wrong_kind["data"]["reference_hash"] = self.listing["hash"]
        with self.assertRaises(Invalid):
            linked_reference(wrong_kind, entries)
        changed_scope = copy.deepcopy(entries)
        changed_scope["reference-one"]["context"]["app_id"] = "sample-two"
        with self.assertRaises(Invalid):
            linked_reference(self.comparison, changed_scope)

    def destination(self, name="target"):
        return Store(Path(self.tmp.name) / (name + ".sqlite"), seed=False)

    def test_portable_history_survives_real_export_restore_without_authority(self):
        target = self.destination()
        target.restore(self.snapshot)
        rows = GrowthReviews(target, lambda: self.stamp).list("sample-one")["history"]
        self.assertEqual(len(rows), 4)
        self.assertEqual({row["id"]:row["hash"] for row in rows}, {row["id"]:row["hash"] for row in self.snapshot["payload"]["growth_reviews"]})
        self.assertTrue(all(row["imported"] == 1 and row["readout"]["availability"] == "IMPORTED_ASSERTION" for row in rows))
        comparison = next(row for row in rows if row["kind"] == "BENCHMARK_COMPARISON")
        self.assertIsNone(comparison["readout"]["analysis"]["difference"])
        with connection(target.path) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM jobs").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT count(*) FROM operator_roles").fetchone()[0], 0)

    def test_context_projection_and_row_validators_preserve_canonical_content(self):
        row = self.comparison
        context_data(row["context"], "sample-one")
        request = {key:value for key,value in row["data"].items() if key not in ("reference", "projection")}
        projection_data(row["data"]["projection"], request, row["created"])
        projection_truth(row["data"]["projection"])
        projection_observation(row["data"]["projection"], request)
        stored_data(row)
        row_data("sample-one", row, self.stamp)
        entries = {entry["id"]:entry for entry in self.snapshot["payload"]["growth_reviews"]}
        linked_data(row, entries)
        with self.assertRaises(Invalid):
            context_data(row["context"], "other-app")

    def test_tampered_or_cross_app_rows_rollback_entire_store_restore(self):
        for name, change in (("hash", lambda row:row.update(hash="a" * 64)), ("app", lambda row:row.update(app_id="other-app")),
                             ("future", lambda row:row.update(created="2999-01-01T00:00:00+00:00")), ("extra", lambda row:row.update(approve=True))):
            snapshot = copy.deepcopy(self.snapshot)
            change(snapshot["payload"]["growth_reviews"][0])
            snapshot["sha256"] = digest(snapshot["payload"])
            target = self.destination(name)
            with self.assertRaises(Invalid):
                target.restore(snapshot)
            self.assertEqual(target.apps(), [])

    def test_recomputed_hash_cannot_import_fabricated_scope_or_authority(self):
        from mission_control.growth_review_contract import entry_hash
        mutations = [lambda row:row["data"]["projection"].update(spend_authority=True),
                     lambda row:row["data"]["projection"].update(classification_provider_verified=True),
                     lambda row:row["data"]["projection"]["binding"].update(job_id="other-job"),
                     lambda row:row["data"]["projection"]["observed"].update(territory="OTHER"),
                     lambda row:row["data"]["reference"].update(value=999)]
        for index, mutate in enumerate(mutations):
            snapshot = copy.deepcopy(self.snapshot)
            row = next(row for row in snapshot["payload"]["growth_reviews"] if row["kind"] == "BENCHMARK_COMPARISON")
            mutate(row)
            row["hash"] = entry_hash(row["kind"], row["data"], row["context"])
            snapshot["sha256"] = digest(snapshot["payload"])
            target = self.destination("forged-" + str(index))
            with self.assertRaises(Invalid):
                target.restore(snapshot)
            self.assertEqual(target.apps(), [])

    def test_duplicate_or_missing_linked_entries_are_rejected_before_insert(self):
        for name, transform in (("duplicate", lambda rows:rows + [rows[0]]), ("missing", lambda rows:[row for row in rows if row["id"] != "reference-one"])):
            snapshot = copy.deepcopy(self.snapshot)
            snapshot["payload"]["growth_reviews"] = transform(snapshot["payload"]["growth_reviews"])
            snapshot["sha256"] = digest(snapshot["payload"])
            target = self.destination(name)
            with self.assertRaises(Invalid):
                target.restore(snapshot)
            self.assertEqual(target.apps(), [])

    def test_legacy_snapshot_and_caller_transaction_rollback(self):
        legacy = copy.deepcopy(self.snapshot)
        del legacy["payload"]["growth_reviews"]
        legacy["sha256"] = digest(legacy["payload"])
        target = self.destination("legacy")
        target.restore(legacy)
        self.assertEqual(GrowthReviews(target, lambda: self.stamp).list("sample-one")["history"], [])
        with self.assertRaises(RuntimeError):
            with connection(target.path) as db:
                db.execute("BEGIN IMMEDIATE")
                restore(db, "sample-one", self.snapshot["payload"]["growth_reviews"])
                raise RuntimeError("Synthetic crash before commit")
        self.assertEqual(GrowthReviews(target, lambda: self.stamp).list("sample-one")["history"], [])
