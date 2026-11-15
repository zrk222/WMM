"""Instrumentation lifecycle: download, owner attestation and live probe stay distinct."""

from pathlib import Path
import json
import tempfile
import unittest
from mission_control.common import Invalid, canonical, digest, now
from mission_control.db import connection
from mission_control.instrumentation_state import record_download, record_installed, record_probe, readout
from mission_control.store import Store
from mission_control.review_access import Access
from mission_control.operator_client import ClientError, OperatorClient
from tests.test_agent_grants import GrantTests

APP = "sample-one"
EXP = "experiment-one"
PROPOSAL = "a" * 64
BUNDLE = "b" * 64
OWNER = {"principal": "github:owner", "login": "owner"}


class InstrumentationLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.store = Store(Path(self.folder.name) / "test.sqlite", seed=False)
        for app in (APP, "sample-two"):
            self.store.save_app(
                app,
                dict(
                    name="Synthetic " + app,
                    release="build-1",
                    job="Synthetic job",
                    audience="Synthetic audience",
                    activation="Synthetic value",
                    locale="en-US",
                ),
            )
            with connection(self.store.path) as db:
                db.execute(
                    "INSERT INTO experiments VALUES(?,?,?,?,?,?,?,?)",
                    (app, EXP, canonical({}), digest({}), "PLANNED", 1, now(), now()),
                )

        Access(self.store).bootstrap(APP, OWNER, {"confirm_owner": True})

    def download(self):
        return record_download(self.store, APP, EXP, PROPOSAL, BUNDLE)

    def install(self, downloaded):
        return record_installed(
            self.store,
            APP,
            EXP,
            dict(
                proposal_hash=PROPOSAL,
                downloaded_id=downloaded["id"],
                downloaded_hash=downloaded["hash"],
                release="build-1",
                install_reference="commit-abc123",
                reported_at=now(),
            ),
            user=OWNER,
        )

    def probe(self, installed):
        return record_probe(
            self.store,
            APP,
            EXP,
            dict(
                previous_id=installed["id"],
                previous_hash=installed["hash"],
                provider="POSTHOG",
                event_id="evt_001",
                observed_at=now(),
                scope="build-1 en-US activation surface",
                source_receipt_sha256="c" * 64,
                release="build-1",
            ),
            user=OWNER,
        )

    def test_download_is_idempotent_and_never_means_installed(self):
        first, second = self.download(), self.download()
        self.assertEqual(first["id"], second["id"])
        value = readout(self.store, APP, EXP)[0]
        self.assertEqual(value["latest_state"], "DOWNLOADED")
        self.assertEqual(
            [item["state"] for item in value["states"]], ["DOWNLOADED", "REPORTED_INSTALLED", "PROBE_OBSERVED"]
        )
        self.assertTrue(value["states"][0]["observed"])
        self.assertFalse(value["states"][1]["observed"])
        self.assertFalse(value["states"][2]["observed"])
        self.assertIn("Report installation", " ".join(value["next_actions"]))
        self.assertIn("not installation", value["boundary"])

    def test_attestation_and_probe_are_ordered_idempotent_and_exact(self):
        downloaded = self.download()
        install_body = dict(
            proposal_hash=PROPOSAL,
            downloaded_id=downloaded["id"],
            downloaded_hash=downloaded["hash"],
            release="build-1",
            install_reference="commit-abc123",
            reported_at=now(),
        )
        installed = record_installed(self.store, APP, EXP, install_body, user=OWNER)
        self.assertEqual(record_installed(self.store, APP, EXP, install_body, user=OWNER)["id"], installed["id"])
        self.assertEqual(installed["data"]["report"], "OWNER_ATTESTED_NOT_VERIFIED_DELIVERY")
        probe_body = dict(
            previous_id=installed["id"],
            previous_hash=installed["hash"],
            provider="POSTHOG",
            event_id="evt_001",
            observed_at=now(),
            scope="build-1 en-US activation surface",
            source_receipt_sha256="c" * 64,
            release="build-1",
        )
        probed = record_probe(self.store, APP, EXP, probe_body, user=OWNER)
        self.assertEqual(record_probe(self.store, APP, EXP, probe_body, user=OWNER)["id"], probed["id"])
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
            record_installed(
                self.store,
                APP,
                EXP,
                dict(
                    proposal_hash=PROPOSAL,
                    downloaded_id=downloaded["id"],
                    downloaded_hash=downloaded["hash"],
                    release="old-build",
                    install_reference="commit",
                    reported_at=now(),
                ),
                user=OWNER,
            )
        with self.assertRaises(Invalid):
            record_installed(
                self.store,
                APP,
                EXP,
                dict(
                    proposal_hash=PROPOSAL,
                    downloaded_id=downloaded["id"],
                    downloaded_hash=downloaded["hash"],
                    release="build-1",
                    install_reference="commit",
                    reported_at="2020-01-01T00:00:00+00:00",
                ),
                user=OWNER,
            )
        with self.assertRaises(Invalid):
            record_installed(
                self.store,
                APP,
                EXP,
                dict(
                    proposal_hash=PROPOSAL,
                    downloaded_id=downloaded["id"],
                    downloaded_hash=downloaded["hash"],
                    release="build-1",
                    install_reference="commit",
                    reported_at=now(),
                    extra="",
                ),
                user=OWNER,
            )
        with self.assertRaises(Invalid):
            self.probe(downloaded)
        installed = self.install(downloaded)
        base = dict(
            previous_id=installed["id"],
            previous_hash=installed["hash"],
            provider="POSTHOG",
            event_id="evt_001",
            observed_at=now(),
            scope="build-1",
            source_receipt_sha256="c" * 64,
            release="build-1",
        )
        for changed in (
            dict(provider="posthog"),
            dict(event_id="event with spaces"),
            dict(source_receipt_sha256="C" * 64),
            dict(observed_at="2020-01-01T00:00:00+00:00"),
            dict(release="old-build"),
        ):
            with self.subTest(changed=changed), self.assertRaises(Invalid):
                record_probe(self.store, APP, EXP, dict(base, **changed), user=OWNER)

    def test_old_release_and_legacy_attestation_cannot_advance_probe(self):
        downloaded = self.download()
        installed = self.install(downloaded)
        app = self.store.app(APP)
        self.store.save_app(APP, dict(app["data"], release="build-2"), app["version"])
        probe = dict(
            previous_id=installed["id"],
            previous_hash=installed["hash"],
            provider="POSTHOG",
            event_id="evt_001",
            observed_at=now(),
            scope="build-2",
            source_receipt_sha256="c" * 64,
            release="build-2",
        )
        with self.assertRaisesRegex(Invalid, "this release"):
            record_probe(self.store, APP, EXP, probe, user=OWNER)
        legacy = dict(installed["data"], release="build-2")
        legacy.pop("owner_attestation")
        old_hash = digest(legacy)
        with connection(self.store.path) as db:
            db.execute(
                "UPDATE instrumentation_receipts SET data=?,hash=? WHERE id=?",
                (canonical(legacy), old_hash, installed["id"]),
            )
        with self.assertRaisesRegex(Invalid, "verified app owner"):
            record_probe(self.store, APP, EXP, dict(probe, previous_hash=old_hash), user=OWNER)
        state = readout(self.store, APP, EXP)[0]
        self.assertEqual((state["latest_state"], state["legacy_unverified_receipts"]), ("DOWNLOADED", 1))

    def test_current_bundle_and_latest_installation_form_one_exact_chain(self):
        first = self.download()
        prior = self.install(first)
        self.probe(prior)
        second = record_download(self.store, APP, EXP, PROPOSAL, "d" * 64)
        with self.assertRaisesRegex(Invalid, "most recently downloaded"):
            self.install(first)
        self.assertEqual(readout(self.store, APP, EXP)[0]["bundle_hash"], second["bundle_hash"])
        installed = self.install(second)
        self.probe(installed)
        new_install = self.install(second)
        with self.assertRaisesRegex(Invalid, "current bundle and installation"):
            self.probe(installed)
        read = readout(self.store, APP, EXP)[0]
        self.assertEqual(read["latest_state"], "REPORTED_INSTALLED")
        self.assertEqual([row["id"] for row in read["receipts"]], [second["id"], new_install["id"]])

    def test_signed_out_http_cannot_attest_and_owner_receipt_binds_actor(self):
        fx = GrantTests("test_owner_issues_once_hash_only_persistence_and_snapshot_no_authority")
        fx.setUp()
        self.addCleanup(fx.tearDown)
        with connection(fx.store.path) as db:
            db.execute(
                "INSERT INTO experiments VALUES(?,?,?,?,?,?,?,?)",
                (APP, EXP, canonical({}), digest({}), "PLANNED", 1, now(), now()),
            )
        previous = record_download(fx.store, APP, EXP, PROPOSAL, BUNDLE)
        app = fx.store.app(APP)
        payload = dict(
            state="REPORTED_INSTALLED",
            proposal_hash=PROPOSAL,
            downloaded_id=previous["id"],
            downloaded_hash=previous["hash"],
            release=app["data"]["release"],
            install_reference="commit-abc123",
            reported_at=now(),
        )
        route = f"/api/apps/{APP}/experiment-tracking/{EXP}/lifecycle"
        signed_out = OperatorClient(fx.origin)
        signed_out.bootstrap()
        with self.assertRaises(ClientError):
            signed_out.request("POST", route, payload)
        self.assertEqual(readout(fx.store, APP, EXP)[0]["latest_state"], "DOWNLOADED")
        receipt = fx.owner.request("POST", route, payload)
        self.assertTrue(receipt["data"]["owner_attestation"]["principal"].startswith("github:"))
        self.assertEqual(readout(fx.store, APP, EXP)[0]["latest_state"], "REPORTED_INSTALLED")

    def test_receipts_are_app_scoped_and_readout_is_bounded(self):
        downloaded = self.download()
        with self.assertRaises(PermissionError):
            record_installed(
                self.store,
                "sample-two",
                EXP,
                dict(
                    proposal_hash=PROPOSAL,
                    downloaded_id=downloaded["id"],
                    downloaded_hash=downloaded["hash"],
                    release="build-1",
                    install_reference="commit",
                    reported_at=now(),
                ),
                user=OWNER,
            )
        self.assertEqual(readout(self.store, APP, "missing"), [])
        self.assertEqual(readout(self.store, "sample-two"), [])


if __name__ == "__main__":
    unittest.main()
