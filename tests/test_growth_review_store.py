"""Real SQLite history, optimistic app scope, immutable notes and source freshness."""
import copy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from mission_control.common import Invalid, canonical
from mission_control.db import connection
from mission_control.store import Store
from mission_control.growth_review_store import GrowthReviews, history, target_entry, decoded, freeze_comparison, current_readout, replay_comparison
from mission_control.growth_review_contract import context_of, entry_hash, entry_data, note_data, comparison_data, comparison_readout, entry_readout, MAX_ENTRIES
from tests.test_benchmark_ads import saved_report, SEGMENT
from tests.test_aso_validation import listing
from tests.test_benchmark_context import records


class GrowthReviewStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "history.sqlite", seed=False)
        for identity in ("sample-one", "sample-two"):
            self.store.save_app(identity, dict(name="Synthetic app", release="build-1", locale="en-US", currency="USD", store_app_id="123"))
        self.stamp = datetime.fromisoformat("2026-10-23T12:00:00+00:00")
        self.work = GrowthReviews(self.store, lambda: self.stamp)
        self.body = dict(id="listing-one", manifest_version=1, kind="ASO_LISTING", data=dict(release="build-1", listing=listing()))

    def tearDown(self):
        self.tmp.cleanup()

    def test_immutable_history_survives_restart_and_replay(self):
        row = self.work.save("sample-one", self.body)
        self.assertEqual(row, self.work.save("sample-one", self.body))
        restarted = GrowthReviews(Store(self.store.path, seed=False), lambda: self.stamp)
        self.assertEqual(restarted.list("sample-one"), self.work.list("sample-one"))
        with connection(self.store.path) as db:
            self.assertEqual(history(db, "sample-one"), [row])
            self.assertEqual(decoded(db.execute("SELECT * FROM growth_review_entries").fetchone()), row)
        changed = copy.deepcopy(self.body)
        changed["data"]["listing"]["fields"]["title"] = "Changed title"
        with self.assertRaises(Invalid):
            self.work.save("sample-one", changed)
        self.assertEqual(self.work.list("sample-one")["history"][0]["hash"], row["hash"])

    def test_scope_guard_rejects_manifest_release_locale_currency_and_unknown_fields(self):
        cases = [dict(self.body, manifest_version=True), dict(self.body, manifest_version=2), dict(self.body, kind="PUBLISH"), dict(self.body, approve=True),
                 dict(self.body, data=dict(release="other", listing=listing())),
                 dict(self.body, data=dict(release="build-1", listing=dict(listing(), locale="fr-FR")))]
        ref, _ = records()
        cases.append(dict(id="reference-one", manifest_version=1, kind="BENCHMARK_REFERENCE", data=dict(release="build-1", reference=dict(ref, currency="EUR"))))
        for body in cases:
            with self.assertRaises(Invalid):
                self.work.save("sample-one", body)
        self.assertEqual(self.work.list("sample-one")["history"], [])

    def test_fresh_readout_retains_original_listing_and_expired_reference(self):
        row = self.work.save("sample-one", self.body)
        ref, _ = records()
        self.work.save("sample-one", dict(id="reference-one", manifest_version=1, kind="BENCHMARK_REFERENCE", data=dict(release="build-1", reference=ref)))
        self.stamp = datetime.fromisoformat("2027-02-01T12:00:00+00:00")
        rows = {row["id"]: row for row in self.work.list("sample-one")["history"]}
        self.assertEqual(rows["reference-one"]["readout"]["analysis"]["status"], "REFERENCE_EXPIRED")
        self.assertEqual(rows["listing-one"]["readout"]["analysis"]["status"], "NEEDS_REPAIR")
        self.assertEqual(rows["listing-one"]["data"], row["data"])
        self.assertEqual(rows["listing-one"]["hash"], row["hash"])

    def test_note_data_and_target_entry_bind_exact_source_without_approval(self):
        target = self.work.save("sample-one", self.body)
        value = dict(target_id=target["id"], target_hash=target["hash"], decision="REVISE", rationale="Shorten the supplied title after review")
        self.assertEqual(note_data(value), value)
        note = self.work.save("sample-one", dict(id="note-one", manifest_version=1, kind="EDITORIAL_NOTE", data=value))
        with connection(self.store.path) as db:
            self.assertEqual(target_entry(db, "sample-one", value), target)
            for app_id, invalid in (("sample-two", value), ("sample-one", dict(value, target_hash="a" * 64)), ("sample-one", dict(value, target_id="note-one", target_hash=note["hash"]))):
                with self.assertRaises(Invalid):
                    target_entry(db, app_id, invalid)
        readout = self.work.list("sample-one")["history"][1]["readout"]
        self.assertEqual(readout["analysis"]["status"], "EDITORIAL_NOTE_ONLY")
        self.assertFalse(readout["execution_authority"])
        self.assertFalse(readout["provider_verified"])

    def test_context_of_entry_hash_and_entry_readout_detect_scope_change_and_tamper(self):
        row = self.work.save("sample-one", self.body)
        current = context_of(self.store.app("sample-one"))
        self.assertEqual(entry_hash(row["kind"], row["data"], current), row["hash"])
        self.assertEqual(entry_data(row["kind"], row["data"], current, self.stamp.isoformat()), row["data"])
        self.assertNotEqual(context_of(self.store.app("sample-two")), current)
        with self.assertRaises(Invalid):
            entry_readout(dict(row, hash="f" * 64), current, self.stamp.isoformat())
        self.assertEqual(entry_readout(dict(row, imported=1), current, self.stamp.isoformat())["availability"], "IMPORTED_ASSERTION")
        app = self.store.app("sample-one")
        self.store.save_app("sample-one", app["data"], app["version"])
        self.assertEqual(self.work.list("sample-one")["history"][0]["readout"]["availability"], "STALE_APP_SCOPE")

    def test_invalid_note_and_private_fields_leave_no_rows(self):
        for data in (dict(target_id="missing", target_hash="a" * 64, decision="APPROVED", rationale="No authority"),
                     dict(target_id="missing", target_hash="bad", decision="KEEP", rationale="No source")):
            with self.assertRaises(Invalid):
                self.work.save("sample-one", dict(id="bad-note", manifest_version=1, kind="EDITORIAL_NOTE", data=data))
        value = copy.deepcopy(self.body)
        value["data"]["api_key"] = "synthetic-forbidden-input"
        with self.assertRaises(Invalid):
            self.work.save("sample-one", value)
        self.assertEqual(self.work.list("sample-one")["history"], [])

    def test_history_bound_and_no_network_execution(self):
        row = self.work.save("sample-one", self.body)
        with connection(self.store.path) as db:
            values = [("sample-one", "entry-" + str(i), row["kind"], canonical(row["data"]), row["hash"], canonical(row["context"]), row["created"], 0) for i in range(MAX_ENTRIES - 1)]
            db.executemany("INSERT INTO growth_review_entries VALUES(?,?,?,?,?,?,?,?)", values)
        with patch("socket.socket", side_effect=AssertionError("Network forbidden")):
            with self.assertRaises(Invalid):
                self.work.save("sample-one", dict(self.body, id="over-bound"))
            replay = self.work.save("sample-one", self.body)
        self.assertEqual(replay, row)
        self.assertEqual(len(self.work.list("sample-one")["history"]), MAX_ENTRIES)

    def comparison_fixture(self):
        record, report = saved_report(self.store)
        reference, _ = records()
        reference.update(period_start="2026-10-01T00:00:00+00:00", period_end="2026-10-08T00:00:00+00:00", published_at="2026-10-10T00:00:00+00:00", retrieved_at="2026-10-22T00:00:00+00:00")
        ref = self.work.save("sample-one", dict(id="reference-one", kind="BENCHMARK_REFERENCE", manifest_version=1, data=dict(release="build-1", reference=reference)))
        data = dict(reference_id=ref["id"], reference_hash=ref["hash"], job_id="job-one", report_hash=report["source_hash"], metric="CPT_MINOR", segment=SEGMENT)
        body = dict(id="comparison-one", kind="BENCHMARK_COMPARISON", manifest_version=1, data=data)
        return record, report, ref, body

    def test_benchmark_comparison_freezes_exact_reference_and_account_observation(self):
        _, _, reference, body = self.comparison_fixture()
        self.assertEqual(comparison_data(body["data"]), body["data"])
        with connection(self.store.path) as db:
            frozen = freeze_comparison(db, "sample-one", body["data"], reference["context"], self.stamp.isoformat())
        row = self.work.save("sample-one", body)
        self.assertEqual(row["data"], frozen)
        self.assertEqual(comparison_readout(frozen, self.stamp.isoformat())["difference"], 100)
        self.assertEqual(self.work.save("sample-one", body), row)
        with connection(self.store.path) as db:
            self.assertEqual(replay_comparison(db, "sample-one", row["id"], row["kind"], body["data"], row["context"]), row)
            self.assertEqual(current_readout(db, row, row["context"], self.stamp.isoformat())["analysis"]["status"], "COMPARABLE_ADVISORY")
        self.assertFalse(self.work.list("sample-one")["execution_authority"])

    def test_current_readout_withholds_difference_after_connection_or_report_change(self):
        record, report, _, body = self.comparison_fixture()
        row = self.work.save("sample-one", body)
        changed = copy.deepcopy(report)
        changed["rows"][0]["totalMetrics"]["taps"] = 20
        with connection(self.store.path) as db:
            db.execute("UPDATE jobs SET result=? WHERE id='job-one'", (canonical(changed),))
        view = next(item for item in self.work.list("sample-one")["history"] if item["id"] == row["id"])
        self.assertEqual(view["readout"]["availability"], "SOURCE_REVIEW_NEEDED")
        self.assertIsNone(view["readout"]["analysis"]["difference"])
        self.assertEqual(self.work.save("sample-one", body), row)
        self.store.save_record("sample-one", dict(record, manifest_version=1, data=dict(record["data"], auth_mode="disconnected")))
        self.assertEqual(GrowthReviews(Store(self.store.path, seed=False), lambda: self.stamp).list("sample-one")["history"][0]["hash"], row["hash"])

    def test_comparison_scope_guard_rejects_wrong_reference_and_caller_totals(self):
        _, _, _, body = self.comparison_fixture()
        for data in (dict(body["data"], reference_hash="a" * 64), dict(body["data"], numerator=100), dict(body["data"], reference_id="missing")):
            with self.assertRaises(Invalid):
                self.work.save("sample-one", dict(body, data=data))
        with self.assertRaises(Invalid):
            self.work.save("sample-two", body)
        row = self.work.save("sample-one", body)
        with self.assertRaises(Invalid):
            self.work.save("sample-one", dict(body, data=dict(body["data"], metric="CR")))
        self.assertEqual(self.work.list("sample-two")["history"], [])
        self.assertEqual(entry_readout(dict(row, imported=1), row["context"], self.stamp.isoformat())["analysis"]["status"], "IMPORTED_ASSERTION")

    def test_comparison_missing_metrics_and_scope_mismatch_remain_visible(self):
        _, report, _, body = self.comparison_fixture()
        value = copy.deepcopy(report)
        value["rows"][0]["totalMetrics"]["totalInstalls"] = None
        with connection(self.store.path) as db:
            db.execute("UPDATE jobs SET result=? WHERE id='job-one'", (canonical(value),))
        row = self.work.save("sample-one", dict(body, data=dict(body["data"], metric="CR")))
        readout = entry_readout(row, row["context"], self.stamp.isoformat())
        self.assertEqual(readout["analysis"]["status"], "SOURCE_METRICS_UNAVAILABLE")
        self.assertIsNone(readout["analysis"]["difference"])
        app = self.store.app("sample-one")
        self.store.save_app("sample-one", dict(app["data"], release="build-2"), app["version"])
        readout = next(item for item in self.work.list("sample-one")["history"] if item["id"] == row["id"])["readout"]
        self.assertEqual(readout["analysis"]["status"], "STALE_APP_SCOPE")
        self.assertIsNone(readout["analysis"]["difference"])
