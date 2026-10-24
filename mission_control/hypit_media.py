"""Dedicated decoded Hypit artifact profile; native silent validation stays unchanged."""
import hashlib
import json
import math
from pathlib import Path
import shutil
from .common import Invalid
from .media_native import SHAPES
from .agent_process import capture

MAX_BYTES = 67108864
TIMEOUT_SECONDS = 15
MAX_SECONDS = 60
TIMING_TOLERANCE = 0.15
FPS = 24
AUDIO_RATE = 48000


def probe(path):
    """Use fixed local media decoding without shell, remote protocols or raw errors."""
    tool = shutil.which('ffprobe')
    if not tool:
        raise Invalid('FFprobe is required to inspect Hypit video')
    fields = 'stream=codec_type,codec_name,pix_fmt,width,height,avg_frame_rate,duration,sample_rate,channels:format=duration'
    argv = [tool, '-v', 'error', '-protocol_whitelist', 'file,pipe', '-show_entries', fields, '-of', 'json', str(path)]
    try:
        result = capture(argv, timeout=TIMEOUT_SECONDS)
    except (OSError, ValueError):
        raise Invalid('Hypit media inspection failed or timed out') from None
    if result['code']:
        raise Invalid('Hypit video could not be decoded')
    try:
        return json.loads(result['stdout'])
    except (ValueError, TypeError):
        raise Invalid('Hypit decoder returned malformed metadata') from None


def duration(value):
    """Exclude nonfinite, negative, boolean and malformed decoder time values."""
    if isinstance(value, bool):
        raise Invalid('Hypit media timing is malformed')
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        raise Invalid('Hypit media timing is malformed') from None
    if not math.isfinite(result) or result <= 0:
        raise Invalid('Hypit media timing is malformed')
    return result


def video_profile(stream, shape, seconds):
    """Require the selected exact raster/encoding and near-exact decoded duration."""
    width, height = SHAPES[shape]
    expected = ('h264', 'yuv420p', width, height, str(FPS) + '/1')
    actual = tuple(stream.get(key) for key in ('codec_name', 'pix_fmt', 'width', 'height', 'avg_frame_rate'))
    if actual != expected or type(stream.get('width')) is not int or type(stream.get('height')) is not int:
        raise Invalid('Hypit video encoding, dimensions or frame rate do not match the project')
    if abs(duration(stream.get('duration')) - seconds) > TIMING_TOLERANCE:
        raise Invalid('Hypit video duration does not match the project')


def audio_profile(stream, seconds):
    """AAC is a stream capability, not evidence of narration, rights or human review."""
    if stream.get('codec_name') != 'aac' or stream.get('sample_rate') != str(AUDIO_RATE):
        raise Invalid('Hypit audio must be AAC at 48000 samples per second')
    if type(stream.get('channels')) is not int or stream['channels'] not in (1, 2):
        raise Invalid('Hypit audio must have one or two channels')
    if abs(duration(stream.get('duration')) - seconds) > TIMING_TOLERANCE:
        raise Invalid('Hypit audio duration does not match the project')


def metadata(value, shape, seconds):
    """Close the decoded stream inventory before accepting the normalized profile."""
    try:
        streams = value['streams']
        if not isinstance(streams, list) or not 1 <= len(streams) <= 2 or not all(isinstance(s, dict) for s in streams):
            raise Invalid('Hypit output must have one video and optional audio stream')
        videos = [s for s in streams if s.get('codec_type') == 'video']
        audios = [s for s in streams if s.get('codec_type') == 'audio']
        if len(videos) != 1 or len(videos) + len(audios) != len(streams):
            raise Invalid('Hypit output contains an unsupported or extra stream')
        video_profile(videos[0], shape, seconds)
        if audios:
            audio_profile(audios[0], seconds)
        actual_seconds = duration(value['format']['duration'])
        if abs(actual_seconds - seconds) > TIMING_TOLERANCE:
            raise Invalid('Hypit container duration does not match the project')
        return dict(codec='h264', pixel_format='yuv420p', width=SHAPES[shape][0], height=SHAPES[shape][1],
                    frame_rate='24/1', duration_seconds=actual_seconds, audio=bool(audios),
                    audio_codec='aac' if audios else None)
    except (KeyError, TypeError, AttributeError):
        raise Invalid('Hypit decoder returned malformed metadata') from None


def validate_video(path, shape, seconds):
    """Inspect caller-owned actual bytes and return their content-bound receipt."""
    if not isinstance(shape, str) or shape not in SHAPES or type(seconds) is not int or not 1 <= seconds <= MAX_SECONDS:
        raise Invalid('Choose a supported Hypit shape and 1 through 60 integer seconds')
    path = Path(path)
    try:
        if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= MAX_BYTES:
            raise Invalid('Hypit artifact is missing, empty, linked or exceeds its size bound')
        before = path.read_bytes()
        decoded = metadata(probe(path.resolve()), shape, seconds)
        after = path.read_bytes()
        if after != before:
            raise Invalid('Hypit video changed during inspection')
        return dict(bytes=len(before), sha256=hashlib.sha256(before).hexdigest(), metadata=decoded)
    except OSError:
        raise Invalid('Hypit artifact could not be read') from None
