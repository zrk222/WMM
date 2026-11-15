"""Synthetic owner, SQLite and native-vault setup contract; no live provider."""

import json
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4
from mission_control.common import Invalid, now
from mission_control.db import connection
from mission_control.operation_authority import bound_owner, protected
from mission_control.onesignal_setup import OneSignalSetup, SCHEMA
from mission_control.store import Store
from tests.test_measurement_connectors import FakeVault
from tests.test_onesignal_transport import APP, ORG, KEY


class Identity:
    def local(self, session, principal, generation=None):
        return {"session_generation": 1}


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.store = Store(Path(self.folder.name) / "synthetic.sqlite3")
        FakeVault.values = {}
        with connection(self.store.path) as db:
            db.executescript(SCHEMA)
            db.execute(
                "INSERT INTO operator_roles VALUES(?,?,?,?,?,?,?,?)",
                ("sample-one", "owner-1", "synthetic", "OWNER", "ACTIVE", 1, now(), "owner-1"),
            )
        self.provider = [{"id": APP, "name": "Synthetic", "organization_id": ORG, "apns_p8": "provider-private"}]
        self.calls = []
        self.fail = False
        self.setup = OneSignalSetup(self.store, FakeVault, self.transport)

    def transport(self, action, key, app_id=None, fields=None, alive=lambda: None):
        alive()
        self.calls.append(action)
        if self.fail and action in ("create", "update"):
            raise RuntimeError("PRIVATE_PROVIDER_ERROR")
        if action == "list":
            return self.provider
        if action == "view":
            return next(row for row in self.provider if row["id"] == app_id)
        if action == "create":
            row = {"id": APP, "name": fields["name"], "organization_id": fields["organization_id"]}
            self.provider.append(row)
            return row
        if action == "update":
            row = next(x for x in self.provider if x["id"] == app_id)
            row.update({k: v for k, v in fields.items() if k.startswith("apns_") and k != "apns_p8"})
            return row
        raise AssertionError(action)

    def invoke(self, method, action, body, app="sample-one", principal="owner-1"):
        env = {"app_id": app, "operation": "onesignal." + action, "input": body}
        user = {"principal": principal}
        with bound_owner(self.store, env, Identity(), "session", user):
            with protected(self.store, env):
                return method(app, **body)

    def save(self, kind="org", version=0):
        return self.invoke(self.setup.save_key, "save-key", {"kind": kind, "key": KEY, "version": version})

    def read(self, selected_id=None):
        return self.invoke(self.setup.read, "read", {"selected_id": selected_id})

    def bind(self):
        return self.invoke(
            self.setup.bind,
            "bind",
            {"provider_app_id": APP, "expected_name": "Synthetic", "expected_org": ORG, "version": 1},
        )

    def test_narrow_app_key_exact_readback_and_secret_redaction(self):
        self.save("app")
        rows = self.read(APP)
        self.assertEqual(self.calls, ["view"])
        self.assertNotIn("provider-private", json.dumps(rows))
        self.assertEqual(self.bind()["state"], "APP_BOUND")
        with connection(self.store.path) as db:
            durable = " ".join(
                str(tuple(r))
                for table in ("onesignal_connections", "onesignal_setup_effects", "onesignal_retirements")
                for r in db.execute("SELECT * FROM " + table)
            )
        self.assertNotIn(KEY, durable)
        self.assertNotIn("provider-private", durable)
        with self.assertRaises(PermissionError):
            self.invoke(self.setup.status, "status", {}, principal="other-owner")
        with self.assertRaises(PermissionError):
            self.setup.status("sample-one")

    def test_rotation_and_revoked_owner(self):
        self.save()
        before = set(FakeVault.values)
        self.save("app", 1)
        self.assertNotEqual(before, set(FakeVault.values))
        self.invoke(self.setup.cleanup, "cleanup", {})
        self.assertFalse(before & set(FakeVault.values))
        with connection(self.store.path) as db:
            db.execute("UPDATE operator_roles SET status='REVOKED',version=2 WHERE app_id='sample-one'")
        with self.assertRaises(PermissionError):
            self.read(APP)

    def test_ambiguous_and_mismatched_selection_are_denied(self):
        self.save()
        self.provider.append({"id": APP, "name": "Synthetic", "organization_id": ORG})
        with self.assertRaises(Invalid):
            self.bind()
        self.provider.pop()
        with self.assertRaises(Invalid):
            self.invoke(
                self.setup.bind,
                "bind",
                {"provider_app_id": APP, "expected_name": "Wrong", "expected_org": ORG, "version": 1},
            )
        with self.assertRaises(Invalid):
            self.invoke(
                self.setup.prepare,
                "prepare",
                {
                    "action": "create",
                    "details": {"name": "Synthetic", "organization_id": ORG},
                    "request_key": str(uuid4()),
                },
            )

    def test_unknown_create_is_reserved_and_never_automatically_replayed(self):
        self.save()
        self.provider = []
        body = {"action": "create", "details": {"name": "Fresh", "organization_id": ORG}, "request_key": str(uuid4())}
        prepared = self.invoke(self.setup.prepare, "prepare", body)
        args = {"effect_id": prepared["id"], "source_hash": prepared["source_hash"], "confirmed": True}
        self.fail = True
        result = self.invoke(self.setup.execute, "execute", args)
        self.assertEqual(result["status"], "UNKNOWN")
        before = list(self.calls)
        self.assertEqual(self.invoke(self.setup.execute, "execute", args)["status"], "UNKNOWN")
        self.assertEqual(before, self.calls)
        self.fail = False
        self.provider = [{"id": APP, "name": "Fresh", "organization_id": ORG}]
        reconciled = self.invoke(
            self.setup.reconcile,
            "reconcile",
            {
                "effect_id": prepared["id"],
                "provider_app_id": APP,
                "expected_name": "Fresh",
                "expected_org": ORG,
                "confirmed": True,
            },
        )
        self.assertEqual(reconciled["status"], "RECONCILED_APP_SELECTED")
        history = self.invoke(self.setup.history, "history", {})["effects"][0]
        self.assertEqual(history["status"], "UNKNOWN")
        self.assertEqual(history["recovery"], "RECOVERED_READBACK_ONLY")

    def test_selected_channel_update_keeps_credentials_private(self):
        self.save()
        self.bind()
        fields = {
            "apns_p8": "-----BEGIN PRIVATE KEY----- synthetic -----END PRIVATE KEY-----",
            "apns_key_id": "ABCDEFGHIJ",
            "apns_team_id": "KLMNOPQRST",
            "apns_bundle_id": "example.synthetic",
        }
        preview = self.invoke(
            self.setup.prepare, "prepare", {"action": "update", "details": fields, "request_key": str(uuid4())}
        )
        self.assertNotIn(fields["apns_p8"], json.dumps(preview))
        result = self.invoke(
            self.setup.execute,
            "execute",
            {"effect_id": preview["id"], "source_hash": preview["source_hash"], "confirmed": True},
        )
        self.assertEqual(result["status"], "SUCCEEDED")
        self.assertIn("APNS_CONFIGURED_UNVERIFIED", result["states"])
        self.assertEqual(result["device"], "DEVICE_SUBSCRIPTION_NOT_VERIFIED")

    def test_concurrent_create_has_only_one_provider_attempt(self):
        import concurrent.futures
        import threading

        self.save()
        self.provider = []
        first = self.invoke(
            self.setup.prepare,
            "prepare",
            {"action": "create", "details": {"name": "Fresh", "organization_id": ORG}, "request_key": str(uuid4())},
        )
        second = self.invoke(
            self.setup.prepare,
            "prepare",
            {"action": "create", "details": {"name": "Fresh", "organization_id": ORG}, "request_key": str(uuid4())},
        )
        entered = threading.Event()
        release = threading.Event()
        original = self.setup.transport

        def slow(action, *args, **kwargs):
            if action == "create":
                entered.set()
                release.wait(5)
            return original(action, *args, **kwargs)

        self.setup.transport = slow

        def execute(preview):
            try:
                return self.invoke(
                    self.setup.execute,
                    "execute",
                    {"effect_id": preview["id"], "source_hash": preview["source_hash"], "confirmed": True},
                )
            except Invalid:
                return {"status": "DENIED"}

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            one = pool.submit(execute, first)
            self.assertTrue(entered.wait(5))
            other = pool.submit(execute, second)
            result = other.result(timeout=5)
            release.set()
            winner = one.result(timeout=5)
        self.assertEqual(result["status"], "DENIED")
        self.assertEqual(winner["status"], "SUCCEEDED")
        self.assertEqual(self.calls.count("create"), 1)

    def test_readback_mismatch_is_unknown_and_preserves_effect(self):
        self.save()
        self.provider = []
        preview = self.invoke(
            self.setup.prepare,
            "prepare",
            {"action": "create", "details": {"name": "Fresh", "organization_id": ORG}, "request_key": str(uuid4())},
        )
        original = self.setup.transport

        def wrong(action, *args, **kwargs):
            result = original(action, *args, **kwargs)
            if action == "create":
                result = dict(result, organization_id="33333333-3333-4333-8333-333333333333")
            return result

        self.setup.transport = wrong
        result = self.invoke(
            self.setup.execute,
            "execute",
            {"effect_id": preview["id"], "source_hash": preview["source_hash"], "confirmed": True},
        )
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertEqual(self.calls.count("create"), 1)

    def test_changed_provider_readback_never_claims_binding(self):
        self.save()
        self.provider = []
        preview = self.invoke(
            self.setup.prepare,
            "prepare",
            {"action": "create", "details": {"name": "Fresh", "organization_id": ORG}, "request_key": str(uuid4())},
        )
        original = self.setup.transport
        created = [False]

        def changed(action, *args, **kwargs):
            result = original(action, *args, **kwargs)
            if action == "create":
                created[0] = True
            if action == "list" and created[0]:
                return [dict(item, name="Different") for item in result]
            return result

        self.setup.transport = changed
        result = self.invoke(
            self.setup.execute,
            "execute",
            {"effect_id": preview["id"], "source_hash": preview["source_hash"], "confirmed": True},
        )
        self.assertEqual(result["status"], "UNKNOWN")
        status = self.invoke(self.setup.status, "status", {})
        self.assertEqual(status["state"], "KEY_SAVED_UNBOUND")

    def test_changed_source_or_approval_hash_never_dispatches(self):
        self.save()
        self.provider = []
        preview = self.invoke(
            self.setup.prepare,
            "prepare",
            {"action": "create", "details": {"name": "Fresh", "organization_id": ORG}, "request_key": str(uuid4())},
        )
        args = {"effect_id": preview["id"], "source_hash": "0" * 64, "confirmed": True}
        with self.assertRaises(Invalid):
            self.invoke(self.setup.execute, "execute", args)
        app = self.store.app("sample-one")
        self.store.save_app("sample-one", {**app["data"], "job": "Changed"}, app["version"])
        args["source_hash"] = preview["source_hash"]
        with self.assertRaises(Invalid):
            self.invoke(self.setup.execute, "execute", args)
        self.assertNotIn("create", self.calls)

    def test_an_inflight_reservation_cannot_be_reconciled(self):
        self.save()
        self.provider = []
        preview = self.invoke(
            self.setup.prepare,
            "prepare",
            {"action": "create", "details": {"name": "Fresh", "organization_id": ORG}, "request_key": str(uuid4())},
        )
        with connection(self.store.path) as db:
            db.execute(
                "UPDATE onesignal_setup_effects SET status='RESERVED',updated=? WHERE id=?", (now(), preview["id"])
            )
        with self.assertRaisesRegex(Invalid, "still be running"):
            self.invoke(
                self.setup.reconcile,
                "reconcile",
                {
                    "effect_id": preview["id"],
                    "provider_app_id": APP,
                    "expected_name": "Fresh",
                    "expected_org": ORG,
                    "confirmed": True,
                },
            )

    def test_readback_recovery_survives_source_and_owner_drift_without_replaying(self):
        self.save()
        self.provider = []
        preview = self.invoke(
            self.setup.prepare,
            "prepare",
            {"action": "create", "details": {"name": "Fresh", "organization_id": ORG}, "request_key": str(uuid4())},
        )
        args = {"effect_id": preview["id"], "source_hash": preview["source_hash"], "confirmed": True}
        self.fail = True
        self.assertEqual(self.invoke(self.setup.execute, "execute", args)["status"], "UNKNOWN")
        self.fail = False
        app = self.store.app("sample-one")
        self.store.save_app("sample-one", {**app["data"], "job": "Changed"}, app["version"])
        with connection(self.store.path) as db:
            db.execute("UPDATE operator_roles SET version=version+1 WHERE app_id='sample-one'")
            db.execute("UPDATE onesignal_connections SET version=version+1 WHERE app_id='sample-one'")
        self.provider = [{"id": APP, "name": "Fresh", "organization_id": ORG}]
        body = {
            "effect_id": preview["id"],
            "provider_app_id": APP,
            "key_kind": "app",
            "key": "synthetic-recovery-key-123456",
        }
        proposal = self.invoke(self.setup.recovery_prepare, "recovery-prepare", body)
        self.assertNotIn(body["key"], json.dumps(proposal))
        calls = list(self.calls)
        result = self.invoke(
            self.setup.recovery_confirm,
            "recovery-confirm",
            {"recovery_id": proposal["id"], "source_hash": proposal["source_hash"], "confirmed": True},
        )
        self.assertEqual(result["status"], "RECOVERED_READBACK_ONLY")
        self.assertNotIn("create", self.calls[len(calls) :])
        history = self.invoke(self.setup.history, "history", {})["effects"][0]
        self.assertEqual((history["status"], history["recovery"]), ("UNKNOWN", "RECOVERED_READBACK_ONLY"))
        self.assertEqual(self.save("app", 2)["state"], "KEY_SAVED_UNBOUND")

    def test_recovery_review_rejects_changed_source_or_readback(self):
        self.save()
        self.provider = []
        preview = self.invoke(
            self.setup.prepare,
            "prepare",
            {"action": "create", "details": {"name": "Fresh", "organization_id": ORG}, "request_key": str(uuid4())},
        )
        self.fail = True
        self.invoke(
            self.setup.execute,
            "execute",
            {"effect_id": preview["id"], "source_hash": preview["source_hash"], "confirmed": True},
        )
        self.fail = False
        self.provider = [{"id": APP, "name": "Fresh", "organization_id": ORG}]
        body = {
            "effect_id": preview["id"],
            "provider_app_id": APP,
            "key_kind": "app",
            "key": "synthetic-recovery-key-123456",
        }
        review = self.invoke(self.setup.recovery_prepare, "recovery-prepare", body)
        approve = {"recovery_id": review["id"], "source_hash": review["source_hash"], "confirmed": True}
        with self.assertRaises(Invalid):
            self.invoke(self.setup.recovery_confirm, "recovery-confirm", {**approve, "source_hash": "0" * 64})
        self.provider[0]["name"] = "Changed"
        with self.assertRaises(Invalid):
            self.invoke(self.setup.recovery_confirm, "recovery-confirm", approve)
        self.provider[0]["name"] = "Fresh"
        app = self.store.app("sample-one")
        self.store.save_app("sample-one", {**app["data"], "job": "Changed"}, app["version"])
        with self.assertRaises(Invalid):
            self.invoke(self.setup.recovery_confirm, "recovery-confirm", approve)
        self.assertEqual(self.invoke(self.setup.history, "history", {})["effects"][0]["status"], "UNKNOWN")

    def test_recovery_provider_private_echo_is_rejected_without_recording_it(self):
        from unittest.mock import patch
        from mission_control.onesignal_transport import request

        self.save()
        self.provider = []
        preview = self.invoke(
            self.setup.prepare,
            "prepare",
            {"action": "create", "details": {"name": "Fresh", "organization_id": ORG}, "request_key": str(uuid4())},
        )
        self.fail = True
        self.invoke(
            self.setup.execute,
            "execute",
            {"effect_id": preview["id"], "source_hash": preview["source_hash"], "confirmed": True},
        )
        self.fail = False
        self.setup.transport = request
        secret = "synthetic-channel-secret"
        row = {"id": APP, "name": secret, "organization_id": ORG, "apns_p8": secret}
        for kind, response in [("app", row), ("org", [row])]:
            with (
                self.subTest(kind=kind),
                patch("mission_control.onesignal_transport.address", return_value="203.0.113.1"),
                patch("mission_control.onesignal_transport.trust_context"),
                patch("mission_control.onesignal_transport.PinnedHTTPS") as wire,
                patch("mission_control.onesignal_transport.response_headers"),
                patch("mission_control.onesignal_transport.response_body", return_value=json.dumps(response).encode()),
            ):
                wire.return_value.getresponse.return_value.status = 200
                with self.assertRaises(Invalid) as denied:
                    self.invoke(
                        self.setup.recovery_prepare,
                        "recovery-prepare",
                        {
                            "effect_id": preview["id"],
                            "provider_app_id": APP,
                            "key_kind": kind,
                            "key": "synthetic-recovery-key-123456",
                        },
                    )
                self.assertNotIn(secret, str(denied.exception))
        with connection(self.store.path) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM onesignal_recoveries").fetchone()[0], 0)
            self.assertEqual(
                db.execute("SELECT status FROM onesignal_setup_effects WHERE id=?", (preview["id"],)).fetchone()[0],
                "UNKNOWN",
            )

    def test_preflight_failure_is_recorded_as_not_sent(self):
        self.save()
        self.provider = []
        preview = self.invoke(
            self.setup.prepare,
            "prepare",
            {"action": "create", "details": {"name": "Fresh", "organization_id": ORG}, "request_key": str(uuid4())},
        )

        def failure(action, *args, **kwargs):
            raise RuntimeError("synthetic preflight failure")

        self.setup.transport = failure
        result = self.invoke(
            self.setup.execute,
            "execute",
            {"effect_id": preview["id"], "source_hash": preview["source_hash"], "confirmed": True},
        )
        self.assertEqual(result["status"], "BLOCKED_NOT_SENT")
        self.assertEqual(self.invoke(self.setup.history, "history", {})["effects"][0]["status"], "BLOCKED_NOT_SENT")

    def test_channel_encoding_limit_rejected_before_reservation(self):
        self.save()
        self.bind()
        cases = [
            {
                "apns_p8": "-----BEGIN PRIVATE KEY-----" + ("x" * 12300) + "-----END PRIVATE KEY-----",
                "apns_key_id": "ABCDEFGHIJ",
                "apns_team_id": "KLMNOPQRST",
                "apns_bundle_id": "example.synthetic",
            },
            {
                "fcm_v1_service_account_json": json.dumps(
                    {"type": "service_account", "private_key": "x" * 12300, "client_email": "synthetic@example.invalid"}
                )
            },
        ]
        for fields in cases:
            with self.subTest(fields=list(fields)), self.assertRaises(Invalid):
                self.invoke(
                    self.setup.prepare, "prepare", {"action": "update", "details": fields, "request_key": str(uuid4())}
                )
        self.assertEqual(self.invoke(self.setup.history, "history", {})["effects"], [])

    def test_private_stage_reference_cannot_change_after_review(self):
        self.save()
        self.bind()
        fields = {
            "apns_p8": "-----BEGIN PRIVATE KEY----- synthetic -----END PRIVATE KEY-----",
            "apns_key_id": "ABCDEFGHIJ",
            "apns_team_id": "KLMNOPQRST",
            "apns_bundle_id": "example.synthetic",
        }
        preview = self.invoke(
            self.setup.prepare, "prepare", {"action": "update", "details": fields, "request_key": str(uuid4())}
        )
        with connection(self.store.path) as db:
            db.execute("UPDATE onesignal_setup_effects SET secret_ref=? WHERE id=?", (str(uuid4()), preview["id"]))
        before = list(self.calls)
        with self.assertRaises(Invalid):
            self.invoke(
                self.setup.execute,
                "execute",
                {"effect_id": preview["id"], "source_hash": preview["source_hash"], "confirmed": True},
            )
        self.assertEqual(before, self.calls)

    def test_readback_private_echo_never_exits_setup(self):
        self.save()
        self.bind()
        secret = "-----BEGIN PRIVATE KEY----- synthetic -----END PRIVATE KEY-----"
        fields = {
            "apns_p8": secret,
            "apns_key_id": "ABCDEFGHIJ",
            "apns_team_id": "KLMNOPQRST",
            "apns_bundle_id": "example.synthetic",
        }
        preview = self.invoke(
            self.setup.prepare, "prepare", {"action": "update", "details": fields, "request_key": str(uuid4())}
        )
        original = self.setup.transport
        done = [False]

        def malicious(action, *args, **kwargs):
            result = original(action, *args, **kwargs)
            if action == "update":
                done[0] = True
            if action == "list" and done[0]:
                return [dict(item, name=secret) for item in result]
            return result

        self.setup.transport = malicious
        result = self.invoke(
            self.setup.execute,
            "execute",
            {"effect_id": preview["id"], "source_hash": preview["source_hash"], "confirmed": True},
        )
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertNotIn(secret, json.dumps(result))

    def test_fcm_readback_private_echo_never_exits_setup(self):
        self.save()
        self.bind()
        secret = json.dumps({"type": "service_account", "private_key": "synthetic", "client_email": "a@b"})
        preview = self.invoke(
            self.setup.prepare,
            "prepare",
            {"action": "update", "details": {"fcm_v1_service_account_json": secret}, "request_key": str(uuid4())},
        )
        original = self.setup.transport
        done = [False]

        def malicious(action, *args, **kwargs):
            result = original(action, *args, **kwargs)
            if action == "update":
                done[0] = True
            if action == "list" and done[0]:
                return [dict(item, name=secret) for item in result]
            return result

        self.setup.transport = malicious
        result = self.invoke(
            self.setup.execute,
            "execute",
            {"effect_id": preview["id"], "source_hash": preview["source_hash"], "confirmed": True},
        )
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertNotIn(secret, json.dumps(result))


if __name__ == "__main__":
    unittest.main()
