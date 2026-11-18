"""Native connector lifecycle, source binding and actionable evidence without provider traffic."""

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mission_control.common import Invalid
from mission_control.db import connection
from mission_control.growth_review_store import GrowthReviews
from mission_control.insights import Insights
from mission_control.openseo_read import read, save_reading
from mission_control.store import Store
from tests.test_measurement_connectors import FakeVault


def setup() -> dict:
    return dict(
        provider="openseo",
        project_id="dedicated-project",
        region="global",
        api_key="oseo_" + "X" * 24,
        automatic=False,
        confirm_read=True,
        dedicated_project=True,
        website="https://sample.example",
        release="build-1",
        locale="en-US",
        territory="US",
        report_mode="pages",
    )


def provider_reply(token: str, tool: str, args: dict) -> dict:
    if tool != "get_search_console_performance":
        raise AssertionError("Unexpected native tool")
    if args["filters"] != [dict(dimension="country", operator="equals", expression="usa")]:
        raise AssertionError("Wrong market")
    return dict(
        ok=True,
        siteUrl="sc-domain:sample.example",
        startDate=args["startDate"],
        endDate=args["endDate"],
        dimensions=["page"],
        rowCount=1,
        hasMore=False,
        rows=[dict(keys=["https://sample.example/guide"], clicks=4, impressions=100, ctr=0.04, position=8.5)],
    )


