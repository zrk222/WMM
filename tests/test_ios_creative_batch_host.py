"""Real native host boundary for synthetic creative batch requests."""

import json
from pathlib import Path
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from mission_control.common import Invalid
from mission_control.ios_host import Runtime
from mission_control.review_access import Access
from mission_control.store import Store
from tests.test_creative_rendering import APP, prepared_render


class NativeCreativeBatchHostTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / "state.sqlite")
        _, self.request = prepared_render(self.store)
        self.principal, self.session, self.generation = str(uuid4()), str(uuid4()), str(uuid4())
        self.active = True
        self.runtime = Runtime(self.store.path, self.verify)
        Access(self.store).bootstrap(APP, self.runtime.identities.fresh(self.session), {"confirm_owner": True})

    def verify(self, session):
        if not self.active or session != self.session:
            return None
        return dict(principal=self.principal, session_generation=self.generation, expires_at_epoch=time.time() + 300)

    @staticmethod
    def data(value):
        return json.dumps(value).encode()

    def owner(self, operation, body):
        return json.loads(
            self.runtime.owner_call(self.session, self.data(dict(app_id=APP, operation=operation, input=body)))
        )

    def test_host_start_and_source_recheck_current_owner(self):
        expires = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
        planned = self.owner(
            "creative.batch.plan", dict(variants=[self.request], max_total_frames=1440, runtime="IOS", expires=expires)
        )
        batch = self.owner(
            "creative.batch.create",
            dict(plan=planned["plan_json"], plan_hash=planned["plan_hash"], request_key="synthetic-host-test"),
        )
        body = dict(batch_id=batch["id"], ordinal=0)
        started = json.loads(self.runtime.native_creative_batch(self.session, APP, "start", self.data(body)))
        self.assertEqual(started["status"], "RUNNING")
        packet = started["packet"]
        scene = packet["scenes"][0]
        source = dict(
            **body, packet_hash=packet["packet_hash"], source_id=scene["source_id"], sha256=scene["source_hash"]
        )
        location = json.loads(self.runtime.native_creative_batch_source(self.session, APP, self.data(source)))
        self.assertTrue(Path(location["path"]).is_file())
        with self.assertRaises(Invalid):
            self.runtime.native_creative_batch(self.session, APP, "finish", self.data(body))
        with self.assertRaises(Invalid):
            self.runtime.native_creative_batch_source(self.session, APP, self.data(dict(source, sha256="0" * 64)))
        finish = dict(**body, packet_hash=packet["packet_hash"])
        forged = dict(
            artifact_id=started["job_id"],
            sha256="0" * 64,
            bytes=1,
            frames=packet["frame_count"],
            width=720,
            height=1280,
            audio=False,
        )
        with self.assertRaises(Invalid):
            self.runtime.native_creative_batch_finish(self.session, APP, self.data(finish), self.data(forged))
        with self.assertRaises(Invalid):
            self.runtime.native_creative_batch_artifact(self.session, APP, self.data(body))
        self.active = False
        with self.assertRaises(PermissionError):
            self.runtime.native_creative_batch_source(self.session, APP, self.data(source))
        with self.assertRaises(PermissionError):
            self.runtime.native_creative_batch_artifact(self.session, APP, self.data(body))

    def test_host_still_upload_requires_fresh_owner_and_keeps_rights_unconfirmed(self):
        import base64

        png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aOZkAAAAASUVORK5CYII="
        )
        saved = json.loads(self.runtime.native_creative_still_upload(self.session, APP, "still.png", png))
        self.assertFalse(saved["data"]["authentic"])
        self.assertFalse(saved["data"]["rights_cleared"])
        self.assertTrue((self.store.path.parent / "files" / APP / saved["data"]["file_id"]).is_file())
        with self.assertRaises(Invalid):
            self.runtime.native_creative_still_upload(self.session, APP, "wrong.jpg", png)
        with self.assertRaises(Invalid):
            self.runtime.native_creative_still_upload(self.session, APP, "large.png", b"x" * 8388609)
        self.active = False
        with self.assertRaises(PermissionError):
            self.runtime.native_creative_still_upload(self.session, APP, "still.png", png)
