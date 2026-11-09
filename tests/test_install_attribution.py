"""MMP install exports stay app-scoped, descriptive and explicitly covered."""
from pathlib import Path
import tempfile
import unittest
from mission_control.common import Invalid
from mission_control.install_attribution import record_batch, report, summary
from mission_control.review_access import Access
from mission_control.store import Store

APP = "sample-one"
CAMPAIGN = "11111111-1111-4111-8111-111111111111"
OWNER = {"principal": "github:owner", "login": "owner"}


class InstallAttributionTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.store = Store(Path(self.folder.name) / "state.sqlite", seed=False)
        for app in (APP, "sample-two"):
            self.store.save_app(app, dict(name="Synthetic " + app, release="build-1", job="Synthetic job",
                                         audience="Synthetic audience", activation="Synthetic value", locale="en-US"))
        Access(self.store).bootstrap(APP, OWNER, {"confirm_owner": True})

    def body(self, request="22222222-2222-4222-8222-222222222222", rows=None, complete=True, count=None):
        installs = rows if rows is not None else [
            dict(install_id="install_a", state="ATTRIBUTED", occurred_at="2026-11-01T00:00:00+00:00"),
            dict(install_id="install_b", state="UNATTRIBUTED", occurred_at="2026-11-01T01:00:00+00:00"),
        ]
        return dict(source="APPSFLYER", campaign_token=CAMPAIGN, request_id=request,
                    source_receipt_sha256="a" * 64, observed_at="2026-11-02T00:00:00+00:00",
                    window=dict(starts_at="2026-10-31T00:00:00+00:00", ends_at="2026-11-03T00:00:00+00:00"),
                    coverage=dict(complete=complete, source_event_count=count if count is not None else (len(installs) if complete else None)),
                    installs=installs)

    def test_records_attributed_unattributed_and_is_idempotent(self):
        first = record_batch(self.store, APP, OWNER, self.body())
        self.assertEqual(first["status"], "RECORDED")
        self.assertEqual(first["inserted"], 2)
        again = record_batch(self.store, APP, OWNER, self.body())
        self.assertEqual(again["status"], "ALREADY_RECORDED")
        value = report(self.store, APP, OWNER, CAMPAIGN)
        self.assertEqual(value["counts"]["ATTRIBUTED"], 1)
        self.assertEqual(value["counts"]["UNATTRIBUTED"], 1)
        self.assertEqual(value["coverage_status"], "COMPLETE")
        self.assertEqual(value["batches"][0]["source_event_count"], 2)
        self.assertNotIn("rate", value)
        self.assertNotIn("lift", value)

    def test_zero_with_complete_coverage_is_explicit_and_partial_is_not_zero(self):
        empty = self.body(request="33333333-3333-4333-8333-333333333333", rows=[], complete=True, count=0)
        record_batch(self.store, APP, OWNER, empty)
        value = report(self.store, APP, OWNER, CAMPAIGN)
        self.assertEqual(value["counts"]["ATTRIBUTED"], 0)
        self.assertEqual(value["coverage_status"], "COMPLETE")
        record_batch(self.store, APP, OWNER, self.body(request="44444444-4444-4444-8444-444444444444",
                                                        rows=[], complete=False, count=None))
        self.assertEqual(report(self.store, APP, OWNER, CAMPAIGN)["coverage_status"], "PARTIAL")
        self.assertEqual(report(self.store, APP, OWNER, "99999999-9999-4999-8999-999999999999")["coverage_status"], "NO_IMPORT")

    def test_conflicting_identity_rejects_the_whole_batch_without_writes(self):
        record_batch(self.store, APP, OWNER, self.body())
        changed = self.body(request="55555555-5555-4555-8555-555555555555", rows=[
            dict(install_id="install_a", state="SUPPRESSED", occurred_at="2026-11-01T00:00:00+00:00")])
        with self.assertRaises(Invalid):
            record_batch(self.store, APP, OWNER, changed)
        self.assertEqual(report(self.store, APP, OWNER, CAMPAIGN)["recorded"], 2)

    def test_validation_rejects_pii_future_times_and_unknown_fields(self):
        for changed in (dict(source="apps"), dict(campaign_token="not-a-uuid"),
                        dict(source_receipt_sha256="A" * 64),
                        dict(coverage=dict(complete=True, source_event_count=None)),
                        dict(extra=True),
                        dict(installs=[dict(install_id="user@example.com", state="ATTRIBUTED",
                                            occurred_at="2026-11-01T00:00:00+00:00")]),
                        dict(installs=[dict(install_id="1234567890", state="ATTRIBUTED",
                                            occurred_at="2026-11-01T00:00:00+00:00")]),
                        dict(installs=[dict(install_id="install_a", state="ATTRIBUTED",
                                            occurred_at="2026-11-03T00:00:00+00:00")]),
                        dict(installs=[dict(install_id="install_a", state="ATTRIBUTED",
                                            occurred_at="2026-10-30T00:00:00+00:00")]),
                        dict(window=dict(starts_at="2026-11-03T00:00:00+00:00",
                                         ends_at="2026-11-02T00:00:00+00:00")),
                        dict(observed_at="2026-10-30T00:00:00+00:00"),
                        dict(installs=[dict(install_id="install_a", state="ATTRIBUTED",
                                            occurred_at="2026-11-01T00:00:00+00:00"),
                                       dict(install_id="install_a", state="UNKNOWN",
                                            occurred_at="2026-11-01T00:00:00+00:00")])):
            with self.subTest(changed=changed), self.assertRaises(Invalid):
                record_batch(self.store, APP, OWNER, dict(self.body(request="66666666-6666-4666-8666-666666666666"), **changed))

    def test_batch_auto_links_to_the_exact_registered_study(self):
        from mission_control.db import connection
        from mission_control.observational_campaign import _tables
        with connection(self.store.path) as db:
            _tables(db)
            db.execute("INSERT INTO observational_campaign_studies VALUES(?,?,?,?,?,?,?,?)",
                       (APP, CAMPAIGN, "77777777-7777-4777-8777-777777777777", "a" * 64, 1, "{}", "b" * 64,
                        "2026-11-01T00:00:00+00:00"))
        self.assertEqual(report(self.store, APP, OWNER, CAMPAIGN)["study_status"], "UNLINKED")
        record_batch(self.store, APP, OWNER, self.body())
        value = report(self.store, APP, OWNER, CAMPAIGN)
        self.assertEqual(value["study_status"], "LINKED")
        self.assertEqual(value["study"]["study_hash"], "b" * 64)

    def test_day_aggregation_counts_distinct_installs_without_double_count(self):
        rows = [dict(install_id="day0", state="ATTRIBUTED", occurred_at="2026-11-01T00:00:00+00:00"),
                dict(install_id="day2", state="ATTRIBUTED", occurred_at="2026-11-03T00:00:00+00:00"),
                dict(install_id="day6", state="UNATTRIBUTED", occurred_at="2026-11-07T00:00:00+00:00")]
        body = dict(self.body(request="88888888-8888-4888-8888-888888888888", rows=rows, count=3),
                    window=dict(starts_at="2026-11-01T00:00:00+00:00", ends_at="2026-11-10T00:00:00+00:00"),
                    observed_at="2026-11-10T00:00:00+00:00")
        record_batch(self.store, APP, OWNER, body)
        self.assertEqual(report(self.store, APP, OWNER, CAMPAIGN, day=1)["recorded"], 1)
        self.assertEqual(report(self.store, APP, OWNER, CAMPAIGN, day=3)["recorded"], 2)
        self.assertEqual(report(self.store, APP, OWNER, CAMPAIGN, day=7)["recorded"], 3)
        with self.assertRaises(Invalid):
            report(self.store, APP, OWNER, CAMPAIGN, day=2)

    def test_workspace_summary_states_no_export_then_metadata_without_counts(self):
        self.assertEqual(summary(self.store, APP)["campaigns"], [])
        record_batch(self.store, APP, OWNER, self.body())
        item = summary(self.store, APP)["campaigns"][0]
        self.assertEqual(item["campaign_token"], CAMPAIGN)
        self.assertEqual(item["batches"], 1)
        self.assertEqual(item["coverage_status"], "COMPLETE")
        self.assertEqual(item["study_status"], "UNLINKED")
        self.assertNotIn("counts", item)

    def test_owner_and_app_boundaries(self):
        with self.assertRaises(PermissionError):
            record_batch(self.store, APP, {"principal": "github:other", "login": "other"}, self.body())
        record_batch(self.store, APP, OWNER, self.body())
        with self.assertRaises(PermissionError):
            report(self.store, "sample-two", OWNER, CAMPAIGN)


if __name__ == "__main__":
    unittest.main()