class OpenSEOReadTests(unittest.TestCase):
    def _read_pages(self, pages: list[str], website: str = "https://sample.example") -> dict:
        def reply(token: str, tool: str, args: dict) -> dict:
            result = provider_reply(token, tool, args)
            result["rows"] = [dict(result["rows"][0], keys=[page]) for page in pages]
            result["rowCount"] = len(pages)
            return result

        with patch("mission_control.openseo_transport.call_tool", side_effect=reply):
            return read(dict(setup(), website=website), setup()["api_key"])

    def test_parameter_and_fragment_pages_are_omitted_without_merging(self) -> None:
        result = self._read_pages(
            [
                "https://sample.example/guide",
                "https://sample.example/guide?topic=sunset",
                "https://sample.example/guide#contact-private",
            ]
        )
        self.assertEqual(result["coverage"], "PARTIAL")
        self.assertEqual(result["omitted_rows"], {"outside_app": 0, "parameter_or_fragment": 2})
        self.assertEqual(len(result["rows"]), 1)
        self.assertEqual(result["rows"][0]["values"]["impressions"], 100)
        self.assertEqual(result["web_evidence"]["observations"][0]["coverage"], "PARTIAL")
        self.assertNotIn("topic=sunset", json.dumps(result))
        self.assertNotIn("contact-private", json.dumps(result))

    def test_only_parameter_pages_are_partial_not_no_results(self) -> None:
        result = self._read_pages(["https://sample.example/guide?topic=sunset"])
        self.assertEqual(result["coverage"], "PARTIAL")
        self.assertEqual(result["rows"], [])
        self.assertIsNone(result["web_evidence"])
        self.assertIn("1 app-page rows", result["interpretation"])

    def test_outside_app_parameter_pages_are_filtered_before_conversion(self) -> None:
        result = self._read_pages(
            [
                "https://sample.example/app/guide",
                "https://sample.example/other?private=hidden",
            ],
            "https://sample.example/app",
        )
        self.assertEqual(result["coverage"], "PARTIAL")
        self.assertEqual(result["omitted_rows"], {"outside_app": 1, "parameter_or_fragment": 0})
        self.assertEqual(len(result["rows"]), 1)
        self.assertNotIn("private=hidden", json.dumps(result))
        for page in ("https://user:secret@sample.example/other?topic=x", "https://127.0.0.1/other?topic=x"):
            with self.subTest(page=page), self.assertRaises(Invalid):
                self._read_pages([page])

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / "native.sqlite", seed=False)
        self.store.save_app(
            "sample-app", dict(name="Sample", website="https://sample.example", release="build-1", locale="en-US")
        )
        FakeVault.values, FakeVault.fail_delete = {}, 0
        self.vault = patch("mission_control.insights.Vault", FakeVault)
        self.vault.start()
        self.addCleanup(self.vault.stop)
        self.remote = patch("mission_control.openseo_transport.call_tool", side_effect=provider_reply)
        self.remote.start()
        self.addCleanup(self.remote.stop)
        self.work = Insights(self.store)

    def test_native_setup_read_save_and_disconnect(self) -> None:
        result = self.work.setup("sample-app", setup())
        sid = result["source_id"]
        fetched = self.work.refresh("sample-app", sid, {"confirm_read": True})
        self.assertEqual(fetched["status"], "CONNECTED")
        view = self.work.list("sample-app")
        self.assertNotIn(setup()["api_key"], json.dumps(view))
        report = view["reports"][0]
        self.assertEqual(fetched["report_id"], report["id"])
        saved = save_reading(
            self.store, "sample-app", sid, dict(id="native-test", manifest_version=1, report_id=report["id"])
        )
        analysis = GrowthReviews(self.store).list("sample-app")["history"][0]["readout"]["analysis"]
        self.assertTrue(analysis["native_connection_read"])
        self.assertFalse(analysis["outcomes_verified"])
        self.assertEqual(analysis["recommendation"]["observed_rate"]["value"], 0.04)
        self.assertEqual(saved["data"]["native_source"]["report_hash"], report["hash"])
        with connection(self.store.path) as db:
            self.assertNotIn(setup()["api_key"], "\n".join(db.iterdump()))
        self.work.disconnect("sample-app", sid, dict(version=1, confirm_disconnect=True))
        self.assertEqual(FakeVault.values, {})

    def test_native_schedule_reads_only_after_explicit_opt_in_and_due_time(self) -> None:
        with patch("mission_control.openseo_transport.call_tool", side_effect=provider_reply) as remote:
            sid = self.work.setup("sample-app", setup())["source_id"]
            remote.assert_called_once()
            remote.reset_mock()
            self.assertEqual(self.work.tick()["status"], "IDLE")
            remote.assert_not_called()

            opt_in = dict(setup(), version=1, automatic=True)
            self.assertEqual(self.work.setup("sample-app", opt_in)["source_id"], sid)
            remote.assert_called_once()
            remote.reset_mock()
            self.assertEqual(self.work.tick()["status"], "IDLE")
            remote.assert_not_called()

            with connection(self.store.path, write=True) as db:
                db.execute("UPDATE insight_sources SET next_due=0 WHERE app_id=? AND id=?", ("sample-app", sid))
            result = self.work.tick()
            self.assertEqual(result["status"], "CONNECTED")
            report = result["report"]
            assert isinstance(report, dict)
            self.assertEqual(report["provider"], "openseo")
            remote.assert_called_once()
            self.assertEqual(self.work.tick()["status"], "IDLE")
            self.assertEqual(remote.call_count, 1)

    def test_wrong_property_cannot_replace_a_working_source(self) -> None:
        source = self.work.setup("sample-app", setup())["source_id"]

        def wrong(token: str, tool: str, args: dict) -> dict:
            return dict(provider_reply(token, tool, args), siteUrl="sc-domain:other.example")

        with patch("mission_control.openseo_transport.call_tool", side_effect=wrong), self.assertRaises(Invalid):
            self.work.setup("sample-app", dict(setup(), version=1))
        view = self.work.list("sample-app")
        self.assertEqual(view["sources"][0]["id"], source)
        self.assertEqual(len(view["reports"]), 1)
        self.assertEqual(len(FakeVault.values), 1)

    def test_app_scope_change_stops_refresh_before_remote_access(self) -> None:
        source = self.work.setup("sample-app", setup())["source_id"]
        app = self.store.app("sample-app")
        self.store.save_app("sample-app", dict(app["data"], website="https://other.example"), app["version"])
        with patch("mission_control.openseo_transport.call_tool") as remote:
            with self.assertRaises(Invalid):
                self.work.refresh("sample-app", source, dict(confirm_read=True))
            remote.assert_not_called()

    def test_forged_native_provenance_and_partial_results(self) -> None:
        source = self.work.setup("sample-app", setup())["source_id"]
        report = self.work.list("sample-app")["reports"][0]
        data = copy.deepcopy(report["data"]["web_evidence"])
        data["observations"][0]["values"]["clicks"] = 90
        data["native_source"] = dict(source_id=source, report_id=report["id"], report_hash=report["hash"])
        with self.assertRaises(Invalid):
            GrowthReviews(self.store).save(
                "sample-app",
                dict(
                    id="forged",
                    kind="WEB_SEO_EVIDENCE",
                    manifest_version=1,
                    data=data,
                ),
            )
        with patch(
            "mission_control.openseo_transport.call_tool",
            side_effect=lambda *args: dict(provider_reply(*args), hasMore=True),
        ):
            result = read(setup(), setup()["api_key"])
        self.assertEqual(result["coverage"], "PARTIAL")
        self.assertEqual(result["web_evidence"]["observations"][0]["coverage"], "PARTIAL")

    def test_native_recommendation_expires_on_disconnect_and_rotation(self) -> None:
        sid = self.work.setup("sample-app", setup())["source_id"]
        report = self.work.list("sample-app")["reports"][0]
        save_reading(self.store, "sample-app", sid, dict(id="native-test", manifest_version=1, report_id=report["id"]))
        before = GrowthReviews(self.store).list("sample-app")["history"][0]["readout"]
        self.assertIn("Read the queries", before["analysis"]["next_action"])
        self.work.setup("sample-app", dict(setup(), version=1))
        rotated = GrowthReviews(self.store).list("sample-app")["history"][0]["readout"]
        self.assertEqual(rotated["availability"], "SOURCE_REVIEW_NEEDED")
        self.assertFalse(rotated["analysis"]["native_connection_read"])
        self.assertIsNone(rotated["analysis"]["recommendation"]["observed_rate"])
        self.work.disconnect("sample-app", sid, dict(version=2, confirm_disconnect=True))
        after = GrowthReviews(self.store).list("sample-app")["history"][0]["readout"]
        self.assertEqual(after["availability"], "SOURCE_REVIEW_NEEDED")

    def test_native_query_mode_retains_only_permitted_bounded_query_page_pairs(self) -> None:
        def queries(token: str, tool: str, args: dict) -> dict:
            self.assertEqual(args["dimensions"], ["page", "query"])
            result = provider_reply(token, tool, args)
            result["dimensions"] = args["dimensions"]
            result["rows"][0]["keys"].append("decision planning app")
            return result

        with patch("mission_control.openseo_transport.call_tool", side_effect=queries):
            result = read(dict(setup(), report_mode="queries"), setup()["api_key"])
        self.assertEqual(result["web_evidence"]["observations"][0]["subject"], "decision planning app")
