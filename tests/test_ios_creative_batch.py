"""Native creative packet source binding with isolated synthetic assets."""
import copy
import sqlite3
import tempfile
import time
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from mission_control.common import Invalid
from mission_control.creative_batches import Batch
from mission_control.creative_rendering import render_request
from mission_control.db import connection, initialize
from mission_control.ios_creative_batch import native_ack_stopped, native_artifact, native_finish, native_packet, native_source, native_source_for_job, native_start, native_validate
from mission_control.ios_host import NativeIdentities
from mission_control.operation_authority import bound_owner, protected
from mission_control.review_access import Access
from mission_control.store import Store
from tests.test_creative_rendering import APP, prepared_render


class NativeCreativeBatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "state.sqlite")
        _, self.request = prepared_render(self.store)

    def tearDown(self):
        self.tmp.cleanup()

    def test_exact_scene_timing_and_app_scoped_actual_still(self):
        with connection(self.store.path) as db:
            variant = render_request(db, self.store, APP, self.request)
            packet = native_packet(db, self.store, APP, variant)
            self.assertEqual(sum(s["frame_count"] for s in packet["scenes"]), packet["frame_count"])
            self.assertEqual([s["caption"] for s in packet["scenes"]], variant["captions"])
            scene = packet["scenes"][0]
            path = native_source(db, self.store, APP, packet, scene["source_id"], scene["source_hash"])
            self.assertTrue(path.is_file())
            for app, source_id, sha in (("sample-two", scene["source_id"], scene["source_hash"]),
                                        (APP, "../other.png", scene["source_hash"]),
                                        (APP, scene["source_id"], "0" * 64)):
                with self.subTest(source=source_id, app=app), self.assertRaises(Invalid):
                    native_source(db, self.store, app, packet, source_id, sha)
            forged = copy.deepcopy(packet); forged["scenes"][0]["caption"] = "invented"
            with self.assertRaises(Invalid):
                native_source(db, self.store, APP, forged, scene["source_id"], scene["source_hash"])
            path.write_bytes(b"changed")
            with self.assertRaises(Invalid):
                native_source(db, self.store, APP, packet, scene["source_id"], scene["source_hash"])

    def test_native_start_rechecks_owner_and_does_not_duplicate_interrupted_claim(self):
        principal, generation, session = str(uuid4()), str(uuid4()), str(uuid4())
        identity = NativeIdentities(lambda _: dict(principal=principal, session_generation=generation,
                                                    expires_at_epoch=time.time() + 300))
        user = identity.fresh(session)
        Access(self.store).bootstrap(APP, user, {"confirm_owner": True})
        expires = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        plan = Batch(self.store).plan(APP, dict(variants=[self.request], max_total_frames=1440,
                                                runtime="IOS", expires=expires))
        body = dict(plan=plan["plan_json"], plan_hash=plan["plan_hash"], request_key="ios-fixture")
        envelope = dict(app_id=APP, operation="creative.batch.create", input=body)
        with bound_owner(self.store, envelope, identity, session, user), protected(self.store, envelope):
            batch = Batch(self.store).create(APP, body)
        with self.assertRaises(PermissionError):
            native_start(self.store, APP, batch["id"], 0)
        action = dict(app_id=APP, operation="native.batch.start", input={"batch_id": batch["id"], "ordinal": 0})
        with bound_owner(self.store, action, identity, session, user), protected(self.store, action):
            started = native_start(self.store, APP, batch["id"], 0)
            self.assertEqual(started["status"], "RUNNING")
            self.assertEqual(native_start(self.store, APP, batch["id"], 0)["status"], "RECONCILE_REQUIRED")
            self.assertEqual(native_validate(self.store, APP, batch["id"], 0, started["packet"]["packet_hash"])["job_id"], started["job_id"])
            scene = started["packet"]["scenes"][0]
            self.assertTrue(native_source_for_job(self.store, APP, batch["id"], 0, started["packet"]["packet_hash"], scene["source_id"], scene["source_hash"]).is_file())
            with self.assertRaises(Invalid):
                native_finish(self.store, APP, batch["id"], 0, started["packet"]["packet_hash"], {})
            with self.assertRaises(Invalid):
                native_artifact(self.store, APP, batch["id"], 0)
            with self.assertRaises(Invalid):
                native_validate(self.store, APP, batch["id"], 0, "0" * 64)
        cancellation = dict(app_id=APP, operation="creative.batch.cancel", input={"batch_id": batch["id"]})
        with bound_owner(self.store, cancellation, identity, session, user), protected(self.store, cancellation):
            self.assertEqual(Batch(self.store).cancel(APP, batch["id"])["state"], "CANCEL_PENDING_HOLD")
        ack = dict(app_id=APP, operation="native.creative.batch.stopped", input={"batch_id": batch["id"], "ordinal": 0, "packet_hash": started["packet"]["packet_hash"]})
        with bound_owner(self.store, ack, identity, session, user), protected(self.store, ack):
            with self.assertRaises(Invalid):
                native_ack_stopped(self.store, APP, batch["id"], 0, "0" * 64)
            self.assertEqual(native_ack_stopped(self.store, APP, batch["id"], 0, started["packet"]["packet_hash"])["status"], "STOPPED")
        self.assertEqual(Batch(self.store).list(APP)["items"][0]["state"], "CANCELLED")

    def test_old_variant_schema_upgrade_preserves_rows_and_is_repeatable(self):
        path = Path(self.tmp.name) / "legacy.sqlite"
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("CREATE TABLE apps(id TEXT PRIMARY KEY,data TEXT NOT NULL,version INTEGER NOT NULL,updated TEXT NOT NULL)")
            db.execute("INSERT INTO apps VALUES('legacy','{}',1,'fixture')")
            db.execute("CREATE TABLE creative_batches(app_id TEXT NOT NULL,id TEXT NOT NULL,request_key TEXT NOT NULL,request_hash TEXT NOT NULL,plan TEXT NOT NULL,plan_hash TEXT NOT NULL,state TEXT NOT NULL,reserved_frames INTEGER NOT NULL,created TEXT NOT NULL,updated TEXT NOT NULL,PRIMARY KEY(app_id,id),UNIQUE(app_id,request_key))")
            db.execute("INSERT INTO creative_batches VALUES('legacy','batch','key','hash','{}','hash','ACTIVE',360,'fixture','fixture')")
            db.execute("CREATE TABLE creative_batch_variants(app_id TEXT NOT NULL,batch_id TEXT NOT NULL,ordinal INTEGER NOT NULL,request_key TEXT NOT NULL,request TEXT NOT NULL,request_hash TEXT NOT NULL,job_id TEXT,inspection TEXT,inspection_hash TEXT,PRIMARY KEY(app_id,batch_id,ordinal),UNIQUE(app_id,request_key))")
            db.execute("INSERT INTO creative_batch_variants VALUES('legacy','batch',0,'child','{}','hash','job',NULL,NULL)")
        initialize(path); initialize(path)
        with connection(path) as db:
            row = db.execute("SELECT * FROM creative_batch_variants WHERE app_id='legacy'").fetchone()
            self.assertEqual((row["request_key"], row["job_id"], row["native_state"], row["native_packet_hash"]),
                             ("child", "job", "PREPARED", None))


if __name__ == "__main__":
    unittest.main()
