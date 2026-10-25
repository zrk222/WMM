"""Bounded media-byte validation and local FFmpeg decode proof."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from mission_control.common import Invalid
import mission_control.managed_media_validation as media


def probed(audio=True):
    video = {
        "codec_type": "video", "codec_name": "h264", "width": 64, "height": 64,
        "avg_frame_rate": "24/1", "duration": "1.0",
    }
    streams = [video]
    if audio:
        streams.append({
            "codec_type": "audio", "codec_name": "aac", "sample_rate": "48000",
            "channels": 2, "duration": "1.0",
        })
    return {"streams": streams, "format": {"duration": "1.0"}}


def framehash(rows=1):
    return "#format: frame checksums\n" + "".join(
        f"0, {index}, {index}, 1, 12, {'a' * 32}\n" for index in range(rows)
    )


class ManagedMediaValidationTests(unittest.TestCase):
    def test_suffix_and_byte_bounds_reject_before_native_execution(self):
        with patch.object(media, "capture") as native:
            for suffix in (".mkv", ".avi", "C:\\private\\input.mp4", "", None):
                with self.subTest(suffix=suffix), self.assertRaises(Invalid):
                    media.inspect(b"synthetic", suffix, tools={"ffprobe": "ffprobe", "ffmpeg": "ffmpeg"})
            for raw in (b"", bytearray(b"x"), None):
                with self.subTest(raw=type(raw).__name__), self.assertRaises(Invalid):
                    media.inspect(raw, ".mp4", tools={"ffprobe": "ffprobe", "ffmpeg": "ffmpeg"})
            with patch.object(media, "MAX_BYTES", 4):
                with self.assertRaises(Invalid):
                    media.inspect(b"12345", ".mp4", tools={"ffprobe": "ffprobe", "ffmpeg": "ffmpeg"})
        native.assert_not_called()

    def test_staging_uses_only_a_generated_private_name_and_preserves_source_identity(self):
        raw = b"private synthetic source"
        with media.media_bytes(raw, ".MP4") as staged:
            self.assertEqual(staged.path.name, "source.mp4")
            self.assertNotIn("private", str(staged.path).lower())
            self.assertEqual(staged.path.read_bytes(), raw)
            self.assertEqual(staged.sha256, hashlib.sha256(raw).hexdigest())
            self.assertEqual(staged.demuxer, "mov")
        self.assertFalse(staged.path.exists())

    def test_metadata_accepts_inclusive_limits_and_normalizes_audio(self):
        payload = probed()
        payload["streams"][0].update(width=4096, height=2048, avg_frame_rate="120/1")
        payload["streams"][1].update(sample_rate="192000", channels=2)
        payload["format"]["duration"] = "60"
        result = media.media_metadata(payload)
        self.assertEqual(result, {
            "codec": "h264", "width": 4096, "height": 2048, "duration_seconds": 60.0,
            "frame_rate": 120.0, "audio": True,
            "audio_metadata": {"codec": "aac", "channels": 2, "sample_rate": 192000},
        })
        payload = probed(audio=False)
        payload["streams"][0].update(width=2, height=2, avg_frame_rate="1/1")
        payload["format"]["duration"] = "0.001"
        result = media.media_metadata(payload)
        self.assertEqual((result["width"], result["height"], result["frame_rate"], result["audio"]), (2, 2, 1.0, False))
        self.assertNotIn("audio_metadata", result)

    def test_metadata_rejects_ambiguous_streams_and_every_declared_numeric_bound(self):
        cases = []
        for key, bad in (("width", True), ("width", 1), ("width", 4097), ("height", 4097),
                         ("avg_frame_rate", "0/1"), ("avg_frame_rate", "121/1"),
                         ("avg_frame_rate", "24/0"), ("avg_frame_rate", "NaN"),
                         ("duration", "0"), ("duration", "60.001"), ("duration", "inf"), ("duration", " 1")):
            payload = probed(audio=False)
            target = payload["format"] if key == "duration" else payload["streams"][0]
            target[key] = bad
            cases.append((key, bad, payload))
        payload = probed(audio=False)
        payload["streams"][0].update(width=4096, height=2049)
        cases.append(("pixel-count", 4096 * 2049, payload))
        for key, bad in (("channels", True), ("channels", 0), ("channels", 3),
                         ("sample_rate", "7999"), ("sample_rate", "192001"),
                         ("sample_rate", "48000.5")):
            payload = probed()
            payload["streams"][1][key] = bad
            cases.append((key, bad, payload))
        payload = probed(audio=False)
        payload["streams"][0]["duration"] = "60.001"
        cases.append(("video-stream-duration", "60.001", payload))
        for label, bad, payload in cases:
            with self.subTest(label=label, bad=bad), self.assertRaises(Invalid):
                media.media_metadata(payload)
        for streams in ([], probed()["streams"] * 2, [dict(probed()["streams"][0], codec_type="subtitle")],
                        [probed()["streams"][0], dict(probed()["streams"][1], codec_type="data")]):
            with self.subTest(streams=streams), self.assertRaises(Invalid):
                media.media_metadata({"streams": streams, "format": {"duration": "1"}})

    def test_metadata_json_requires_finite_unique_properties_and_bounded_size(self):
        duplicate = '{"streams": [], "streams": [], "format": {"duration": "1"}}'
        for value in ("NaN", duplicate, "{" + " " * (media.CAP + 1), b"\xff"):
            with self.subTest(value=type(value).__name__), self.assertRaises(Invalid):
                media.media_metadata(value)

    def test_media_probe_media_decode_are_protocol_limited_generated_name_only_and_sanitized(self):
        raw = b"opaque bytes"
        mapped_streams = []

        def native(args, **kwargs):
            self.assertIn("-protocol_whitelist", args)
            position = args.index("-protocol_whitelist")
            self.assertEqual(args[position + 1], "file,pipe")
            self.assertEqual(args[-1], "pipe:1" if args[0] == "ffmpeg" else "source.webm")
            self.assertFalse(any("private" in str(arg).lower() or ".." in str(arg) for arg in args))
            self.assertEqual(kwargs["folder"].name.split("-")[0], "wmm")
            if args[0] == "ffprobe":
                self.assertIn("matroska", args)
                self.assertEqual(kwargs["timeout"], media.PROBE_TIMEOUT_SECONDS)
                return {"code": 0, "stdout": json.dumps(probed()), "stderr": "PRIVATE_PATH secret"}
            self.assertLessEqual(kwargs["timeout"], media.DECODE_TIMEOUT_SECONDS)
            mapped = args[args.index("-map") + 1]
            mapped_streams.append(mapped)
            self.assertIn("-an" if mapped == "0:v:0" else "-vn", args)
            return {"code": 0, "stdout": framehash(3), "stderr": "PRIVATE_PATH secret"}

        with patch.object(media, "capture", side_effect=native) as run:
            with media.media_bytes(raw, ".WEBM") as staged:
                metadata = media.media_probe(staged, "ffprobe")
                decoded = media.media_decode(staged, metadata, "ffmpeg")
                staged.verify_unchanged()
                self.assertEqual(staged.sha256, hashlib.sha256(raw).hexdigest())
                self.assertEqual(staged.size, len(raw))
                self.assertTrue(metadata["audio"])
                self.assertEqual(decoded, {"video_frames": 3, "audio_frames": 3})
        self.assertEqual(run.call_count, 3)
        self.assertEqual(mapped_streams, ["0:v:0", "0:a:0"])

    def test_native_failure_zero_frames_and_audio_failure_do_not_accept_media(self):
        tools = {"ffprobe": "ffprobe", "ffmpeg": "ffmpeg"}
        with patch.object(media, "capture", return_value={"code": 2, "stdout": "", "stderr": "PRIVATE_NATIVE_PATH"}):
            with self.assertRaises(Invalid) as caught:
                media.inspect(b"opaque", ".mp4", tools=tools)
        self.assertNotIn("PRIVATE", str(caught.exception))
        with patch.object(media, "capture", side_effect=[
            {"code": 0, "stdout": json.dumps(probed()), "stderr": ""},
            {"code": 0, "stdout": "# empty frame stream\n", "stderr": ""},
        ]):
            with self.assertRaisesRegex(Invalid, "zero pictures"):
                media.inspect(b"opaque", ".mp4", tools=tools)

        with patch.object(media, "capture", side_effect=[
            {"code": 0, "stdout": json.dumps(probed()), "stderr": ""},
            {"code": 0, "stdout": framehash(2), "stderr": ""},
            {"code": 1, "stdout": "", "stderr": "PRIVATE_NATIVE_PATH"},
        ]):
            with self.assertRaisesRegex(Invalid, "decode failed"):
                media.inspect(b"opaque", ".mp4", tools=tools)

    def test_probe_deadline_and_native_diagnostics_are_closed(self):
        with media.media_bytes(b"opaque", ".mp4") as staged:
            with patch.object(media, "capture", side_effect=Invalid("PRIVATE_NATIVE_PATH")) as native:
                with self.assertRaises(Invalid) as caught:
                    media.media_probe(staged, "ffprobe")
            self.assertNotIn("PRIVATE", str(caught.exception))
            self.assertEqual(native.call_args.kwargs["timeout"], media.PROBE_TIMEOUT_SECONDS)
            self.assertEqual(native.call_args.kwargs["folder"], staged.path.parent)
            with patch.object(media, "capture", return_value={"code": 0, "stdout": "x" * (media.CAP + 1), "stderr": ""}):
                with self.assertRaises(Invalid):
                    media.media_probe(staged, "ffprobe")

    def test_actual_mp4_mov_webm_and_silent_input_decode_video_and_audio(self):
        ffmpeg = shutil.which("ffmpeg")
        ffprobe = shutil.which("ffprobe")
        self.assertTrue(ffmpeg and ffprobe, "local FFmpeg and FFprobe are required for this proof")
        cases = (
            (".mp4", ["-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac"]),
            (".mov", ["-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac"]),
            (".webm", ["-c:v", "libvpx-vp9", "-deadline", "realtime", "-cpu-used", "8", "-c:a", "libopus"]),
        )
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            for suffix, codecs in cases:
                path = folder / ("synthetic" + suffix)
                command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin",
                           "-f", "lavfi", "-i", "color=c=blue:s=64x64:r=24",
                           "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
                           "-t", "1", "-pix_fmt", "yuv420p", "-shortest", *codecs, "-y", str(path)]
                subprocess.run(command, capture_output=True, timeout=40, check=True)
                original = path.read_bytes()
                result = media.inspect(original, suffix, tools={"ffprobe": ffprobe, "ffmpeg": ffmpeg})
                self.assertEqual(result["sha256"], hashlib.sha256(original).hexdigest())
                self.assertEqual(result["bytes"], len(original))
                self.assertEqual(result["metadata"]["width"], 64)
                self.assertEqual(result["metadata"]["height"], 64)
                self.assertGreater(result["decoded"]["video_frames"], 0)
                self.assertGreater(result["decoded"]["audio_frames"], 0)
                self.assertTrue(result["metadata"]["audio"])
                self.assertEqual(path.read_bytes(), original)
            silent = folder / "synthetic-silent.mp4"
            subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-f", "lavfi", "-i",
                            "color=c=blue:s=64x64:r=24", "-t", "1", "-c:v", "libx264", "-preset", "ultrafast",
                            "-pix_fmt", "yuv420p", "-y", str(silent)], capture_output=True, timeout=40, check=True)
            result = media.inspect(silent.read_bytes(), ".mp4", tools={"ffprobe": ffprobe, "ffmpeg": ffmpeg})
            self.assertFalse(result["metadata"]["audio"])
            self.assertEqual(result["decoded"]["audio_frames"], 0)
            self.assertGreater(result["decoded"]["video_frames"], 0)

    def test_invalid_container_bytes_fail_without_raw_native_diagnostics(self):
        tools = {"ffprobe": shutil.which("ffprobe"), "ffmpeg": shutil.which("ffmpeg")}
        self.assertTrue(all(tools.values()))
        with self.assertRaises(Invalid) as caught:
            media.inspect(b"not a media container", ".mp4", tools=tools)
        self.assertNotIn("wmm-imported-video", str(caught.exception))
        self.assertNotIn("not a media", str(caught.exception))

    def test_max_duration_and_audio_rate_decode_within_capture_bound(self):
        ffmpeg = shutil.which("ffmpeg")
        ffprobe = shutil.which("ffprobe")
        self.assertTrue(ffmpeg and ffprobe, "local FFmpeg and FFprobe are required for this proof")
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "maximum.mov"
            command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin",
                       "-f", "lavfi", "-i", "color=c=black:s=16x16:r=1",
                       "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=192000",
                       "-t", "60", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                       "-c:a", "pcm_s16le", "-ac", "1", "-y", str(path)]
            subprocess.run(command, capture_output=True, timeout=60, check=True)
            raw = path.read_bytes()
            self.assertLessEqual(len(raw), media.MAX_BYTES)
            result = media.inspect(raw, ".mov", tools={"ffprobe": ffprobe, "ffmpeg": ffmpeg})
            self.assertEqual(result["metadata"]["duration_seconds"], 60.0)
            self.assertEqual(result["metadata"]["audio_metadata"]["sample_rate"], 192000)
            self.assertGreater(result["decoded"]["video_frames"], 0)
            self.assertGreater(result["decoded"]["audio_frames"], 0)


if __name__ == "__main__":
    unittest.main()
