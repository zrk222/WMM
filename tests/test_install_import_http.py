"""Owner HTTP preview/confirm for the install import; no browser dependency."""

import hashlib
import json
import unittest
from urllib.error import HTTPError
from urllib.request import Request
from mission_control.operator_client import ClientError, OperatorClient
from tests.test_agent_grants import GrantTests

CAMPAIGN = "11111111-1111-4111-8111-111111111111"
REQUEST = "22222222-2222-4222-8222-222222222222"


class InstallImportHTTPTests(unittest.TestCase):
    def setUp(self):
        self.fx = GrantTests("test_owner_issues_once_hash_only_persistence_and_snapshot_no_authority")
        self.fx.setUp()
        self.addCleanup(self.fx.tearDown)

    def payload(self, event="install"):
        return dict(
            text="id,event,time\ninstall_a," + event + ",2026-11-02T00:00:00+00:00\n",
            format="csv",
            mapping=dict(
                install_id="id",
                state="event",
                occurred_at="time",
                state_values={"install": "ATTRIBUTED", "organic": "UNATTRIBUTED"},
            ),
            source="APPSFLYER",
            campaign_token=CAMPAIGN,
            request_id=REQUEST,
            observed_at="2026-11-10T00:00:00+00:00",
            window=dict(starts_at="2026-11-01T00:00:00+00:00", ends_at="2026-11-08T00:00:00+00:00"),
            coverage=dict(complete=True, source_event_count=1),
        )

    def test_preview_then_confirm_records_once_and_updates_summary(self):
        preview = self.fx.owner.request(
            "POST", "/api/apps/sample-one/install-attribution/imports/preview", self.payload()
        )
        self.assertEqual(preview["checklist"]["status"], "READY")
        self.assertEqual(preview["checklist"]["rows_emitted"], 1)
        self.assertNotIn("installs", preview["batch"])
        self.assertNotIn("install_a", str(preview))
        payload = dict(self.payload(), preview_id=preview["preview_id"])
        confirm = self.fx.owner.request("POST", "/api/apps/sample-one/install-attribution/imports/confirm", payload)
        self.assertEqual(confirm["result"]["inserted"], 1)
        again = self.fx.owner.request("POST", "/api/apps/sample-one/install-attribution/imports/confirm", payload)
        self.assertEqual(again["result"]["status"], "ALREADY_RECORDED")
        summary = self.fx.server.service.workspace("sample-one")["install_attribution"]
        self.assertEqual(summary["campaigns"][0]["campaign_token"], CAMPAIGN)

    def test_confirm_is_bound_to_preview_and_detailed_readback_is_owner_only(self):
        base = "/api/apps/sample-one/install-attribution"
        with self.assertRaises(ClientError):
            self.fx.owner.request("POST", base + "/imports/confirm", self.payload())
        original = self.payload()
        original["text"] = "\ufeff" + original["text"].replace("\n", "\r\n")
        preview = self.fx.owner.request("POST", base + "/imports/preview", original)
        self.assertEqual(
            preview["batch"]["source_receipt_sha256"], hashlib.sha256(original["text"].encode()).hexdigest()
        )
        payload = dict(original, preview_id=preview["preview_id"])
        with self.assertRaises(ClientError):
            self.fx.owner.request(
                "POST",
                base + "/imports/confirm",
                dict(payload, text=original["text"].replace(",install,", ",organic,")),
            )
        self.fx.owner.request("POST", base + "/imports/confirm", payload)
        endpoint = base + "/reports/" + CAMPAIGN + "?day=7"
        report = self.fx.owner.request("GET", endpoint)
        self.assertEqual(report["counts"]["ATTRIBUTED"], 1)
        self.assertEqual(report["batches"][0]["source_receipt_sha256"], preview["batch"]["source_receipt_sha256"])
        with self.assertRaises(ClientError):
            self.fx.owner.request(
                "POST",
                base + "/imports/preview",
                dict(self.payload("organic"), request_id="44444444-4444-4444-8444-444444444444"),
            )
        visitor = OperatorClient(self.fx.origin)
        visitor.bootstrap()
        with self.assertRaises(ClientError):
            visitor.request("GET", endpoint)

    def test_preview_excludes_raw_values_and_rejects_malformed_shape(self):
        base = "/api/apps/sample-one/install-attribution/imports/preview"
        data = self.payload()
        for changed in ({"coverage": None}, {"text": "id,event,time,extra\ninstall_a,install,2026-11-02T00:00:00Z"}):
            with self.subTest(changed=changed), self.assertRaises(ClientError):
                self.fx.owner.request("POST", base, dict(data, **changed))
        owner = self.fx.owner
        raw = Request(
            self.fx.origin + base,
            method="POST",
            data=json.dumps(dict(data, text="\ud800")).encode(),
            headers={"Content-Type": "application/json", "Origin": self.fx.origin, "X-CSRF-Token": owner.csrf},
        )
        with self.assertRaises(HTTPError) as malformed:
            owner.opener.open(raw)
        self.assertEqual(malformed.exception.code, 400)
        result = self.fx.owner.request("POST", base, self.payload("private@example.test"))
        self.assertEqual(result["checklist"]["status"], "BLOCKED")
        self.assertNotIn("private@example.test", str(result))
        preview = self.fx.owner.request("POST", base, data)
        endpoint = base.replace("preview", "confirm")
        payload = dict(data, preview_id=preview["preview_id"])
        with self.assertRaises(ClientError):
            self.fx.owner.request("POST", endpoint, dict(payload, text=payload["text"].replace("\n", "\r\n")))
        app = self.fx.store.app("sample-one")
        self.fx.store.save_app("sample-one", dict(app["data"], job="Changed app"), app["version"])
        with self.assertRaises(ClientError):
            self.fx.owner.request("POST", endpoint, payload)

    def test_mature_empty_export_is_a_confirmed_zero(self):
        base = "/api/apps/sample-one/install-attribution"
        data = dict(self.payload(), text="[]", format="json", coverage=dict(complete=True, source_event_count=0))
        preview = self.fx.owner.request("POST", base + "/imports/preview", data)
        self.fx.owner.request("POST", base + "/imports/confirm", dict(data, preview_id=preview["preview_id"]))
        report = self.fx.owner.request("GET", base + "/reports/" + CAMPAIGN)
        self.assertEqual(report["coverage_status"], "COMPLETE")
        self.assertEqual(report["counts"]["ATTRIBUTED"], 0)

    def test_blocked_preview_and_confirm_do_not_write(self):
        blocked = self.fx.owner.request(
            "POST", "/api/apps/sample-one/install-attribution/imports/preview", self.payload("purchase")
        )
        self.assertEqual(blocked["checklist"]["status"], "BLOCKED")
        self.assertIsNone(blocked["batch"])
        with self.assertRaises(ClientError):
            self.fx.owner.request(
                "POST", "/api/apps/sample-one/install-attribution/imports/confirm", self.payload("purchase")
            )


if __name__ == "__main__":
    unittest.main()
