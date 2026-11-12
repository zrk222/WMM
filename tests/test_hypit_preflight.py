"""Read-only planning and exact retained-result reuse using isolated SQLite."""

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4
from mission_control.common import Invalid, canonical, digest, now
from mission_control.db import connection
from mission_control.hypit_authoring import project
from mission_control.hypit_jobs import HypitRenders, artifact_file
from mission_control.store import Store
from mission_control.worker import jobs, run_once
from tests.test_creative_rendering import prepared_render

APP = "render-test"
MEDIA = b"fixture bytes: artifact identity only, not a decoded video"


class HypitPreflightTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name) / "state.sqlite")
        self.brief, self.request = prepared_render(self.store)
        self.renders = HypitRenders(self.store)
        self.launcher = patch(
            "mission_control.hypit_jobs.identity", return_value={"launcher": "fixture", "launcher_sha256": "a" * 64}
        )
        self.launcher.start()
        self.addCleanup(self.launcher.stop)
        self.tools = patch(
            "mission_control.hypit_preflight.media_capability",
            return_value={"tools": {"ffmpeg": "private-ffmpeg-path", "ffprobe": None}, "font": None},
        )
        self.tools.start()
        self.addCleanup(self.tools.stop)

    def retain(self):
        self.renders.queue(APP, {"data": self.request, "request_key": "fixture-render"})

        def render(folder, scene, alive, submitted):
            alive()
            submitted("bld_20261024_TEST1234")
            (folder / "video.mp4").write_bytes(MEDIA)
            return dict(
                build_id="bld_20261024_TEST1234",
                source=project(scene)["receipt"],
                artifact={"sha256": hashlib.sha256(MEDIA).hexdigest(), "bytes": len(MEDIA)},
                publication="NOT_RUN",
                visual_review="REQUIRED",
            )

        with patch("mission_control.hypit_jobs.render", side_effect=render):
            self.assertTrue(run_once(self.store))
        return self.renders.list(APP)["items"][0]["id"]

    def test_plan_is_read_only_and_advisory(self):
        with (
            patch("mission_control.worker.enqueue", side_effect=AssertionError("enqueue")),
            patch("mission_control.hypit_jobs.render", side_effect=AssertionError("render")),
            patch("mission_control.hypit_runtime.invoke", side_effect=AssertionError("runtime")),
            patch("mission_control.hypit_preflight.shutil.which", return_value=None),
        ):
            plan = self.renders.plan(APP, {"data": self.request})
        self.assertEqual(jobs(self.store, APP), [])
        self.assertEqual(plan["authoring_mode"], "APPROVED_BRIEF_CAPTIONS")
        self.assertEqual(plan["visual_review"], "REQUIRED")
        self.assertEqual(plan["readability"]["kind"], "ADVISORY_HEURISTIC")
        self.assertEqual(plan["readiness"]["compiler"], "NOT_CHECKED")
        self.assertEqual(plan["readiness"]["browser_and_endpoints"], "NOT_CHECKED")
        self.assertFalse(plan["readiness"]["font_detected"])
        self.assertFalse(plan["readiness"]["ffprobe_detected"])
        self.assertFalse(plan["readiness"]["node_detected"])
        self.assertNotIn("private-ffmpeg-path", canonical(plan))
        self.assertEqual(plan["scene"]["scenes"][0]["start_seconds"], 0)
        self.assertEqual(plan["scene"]["scenes"][-1]["end_seconds"], plan["scene"]["duration_seconds"])
        self.assertEqual(plan["reuse_candidates"]["items"], [])
        self.assertEqual(len(plan["input_hash"]), 64)
        self.assertEqual(len(plan["source_hash"]), 64)

    def test_plan_rejects_unverified_managed_source_without_queue(self):
        data = dict(
            self.request,
            footage=[
                dict(
                    scene_index=0, id="11111111-1111-1111-1111-111111111111", sha256="a" * 64, in_frame=0, audio="MUTE"
                )
            ],
        )
        with self.assertRaises(Invalid):
            self.renders.plan(APP, {"data": data})
        self.assertEqual(jobs(self.store, APP), [])

    def test_explicit_reuse_rechecks_artifact_without_enqueue_or_build(self):
        identity = self.retain()
        before = jobs(self.store, APP)
        with (
            patch("mission_control.worker.enqueue", side_effect=AssertionError("enqueue")),
            patch("mission_control.hypit_jobs.render", side_effect=AssertionError("render")),
            patch("mission_control.hypit_runtime.invoke", side_effect=AssertionError("runtime")),
        ):
            plan = self.renders.plan(APP, {"data": self.request})
            self.assertEqual([row["render_id"] for row in plan["reuse_candidates"]["items"]], [identity])
            receipt = self.renders.reuse(
                APP, {"data": self.request, "render_id": identity, "source_hash": plan["source_hash"]}
            )
        self.assertEqual(receipt["artifact_hash"], hashlib.sha256(MEDIA).hexdigest())
        self.assertTrue(receipt["reused"])
        self.assertFalse(receipt["job_created"])
        self.assertFalse(receipt["build_started"])
        self.assertEqual(receipt["visual_review"], "REQUIRED")
        self.assertEqual(jobs(self.store, APP), before)

    def test_missing_modified_and_bad_provenance_are_not_reused(self):
        identity = self.retain()
        plan = self.renders.plan(APP, {"data": self.request})
        body = {"data": self.request, "render_id": identity, "source_hash": plan["source_hash"]}
        path, _ = artifact_file(self.store, APP, identity)
        path.write_bytes(b"changed")
        self.assertEqual(self.renders.plan(APP, {"data": self.request})["reuse_candidates"]["items"], [])
        with self.assertRaises(Invalid):
            self.renders.reuse(APP, body)
        path.unlink()
        with self.assertRaises(Invalid):
            self.renders.reuse(APP, body)
        path.write_bytes(MEDIA)
        with connection(self.store.path) as db:
            row = db.execute("SELECT data FROM hypit_renders WHERE app_id=? AND id=?", (APP, identity)).fetchone()
            data = json.loads(row["data"])
            data["receipt"]["source"]["source_hashes"]["film.svml"] = "0" * 64
            db.execute(
                "UPDATE hypit_renders SET data=?,hash=? WHERE app_id=? AND id=?",
                (canonical(data), digest(data), APP, identity),
            )
        self.assertEqual(self.renders.plan(APP, {"data": self.request})["reuse_candidates"]["items"], [])
        with self.assertRaises(Invalid):
            self.renders.reuse(APP, body)

    def test_result_and_artifact_receipts_must_match(self):
        identity = self.retain()
        plan = self.renders.plan(APP, {"data": self.request})
        with connection(self.store.path) as db:
            row = db.execute("SELECT data FROM hypit_renders WHERE app_id=? AND id=?", (APP, identity)).fetchone()
            data = json.loads(row["data"])
            data["receipt"]["artifact"]["sha256"] = "0" * 64
            db.execute(
                "UPDATE hypit_renders SET data=?,hash=? WHERE app_id=? AND id=?",
                (canonical(data), digest(data), APP, identity),
            )
        self.assertEqual(self.renders.plan(APP, {"data": self.request})["reuse_candidates"]["items"], [])
        with self.assertRaises(Invalid):
            self.renders.reuse(APP, {"data": self.request, "render_id": identity, "source_hash": plan["source_hash"]})

    def test_artifact_size_receipt_must_match_actual_bytes(self):
        identity = self.retain()
        plan = self.renders.plan(APP, {"data": self.request})
        with connection(self.store.path) as db:
            row = db.execute("SELECT data FROM hypit_renders WHERE app_id=? AND id=?", (APP, identity)).fetchone()
            data = json.loads(row["data"])
            data["artifact"]["bytes"] += 1
            db.execute(
                "UPDATE hypit_renders SET data=?,hash=? WHERE app_id=? AND id=?",
                (canonical(data), digest(data), APP, identity),
            )
        self.assertEqual(self.renders.plan(APP, {"data": self.request})["reuse_candidates"]["items"], [])
        with self.assertRaises(Invalid):
            self.renders.reuse(APP, {"data": self.request, "render_id": identity, "source_hash": plan["source_hash"]})

    def test_stale_foreign_or_changed_source_cannot_be_selected(self):
        identity = self.retain()
        plan = self.renders.plan(APP, {"data": self.request})
        body = {"data": self.request, "render_id": identity, "source_hash": plan["source_hash"]}
        with self.assertRaises(Invalid):
            self.renders.reuse(APP, {**body, "source_hash": "0" * 64})
        _, foreign = prepared_render(self.store, "foreign-render")
        foreign_plan = self.renders.plan("foreign-render", {"data": foreign})
        with self.assertRaises(Invalid):
            self.renders.reuse(
                "foreign-render", {"data": foreign, "render_id": identity, "source_hash": foreign_plan["source_hash"]}
            )
        app = self.store.app(APP)
        self.store.save_app(APP, dict(app["data"], name="Changed app"), app["version"])
        with self.assertRaises(Invalid):
            self.renders.plan(APP, {"data": self.request})
        with self.assertRaises(Invalid):
            self.renders.reuse(APP, body)

    def test_exact_input_and_runtime_source_changes_are_rejected(self):
        identity = self.retain()
        plan = self.renders.plan(APP, {"data": self.request})
        body = {"data": self.request, "render_id": identity, "source_hash": plan["source_hash"]}
        other = {**self.request, "shape": "LANDSCAPE"}
        other_plan = self.renders.plan(APP, {"data": other})
        with self.assertRaises(Invalid):
            self.renders.reuse(APP, {"data": other, "render_id": identity, "source_hash": other_plan["source_hash"]})
        with patch("mission_control.hypit_preflight.source_hashes", return_value={"film.svml": "f" * 64}):
            with self.assertRaises(Invalid):
                self.renders.reuse(APP, body)

    def test_candidate_inventory_and_byte_checks_are_bounded(self):
        self.retain()
        with connection(self.store.path) as db:
            existing = db.execute("SELECT data,hash FROM hypit_renders WHERE app_id=?", (APP,)).fetchone()
            for i in range(55):
                job = str(uuid4())
                render = str(uuid4())
                stamp = "2100-01-01T00:00:%02dZ" % (i % 60)
                db.execute(
                    "INSERT INTO jobs(id,app_id,action,data,status,created,updated,request_key) VALUES(?,?,?,?,?,?,?,?)",
                    (job, APP, "hypit_render", "{}", "SUCCEEDED", stamp, stamp, "fixture-" + str(i)),
                )
                db.execute(
                    "INSERT INTO hypit_renders VALUES(?,?,?,?,?,?)",
                    (APP, render, job, existing["data"], existing["hash"], stamp),
                )
        result = self.renders.plan(APP, {"data": self.request})["reuse_candidates"]
        self.assertLessEqual(result["scanned"], 50)
        self.assertLessEqual(result["verified_attempts"], 5)
        self.assertTrue(result["truncated"])
        self.assertEqual(result["items"], [])

    def test_rejects_extra_fields_and_never_submits_work(self):
        for body in (None, {}, {"data": self.request, "command": "run"}):
            with self.subTest(body=body), self.assertRaises(Invalid):
                self.renders.plan(APP, body)
        with self.assertRaises(Invalid):
            self.renders.reuse(APP, {"data": self.request, "render_id": "fake", "source_hash": "x", "command": "run"})
        self.assertEqual(jobs(self.store, APP), [])


if __name__ == "__main__":
    unittest.main()
