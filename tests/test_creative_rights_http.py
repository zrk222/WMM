"""Real HTTP identity and commit checks for local asset-rights assertions."""

import unittest
from unittest.mock import patch

from mission_control.db import connection
from mission_control.operator_client import ClientError, OperatorClient
from tests import test_experiment_schedule_http as fixture


class CreativeRightsHTTPTests(unittest.TestCase):
    setUp = fixture.ExperimentScheduleHTTPTests.setUp

    def asset(self):
        saved = self.server.service.upload("sample-one", "fixture.png", b"\x89PNG\r\n\x1a\nsynthetic")
        return dict(
            id=saved["id"],
            version=saved["version"],
            manifest_version=self.store.app("sample-one")["version"],
            kind="asset",
            title=saved["title"],
            source=saved["source"],
            data=dict(saved["data"], authentic=True, rights_cleared=True),
        )

    def test_both_asset_routes_require_current_owner(self):
        anonymous = OperatorClient(self.client.origin)
        anonymous.bootstrap()
        for suffix in ("records", "workflow-evidence"):
            body = self.asset()
            path = "/api/apps/sample-one/" + suffix
            with self.subTest(route=suffix):
                with self.assertRaises(ClientError) as denied:
                    anonymous.request("POST", path, body)
                self.assertEqual(denied.exception.status, 403)
                saved = self.client.request("POST", path, body)
                self.assertTrue(saved["data"]["rights_cleared"])

    def test_revocation_before_business_commit_refuses_assertion(self):
        body = self.asset()
        original = self.server.service.evidence

        def revoke(app_id, data):
            with connection(self.store.path) as db:
                db.execute(
                    "UPDATE operator_roles SET status='REVOKED',version=version+1 WHERE app_id=?", ("sample-one",)
                )
            return original(app_id, data)

        with patch.object(self.server.service, "evidence", side_effect=revoke):
            with self.assertRaises(ClientError):
                self.client.request("POST", "/api/apps/sample-one/records", body)
        saved = next(r for r in self.store.records("sample-one") if r["id"] == body["id"])
        self.assertFalse(saved["data"]["rights_cleared"])

    def test_summary_withholds_handoff_metadata_without_fresh_app_owner(self):
        anonymous = OperatorClient(self.client.origin)
        anonymous.bootstrap()
        path = "/api/apps/sample-one/reports/summary"
        public = anonymous.request("GET", path)
        self.assertFalse(any(row["metric"] == "Agent handoffs" for row in public["rows"]))
        result = self.client.request("GET", path)
        self.assertEqual(result["appID"], "sample-one")
        self.assertTrue(any(row["metric"] == "Agent handoffs" for row in result["rows"]))
        with connection(self.store.path) as db:
            db.execute("UPDATE operator_roles SET status='REVOKED',version=version+1 WHERE app_id=?", ("sample-one",))
        revoked = self.client.request("GET", path)
        self.assertFalse(any(row["metric"] == "Agent handoffs" for row in revoked["rows"]))

    def test_legacy_source_and_inspection_writes_require_fresh_owner(self):
        from tests.test_creative_library import reference
        from tests.test_creative_production import inspection
        from tests.production_fixtures import profile, requirement
        from mission_control.creative_library import Library

        anonymous = OperatorClient(self.client.origin)
        anonymous.bootstrap()
        paths = (
            "/references",
            "/references/import",
            "/production/analyses",
            "/production/profile",
            "/production/requirement",
            "/production/briefs",
        )
        for suffix in paths:
            with self.subTest(route=suffix), self.assertRaises(ClientError) as denied:
                anonymous.request("POST", "/api/apps/sample-one" + suffix, {})
            self.assertEqual(denied.exception.status, 403)
        saved = self.client.request("POST", "/api/apps/sample-one/references", {"data": reference()})
        source = next(r for r in Library(self.store).list("sample-one") if r["id"] == saved["id"])
        refreshed = self.client.request(
            "POST",
            "/api/apps/sample-one/references",
            dict(id=saved["id"], version=1, data=reference(title="Owner-reviewed revision")),
        )
        self.assertEqual(refreshed["id"], saved["id"])
        source = next(r for r in Library(self.store).list("sample-one") if r["id"] == saved["id"])
        analyzed = self.client.request("POST", "/api/apps/sample-one/production/analyses", {"data": inspection(source)})
        self.assertEqual(analyzed["data"]["inspection_kind"], "DIRECT_VIEW")
        self.client.request(
            "POST", "/api/apps/sample-one/production/profile", {"data": profile(self.store, "sample-one")}
        )
        self.client.request("POST", "/api/apps/sample-one/production/requirement", {"data": requirement(source)})
        preview = anonymous.request(
            "POST", "/api/apps/sample-one/references/preview", {"rows": [reference(post_id="another-source")]}
        )
        imported = self.client.request(
            "POST", "/api/apps/sample-one/references/import", {k: preview[k] for k in ("rows", "preview_hash")}
        )
        self.assertEqual(imported["results"][0]["status"], "SAVED")

    def test_legacy_brief_owner_request_keeps_original_payload(self):
        from tests.test_creative_production import ready_production

        app = self.store.app("sample-one")
        self.store.save_app(
            "sample-one",
            dict(app["data"], job="Rehearse a conversation", audience="Synthetic users", activation="Save a next step"),
            app["version"],
        )
        _, _, _, body = ready_production(self.store, "sample-one")
        saved = self.client.request("POST", "/api/apps/sample-one/production/briefs", {"data": body})
        self.assertEqual(saved["data"]["render"], "NOT_RUN")


if __name__ == "__main__":
    unittest.main()
