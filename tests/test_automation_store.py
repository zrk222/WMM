"""Owner-authored rule sets are immutable versions; saving does not evaluate."""
from pathlib import Path
import tempfile
import unittest

from mission_control.automation_store import current, history, save
from mission_control.common import Invalid
from mission_control.store import Store

ROOT = Path(__file__).resolve().parents[1]
OWNER = {"principal": "github:1", "login": "owner"}
APP = "sample-one"


class AutomationStoreTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.store = Store(Path(self.folder.name) / "state.sqlite", seed=False)
        self.store.save_app(APP, dict(name="Synthetic app", release="build-1", job="Synthetic job",
                                     audience="Synthetic audience", activation="Synthetic value", locale="en-US"))
        self.document = {"schema": "wmm.automation-rules.v1", "mode": "PROPOSE_ONLY", "timezone": "UTC",
                         "rules": [{"id": "one", "enabled": True, "priority": 1,
                                    "when": {"fact": "app.release", "op": "eq", "value": "build-1"},
                                    "then": {"propose": {"action": "review", "tool": "reports.read", "reason": "ready"},
                                             "requires": ["OWNER_REVIEW"]}}]}

    def test_save_is_versioned_and_does_not_evaluate(self):
        first = save(self.store, APP, OWNER, self.document)
        self.assertEqual(first["version"], 1)
        self.assertEqual(current(self.store, APP)["hash"], first["hash"])
        second = save(self.store, APP, OWNER, self.document)
        self.assertEqual(second["version"], 2)
        self.assertEqual([row["version"] for row in history(self.store, APP)], [2, 1])

    def test_invalid_document_and_identity_reject(self):
        with self.assertRaises(Invalid):
            save(self.store, APP, OWNER, {"schema": "wrong"})
        with self.assertRaises(PermissionError):
            save(self.store, APP, {}, self.document)
        with self.assertRaises(KeyError):
            save(self.store, "other-app", OWNER, self.document)
