"""Exercise owner demo intake with synthetic MP4s and a disposable local store."""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from mission_control.common import Invalid
from mission_control.db import connection
from mission_control.managed_media_store import Media
from mission_control.managed_media_validation import inspect
from mission_control.operation_authority import REQUEST, bound_owner
from mission_control.organic_video_capture import SOURCE, demo_snapshot, import_owner_demo, intake_envelope
from mission_control.review_access import Access
from mission_control.store import Store


APP = "synthetic-demo"
OWNER = {"principal": "github:301", "login": "fixture-owner"}
CHECKER = {"principal": "github:302", "login": "fixture-checker"}
SELECTION = dict(
    request_id="demo-import-001",
    manifest_version=1,
    release="1.0",
    filename="demo.mp4",
    source=SOURCE,
    app_owned=True,
    contains_private_data=False,
    uses_personal_account=False,
)


class SyntheticIdentitySession:
    active = True

    def local(self, session, principal, generation=None):
        if not self.active or session != "fixture-session" or generation not in (None, "fixture-generation"):
            raise PermissionError("Synthetic owner session changed")
        return {"session_generation": "fixture-generation"}


class OrganicVideoCaptureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        folder = tempfile.TemporaryDirectory()
        cls.addClassCleanup(folder.cleanup)
        path = Path(folder.name) / "synthetic.mp4"
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg or not shutil.which("ffprobe"):
            raise RuntimeError("FFmpeg and FFprobe are required for actual organic demo intake proof")
        subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-nostdin",
                "-f",
                "lavfi",
                "-i",
                "color=c=blue:s=64x64:r=24",
                "-t",
                "1",
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-pix_fmt",
                "yuv420p",
                "-y",
                str(path),
            ],
            capture_output=True,
            timeout=40,
            check=True,
        )
        cls.raw = path.read_bytes()

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.store = Store(self.root / "state.sqlite", seed=False)
        self.media = Media(self.store)
        self.sessions = SyntheticIdentitySession()
        self.store.save_app(APP, {"name": "Synthetic Demo App", "release": "1.0"})
        access = Access(self.store)
        access.bootstrap(APP, OWNER, {"confirm_owner": True})
        access.save(APP, OWNER, CHECKER, dict(login=CHECKER["login"], role="CHECKER", status="ACTIVE", version=None))

    def import_demo(self, selection=None, raw=None, user=OWNER, app_id=APP):
        selection = dict(SELECTION) if selection is None else selection
        raw = self.raw if raw is None else raw
        envelope = intake_envelope(app_id, selection, raw)
        with bound_owner(self.store, envelope, self.sessions, "fixture-session", user):
            return import_owner_demo(self.store, app_id, selection, raw)

    def review(self, receipt, *, status="ALLOWED", basis="OWNED", expected_version=0, manifest_version=1):
        return self.media.review(
            APP,
            receipt["media_id"],
            dict(
                expected_version=expected_version,
                manifest_version=manifest_version,
                source_sha256=receipt["source_sha256"],
                status=status,
                basis=basis,
                evidence="Synthetic app-owned fixture for local testing.",
            ),
            OWNER,
        )

    def snapshot(self, receipt, *, capture=False):
        with connection(self.store.path) as db:
            db.execute("BEGIN")
            return demo_snapshot(db, self.store, APP, receipt["media_id"], receipt["source_sha256"], capture=capture)

    def stored_counts(self):
        with connection(self.store.path) as db:
            rows = db.execute("SELECT count(*) FROM managed_media").fetchone()[0]
        return rows, sum(path.is_file() for path in (self.root / "managed-media").rglob("*"))

    def test_real_import_replays_and_requires_separate_current_owned_rights(self):
        receipt = self.import_demo()
        self.assertEqual(receipt, self.import_demo())
        self.assertEqual(self.stored_counts(), (1, 1))
        self.assertEqual(receipt["source_sha256"], hashlib.sha256(self.raw).hexdigest())
        self.assertEqual(receipt["byte_count"], len(self.raw))
        saved = self.media.read(APP, receipt["media_id"])
        self.assertEqual(saved["hash"], receipt["media_record_sha256"])
        self.assertGreater(saved["decoded"]["video_frames"], 0)
        self.assertEqual(saved["rights_status"], "UNKNOWN")
        self.assertEqual(saved["review_history"], [])
        self.assertEqual(saved["provenance"]["kind"], SOURCE)
        self.assertEqual(saved["provenance"]["owner_principal"], OWNER["principal"])
        self.assertNotIn(SELECTION["request_id"], json.dumps(receipt))
        self.assertNotIn("storage_name", json.dumps(receipt))
        with self.assertRaisesRegex(Invalid, "attestation"):
            self.snapshot(receipt)
        self.review(receipt, basis="LICENSED")
        with self.assertRaisesRegex(Invalid, "OWNED basis"):
            self.snapshot(receipt)
        self.review(receipt, expected_version=1)
        item, raw = self.snapshot(receipt, capture=True)
        self.assertEqual(item["hash"], receipt["media_record_sha256"])
        self.assertEqual(raw, self.raw)
        self.review(receipt, status="REVOKED", expected_version=2)
        with self.assertRaisesRegex(Invalid, "attestation"):
            self.snapshot(receipt)

    def test_generic_owned_media_cannot_enter_organic_demo_path(self):
        generic = self.media.upload(APP, "generic.mp4", self.raw, dict(manifest_version=1, request_key="generic"))
        receipt = dict(media_id=generic["id"], source_sha256=generic["source_sha256"])
        self.review(receipt)
        with self.assertRaisesRegex(Invalid, "organic demo import"):
            self.snapshot(receipt)

    def test_snapshot_rejects_wrong_digest_and_changed_retained_bytes(self):
        receipt = self.import_demo()
        self.review(receipt)
        with self.assertRaisesRegex(Invalid, "Selected media digest changed"):
            self.snapshot(dict(receipt, source_sha256="0" * 64))
        original = self.media.resolve(APP, receipt["media_id"], receipt["source_sha256"])
        original.write_bytes(bytes([self.raw[0] ^ 1]) + self.raw[1:])
        with self.assertRaises(Invalid):
            self.snapshot(receipt, capture=True)

    def test_rejects_paths_urls_sessions_and_private_or_malformed_selection(self):
        bad = (
            {"filename": "C:\\demo.mp4"},
            {"filename": "../demo.mp4"},
            {"filename": "https://site.invalid/demo.mp4"},
            {"filename": "demo.mov"},
            {"source": "BROWSER_SESSION"},
            {"source": "URL_CAPTURE"},
            {"contains_private_data": True},
            {"uses_personal_account": True},
            {"app_owned": 1},
            {"path": "/demo.mp4"},
            {"url": "https://site.invalid/"},
            {"browser_session": "existing-session"},
            {"manifest_version": True},
            {"request_id": "x" * 101},
            {"release": "x" * 81},
        )
        for fields in bad:
            with self.subTest(fields=fields), self.assertRaises(Invalid):
                self.import_demo(dict(SELECTION, **fields))
        for raw in (b"", bytearray(self.raw)):
            with self.subTest(raw_type=type(raw)), self.assertRaisesRegex(Invalid, "64 MiB"):
                self.import_demo(raw=raw)
        with patch("mission_control.organic_video_capture.MAX_BYTES", len(self.raw) - 1):
            with self.assertRaisesRegex(Invalid, "64 MiB"):
                self.import_demo()
        with self.assertRaises(Invalid):
            self.import_demo(raw=b"not an MP4")
        self.assertEqual(self.stored_counts(), (0, 0))

    def test_requires_exact_owner_admission_for_app_request_and_bytes(self):
        with self.assertRaises(PermissionError):
            import_owner_demo(self.store, APP, SELECTION, self.raw)
        with self.assertRaises(PermissionError):
            self.import_demo(user=CHECKER)
        envelope = intake_envelope(APP, SELECTION, self.raw)
        token = REQUEST.set({"grant_id": "synthetic-agent-grant"})
        try:
            with self.assertRaises(PermissionError):
                import_owner_demo(self.store, APP, SELECTION, self.raw)
        finally:
            REQUEST.reset(token)
        with bound_owner(self.store, envelope, self.sessions, "fixture-session", OWNER):
            with self.assertRaisesRegex(PermissionError, "exact operation authority"):
                import_owner_demo(self.store, APP, SELECTION, self.raw + b"changed")
            with self.assertRaisesRegex(PermissionError, "exact operation authority"):
                import_owner_demo(self.store, APP, dict(SELECTION, request_id="other-request"), self.raw)
        self.store.save_app("other-app", {"name": "Other App", "release": "1.0"})
        with self.assertRaises(PermissionError):
            self.import_demo(app_id="other-app")
        self.assertEqual(self.stored_counts(), (0, 0))

    def test_request_id_rejects_changed_bytes_or_filename_and_concurrent_replays_converge(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            first, second = list(pool.map(lambda _: self.import_demo(), range(2)))
        self.assertEqual(first, second)
        with self.assertRaisesRegex(Invalid, "different media upload"):
            self.import_demo(raw=self.raw + b"changed")
        with self.assertRaisesRegex(Invalid, "different media upload"):
            self.import_demo(dict(SELECTION, filename="other.mp4"))
        self.assertEqual(self.stored_counts(), (1, 1))

    def test_current_release_and_manifest_are_required_for_import_and_snapshot(self):
        with self.assertRaisesRegex(Invalid, "current app release and manifest"):
            self.import_demo(dict(SELECTION, release="wrong-release"))
        with self.assertRaisesRegex(Invalid, "current app release and manifest"):
            self.import_demo(dict(SELECTION, manifest_version=2))
        receipt = self.import_demo()
        self.review(receipt)
        self.store.save_app(APP, {"name": "Synthetic Demo App", "release": "2.0"}, version=1)
        with self.assertRaisesRegex(Invalid, "current app release and manifest"):
            self.import_demo()
        self.review(receipt, expected_version=1, manifest_version=2)
        with self.assertRaisesRegex(Invalid, "current app release and manifest"):
            self.snapshot(receipt)
        self.assertEqual(self.stored_counts(), (1, 1))

    def test_session_expiry_during_actual_inspection_cannot_commit(self):
        def inspect_then_expire(*args, **kwargs):
            result = inspect(*args, **kwargs)
            self.sessions.active = False
            return result

        with patch("mission_control.managed_media_store.inspect", side_effect=inspect_then_expire):
            with self.assertRaisesRegex(PermissionError, "session changed"):
                self.import_demo()
        self.assertEqual(self.stored_counts(), (0, 0))
