"""Synthetic wire tests; no account or network access."""

import json
import base64
import contextlib
import io
import unittest
from unittest.mock import patch
from mission_control.common import Invalid
from mission_control.onesignal_transport import request

APP = "11111111-1111-4111-8111-111111111111"
ORG = "22222222-2222-4222-8222-222222222222"
KEY = "synthetic-onesignal-key-123456"


class TransportTests(unittest.TestCase):
    def call(self, action, app=None, fields=None, status=200, response=None):
        result = (
            response
            if response is not None
            else {
                "id": APP,
                "name": "Synthetic",
                "organization_id": ORG,
                "apns_p8": "sensitive-p8",
                "fcm_v1_service_account_json": "sensitive-json",
            }
        )
        with (
            patch("mission_control.onesignal_transport.address", return_value="203.0.113.1"),
            patch("mission_control.onesignal_transport.trust_context"),
            patch("mission_control.onesignal_transport.PinnedHTTPS") as wire,
            patch("mission_control.onesignal_transport.response_headers"),
            patch("mission_control.onesignal_transport.response_body", return_value=json.dumps(result).encode()),
        ):
            wire.return_value.getresponse.return_value.status = status
            output = request(action, KEY, app, fields)
            return output, wire.return_value.request.call_args

    def test_read_paths_redact_provider_secrets(self):
        record = {"id": APP, "name": "Synthetic", "organization_id": ORG, "apns_p8": "sensitive-p8"}
        for action, app, response, path in [("view", APP, record, "/apps/" + APP), ("list", None, [record], "/apps")]:
            output, wire = self.call(action, app, response=response)
            self.assertNotIn("sensitive-p8", json.dumps(output))
            self.assertEqual(wire.args[:2], ("GET", path))
            self.assertEqual(wire.kwargs["headers"]["Authorization"], "Key " + KEY)

    def test_only_fixed_create_and_selected_channel_fields_are_reachable(self):
        _, wire = self.call("create", fields={"name": "Synthetic", "organization_id": ORG})
        self.assertEqual(wire.args[:2], ("POST", "/apps"))
        _, wire = self.call("update", APP, {"apns_bundle_id": "example.app"})
        self.assertEqual(wire.args[:2], ("PUT", "/apps/" + APP))
        for action, app, fields in [
            ("delete", APP, None),
            ("send", APP, {}),
            ("billing", None, None),
            ("update", APP, {"organization_id": ORG}),
            ("view", "../../messages", None),
        ]:
            with self.subTest(action=action), self.assertRaises(Invalid):
                request(action, KEY, app, fields)

    def test_failure_and_duplicate_list_are_not_retried_or_exposed(self):
        for status in (301, 403, 429, 500):
            with self.subTest(status=status), self.assertRaises(Invalid):
                self.call("view", APP, status=status)
        row = {"id": APP, "name": "Synthetic", "organization_id": ORG}
        with self.assertRaises(Invalid):
            self.call("list", response=[row, row])
        with self.assertRaises(Invalid):
            self.call("view", APP, response={"id": APP, "name": KEY, "organization_id": ORG})

    def test_encoded_and_decoded_private_fields_cannot_echo_in_public_metadata(self):
        for field, secret in [
            ("apns_p8", "synthetic-p8-private"),
            ("fcm_v1_service_account_json", "synthetic-firebase-private"),
        ]:
            encoded = base64.b64encode(secret.encode()).decode()
            for echo in (secret, encoded):
                with self.subTest(field=field, echo=echo):
                    with self.assertRaises(Invalid) as denied:
                        self.call(
                            "update", APP, {field: encoded}, response={"id": APP, "name": echo, "organization_id": ORG}
                        )
                    self.assertNotIn(secret, str(denied.exception))
                    self.assertNotIn(encoded, str(denied.exception))

    def test_view_and_list_reject_raw_response_private_field_echoes(self):
        fields = ("apns_p8", "fcm_v1_service_account_json", "gcm_key", "apns_certificates", "safari_apns_certificate")
        secret = "synthetic-channel-secret"
        encoded = base64.b64encode(secret.encode()).decode()
        for field in fields:
            for stored, echo in ((secret, secret), (encoded, secret), (secret, encoded), (encoded, encoded)):
                row = {"id": APP, "name": echo, "organization_id": ORG, field: stored}
                for action, app, response in (("view", APP, row), ("list", None, [row])):
                    with self.subTest(field=field, stored=stored, action=action):
                        with self.assertRaises(Invalid) as denied:
                            self.call(action, app, response=response)
                        self.assertNotIn(secret, str(denied.exception))
                        self.assertNotIn(encoded, str(denied.exception))

    def test_list_rejects_private_values_echoed_in_another_app(self):
        secret = "synthetic-cross-app-secret"
        first = {"id": APP, "name": "Synthetic", "organization_id": ORG, "apns_p8": secret}
        second = {"id": "33333333-3333-4333-8333-333333333333", "name": secret, "organization_id": ORG}
        with self.assertRaises(Invalid) as denied:
            self.call("list", response=[first, second])
        self.assertNotIn(secret, str(denied.exception))

    def test_nested_firebase_private_key_echo_is_rejected(self):
        secret = "synthetic-firebase-private-key"
        service = json.dumps(
            {"type": "service_account", "private_key": secret, "client_email": "synthetic@example.invalid"}
        )
        for value in (service, base64.b64encode(service.encode()).decode()):
            for echo in (secret, base64.b64encode(secret.encode()).decode()):
                with self.subTest(value=value, echo=echo), self.assertRaises(Invalid):
                    self.call(
                        "view",
                        APP,
                        response={
                            "id": APP,
                            "name": echo,
                            "organization_id": ORG,
                            "fcm_v1_service_account_json": value,
                        },
                    )

    def test_malformed_private_metadata_is_rejected(self):
        for value in ({"private_key": "sensitive"}, ["sensitive"], 42):
            with self.subTest(value=value), self.assertRaises(Invalid):
                self.call(
                    "view", APP, response={"id": APP, "name": "Synthetic", "organization_id": ORG, "apns_p8": value}
                )

    def test_rejected_private_echo_is_not_written_to_output(self):
        secret = "synthetic-channel-secret"
        output = io.StringIO()
        errors = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            with self.assertRaises(Invalid) as denied:
                self.call("view", APP, response={"id": APP, "name": secret, "organization_id": ORG, "apns_p8": secret})
        self.assertNotIn(secret, str(denied.exception))
        self.assertNotIn(secret, output.getvalue() + errors.getvalue())


if __name__ == "__main__":
    unittest.main()
