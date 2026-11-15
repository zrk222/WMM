"""Account confirmation cannot leak credentials, adopt other subjects or race saves."""

import time
import unittest
from unittest.mock import patch

from mission_control.common import Invalid, canonical
from mission_control.db import connection
from mission_control.social_connections import Connections
from mission_control.social_flows import Flows
from mission_control.social_profiles import Identity
from mission_control.social_setup import Setup
from mission_control.store import Store
from tests import test_social_flows as flow_fixtures
from tests.test_measurement_connectors import FakeVault


class SocialConnectionTests(unittest.TestCase):
    store: Store
    setup: Setup
    flows: Flows

    setUp = flow_fixtures.SocialFlowTests.setUp
    begin = flow_fixtures.SocialFlowTests.begin
    success = flow_fixtures.SocialFlowTests.success

    def confirmed(self):
        started, request = self.begin()
        self.success(request)
        saved = Connections(self.store).confirm(
            "sample-one", dict(flow_id=started["flow_id"], destination_id="synthetic-user", connection_id="", version=0)
        )
        return saved

    def test_confirmed_account_retains_scoped_grant_and_disconnected_cleanup(self):
        saved = self.confirmed()
        service = Connections(self.store)
        self.assertEqual(saved["status"], "CONNECTED_READ_TESTED")
        self.assertEqual(saved["version"], 1)
        self.assertNotIn("synthetic-access", canonical(saved))
        self.assertNotIn("secret_ref", canonical(saved))
        self.assertEqual(service.view("sample-two")["accounts"], [])
        self.assertNotIn("synthetic-access", canonical(self.store.export("sample-one")))
        row = service.get("sample-one", saved["id"])
        self.assertEqual(
            service.secrets.load("sample-one", "tiktok", row["secret_ref"])["access_token"], "synthetic-access"
        )
        with self.assertRaises(Invalid):
            service.disconnect("sample-two", saved["id"], 1)
        result = service.disconnect("sample-one", saved["id"], 1)
        self.assertEqual(result["provider_revocation"], "NOT_PERFORMED")
        self.assertEqual(len(FakeVault.values), 1)
        self.assertEqual(service.get("sample-one", saved["id"])["status"], "DISCONNECTED")

    def test_one_facebook_page_has_three_independent_app_connections(self):
        from urllib.parse import parse_qs, urlsplit

        from mission_control.social_callbacks import callback
        from mission_control.social_tokens import parse
        from tests.test_social_providers import token
        from tests.test_social_setup import body

        service = Connections(self.store)
        apps = ("sample-one", "sample-two", "shared-page-third")
        self.store.save_app(apps[-1], {"name": "Synthetic third company app"})
        page = dict(id="123", name="Synthetic company Page", kind="PAGE", tasks=["CREATE_CONTENT"])
        identity = Identity("synthetic-company-owner", "Synthetic operator", [page], ["pages_show_list"])
        results = []
        for index, app_id in enumerate(apps):
            self.setup.save(app_id, body("facebook"))
            start = self.flows.start(app_id, "facebook", 1)
            authorization_url = start["authorization_url"]
            assert isinstance(authorization_url, str)
            state = parse_qs(urlsplit(authorization_url).query)["state"][0]
            request = dict(provider="facebook", state=state, code="synthetic-code", error="")
            grant = parse("facebook", token("facebook", **{"access_token": f"synthetic-grant-{index}"}), time.time())
            with (
                patch("mission_control.social_callbacks.exchange_code", return_value=grant),
                patch("mission_control.social_callbacks.verify", return_value=identity),
                patch(
                    "mission_control.social_connections.selected_page", return_value=(page, f"synthetic-page-{index}")
                ),
            ):
                self.assertEqual(callback(self.store, request)["status"], "AWAITING_DESTINATION")
                saved = service.confirm(
                    app_id, dict(flow_id=start["flow_id"], destination_id=page["id"], connection_id="", version=0)
                )
            self.assertEqual(saved["data"]["destination"]["id"], page["id"])
            self.assertNotIn("secret_ref", canonical(saved))
            results.append(saved["id"])
        self.assertEqual(len(set(results)), 3)
        for app_id, connection_id in zip(apps, results, strict=True):
            accounts = service.view(app_id)["accounts"]
            assert isinstance(accounts, list)
            self.assertEqual([row["id"] for row in accounts], [connection_id])
            for other in set(results) - {connection_id}:
                with self.assertRaises(Invalid):
                    service.get(app_id, other)
        service.disconnect(apps[1], results[1], 1)
        self.assertEqual(service.get(apps[0], results[0])["status"], "CONNECTED_READ_TESTED")
        self.assertEqual(service.get(apps[2], results[2])["status"], "CONNECTED_READ_TESTED")

    def test_view_lists_all_implemented_channels_without_refresh_or_authority(self):
        service = Connections(self.store)
        with patch("mission_control.social_connections.verify") as network:
            snapshot = service.view("sample-one")
        self.assertEqual(snapshot["publication_providers"], ["facebook", "instagram", "tiktok", "youtube", "linkedin"])
        self.assertEqual(snapshot["accounts"], [])
        self.assertFalse(snapshot["automatic_ad_spend"])
        network.assert_not_called()

    def test_destination_replay_or_invention_cannot_adopt_or_duplicate_accounts(self):
        started, request = self.begin()
        self.success(request)
        service = Connections(self.store)
        body = dict(flow_id=started["flow_id"], destination_id="invented-user", connection_id="", version=0)
        with self.assertRaises(Invalid):
            service.confirm("sample-one", body)
        saved = service.confirm("sample-one", {**body, "destination_id": "synthetic-user"})
        with self.assertRaises(Invalid):
            service.confirm("sample-one", {**body, "destination_id": "synthetic-user"})
        started, request = self.begin()
        self.success(request)
        body = {**body, "flow_id": started["flow_id"], "destination_id": "synthetic-user"}
        with self.assertRaisesRegex(Invalid, "already saved"):
            service.confirm("sample-one", body)
        self.assertEqual(service.get("sample-one", saved["id"])["version"], 1)
        reconnected = service.confirm("sample-one", {**body, "connection_id": saved["id"], "version": 1})
        self.assertEqual(reconnected["version"], 2)

    def test_read_test_requires_same_subject_and_detects_disconnect_race(self):
        saved = self.confirmed()
        service = Connections(self.store)
        found = Identity(
            "synthetic-user",
            "Updated name",
            [dict(id="synthetic-user", name="Updated name", kind="PROFILE", tasks=[])],
            ["user.info.basic"],
        )
        with patch("mission_control.social_connections.verify", return_value=found):
            tested = service.read_test("sample-one", saved["id"], 1)
        self.assertEqual(tested["data"]["identity"]["name"], "Updated name")
        self.assertEqual(tested["version"], 2)
        with (
            patch("mission_control.social_connections.verify", return_value=Identity("other", "Other", [], None)),
            self.assertRaises(Invalid),
        ):
            service.read_test("sample-one", saved["id"], 2)

        def raced(*args):
            service.disconnect("sample-one", saved["id"], 2)
            return found

        with patch("mission_control.social_connections.verify", side_effect=raced), self.assertRaises(Invalid):
            service.read_test("sample-one", saved["id"], 2)
        self.assertEqual(service.get("sample-one", saved["id"])["status"], "DISCONNECTED")

    def test_configuration_change_or_expiry_prevents_read_and_adoption(self):
        saved = self.confirmed()
        service = Connections(self.store)
        with connection(self.store.path) as db:
            db.execute("UPDATE social_connections SET expires=? WHERE id=?", (time.time() - 1, saved["id"]))
        accounts = service.view("sample-one")["accounts"]
        assert isinstance(accounts, list)
        self.assertTrue(accounts[0]["reconnect_required"])
        with patch("mission_control.social_connections.verify") as network:
            with self.assertRaises(Invalid):
                service.read_test("sample-one", saved["id"], 1)
            network.assert_not_called()
        started, request = self.begin()
        self.success(request)
        with connection(self.store.path) as db:
            db.execute(
                "UPDATE social_configs SET version=version+1 WHERE app_id=? AND provider=?", ("sample-one", "tiktok")
            )
        with self.assertRaises(Invalid):
            service.confirm(
                "sample-one",
                dict(flow_id=started["flow_id"], destination_id="synthetic-user", connection_id=saved["id"], version=1),
            )
        self.assertEqual(service.get("sample-one", saved["id"])["version"], 1)


if __name__ == "__main__":
    unittest.main()
