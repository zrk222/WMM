"""Synthetic Page Reels transport: no external network or credentials."""

import hashlib
import hmac
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from mission_control.common import Invalid
from mission_control.campaign_transport import Unconfirmed
from mission_control.campaign_video_transport import Context, create, upload, read, publish


class ReelTransportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "synthetic.mp4"
        self.raw = b"synthetic-local-media"
        self.path.write_bytes(self.raw)
        self.artifact = dict(
            path=self.path, sha256=hashlib.sha256(self.raw).hexdigest(), bytes=len(self.raw), duration_seconds=4
        )
        self.receipt = dict(sha256=self.artifact["sha256"], bytes=len(self.raw))
        self.pulses = []
        self.context = Context("123", "synthetic-token", "synthetic-secret", lambda: self.pulses.append(1))
        self.calls = []
        self.proof = hmac.new(b"synthetic-secret", b"synthetic-token", hashlib.sha256).hexdigest()

    def fake(self, response):
        def request(parts, method, route, body, headers, alive, deadline):
            alive()
            raw = b"".join(body) if body is not None and not isinstance(body, bytes) else body
            self.calls.append((parts.scheme, parts.netloc, method, route, raw, dict(headers)))
            return response

        return request

    def test_create_exact_graph_route_and_pinned_returned_url(self):
        result = dict(video_id="456", upload_url="https://rupload.facebook.com/video-upload/v26.0/456")
        with patch("mission_control.campaign_video_transport.exchange", side_effect=self.fake(result)):
            self.assertEqual(create("123", {}, self.context), dict(video_id="456", state="CREATED"))
        scheme, host, method, route, body, headers = self.calls[0]
        self.assertEqual(
            (scheme, host, method, route), ("https", "graph.facebook.com", "POST", "/v26.0/me/video_reels")
        )
        self.assertEqual(parse_qs(body.decode()), {"upload_phase": ["start"], "appsecret_proof": [self.proof]})
        self.assertEqual(headers["Authorization"], "Bearer synthetic-token")
        self.assertNotIn("synthetic-token", repr(self.context))
        self.assertNotIn("synthetic-secret", repr(self.context))
        for url in (
            "https://evil.example/video-upload/v26.0/456",
            "https://rupload.facebook.com.evil.example/video-upload/v26.0/456",
            "https://rupload.facebook.com/video-upload/v26.0/457",
            "https://rupload.facebook.com/video-upload/v26.0/456?x=1",
        ):
            with (
                self.subTest(url=url),
                patch(
                    "mission_control.campaign_video_transport.exchange",
                    side_effect=self.fake(dict(result, upload_url=url)),
                ),
                self.assertRaises(Unconfirmed),
            ):
                create("123", {}, self.context)

    def test_upload_sends_exact_binary_to_fixed_host(self):
        with (
            patch("mission_control.campaign_video_transport.validate_video", return_value=self.receipt),
            patch("mission_control.campaign_video_transport.exchange", side_effect=self.fake({"success": True})),
        ):
            self.assertEqual(upload("456", self.artifact, self.context)["state"], "UPLOAD_ACKNOWLEDGED")
        scheme, host, method, route, body, headers = self.calls[0]
        self.assertEqual(
            (scheme, host, method, route, body),
            ("https", "rupload.facebook.com", "POST", "/video-upload/v26.0/456", self.raw),
        )
        self.assertEqual(
            (headers["Authorization"], headers["offset"], headers["file_size"], headers["Content-Length"]),
            ("OAuth synthetic-token", "0", str(len(self.raw)), str(len(self.raw))),
        )
        self.assertNotIn("appsecret_proof", headers)
        self.assertNotIn("synthetic-secret", repr(headers))
        self.assertGreaterEqual(len(self.pulses), 2)

    def test_decode_and_upload_use_captured_snapshot_when_original_changes(self):
        def inspect(snapshot, shape, seconds):
            self.assertNotEqual(snapshot, self.path)
            self.assertEqual(snapshot.read_bytes(), self.raw)
            self.path.write_bytes(b"changed after capture")
            return self.receipt

        with (
            patch("mission_control.campaign_video_transport.validate_video", side_effect=inspect),
            patch("mission_control.campaign_video_transport.exchange", side_effect=self.fake({"success": True})),
        ):
            self.assertEqual(upload("456", self.artifact, self.context)["state"], "UPLOAD_ACKNOWLEDGED")
        self.assertEqual(self.calls[0][4], self.raw)

    def test_upload_rejects_mismatch_before_network(self):
        for changes in (
            dict(sha256="0" * 64),
            dict(bytes=1),
            dict(bytes=True),
            dict(duration_seconds=3),
            dict(path="https://evil.example/video.mp4"),
            dict(extra="https://evil.example"),
        ):
            with (
                self.subTest(changes=changes),
                patch("mission_control.campaign_video_transport.validate_video", return_value=self.receipt),
                patch("mission_control.campaign_video_transport.exchange") as call,
                self.assertRaises(Invalid),
            ):
                upload("456", dict(self.artifact, **changes), self.context)
            call.assert_not_called()
        for identity in ("../456", "456?x=1", "https://evil.example", 1):
            with self.subTest(identity=identity), self.assertRaises(Invalid):
                upload(identity, self.artifact, self.context)

    def test_publish_and_read_keep_acknowledgements_and_phases_separate(self):
        with patch("mission_control.campaign_video_transport.exchange", side_effect=self.fake({"success": True})):
            self.assertEqual(
                publish("456", {"caption": "A test caption"}, self.context)["state"], "PUBLISH_ACKNOWLEDGED"
            )
        self.assertEqual(
            parse_qs(self.calls[0][4].decode()),
            dict(
                upload_phase=["finish"],
                video_id=["456"],
                video_state=["PUBLISHED"],
                description=["A test caption"],
                appsecret_proof=[self.proof],
            ),
        )
        value = dict(
            id="456",
            status=dict(
                video_status="processing",
                uploading_phase=dict(status="complete"),
                processing_phase=dict(status="in_progress"),
                publishing_phase=dict(status="not_started"),
            ),
        )
        with patch("mission_control.campaign_video_transport.exchange", side_effect=self.fake(value)):
            observed = read("456", self.context)
        self.assertEqual(observed["uploading_phase"], "complete")
        self.assertEqual(observed["video_status"], "processing")
        self.assertEqual(observed["publishing_phase"], "not_started")
        route = urlsplit(self.calls[-1][3])
        self.assertEqual(route.path, "/v26.0/456")
        self.assertEqual(parse_qs(route.query), dict(fields=["status"], appsecret_proof=[self.proof]))
        value["status"].update(
            video_status="ready", processing_phase=dict(status="complete"), publishing_phase=dict(status="complete")
        )
        with patch("mission_control.campaign_video_transport.exchange", side_effect=self.fake(value)):
            observed = read("456", self.context)
        self.assertEqual(observed["publishing_phase"], "complete")
        self.assertNotIn("publication_verified", observed)
        with (
            patch("mission_control.campaign_video_transport.exchange", return_value=dict(value, id="457")),
            self.assertRaises(Unconfirmed),
        ):
            read("456", self.context)

    def test_real_exchange_blocks_redirect_and_hides_provider_error(self):
        class Response:
            status = 302

        class Connection:
            def __init__(self, *args):
                pass

            def request(self, *args, **kwargs):
                pass

            def getresponse(self):
                return Response()

            def close(self):
                pass

        with (
            patch("mission_control.social_transport.address", return_value="1.1.1.1"),
            patch("mission_control.social_transport.PinnedHTTPS", Connection),
        ):
            with self.assertRaises(Unconfirmed) as error:
                create("123", {}, self.context)
        self.assertNotIn("synthetic-token", str(error.exception))
        with patch(
            "mission_control.campaign_video_transport.exchange",
            return_value={"error": {"message": "synthetic-token synthetic-secret"}},
        ):
            with self.assertRaises(Unconfirmed) as error:
                create("123", {}, self.context)
        self.assertNotIn("synthetic-token", str(error.exception))
        self.assertNotIn("synthetic-secret", str(error.exception))

    def test_graph_proof_changes_with_secret(self):
        result = dict(video_id="456", upload_url="https://rupload.facebook.com/video-upload/v26.0/456")
        other = Context("123", "synthetic-token", "another-secret", lambda: None)
        with patch("mission_control.campaign_video_transport.exchange", side_effect=self.fake(result)):
            create("123", {}, self.context)
            create("123", {}, other)
        first = parse_qs(self.calls[-2][4].decode())["appsecret_proof"][0]
        second = parse_qs(self.calls[-1][4].decode())["appsecret_proof"][0]
        self.assertEqual(first, self.proof)
        self.assertEqual(second, hmac.new(b"another-secret", b"synthetic-token", hashlib.sha256).hexdigest())
        self.assertNotEqual(first, second)

    def test_context_page_metadata_and_ids_are_closed(self):
        for call in (
            lambda: create("124", {}, self.context),
            lambda: create("123", {"url": "https://evil.example"}, self.context),
            lambda: create("123", {}, dict(token="x")),
            lambda: publish("456", {"caption": "text", "extra": 1}, self.context),
            lambda: publish("456", {"caption": "bad\x00"}, self.context),
            lambda: read("456/evil", self.context),
        ):
            with self.assertRaises(Invalid):
                call()

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "local FFmpeg and FFprobe required")
    def test_actual_decoded_profile_is_checked(self):
        subprocess.run(
            [
                shutil.which("ffmpeg"),
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=black:s=720x1280:r=24:d=4",
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-pix_fmt",
                "yuv420p",
                str(self.path),
            ],
            check=True,
            timeout=40,
            capture_output=True,
        )
        raw = self.path.read_bytes()
        artifact = dict(path=self.path, sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw), duration_seconds=4)
        with patch("mission_control.campaign_video_transport.exchange", side_effect=self.fake({"success": True})):
            self.assertEqual(upload("456", artifact, self.context)["state"], "UPLOAD_ACKNOWLEDGED")
        with patch("mission_control.campaign_video_transport.exchange") as call, self.assertRaises(Invalid):
            upload("456", dict(artifact, duration_seconds=5), self.context)
        call.assert_not_called()


if __name__ == "__main__":
    unittest.main()
