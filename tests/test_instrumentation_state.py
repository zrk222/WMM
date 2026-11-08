"""Instrumentation lifecycle: download, owner attestation and live probe stay distinct."""
from pathlib import Path
import json
import tempfile
import unittest
from mission_control.common import Invalid, canonical, digest, now
from mission_control.db import connection
from mission_control.instrumentation_state import record_download, record_installed, record_probe, readout
from mission_control.store import Store

APP = "sample-one"
EXP = "experiment-one"
PROPOSAL = "a" * 64
BUNDLE = "b" * 64


class InstrumentationLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.store = Store(Path(self.folder.name) / "test.sqlite", seed=False)
        for app in (APP, "sample-two"):
            self.store.save_app(app, dict(name="Synthetic " + app, release="build-1", job="Synthetic job",
                                         audience="Synthetic audience", activation="Synthetic value", locale="en-US"))
            with connection(self.store.path) as db:
                db.execute("INSERT INTO experiments VALUES(?,?,?,?,?,?,?,?)",
                           (app, EXP, canonical({}), digest({}), "PLANNED", 1, now(), now()))

    def download(self):
        return record_download(self.store, APP, EXP, PROPOSAL, BUNDLE)

    def install(self, downloaded):
        return record_installed(self.store, APP, EXP, dict(
            proposal_hash=PROPOSAL, downloaded_id=downloaded["id"], downloaded_hash=downloaded["hash"],
            release="build-1", install_reference="commit-abc123", reported_at=now()))

    def probe(self, installed):
        return record_probe(self.store, APP, EXP, dict(
            previous_id=installed["id"], previous_hash=installed["hash"], provider="POSTHOG",
            event_id="evt_001", observed_at=now(), scope="build-1 en-US activation surface",
            source_receipt_sha256="c" * 64, release="build-1"))

    def test_download_is_idempotent_and_never_means_installed(self):
        first, second = self.download(), self.download()
        self.assertEqual(first["id"], second["id"])
        value = readout(self.store, APP, EXP)[0]
        self.assertEqual(value["latest_state"], "DOWNLOADED")
        self.assertEqual([item["state"] for item in value["states"]],
                         ["DOWNLOADED", "REPORTED_INSTALLED", "PROBE_OBSERVED"])
        self.assertTrue(value["states"][0]["observed"])
        self.assertFalse(value["states"][1]["observed"])
        self.assertFalse(value["states"][2]["observed"])
        self.assertIn("Report installation", " ".join(value["next_actions"]))
        self.assertIn("not installation", value["boundary"])

    def test_attestation_and_probe_are_ordered_idempotent_and_exact(self):
        downloaded = self.download()
        install_body = dict(proposal_hash=PROPOSAL, downloaded_id=downloaded["id"],
                            downloaded_hash=downloaded["hash"], release="build-1",
                            install_reference="commit-abc123", reported_at=now())
        installed = record_installed(self.store, APP, EXP, install_body)
        self.assertEqual(record_installed(self.store, APP, EXP, install_body)["id"], installed["id"])
        self.assertEqual(installed["data"]["report"], "OWNER_ATTESTED_NOT_VERIFIED_DELIVERY")
        probe_body = dict(previous_id=installed["id"], previous_hash=installed["hash"], provider="POSTHOG",
                          event_id="evt_001", observed_at=now(), scope="build-1 en-US activation surface",
                          source_receipt_sha256="c" * 64, release="build-1")
        probed = record_probe(self.store, APP, EXP, probe_body)
        self.assertEqual(record_probe(self.store, APP, EXP, probe_body)["id"], probed["id"])
        self.assertEqual(probed["data"]["report"], "OWNER_REPORTED_LIVE_PROBE_NOT_INDEPENDENTLY_VERIFIED")
        value = readout(self.store, APP, EXP)[0]
        self.assertEqual(value["latest_state"], "PROBE_OBSERVED")
        self.assertTrue(all(item["observed"] for item in value["states"]))
        receipt = value["receipts"][-1]
        self.assertEqual((receipt["provider"], receipt["event_id"]), ("POSTHOG", "evt_001"))
        self.assertEqual(receipt["scope"], "build-1 en-US activation surface")
        self.assertEqual(receipt["source_receipt_sha256"], "c" * 64)
        self.assertNotIn("PRIVATE", canonical(value))

    def test_invalid_order_release_scope_and_identities_are_rejected(self):
        downloaded = self.download()
        with self.assertRaises(Invalid):
            record_installed(self.store, APP, EXP, dict(
                proposal_hash=PROPOSAL, downloaded_id=downloaded["id"], downloaded_hash=downloaded["hash"],
                release="old-build", install_reference="commit", reported_at=now()))
        with self.assertRaises(Invalid):
            record_installed(self.store, APP, EXP, dict(
                proposal_hash=PROPOSAL, downloaded_id=downloaded["id"], downloaded_hash=downloaded["hash"],
                release="build-1", install_reference="commit", reported_at="2020-01-01T00:00:00+00:00"))
        with self.assertRaises(Invalid):
            record_installed(self.store, APP, EXP, dict(
                proposal_hash=PROPOSAL, downloaded_id=downloaded["id"], downloaded_hash=downloaded["hash"],
                release="build-1", install_reference="commit", reported_at=now(), extra=""))
        with self.assertRaises(Invalid):
            self.probe(downloaded)
        installed = self.install(downloaded)
        base = dict(previous_id=installed["id"], previous_hash=installed["hash"], provider="POSTHOG",
                    event_id="evt_001", observed_at=now(), scope="build-1", source_receipt_sha256="c" * 64,
                    release="build-1")
        for changed in (dict(provider="posthog"), dict(event_id="event with spaces"),
                        dict(source_receipt_sha256="C" * 64), dict(observed_at="2020-01-01T00:00:00+00:00"),
                        dict(release="old-build")):
            with self.subTest(changed=changed), self.assertRaises(Invalid):
                record_probe(self.store, APP, EXP, dict(base, **changed))

    def test_receipts_are_app_scoped_and_readout_is_bounded(self):
        downloaded = self.download()
        with self.assertRaises(Invalid):
            record_installed(self.store, "sample-two", EXP, dict(
                proposal_hash=PROPOSAL, downloaded_id=downloaded["id"], downloaded_hash=downloaded["hash"],
                release="build-1", install_reference="commit", reported_at=now()))
        self.assertEqual(readout(self.store, APP, "missing"), [])
        self.assertEqual(readout(self.store, "sample-two"), [])


if __name__ == "__main__":
    unittest.main()
