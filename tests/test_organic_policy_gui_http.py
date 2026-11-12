"""Owner GUI route admission and reviewed app context are checked by real HTTP."""

import unittest
from mission_control.common import uid
from tests.test_verified_review import OWNER_TOKEN
from mission_control.operator_client import ClientError
from mission_control.db import connection
from tests import test_organic_video_policy_http as fixture
from tests.test_organic_video_policy import APP


class OrganicPolicyGUIHTTPTests(unittest.TestCase):
    setUp = fixture.PolicyHTTPTests.setUp
    request = fixture.PolicyHTTPTests.request
    close = fixture.PolicyHTTPTests.close

    def reviewed(self):
        context = self.request("policy-context", {})
        app = context["app"]
        policy = dict(self.f.policy, mode="STANDING_GENERATED", approved_output_hashes=[])
        return dict(
            request_id=uid(),
            policy=policy,
            manifest_version=app["version"],
            app_hash=app["hash"],
            **context["review"],
            page_binding=context["pages"][0]["binding"],
        )

    def test_reviewed_context_pair_is_bound_to_the_atomic_create_and_replay(self):
        body = self.reviewed()
        saved = self.request("policy-create", body)
        self.assertEqual(saved["data"]["app_version"], body["manifest_version"])
        self.assertEqual(saved["data"]["app_hash"], body["app_hash"])
        self.assertEqual(self.request("policy-create", body), saved)
        with connection(self.store.path) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM organic_video_policies").fetchone()[0], 1)

    def test_stale_or_incomplete_reviewed_context_never_creates_authority(self):
        body = self.reviewed()
        for patch in [
            dict(manifest_version=True),
            dict(app_hash="0" * 64),
            dict(manifest_version=body["manifest_version"] + 1),
            dict(owner_version=2),
            dict(page_binding={**body["page_binding"], "version": 2}),
        ]:
            with self.assertRaises(ClientError):
                self.request("policy-create", dict(body, **patch))
        for key in ["manifest_version", "app_hash"]:
            value = dict(body)
            value.pop(key)
            with self.assertRaises(ClientError):
                self.request("policy-create", value)
        app = self.store.app(APP)
        self.store.save_app(APP, dict(app["data"], name="Changed after GUI review"), app["version"])
        with self.assertRaises(ClientError):
            self.request("policy-create", body)

    def test_reauthentication_and_missing_completed_exact_output_fail_closed(self):
        body = self.reviewed()
        with self.assertRaises(ClientError):
            self.request("policy-create", dict(body, policy=self.f.policy))
        self.owner.request("POST", "/api/identity/login", dict(token=OWNER_TOKEN))
        with self.assertRaises(ClientError):
            self.request("policy-create", body)
        self.assertEqual(self.request("policy-history", dict(offset=0, request_id=None))["items"], [])

    def test_completed_render_becomes_selectable_and_held_usage_stays_separate(self):
        existing = self.f.create()
        artifact = self.f.reserved_render(existing)
        context = self.request("policy-context", {})
        self.assertIn(artifact["sha256"], [item["sha256"] for item in context["approved_outputs"]])
        approved = self.request("policy-create", dict(self.reviewed(), policy=self.f.policy))
        self.assertEqual(approved["data"]["policy"]["approved_output_hashes"], [artifact["sha256"]])
        rows = self.request("policy-history", dict(offset=0, request_id=None))["items"]
        held = next(row for row in rows if row["id"] == existing["id"])
        self.assertEqual(held["usage"]["generations_held"], 1)
        self.assertEqual(held["usage"]["artifact_slots_admitted"], 0)
        self.assertEqual(held["usage"]["provider_phase_complete"], 0)
