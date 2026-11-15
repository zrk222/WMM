"""Audit bundles are read-only, source-bound manifests, not audit opinions."""

from pathlib import Path
import json
import tempfile
import unittest
import importlib.util
from mission_control.store import Store

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("wmm_audit_bundle", ROOT / "tools" / "audit_bundle.py")
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)
APP = "sample-one"


class AuditBundleTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "state.sqlite"
        self.store = Store(self.path, seed=False)
        self.store.save_app(
            APP,
            dict(
                name="Synthetic app",
                release="build-1",
                job="Synthetic job",
                audience="Synthetic audience",
                activation="Synthetic value",
                locale="en-US",
            ),
        )

    def test_export_verifies_and_omits_raw_app_data(self):
        value = audit.build(self.path, APP)
        checked = audit.verify(self.path, APP, value)
        self.assertEqual(checked["status"], "MATCH")
        self.assertGreater(value["audit"]["count"], 0)
        self.assertNotIn("Synthetic job", json.dumps(value))
        self.assertNotIn("Synthetic audience", json.dumps(value))

    def test_tampered_bundle_and_changed_database_are_rejected(self):
        value = audit.build(self.path, APP)
        changed = json.loads(json.dumps(value))
        changed["audit"]["count"] += 1
        with self.assertRaises(ValueError):
            audit.verify(self.path, APP, changed)
        from mission_control.db import connection

        with connection(self.path) as db:
            db.execute("UPDATE apps SET version=version+1 WHERE id=?", (APP,))
        with self.assertRaises(ValueError):
            audit.verify(self.path, APP, value)

    def test_wrong_app_and_missing_database_reject(self):
        with self.assertRaises(ValueError):
            audit.build(self.path, "other-app")
        with self.assertRaises(FileNotFoundError):
            audit.build(Path(self.folder.name) / "missing.sqlite", APP)
