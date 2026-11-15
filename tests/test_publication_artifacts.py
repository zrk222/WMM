"""App-scoped organic publication artifact binding and byte-integrity tests."""

import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from mission_control.common import Invalid, digest, uid
from mission_control.db import connection
from mission_control.hypit_jobs import HypitRenders, private_path
from mission_control.publication_artifacts import describe, load, verify
from mission_control.store import Store
from mission_control.worker import run_once
from tests.test_creative_rendering import prepared_render


APP = "render-test"
RAW = b"synthetic publication artifact bytes"
META = dict(
    codec="h264",
    pixel_format="yuv420p",
    width=720,
    height=1280,
    frame_rate="24/1",
    duration_seconds=8.0,
    audio=False,
    audio_codec=None,
)


class PublicationArtifactTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name) / "state.sqlite")
        _, self.request = prepared_render(self.store)
        self.renders = HypitRenders(self.store)
        self.brief_hash = self.request["brief_hash"]
        with patch(
            "mission_control.hypit_jobs.identity", return_value={"launcher": "fixture", "launcher_sha256": "0" * 64}
        ):
            self.job = self.renders.queue(APP, {"data": self.request, "request_key": "publication-fixture"})

        def render(folder, scene, alive, submitted, sources=None):
            alive()
            submitted("bld_20261024_TEST1234")
            (folder / "video.mp4").write_bytes(RAW)
            return dict(
                build_id="bld_20261024_TEST1234",
                artifact=dict(sha256=hashlib.sha256(RAW).hexdigest(), bytes=len(RAW), metadata=META),
                cleanup=dict(worker="STOPPED"),
                publication="NOT_RUN",
                visual_review="REQUIRED",
            )

        with patch("mission_control.hypit_jobs.render", side_effect=render):
            self.assertTrue(run_once(self.store))
        self.render_id = self.renders.list(APP)["items"][0]["id"]

    def draft(self, metadata=None):
        from mission_control.publication_artifacts import describe

        info = describe(self.store, APP, self.render_id)
        return dict(
            schema="wmm.organic-publication.v1",
            request_id=uid(),
            app_id=APP,
            manifest_version=self.store.app(APP)["version"],
            provider="linkedin",
            connection_id=uid(),
            connection_version=1,
            destination_id="profile1",
            kind="linkedin_video",
            title="Fixture video",
            caption="Synthetic test copy",
            link=None,
            artifact={"id": self.render_id, "sha256": info["sha256"]},
            rights_hashes=info["rights_hashes"],
            source_hashes=info["source_hashes"],
            settings={"visibility": "PUBLIC"},
        )

    def test_describe_verify_and_load_bind_exact_app_artifact_and_source(self):
        info = describe(self.store, APP, self.render_id)
        self.assertEqual(info["source_hashes"], [self.brief_hash])
        self.assertEqual(info["rights_basis"], "OWNER_ORIGINAL_RENDER_CONFIRMATION_REQUIRED")
        self.assertNotIn("path", info)
        draft = self.draft()
        with connection(self.store.path) as db:
            binding = verify(self.store, db, APP, draft)
        self.assertEqual(binding["artifact_sha256"], info["sha256"])
        self.assertEqual(binding["rights_hashes"], draft["rights_hashes"])
        with (
            patch("mission_control.hypit_media.probe", return_value={"fixture": True}),
            patch("mission_control.hypit_media.metadata", return_value=META),
        ):
            loaded = load(self.store, APP, draft)
        self.assertEqual(
            (loaded["raw"], loaded["sha256"], loaded["bytes"]), (RAW, hashlib.sha256(RAW).hexdigest(), len(RAW))
        )
        self.assertEqual(loaded["fps"], 24.0)
        with self.assertRaises(Invalid):
            describe(self.store, "sample-two", self.render_id)

    def test_changed_artifact_and_forged_hash_fail_closed(self):
        draft = self.draft()
        path = private_path(self.store, APP, "artifacts", self.render_id + ".mp4")
        path.write_bytes(RAW + b"!")
        with connection(self.store.path) as db, self.assertRaises(Invalid):
            verify(self.store, db, APP, draft)
        with self.assertRaises(Invalid):
            load(self.store, APP, draft)
        draft["artifact"]["sha256"] = "0" * 64
        with connection(self.store.path) as db, self.assertRaises(Invalid):
            verify(self.store, db, APP, draft, verify_bytes=False)

    def test_text_copy_binding_is_exact_and_requires_separate_owner_confirmation(self):
        from mission_control.publication_contract import validate_draft
        from mission_control.publication_artifacts import verify

        text = dict(
            schema="wmm.organic-publication.v1",
            request_id=uid(),
            app_id=APP,
            manifest_version=self.store.app(APP)["version"],
            provider="linkedin",
            connection_id=uid(),
            connection_version=1,
            destination_id="profile1",
            kind="linkedin_text",
            title="",
            caption="Original copy",
            link=None,
            artifact=None,
            rights_hashes=[
                digest({"kind": "OWNER_ORIGINAL_COPY", "title": "", "caption": "Original copy", "link": None})
            ],
            source_hashes=[],
            settings={"visibility": "PUBLIC"},
        )
        with connection(self.store.path) as db:
            result = verify(self.store, db, APP, validate_draft(text))
        self.assertEqual(result["rights_basis"], "OWNER_ORIGINAL_COPY_CONFIRMATION_REQUIRED")
        text["caption"] += " edited"
        with connection(self.store.path) as db, self.assertRaises(Invalid):
            verify(self.store, db, APP, text)

    def test_stale_app_revision_rejects_even_if_saved_file_is_unchanged(self):
        draft = self.draft()
        current = self.store.app(APP)
        self.store.save_app(APP, current["data"], version=current["version"])
        with connection(self.store.path) as db, self.assertRaises(Invalid):
            verify(self.store, db, APP, draft, verify_bytes=False)

    def test_managed_source_review_is_fingerprinted_and_rechecked(self):
        from mission_control.managed_media_store import Media
        from mission_control.review_access import Access

        source_raw = b"synthetic owner-reviewed footage"
        owner = {"principal": "github:321", "login": "owner"}
        Access(self.store).bootstrap(APP, owner, {"confirm_owner": True})

        def inspect(data, suffix, alive):
            return {
                "sha256": hashlib.sha256(data).hexdigest(),
                "bytes": len(data),
                "metadata": {
                    "codec": "h264",
                    "width": 720,
                    "height": 1280,
                    "duration_seconds": 30.0,
                    "frame_rate": 24.0,
                    "audio": False,
                },
                "decoded": {"video_frames": 720, "audio_frames": 0},
            }

        media = Media(self.store, inspector=inspect)
        version = self.store.app(APP)["version"]
        item = media.upload(
            APP, "source.mp4", source_raw, {"manifest_version": version, "request_key": "publication-source"}
        )
        review = dict(
            expected_version=0,
            manifest_version=version,
            source_sha256=item["source_sha256"],
            status="ALLOWED",
            basis="OWNED",
            evidence="Synthetic fixture owner attestation.",
        )
        item = media.review(APP, item["id"], review, owner)
        footage = dict(scene_index=0, id=item["id"], sha256=item["source_sha256"], in_frame=0, audio="MUTE")
        with patch(
            "mission_control.hypit_jobs.identity", return_value={"launcher": "fixture", "launcher_sha256": "0" * 64}
        ):
            self.renders.queue(
                APP, {"data": dict(self.request, footage=[footage]), "request_key": "publication-managed"}
            )

        def render(folder, scene, alive, submitted, sources):
            alive()
            submitted("bld_20261024_TEST1234")
            self.assertEqual(sources[0], source_raw)
            (folder / "video.mp4").write_bytes(RAW)
            return dict(
                build_id="bld_20261024_TEST1234",
                artifact=dict(sha256=hashlib.sha256(RAW).hexdigest(), bytes=len(RAW), metadata=META),
                cleanup=dict(worker="STOPPED"),
                publication="NOT_RUN",
                visual_review="REQUIRED",
            )

        with patch("mission_control.hypit_jobs.render", side_effect=render):
            self.assertTrue(run_once(self.store))
        render_id = self.renders.list(APP)["items"][0]["id"]
        info = describe(self.store, APP, render_id)
        self.assertEqual(info["source_hashes"], sorted([self.brief_hash, item["source_sha256"]]))
        self.assertEqual(info["rights_basis"], "CURRENT_OWNER_SOURCE_ATTESTATIONS")
        draft = self.draft()
        draft["artifact"] = {"id": render_id, "sha256": info["sha256"]}
        draft["rights_hashes"] = info["rights_hashes"]
        draft["source_hashes"] = info["source_hashes"]
        with connection(self.store.path) as db:
            verify(self.store, db, APP, draft)
        media.review(APP, item["id"], dict(review, expected_version=1, status="REVOKED"), owner)
        with connection(self.store.path) as db, self.assertRaises(Invalid):
            verify(self.store, db, APP, draft)


if __name__ == "__main__":
    unittest.main()
