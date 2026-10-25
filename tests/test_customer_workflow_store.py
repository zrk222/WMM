"""SQLite persistence, immutable customer history, source expiry and portable atomicity."""
import copy
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from mission_control.common import Invalid, digest
from mission_control.db import connection
from mission_control.store import Store
from mission_control.customer_workflow_store import CustomerWorkflows, history, app_scope, restored_entry, restore
from tests.test_customer_workflow import proposal, OBSERVED


class CustomerWorkflowStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "source.sqlite")
        app = self.store.app("sample-one")
        self.store.save_app("sample-one", dict(app["data"], release="build-1", locale="en-US", currency="USD"), app["version"])
        self.work = CustomerWorkflows(self.store, lambda: OBSERVED)
        self.body = dict(id="workflow-one", manifest_version=self.store.app("sample-one")["version"], data=proposal())

    def tearDown(self):
        self.tmp.cleanup()

    def test_save_list_history_restart_and_immutable_replay(self):
        row = self.work.save("sample-one", self.body)
        self.assertEqual(self.work.save("sample-one", self.body), row)
        self.assertEqual(CustomerWorkflows(Store(self.store.path), lambda: OBSERVED).list("sample-one"), self.work.list("sample-one"))
        with connection(self.store.path) as db:
            self.assertEqual(history(db, "sample-one"), [row])
        changed = copy.deepcopy(self.body)
        changed["data"]["buyer"] = "A different synthetic buyer"
        with self.assertRaises(Invalid):
            self.work.save("sample-one", changed)

    def test_manifest_and_app_scope_rejection_without_cross_app_borrowing(self):
        for app_id, body in (("sample-two", self.body), ("sample-one", dict(self.body, manifest_version=True)),
                             ("sample-one", dict(self.body, data=dict(proposal(), release="other")))):
            with self.assertRaises(Invalid):
                self.work.save(app_id, body)
        with self.assertRaises(Invalid):
            app_scope(self.store.app("sample-two"), proposal())
        self.assertEqual(self.work.list("sample-one")["history"], [])

    def test_expiry_and_app_changes_preserve_original_evidence(self):
        self.work.save("sample-one", self.body)
        later = CustomerWorkflows(self.store, lambda: datetime.fromisoformat("2027-01-01T00:00:00+00:00"))
        self.assertEqual(later.list("sample-one")["history"][0]["readout"]["status"], "SOURCE_REVIEW_NEEDED")
        app = self.store.app("sample-one")
        self.store.save_app("sample-one", dict(app["data"], release="new-build"), app["version"])
        self.assertEqual(self.work.list("sample-one")["history"][0]["readout"]["status"], "STALE_APP_SCOPE")

    def test_restored_entry_restore_tamper_and_duplicate_atomicity(self):
        row = self.work.save("sample-one", self.body)
        restored_entry("sample-one", row, OBSERVED)
        with self.assertRaises(Invalid):
            restored_entry("sample-two", row, OBSERVED)
        target = Store(Path(self.tmp.name) / "target.sqlite")
        with connection(target.path) as db:
            db.execute("BEGIN IMMEDIATE")
            restore(db, "sample-one", [row])
        with connection(target.path) as db:
            self.assertEqual(history(db, "sample-one")[0]["hash"], row["hash"])
            self.assertEqual(history(db, "sample-one")[0]["imported"], 1)
        empty = Store(Path(self.tmp.name) / "empty.sqlite")
        with self.assertRaises(Invalid), connection(empty.path) as db:
            db.execute("BEGIN IMMEDIATE")
            restore(db, "sample-one", [row, row])
        with connection(empty.path) as db:
            self.assertEqual(history(db, "sample-one"), [])
            restore(db, "sample-one", None)
        bad = dict(row, hash="0" * 64)
        with self.assertRaises(Invalid):
            restored_entry("sample-one", bad, OBSERVED)

    def test_existing_pmf_history_remains_unchanged_when_store_reopens(self):
        from mission_control.pmf_research import Research
        research = Research(self.store, lambda: OBSERVED)
        value = dict(segment="Synthetic founders", problem="Billing reconciliation", alternative="Manual spreadsheet",
            switching_cost="Unmeasured", value_event="First reconciliation", cadence="weekly", release="build-1",
            locale="en-US", currency="USD", arm="discovery", starts_at="2026-10-01T00:00:00+00:00",
            ends_at="2026-10-10T00:00:00+00:00", matures_at="2026-10-20T00:00:00+00:00", target_responses=10)
        research.save("sample-one", "study", dict(id="existing-study", manifest_version=self.body["manifest_version"], data=value))
        before = research.list("sample-one")
        self.work.save("sample-one", self.body)
        reopened = Store(self.store.path)
        self.assertEqual(Research(reopened, lambda: OBSERVED).list("sample-one"), before)
