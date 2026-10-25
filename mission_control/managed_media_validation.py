"""Bounded technical validation of imported video bytes; grants no reuse rights."""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import tempfile
import time

from .agent_process import CAP, capture
from .common import Invalid

MAX_BYTES = 67108864
MAX_DURATION_SECONDS = 60.0
MAX_WIDTH = 4096
MAX_HEIGHT = 4096
MAX_PIXELS = 8388608
MIN_FPS = 1.0
MAX_FPS = 120.0
MIN_SAMPLE_RATE = 8000
MAX_SAMPLE_RATE = 192000
PROBE_TIMEOUT_SECONDS = 15
DECODE_TIMEOUT_SECONDS = 180
_SUFFIXES = {".mp4": "mov", ".mov": "mov", ".webm": "matroska"}
_CODEC = re.compile(r"[a-z0-9_+-]{1,64}\Z")
_RATIONAL = re.compile(r"([0-9]{1,12})/([0-9]{1,12})\Z")
_DECIMAL = re.compile(r"(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z")


@dataclass
class _StagedMedia:
    """Private generated file and immutable source identity, owned until close."""

    directory: tempfile.TemporaryDirectory
    path: Path = field(repr=False)
    suffix: str
    demuxer: str
    size: int
    sha256: str

    def close(self):
        self.directory.cleanup()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def verify_unchanged(self):
        try:
            content = self.path.read_bytes()
        except OSError:
            raise Invalid("Imported video changed during validation") from None
        if len(content) != self.size or hashlib.sha256(content).hexdigest() != self.sha256:
            raise Invalid("Imported video changed during validation")


def media_bytes(raw: bytes, suffix: str) -> _StagedMedia:
    """Stage bounded imported bytes under a generated filename, never a user path."""
    if not isinstance(suffix, str) or suffix.lower() not in _SUFFIXES:
        raise Invalid("Choose an MP4, MOV or WebM video")
    if type(raw) is not bytes or not 1 <= len(raw) <= MAX_BYTES:
        raise Invalid("Imported video must contain 1 through 67108864 bytes")
    suffix = suffix.lower()
    directory = tempfile.TemporaryDirectory(prefix="wmm-imported-video-")
    path = Path(directory.name) / ("source" + suffix)
    digest = hashlib.sha256(raw).hexdigest()
    try:
        path.write_bytes(raw)
    except OSError:
        directory.cleanup()
        raise Invalid("Imported video could not be staged") from None
    return _StagedMedia(directory, path, suffix, _SUFFIXES[suffix], len(raw), digest)


def _reject_constant(_value):
    raise ValueError("nonfinite JSON number")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON property")
        result[key] = value
    return result


def _codec(value):
    if not isinstance(value, str) or not _CODEC.fullmatch(value):
        raise Invalid("Video metadata contains an unsupported codec label")
    return value


def _finite_seconds(value, field_name):
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise Invalid(f"Video {field_name} is malformed")
    if isinstance(value, str) and not _DECIMAL.fullmatch(value):
        raise Invalid(f"Video {field_name} is malformed")
    try:
        seconds = float(value)
    except (ValueError, OverflowError):
        raise Invalid(f"Video {field_name} is malformed") from None
    if not math.isfinite(seconds) or seconds <= 0 or seconds > MAX_DURATION_SECONDS:
        raise Invalid(f"Video {field_name} is outside the supported range")
    return seconds


def _frame_rate(value):
    if not isinstance(value, str) or len(value) > 25:
        raise Invalid("Video frame rate is malformed")
    match = _RATIONAL.fullmatch(value)
    if match is None:
        raise Invalid("Video frame rate is malformed")
    numerator, denominator = (int(part) for part in match.groups())
    if denominator == 0 or numerator == 0:
        raise Invalid("Video frame rate is malformed")
    result = numerator / denominator
    if not math.isfinite(result) or not MIN_FPS <= result <= MAX_FPS:
        raise Invalid("Video frame rate is outside the supported range")
    return result


