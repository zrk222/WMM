"""Real video frame checks and store-bound publication denial."""

import importlib.util
import shutil
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path

from mission_control.common import Invalid, canonical
from mission_control.video_download_qr import download_target, stamp_download_qr, verify_download_qr


class DownloadQrTests(unittest.TestCase):
    def test_only_current_store_is_allowed_to_publish(self) -> None:
        with sqlite3.connect(":memory:") as db:
            db.row_factory = sqlite3.Row
            db.execute("CREATE TABLE apps(id TEXT PRIMARY KEY, data TEXT)")
            db.executemany(
                "INSERT INTO apps VALUES(?,?)",
                [
                    ("apple", canonical({"store_app_id": "123456789", "android_package": "test.other.store"})),
                    ("android", canonical({"android_package": "example.synthetic.sample"})),
                    ("not-ready", canonical({"website": "https://example.com/download"})),
                ],
            )
            apple = download_target(db, "apple")
            android = download_target(db, "android")
            self.assertIsNotNone(apple)
            self.assertIsNotNone(android)
            assert apple and android
            self.assertEqual(apple["url"], "https://apps.apple.com/app/id123456789")
            self.assertEqual(android["url"], "https://play.google.com/store/apps/details?id=example.synthetic.sample")
            artifact = {"inputs": {"download_qr": apple}, "receipt": {"download_qr": apple}}
            self.assertEqual(verify_download_qr(db, "apple", artifact), apple)
            disabled = {"inputs": {"download_qr": False}, "receipt": {}}
            self.assertIsNone(verify_download_qr(db, "not-ready", disabled))
            with self.assertRaisesRegex(Invalid, "saved video choice"):
                verify_download_qr(db, "apple", dict(disabled, receipt={"download_qr": apple}))
            with self.assertRaisesRegex(Invalid, "App setup"):
                verify_download_qr(db, "not-ready", artifact)
            with self.assertRaisesRegex(Invalid, "render|Render"):
                verify_download_qr(db, "android", artifact)
            with self.assertRaisesRegex(Invalid, "render|Render"):
                verify_download_qr(db, "apple", {"inputs": {"download_qr": apple}, "receipt": {}})
            db.execute("UPDATE apps SET data=? WHERE id='apple'", (canonical({"store_app_id": "987654321"}),))
            with self.assertRaisesRegex(Invalid, "render|Render"):
                verify_download_qr(db, "apple", artifact)

    @unittest.skipUnless(shutil.which("ffmpeg"), "requires FFmpeg")
    def test_qr_persists_to_last_encoded_frame(self) -> None:
        ffmpeg = shutil.which("ffmpeg")
        assert ffmpeg
        cases = (
            ((720, 1280), "https://apps.apple.com/app/id123456789"),
            ((1280, 720), "https://play.google.com/store/apps/details?id=example.synthetic.sample"),
        )
        for (width, height), url in cases:
            with self.subTest(url=url), tempfile.TemporaryDirectory() as temporary:
                folder = Path(temporary)
                video = folder / "video.mp4"
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
                        f"color=c=0x102124:s={width}x{height}:r=24:d=1",
                        "-c:v",
                        "libx264",
                        str(video),
                    ],
                    check=True,
                    capture_output=True,
                    timeout=20,
                )
                stamp_download_qr(
                    folder, (width, height), {"schema": "wmm.video-download-qr.v1", "url": url}, lambda: None
                )
                # Test the actual H.264 output even on CI hosts with no QR decoder installed.
                _, dimensions, _, pixels = (folder / "download-qr.pgm").read_bytes().split(b"\n", 3)
                size = int(dimensions.split()[0])
                x, y = (42, 50) if width == 720 else (76, 28)
                raw = subprocess.run(
                    [
                        ffmpeg,
                        "-hide_banner",
                        "-loglevel",
                        "error",
                        "-i",
                        str(video),
                        "-vf",
                        rf"select=eq(n\,0)+eq(n\,23),crop={size}:{size}:{x}:{y},format=gray",
                        "-fps_mode",
                        "passthrough",
                        "-frames:v",
                        "2",
                        "-f",
                        "rawvideo",
                        "pipe:1",
                    ],
                    check=True,
                    capture_output=True,
                    timeout=20,
                ).stdout
                self.assertEqual(len(raw), 2 * len(pixels))
                for offset in (0, len(pixels)):
                    disagreements = sum(
                        (output > 127) != (original > 127)
                        for output, original in zip(raw[offset : offset + len(pixels)], pixels, strict=True)
                    )
                    self.assertLess(disagreements, len(pixels) // 100)
                if importlib.util.find_spec("cv2"):
                    self._verify_scans(video, (width, height), url)

    def _verify_scans(self, video: Path, size: tuple[int, int], url: str) -> None:
        cv2 = importlib.import_module("cv2")

        stream, scanner = cv2.VideoCapture(str(video)), cv2.QRCodeDetector()
        try:
            self.assertEqual(int(stream.get(cv2.CAP_PROP_FRAME_COUNT)), 24)
            for number in (0, 23):
                stream.set(cv2.CAP_PROP_POS_FRAMES, number)
                ok, frame = stream.read()
                self.assertTrue(ok)
                self.assertEqual(scanner.detectAndDecode(frame)[0], url)
                smaller = cv2.resize(frame, (size[0] // 2, size[1] // 2), interpolation=cv2.INTER_AREA)
                self.assertEqual(scanner.detectAndDecode(smaller)[0], url)
        finally:
            stream.release()
