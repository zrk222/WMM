"""Synthetic Apple boundary; real adapter/state transitions, never live provider writes."""
import copy
from io import BytesIO
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from mission_control.common import Invalid, canonical, digest
from mission_control.db import connection
from mission_control.store import Store
from mission_control.provider_outbox import Outbox
from mission_control import store_actions
from tests.test_verified_review import fixture, OWNER, CHECKER, STRANGER

APP = "review-test"


class SyntheticApple:
    """Only tests construct this provider. Production uses the fixed HTTPS transport."""
    def __init__(self):
        self.text = "Previous synthetic copy"; self.writes = 0; self.fail_write = False; self.fail_read = False
        self.app = "12345"; self.release = "1"; self.locale = "en-US"

    def __call__(self, binding, app_id, path, method="GET", body=None):
        store_actions.destination(path, method, body)
        if method == "PATCH":
            self.writes += 1; self.text = body["data"]["attributes"]["promotionalText"]
            if self.fail_write: raise Invalid("Synthetic lost response after applying change")
        elif self.fail_read:
            raise Invalid("Synthetic provider read unavailable")
        if path.endswith("/appStoreVersionLocalizations?limit=200"):
            return {"data": [{"type": "appStoreVersionLocalizations", "id": "LOC-1", "attributes": {"locale": self.locale}}]}
        if path.startswith("/v1/apps/"):
            return {"data": [{"type": "appStoreVersions", "id": "VERSION-1", "attributes": {"versionString": self.release, "platform": "IOS"}}]}
        if "appStoreVersionLocalizations" in path:
            return {"data": {"type": "appStoreVersionLocalizations", "id": "LOC-1", "attributes": {"locale": self.locale, "promotionalText": self.text}, "relationships": {"appStoreVersion": {"data": {"type": "appStoreVersions", "id": "VERSION-1"}}}}}
        return {"data": {"type": "appStoreVersions", "id": "VERSION-1", "attributes": {"versionString": self.release, "platform": "IOS"}, "relationships": {"app": {"data": {"type": "apps", "id": self.app}}}}}


def outbox_fixture(store, app=APP):
    record = fixture(store, app)
    record = store.save_record(app, {"id": record["id"], "version": record["version"], "kind": "store", "title": "Exact synthetic promotional copy", "source": "Synthetic test only", "data": {"release": "1", "locale": "en-US", "promotional_text": "Test the actual app before choosing a plan.", "destination": "https://apps.apple.com/app/id12345", "availability": "Synthetic test only", "checked_at": "2026-10-11T12:00:00+00:00"}})
    conn = store.save_record(app, {"kind": "connection", "title": "Synthetic Apple connection", "source": "Synthetic test only", "data": {"provider": "app_store", "store_app_id": "12345", "account_id": "0", "env_ref": "GROWTH_"+app.upper().replace("-", "_")+"_APPLE"}})
    return {"record_id": record["id"], "connection_id": conn["id"], "localization_id": "LOC-1"}


class ProviderOutboxTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.store = Store(Path(self.tmp.name)/"state.sqlite", seed=False)
        self.data = outbox_fixture(self.store); self.outbox = Outbox(self.store); self.remote = SyntheticApple()
        self.network = patch("mission_control.store_actions.request", side_effect=self.remote); self.network.start()

    def tearDown(self): self.network.stop(); self.tmp.cleanup()

    def prepared(self): return self.outbox.prepare(APP, OWNER, self.data)

    def approved(self):
        row = self.prepared()
        return self.outbox.approve(APP, row["id"], CHECKER, {"hash": row["hash"], "confirm_provider_change": True})

    def send(self, row): return self.outbox.execute(APP, row["id"], OWNER, {"hash": row["hash"], "confirm_send": True})

    def test_scoped_transport_bounds_payload_and_secret_redaction(self):
        self.network.stop()
        body = {"data": {"type": "appStoreVersionLocalizations", "id": "LOC-1", "attributes": {"promotionalText": "Exact approved copy"}}}
        binding = {"provider": "app_store"}
        with patch("mission_control.store_actions.credential", return_value="synthetic-secret-token"), patch("mission_control.store_actions.build_opener") as opener:
            response = opener.return_value.open.return_value.__enter__.return_value
            response.read.return_value = b'{"data":{}}'
            self.assertEqual(store_actions.request(binding, APP, "/v1/appStoreVersionLocalizations/LOC-1", "PATCH", body), {"data": {}})
            req = opener.return_value.open.call_args.args[0]
            self.assertEqual(req.full_url, store_actions.HOST+"/v1/appStoreVersionLocalizations/LOC-1")
            self.assertEqual(req.get_method(), "PATCH"); self.assertEqual(json.loads(req.data), body)
            self.assertEqual(opener.return_value.open.call_args.kwargs["timeout"], 15); response.read.assert_called_once_with(262145)
            for method, path, data in [("DELETE", "/v1/apps/12345", None), ("PATCH", "https://evil.test/x", body), ("PATCH", "/v1/appStoreVersionLocalizations/LOC-1?include=appStoreVersion", body), ("PATCH", "/v1/appStoreVersionLocalizations/OTHER", body), ("PATCH", "/v1/appStoreVersionLocalizations/LOC-1", {"data": {**body["data"], "attributes": {"keywords": "not authorized"}}})]:
                count = opener.return_value.open.call_count
                with self.assertRaises(Invalid): store_actions.request(binding, APP, path, method, data)
                self.assertEqual(opener.return_value.open.call_count, count)
            for bad in (b"x"*262145, b"not-json", b"[]", b'{"errors":[{"detail":"secret"}]}'):
                response.read.return_value = bad
                with self.assertRaises(Invalid) as caught: store_actions.request(binding, APP, "/v1/appStoreVersions/VERSION-1?include=app")
                self.assertNotIn("secret", str(caught.exception))
            opener.return_value.open.side_effect = HTTPError("https://private", 403, "synthetic-secret-token", {}, BytesIO(b"synthetic-secret-token"))
            with self.assertRaises(Invalid) as caught: store_actions.request(binding, APP, "/v1/appStoreVersions/VERSION-1?include=app")
            self.assertNotIn("synthetic-secret-token", str(caught.exception))
        for value in ("../path", "LOC?token=secret", "", "x"*101):
            with self.assertRaises(Invalid): store_actions.opaque(value)
        for value in ("x"*171, "hidden\ncopy", "bad\ud800"):
            with self.assertRaises(Invalid): store_actions.copy_text(value)
        with self.assertRaises(Invalid): store_actions.resource({"data": []}, "apps", "1")
        with self.assertRaises(Invalid): store_actions.relationship({}, "app", "apps")

    def test_exact_independent_approval_send_and_immutable_receipts(self):
        row = self.prepared(); self.assertEqual(row["status"], "WAITING_APPROVAL"); self.assertEqual(self.remote.writes, 0)
        approve = {"hash": row["hash"], "confirm_provider_change": True}
        for user, body in ((OWNER, approve), (STRANGER, approve), (CHECKER, dict(approve, hash="changed")), (CHECKER, dict(approve, confirm_provider_change=1))):
            with self.assertRaises((Invalid, PermissionError)): self.outbox.approve(APP, row["id"], user, body)
        row = self.outbox.approve(APP, row["id"], CHECKER, approve)
        with self.assertRaises(Invalid): self.outbox.approve(APP, row["id"], CHECKER, approve)
        with self.assertRaises(Invalid): self.outbox.execute(APP, row["id"], CHECKER, {"hash": row["hash"], "confirm_send": True})
        done = self.send(row); self.assertEqual(done["status"], "VERIFIED_APPLIED"); self.assertEqual(done["dispatches"], 1); self.assertEqual(self.remote.writes, 1)
        self.assertEqual(done["events"][-1]["data"]["detail"]["attribution"], "ACKNOWLEDGED_WRITE")
        self.assertEqual(done["events"][-1]["data"]["detail"]["public_availability"], "NOT_VERIFIED")
        for receipt in done["events"]: self.assertEqual(receipt["hash"], digest(receipt["data"]))
        with self.assertRaises(Invalid): self.send(row)
        with self.assertRaises(Invalid): self.outbox.cancel(APP, row["id"], OWNER, {})
        self.assertEqual(self.remote.writes, 1)
        self.assertEqual(Outbox(Store(self.store.path, seed=False)).list(APP)[0]["status"], "VERIFIED_APPLIED")

    def test_wrong_provider_scope_and_changed_remote_baseline_never_write(self):
        self.assertEqual(self.outbox.destination(APP, OWNER, {k: self.data[k] for k in ("record_id", "connection_id")})["localization_id"], "LOC-1")
        with self.assertRaises(Invalid): store_actions.select({"data": []}, "appStoreVersions", {"versionString": "1"})
        with self.assertRaises(Invalid): store_actions.select({"data": [{}]*201}, "appStoreVersions", {})
        for attribute, value in (("app", "99999"), ("release", "other"), ("locale", "he")):
            old = getattr(self.remote, attribute); setattr(self.remote, attribute, value)
            with self.assertRaises(Invalid): self.prepared()
            setattr(self.remote, attribute, old)
        row = self.approved(); self.remote.text = "Another administrator's change"
        self.assertEqual(self.send(row)["status"], "BASELINE_CHANGED"); self.assertEqual(self.remote.writes, 0)
        row = self.approved(); self.remote.text = row["packet"]["after"]["promotional_text"]
        self.assertEqual(self.send(row)["status"], "ALREADY_DESIRED"); self.assertEqual(self.remote.writes, 0)
        self.store.save_app("other", {"name": "Other app"})
        with self.assertRaises(Invalid): self.outbox.execute("other", row["id"], OWNER, {"hash": row["hash"], "confirm_send": True})

    def test_exact_source_role_expiry_and_preflight_changes_reject(self):
        row = self.approved()
        with connection(self.store.path) as db: db.execute("UPDATE records SET title='Changed title' WHERE id=?", (self.data["record_id"],))
        with self.assertRaises(Invalid): self.send(row)
        row = self.approved()
        with connection(self.store.path) as db: db.execute("UPDATE operator_roles SET version=version+1 WHERE principal=?", (CHECKER["principal"],))
        with self.assertRaises(Invalid): self.send(row)
        row = self.approved()
        with connection(self.store.path) as db: db.execute("UPDATE provider_actions SET expires='2000-01-01T00:00:00+00:00' WHERE id=?", (row["id"],))
        with self.assertRaises(Invalid): self.send(row)
        row = self.approved()
        original = self.remote.__call__
        def changed_during_read(*args, **kwargs):
            with connection(self.store.path) as db: db.execute("UPDATE apps SET version=version+1 WHERE id=?", (APP,))
            return original(*args, **kwargs)
        with patch("mission_control.store_actions.request", side_effect=changed_during_read):
            with self.assertRaises(Invalid): self.send(row)
        self.assertEqual(self.remote.writes, 0)

    def test_lost_applied_response_is_observed_without_resend(self):
        row = self.approved(); self.remote.fail_write = True
        done = self.send(row)
        self.assertEqual(done["status"], "VERIFIED_APPLIED"); self.assertEqual(self.remote.writes, 1)
        self.assertEqual(done["events"][-1]["data"]["detail"]["attribution"], "UNPROVEN")

    def test_crash_expired_lease_and_read_failure_reconcile_without_new_write(self):
        row = self.approved()
        def interrupted(*args):
            self.remote.text = row["packet"]["after"]["promotional_text"]; self.remote.writes += 1
            raise SystemExit("Synthetic process interruption after remote apply")
        with patch("mission_control.store_actions.apply", side_effect=interrupted):
            with self.assertRaises(SystemExit): self.send(row)
        with self.assertRaises(Invalid): self.outbox.reconcile(APP, row["id"], CHECKER, {})
        with connection(self.store.path) as db: db.execute("UPDATE provider_actions SET lease=0 WHERE id=?", (row["id"],))
        self.remote.fail_read = True
        unknown = self.outbox.reconcile(APP, row["id"], CHECKER, {})
        self.assertEqual(unknown["status"], "NEEDS_RECONCILIATION")
        self.assertEqual(unknown["events"][-1]["data"]["detail"]["outcome"], "READ_UNAVAILABLE")
        with self.assertRaises(Invalid): self.send(row)
        self.remote.fail_read = False
        with connection(self.store.path) as db: db.execute("UPDATE provider_actions SET expires='2000-01-01T00:00:00+00:00' WHERE id=?", (row["id"],))
        done = self.outbox.reconcile(APP, row["id"], CHECKER, {})
        self.assertEqual(done["status"], "VERIFIED_APPLIED"); self.assertEqual(done["availability"], "UNAVAILABLE"); self.assertEqual(self.remote.writes, 1)

    def test_concurrent_dispatch_and_stale_outcome_owner_are_rejected(self):
        row = self.approved(); gate = threading.Event(); started = threading.Event(); results = []
        original = store_actions.apply
        def slow(*args): started.set(); gate.wait(5); return original(*args)
        with patch("mission_control.store_actions.apply", side_effect=slow):
            thread = threading.Thread(target=lambda: results.append(self.send(row))); thread.start(); self.assertTrue(started.wait(5))
            with self.assertRaises(Invalid): self.send(row)
            with self.assertRaises(Invalid): self.outbox.reconcile(APP, row["id"], CHECKER, {})
            gate.set(); thread.join(10); self.assertFalse(thread.is_alive())
        self.assertEqual(self.remote.writes, 1); self.assertEqual(results[0]["status"], "VERIFIED_APPLIED")
        with connection(self.store.path) as db:
            db.execute("UPDATE provider_actions SET status='DISPATCHING',owner='new-reconciliation-owner' WHERE id=?", (row["id"],))
        with self.assertRaises(Invalid): self.outbox.readback(APP, row["id"], row["packet"], row["packet"]["connection"], "expired-owner")

    def test_same_destination_exclusion_and_unapplied_uncertain_result(self):
        first = self.approved(); second = self.approved(); started = threading.Event(); gate = threading.Event(); done = []
        original = store_actions.apply
        def slow(*args): started.set(); gate.wait(5); return original(*args)
        with patch("mission_control.store_actions.apply", side_effect=slow):
            thread = threading.Thread(target=lambda: done.append(self.send(first))); thread.start(); self.assertTrue(started.wait(5))
            with self.assertRaises(Invalid): self.send(second)
            gate.set(); thread.join(10); self.assertFalse(thread.is_alive())
        self.assertEqual(done[0]["status"], "VERIFIED_APPLIED"); self.assertEqual(self.send(second)["status"], "ALREADY_DESIRED")
        self.remote.text = "New baseline for failed attempt"; row = self.approved()
        with patch("mission_control.store_actions.apply", side_effect=Invalid("Synthetic failure before remote apply")):
            result = self.send(row)
        self.assertEqual(result["status"], "NEEDS_RECONCILIATION")
        self.assertEqual(result["events"][-1]["data"]["detail"]["outcome"], "OBSERVED_BASELINE")
        self.remote.text = "Different remote change"; result = self.outbox.reconcile(APP, row["id"], CHECKER, {})
        self.assertEqual(result["events"][-1]["data"]["detail"]["outcome"], "OBSERVED_DIFFERENT")
        with self.assertRaises(Invalid): self.send(row)
        self.assertEqual(self.remote.writes, 1)

    def test_cancellation_and_snapshot_cannot_transfer_write_authority(self):
        row = self.approved()
        with self.assertRaises(PermissionError): self.outbox.cancel(APP, row["id"], STRANGER, {})
        self.assertEqual(self.outbox.cancel(APP, row["id"], OWNER, {})["status"], "CANCELLED")
        with self.assertRaises(Invalid): self.send(row)
        snapshot = self.store.export(APP)
        self.assertNotIn("provider_actions", snapshot); self.assertNotIn("operator_roles", snapshot)
        fresh = Store(Path(self.tmp.name)/"fresh.sqlite", seed=False); fresh.restore(snapshot)
        self.assertEqual(Outbox(fresh).list(APP), []); self.assertEqual(self.remote.writes, 0)
