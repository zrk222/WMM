"""Unified provider health: login and publishing access stay separate from analytics permission."""
from pathlib import Path
import tempfile
import unittest
from mission_control.common import canonical
from mission_control.provider_health import project, recovery_text
from mission_control.service import Service
from mission_control.store import Store


def workspace():
    return dict(
        records=[dict(kind="connection", id="store-1", data=dict(provider="app_store", store_app_id="123",
                                                                  credential_ref="PRIVATE_CREDENTIAL")),
                 dict(kind="connection", id="ads-1", data=dict(provider="apple_ads", store_app_id="123",
                                                               account_id="456"))],
        connections={"store-1": {"status": "RECONNECT_REQUIRED"},
                     "ads-1": {"status": "PROTECTED_KEY_PRESENT"}},
        insights={"sources": [dict(provider="posthog", status="CONNECTED", updated="2026-11-01T00:00:00+00:00",
                                   data=dict(project_id="project-1"), last_error=None),
                              dict(provider="clarity", status="DISCONNECTED", updated="2026-11-01T00:00:00+00:00",
                                   data=dict(project_id="clarity-1"), last_error="PERMISSION_REQUIRED")]},
        social_access={"accounts": [dict(provider="facebook", status="CONNECTED", reconnect_required=False,
                                         expires=1900000000, updated="2026-11-01T00:00:00+00:00")]},
        play={"flows": [dict(status="EXPIRED", config=dict(package_name="com.example.app"), updated="2026-11-01T00:00:00+00:00")]},
    )


class ProviderHealthTests(unittest.TestCase):
    def entries(self):
        return {item["provider"]: item for item in project(workspace())["entries"]}

    def test_store_key_presence_is_not_analytics_permission(self):
        entries = self.entries()
        store = entries["app_store"]
        self.assertEqual(store["kind"], "STORE_READ")
        self.assertEqual(store["state"], "RECONNECT_REQUIRED")
        self.assertEqual(store["permission_state"], "ANALYTICS_READ_UNVERIFIED")
        self.assertEqual(store["scope"], {"store_app_id": "123"})
        self.assertIn("Reconnect", store["next_action"])
        self.assertEqual(store["recovery_route"], "connections")
        ads = entries["apple_ads"]
        self.assertEqual(ads["permission_state"], "ANALYTICS_READ_UNVERIFIED")
        self.assertIn("read test", ads["next_action"])

    def test_analytics_connection_keeps_its_own_permission_state(self):
        entries = self.entries()
        self.assertEqual(entries["posthog"]["permission_state"], "ANALYTICS_READ_CONFIGURED")
        self.assertEqual(entries["clarity"]["permission_state"], "ANALYTICS_READ_UNVERIFIED")
        self.assertEqual(entries["clarity"]["failure"], "PERMISSION_REQUIRED")
        self.assertIn("Reconnect", entries["clarity"]["next_action"])

    def test_publishing_login_is_explicitly_not_analytics_or_delivery(self):
        entries = self.entries()
        facebook = entries["facebook"]
        self.assertEqual(facebook["kind"], "PUBLISHING")
        self.assertEqual(facebook["permission_state"], "PUBLISHING_ONLY_NOT_ANALYTICS")
        self.assertEqual(facebook["state"], "CONNECTED")
        self.assertEqual(entries["google_play"]["state"], "EXPIRED")
        self.assertEqual(entries["google_play"]["permission_state"], "NOT_ANALYTICS_PERMISSION")

    def test_one_highest_priority_recovery_and_no_secret_leakage(self):
        value = project(workspace())
        self.assertEqual(value["recovery"]["provider"], "app_store")
        self.assertIn("Reconnect", recovery_text(value["recovery"]))
        encoded = canonical(value)
        for private in ("PRIVATE_CREDENTIAL", "api_key", "token", "secret"):
            self.assertNotIn(private, encoded)

    def test_ambiguous_failure_is_sanitized_and_empty_is_explicit(self):
        value = workspace()
        value["insights"]["sources"][0]["last_error"] = "Token expired for project; see private response"
        entry = {item["provider"]: item for item in project(value)["entries"]}["posthog"]
        self.assertEqual(entry["failure"], "READ_FAILED")
        empty = project({})
        self.assertEqual(empty["entries"], [])
        self.assertIsNone(empty["recovery"])
        self.assertIn("No provider needs repair", recovery_text(None))

    def test_workspace_exposes_the_same_projection(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        store = Store(Path(folder.name) / "state.sqlite", seed=False)
        store.save_app("sample-one", dict(name="Synthetic app", release="build-1", job="Synthetic job",
                                          audience="Synthetic audience", activation="Synthetic value", locale="en-US"))
        value = Service(store).workspace("sample-one")
        self.assertEqual(value["provider_health"]["schema"], "growth.provider-health.v1")
        self.assertEqual(value["provider_health"], project(value))


if __name__ == "__main__":
    unittest.main()
