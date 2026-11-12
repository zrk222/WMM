"""Owned local source provenance never implies a public or viral claim."""

import tempfile
import time
import unittest
from pathlib import Path

from mission_control.common import Invalid, now
from mission_control.creative_analysis import Analyses
from mission_control.creative_briefs import Briefs
from mission_control.creative_library import Library, owned_reference, reference_location, verify_owned_source
from mission_control.creative_rendering import Renders, render_request
from mission_control.db import connection
from mission_control.ios_creative_batch import native_packet, native_source
from mission_control.operation_authority import bound_owner, protected
from mission_control.operation_runtime import execute
from mission_control.operator_identity import Identities
from mission_control.review_access import Access
from mission_control.service import Service
from mission_control.store import Store
from tests.production_fixtures import profile, ready_capabilities, requirement
from tests.test_creative_library import reference
from tests.test_creative_production import inspection
from tests.test_creative_rendering import APP, prepared_render, synthetic_png
from tests.test_verified_review import OWNER
from tests.journey_fixtures import covered


class OwnedCreativeSourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "source.sqlite")
        self.original, _ = prepared_render(self.store)
        self.asset = next(r for r in self.original["data"]["records"] if r["kind"] == "asset")
        self.data = reference(
            platform="other",
            post_id=self.asset["id"],
            url="wmm-owned://asset/" + self.asset["id"] + "/" + self.asset["data"]["sha256"],
            captured_at=now(),
            published_at=None,
            rights="LICENSED",
            metric_kind="UNKNOWN",
            metric_value=None,
            metric_at=None,
            source="Owner-provided local fixture; not a public post",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_local_owned_source_requires_current_app_rights_bytes_and_unknown_metrics(self):
        library = Library(self.store)
        for changes in (
            dict(metric_kind="VIEWS", metric_value=100000, metric_at=now()),
            dict(rights="REFERENCE_ONLY"),
            dict(permission_confirmed=False),
            dict(url=self.data["url"] + "/"),
            dict(post_id="wrong"),
        ):
            with self.subTest(changes=changes), self.assertRaises(Invalid):
                library.save(APP, {"data": dict(self.data, **changes)})
        with self.assertRaises(Invalid):
            library.save("sample-two", {"data": self.data})
        created = library.save(APP, {"data": self.data})
        self.assertEqual(owned_reference(self.data), self.data["url"])
        self.assertEqual(reference_location(self.data), self.data["url"])
        self.assertEqual(reference_location(reference()), "https://example.com/public-post-1")
        with connection(self.store.path) as db:
            self.assertIsNone(verify_owned_source(db, self.store, APP, self.data))
        source = next(s for s in library.list(APP) if s["id"] == created["id"])
        self.assertIsNone(source["current"]["data"]["metric_value"])
        self.assertTrue(source["current"]["data"]["url"].startswith("wmm-owned://asset/"))
        data = dict(inspection(source), duration_seconds=None)
        data["observations"][0].update(start_seconds=None, end_seconds=None)
        analysis = Analyses(self.store).save(APP, {"data": data})
        ready_capabilities(self.store, APP, [source])
        definition = dict(
            self.original["data"]["definition"], analysis_id=analysis["id"], analysis_hash=analysis["hash"]
        )
        brief = Briefs(self.store).save(APP, {"data": definition})
        self.assertEqual(brief["data"]["source"]["data"]["url"], self.data["url"])
        snapshot = self.store.export(APP)
        target = Store(Path(self.tmp.name) / "restored" / "state.sqlite")
        target.restore(snapshot)
        self.assertEqual(Briefs(target).list(APP)[0]["evidence_status"], "CURRENT")
        asset = next(row for row in self.store.records(APP) if row["id"] == self.asset["id"])
        self.store.save_record(
            APP,
            dict(
                id=asset["id"],
                version=asset["version"],
                kind="asset",
                title=asset["title"],
                source=asset["source"],
                data=dict(asset["data"], rights_cleared=False),
            ),
        )
        with self.assertRaises(Invalid):
            Renders(self.store).queue(
                APP,
                dict(
                    data=dict(brief_id=brief["id"], brief_hash=brief["hash"], shape="PORTRAIT"), request_key="revoked"
                ),
            )

    def test_fresh_local_owned_source_can_prepare_without_a_public_post(self):
        store = Store(Path(self.tmp.name) / "fresh" / "state.sqlite", seed=False)
        app = "fresh-owned-app"
        store.save_app(
            app,
            dict(
                name="Synthetic local app",
                job="Test job",
                audience="Test audience",
                activation="Test activation",
                release="test-1",
                locale="en-US",
                currency="USD",
            ),
        )
        service = Service(store)
        Access(store).bootstrap(app, OWNER, {"confirm_owner": True})
        identity = Identities()
        session = "synthetic-owned-session"
        identity.sessions[session] = dict(user=OWNER, token="fixture", expires=time.time() + 900)

        def call(operation, body):
            envelope = dict(app_id=app, operation=operation, input=body)
            with bound_owner(store, envelope, identity, session, OWNER), protected(store, envelope):
                return execute(service, envelope, caller="LOCAL_SESSION")

        uploaded = service.upload(app, "real-fixture.png", synthetic_png())
        asset = call(
            "evidence.save",
            dict(
                id=uploaded["id"],
                version=uploaded["version"],
                manifest_version=1,
                kind="asset",
                title="Synthetic owned image",
                source="Synthetic owner rights attestation",
                data=dict(uploaded["data"], authentic=True, rights_cleared=True, device="Synthetic device"),
            ),
        )
        stamp = now()
        release = "test-1"
        locale = "en-US"
        definitions = dict(
            claim=dict(release=release, locale=locale, claim="A fictional claim", result="PASS", checked_at=stamp),
            readiness=covered(release, locale, stamp),
            store=dict(
                release=release,
                locale=locale,
                destination="https://example.com/first-value",
                availability="AVAILABLE",
                checked_at=stamp,
            ),
            route=dict(
                release=release,
                result="PASS",
                installed=True,
                fresh_install=True,
                signed_out=True,
                fallback="Synthetic fallback",
                checked_at=stamp,
            ),
        )
        evidence = {
            kind: service.evidence(
                app, dict(kind=kind, title="Synthetic " + kind, source="Synthetic fixture evidence", data=data)
            )
            for kind, data in definitions.items()
        }
        data = reference(
            platform="other",
            post_id=asset["id"],
            url="wmm-owned://asset/" + asset["id"] + "/" + asset["data"]["sha256"],
            captured_at=now(),
            published_at=None,
            rights="LICENSED",
            source="Synthetic owner attestation",
        )
        created = call("creative.source.save", {"data": data})
        source = next(item for item in Library(store).list(app) if item["id"] == created["id"])
        observed = dict(inspection(source), duration_seconds=None)
        observed["observations"][0].update(start_seconds=None, end_seconds=None)
        analysis = call("creative.analysis.save", {"data": observed})
        declaration = profile(
            store,
            app,
            executions=["SLIDES"],
            talent=["NONE"],
            audio=["SILENT"],
            channels=["SHORT_VIDEO"],
            editing_level=0,
            cost_minor=0,
            time_minutes=30,
        )
        call("creative.profile.save", {"data": declaration})
        needed = requirement(source, execution="SLIDES", editing_level=0, cost_minor=0, time_minutes=30)
        call("creative.requirement.save", {"data": needed})
        definition = dict(
            analysis_id=analysis["id"],
            analysis_hash=analysis["hash"],
            channel="SHORT_VIDEO",
            objective="A fictional objective",
            owner="Synthetic reviewer",
            claim_ids=[evidence["claim"]["id"]],
            asset_ids=[asset["id"]],
            readiness_id=evidence["readiness"]["id"],
            store_id=evidence["store"]["id"],
            route_id=evidence["route"]["id"],
            currency="USD",
            budget_minor=0,
            duration_seconds=30,
        )
        brief = call("creative.brief.save", {"data": definition})
        self.assertEqual(brief["data"]["source"]["data"]["url"], data["url"])
        self.assertIsNone(brief["data"]["source"]["data"]["metric_value"])
        self.assertEqual(brief["data"]["publication"], "NOT_RUN")
        with connection(store.path) as db:
            request = render_request(
                db, store, app, dict(brief_id=brief["id"], brief_hash=brief["hash"], shape="PORTRAIT")
            )
            packet = native_packet(db, store, app, request)
            scene = packet["scenes"][0]
            self.assertTrue(native_source(db, store, app, packet, scene["source_id"], scene["source_hash"]).is_file())
            self.assertEqual(packet["publication"], "NOT_RUN")


if __name__ == "__main__":
    unittest.main()