def _positive_integer(value, name, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise Invalid(f"Video {name} is outside the supported range")
    return value


def _load_metadata(value):
    if isinstance(value, (str, bytes)):
        if len(value) > CAP:
            raise Invalid("Video metadata exceeded its size limit")
        return json.loads(value, parse_constant=_reject_constant, object_pairs_hook=_unique_object)
    return value


def _stream_inventory(streams):
    if not isinstance(streams, list) or len(streams) not in (1, 2) or not all(isinstance(s, dict) for s in streams):
        raise Invalid("Video must contain one video stream and at most one audio stream")
    videos = [stream for stream in streams if stream.get("codec_type") == "video"]
    audios = [stream for stream in streams if stream.get("codec_type") == "audio"]
    if len(videos) != 1 or len(audios) > 1 or len(videos) + len(audios) != len(streams):
        raise Invalid("Video must contain one video stream and at most one audio stream")
    return videos[0], audios[0] if audios else None


def _dimensions(video):
    width = _positive_integer(video.get("width"), "width", 2, MAX_WIDTH)
    height = _positive_integer(video.get("height"), "height", 2, MAX_HEIGHT)
    if width * height > MAX_PIXELS:
        raise Invalid("Video pixel dimensions exceed the supported limit")
    return width, height


def _audio_stream(stream):
    codec = _codec(stream.get("codec_name"))
    channels = _positive_integer(stream.get("channels"), "audio channel count", 1, 2)
    raw_rate = stream.get("sample_rate")
    if not isinstance(raw_rate, str) or not re.fullmatch(r"[0-9]{1,6}", raw_rate):
        raise Invalid("Video audio sample rate is malformed")
    sample_rate = _positive_integer(int(raw_rate), "audio sample rate", MIN_SAMPLE_RATE, MAX_SAMPLE_RATE)
    if "duration" in stream and stream["duration"] not in (None, "N/A"):
        _finite_seconds(stream["duration"], "audio duration")
    return {"codec": codec, "channels": channels, "sample_rate": sample_rate}


def _normalized_metadata(video, audio_stream, container):
    width, height = _dimensions(video)
    frame_rate = _frame_rate(video.get("avg_frame_rate"))
    duration = _finite_seconds(container.get("duration") if isinstance(container, dict) else None, "duration")
    if "duration" in video and video["duration"] not in (None, "N/A"):
        _finite_seconds(video["duration"], "video stream duration")
    audio = _audio_stream(audio_stream) if audio_stream else None
    return {
        "codec": _codec(video.get("codec_name")),
        "width": width,
        "height": height,
        "duration_seconds": duration,
        "frame_rate": frame_rate,
        "audio": bool(audio),
        **({"audio_metadata": audio} if audio else {}),
    }


def media_metadata(value: str | bytes | dict) -> dict:
    """Parse ffprobe JSON or a decoded JSON document using finite closed bounds."""
    try:
        value = _load_metadata(value)
        if not isinstance(value, dict):
            raise Invalid("Video decoder returned malformed metadata")
        video, audio = _stream_inventory(value.get("streams"))
        return _normalized_metadata(video, audio, value.get("format"))
    except Invalid:
        raise
    except (ValueError, TypeError, OverflowError, RecursionError):
        raise Invalid("Video decoder returned malformed metadata") from None


def _native_result(args, folder, timeout, alive):
    try:
        result = capture(args, alive=alive, timeout=timeout, folder=folder)
    except Exception:
        raise Invalid("Native video validation failed or timed out") from None
    if not isinstance(result, dict) or type(result.get("code")) is not int:
        raise Invalid("Native video validation returned malformed output")
    stdout = result.get("stdout")
    if not isinstance(stdout, str) or len(stdout.encode("utf-8", errors="replace")) > CAP:
        raise Invalid("Native video validation returned malformed output")
    if result["code"] != 0:
        raise Invalid("Imported video could not be inspected or decoded")
    return stdout


def media_probe(media: _StagedMedia, ffprobe: str, alive=lambda: None) -> dict:
    """Run the pinned demuxer on the generated local filename with bounded protocols."""
    if not isinstance(media, _StagedMedia) or not isinstance(ffprobe, str) or not ffprobe:
        raise Invalid("FFprobe is required to inspect imported video")
    fields = "stream=codec_type,codec_name,width,height,avg_frame_rate,duration,sample_rate,channels:format=duration"
    args = [ffprobe, "-v", "error", "-protocol_whitelist", "file,pipe", "-f", media.demuxer,
            "-show_entries", fields, "-of", "json", media.path.name]
    try:
        output = _native_result(args, media.path.parent, PROBE_TIMEOUT_SECONDS, alive)
    except Invalid:
        raise Invalid("Imported video could not be inspected") from None
    return media_metadata(output)


def _frame_count(output):
    count = 0
    for line in output.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        fields = [part.strip() for part in line.split(",")]
        if len(fields) != 6 or fields[0] != "0":
            raise Invalid("Native video decoder returned malformed frame evidence")
        if any(not re.fullmatch(r"-?[0-9]+|N/A", fields[index]) for index in (1, 2)):
            raise Invalid("Native video decoder returned malformed frame evidence")
        if not re.fullmatch(r"[0-9]+|N/A", fields[3]) or not re.fullmatch(r"[1-9][0-9]*", fields[4]):
            raise Invalid("Native video decoder returned malformed frame evidence")
        if not re.fullmatch(r"[0-9a-fA-F]{32}", fields[5]):
            raise Invalid("Native video decoder returned malformed frame evidence")
        count += 1
    return count


def _decode_one(media, ffmpeg, stream_map, disable_other, alive, deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise Invalid("Imported video decode exceeded its time limit")
    timeout = min(DECODE_TIMEOUT_SECONDS, int(remaining))
    if timeout < 1:
        raise Invalid("Imported video decode exceeded its time limit")
    args = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-xerror", "-err_detect", "explode",
            "-protocol_whitelist", "file,pipe", "-f", media.demuxer, "-i", media.path.name,
            "-map", stream_map, disable_other, "-f", "framehash", "-hash", "md5", "pipe:1"]
    try:
        output = _native_result(args, media.path.parent, timeout, alive)
    except Invalid:
        raise Invalid("Imported video decode failed") from None
    return _frame_count(output)


def media_decode(media: _StagedMedia, metadata: dict, ffmpeg: str, alive=lambda: None) -> dict:
    """Decode selected video and optional audio to bounded frame-hash streams."""
    if not isinstance(media, _StagedMedia) or not isinstance(metadata, dict) or not isinstance(ffmpeg, str) or not ffmpeg:
        raise Invalid("FFmpeg is required to decode imported video")
    deadline = time.monotonic() + DECODE_TIMEOUT_SECONDS
    video_frames = _decode_one(media, ffmpeg, "0:v:0", "-an", alive, deadline)
    if video_frames < 1:
        raise Invalid("Imported video decoded zero pictures")
    audio_frames = 0
    if metadata.get("audio") is True:
        audio_frames = _decode_one(media, ffmpeg, "0:a:0", "-vn", alive, deadline)
        if audio_frames < 1:
            raise Invalid("Imported video audio stream decoded zero frames")
    return {"video_frames": video_frames, "audio_frames": audio_frames}


def inspect(raw: bytes, suffix: str, alive=lambda: None, tools=None) -> dict:
    """Validate complete supplied video bytes; never accepts a caller host path."""
    staged = media_bytes(raw, suffix)
    try:
        if tools is None:
            binaries = {name: shutil.which(name) for name in ("ffprobe", "ffmpeg")}
        elif isinstance(tools, dict):
            binaries = {name: tools.get(name) for name in ("ffprobe", "ffmpeg")}
        else:
            raise Invalid("Native video tools are unavailable")
        if not all(isinstance(value, str) and value for value in binaries.values()):
            raise Invalid("FFmpeg and FFprobe are required to validate imported video")
        metadata = media_probe(staged, binaries["ffprobe"], alive)
        decoded = media_decode(staged, metadata, binaries["ffmpeg"], alive)
        staged.verify_unchanged()
        return {"sha256": staged.sha256, "bytes": staged.size, "metadata": metadata, "decoded": decoded}
    finally:
        staged.close()
