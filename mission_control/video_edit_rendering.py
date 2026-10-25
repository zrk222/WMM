"""Execute the closed shared timeline through fixed offline native media argv."""
import hashlib
import json
from pathlib import Path
import time
from .common import Invalid
from .media_native import capability, invoke
from .agent_process import capture
from .managed_media_validation import media_metadata
from .video_edit_contract import definition, timing, output_frames, PROFILES, FPS, clip, source_key

MAX_BYTES = 67108864
RENDER_SECONDS = 180


def numeric(value):
    """Emit only adapter-computed numeric literals, never user filter syntax."""
    return format(value, '.10g')


def clip_filters(item, output):
    """Compile validated crop, orientation, fit and color fields in a fixed order."""
    item = clip(item)
    if not isinstance(output, str) or output not in PROFILES:raise Invalid('Choose a supported edited-video output profile')
    crop = item['transform']['crop'];transform = item['transform'];effect = item['effects']
    filters = (['fps=24'] if item['source']['kind'] == 'MANAGED' else []) + [f"trim=start_frame={item['in_frame']}:end_frame={item['out_frame']}",
               'setpts=(PTS-STARTPTS)*' + numeric(100 / item['speed_percent']),
               f"crop=w=max(2\\,floor(iw*{numeric(crop['width']/10000)}/2)*2):h=max(2\\,floor(ih*{numeric(crop['height']/10000)}/2)*2):x=floor(iw*{numeric(crop['x']/10000)}/2)*2:y=floor(ih*{numeric(crop['y']/10000)}/2)*2"]
    rotations = {0: [], 90: ['transpose=clock'], 180: ['hflip', 'vflip'], 270: ['transpose=cclock']}
    filters.extend(rotations[transform['rotation']])
    if transform['flip_x']:filters.append('hflip')
    if transform['flip_y']:filters.append('vflip')
    width, height = PROFILES[output]
    if transform['fit'] == 'COVER':
        filters.extend([f'scale={width}:{height}:force_original_aspect_ratio=increase', f'crop={width}:{height}'])
    else:
        color = '0x' + transform['background'][1:]
        filters.extend([f'scale={width}:{height}:force_original_aspect_ratio=decrease',
                        f'pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color={color}'])
    filters.extend([f"eq=brightness={numeric(effect['brightness']/100)}:contrast={numeric(effect['contrast']/100)}:saturation={numeric(effect['saturation']/100)}",
                    'setsar=1', 'fps=24', 'format=yuv420p'])
    return ','.join(filters)


def edit_metadata(path, tools=None):
    """Read bounded native stream metadata, retaining the strict imported-stream inventory."""
    tools = tools or capability()['tools']
    argv = [tools['ffprobe'], '-v', 'error', '-protocol_whitelist', 'file,pipe',
            '-show_streams', '-show_format', '-of', 'json', str(path)]
    result = capture(argv, alive=lambda: None, timeout=15, folder=Path(path).parent)
    if result['code'] != 0:
        raise Invalid('Edited media could not be inspected')
    parsed = json.loads(result['stdout']);metadata = media_metadata(parsed)
    video = next(row for row in parsed['streams'] if row['codec_type'] == 'video')
    return dict(metadata, pixel_format=video.get('pix_fmt'), frame_rate=video['avg_frame_rate'])


def validate(path, value, tools=None):
    """Accept only decoded silent H264 with exact requested fps, shape and timing."""
    value = definition(value);size = path.stat().st_size
    if not 0 < size <= MAX_BYTES:raise Invalid('Edited video exceeds the supported artifact size')
    metadata = edit_metadata(path, tools)
    if (metadata['width'], metadata['height']) != PROFILES[value['output']]:
        raise Invalid('Edited video dimensions do not match the project')
    expected_audio = any(c.get('audio', 'MUTE') == 'RETAIN' for c in value['clips'])
    if (metadata['codec'], metadata['pixel_format'], metadata['frame_rate'], metadata['audio']) != ('h264', 'yuv420p', '24/1', expected_audio):
        raise Invalid('Edited video encoding does not match the project profile')
    if abs(metadata['duration_seconds'] - timing(value)['total_frames'] / FPS) > 1 / FPS:
        raise Invalid('Edited video timing does not match the project')
    return dict(bytes=size, sha256=hashlib.sha256(path.read_bytes()).hexdigest(), metadata=metadata)


def audio_filters(item):
    """Trim in normalized timeline seconds and preserve pitch across supported speeds."""
    speed = item['speed_percent'] / 100
    tempo = []
    while speed < 0.5:
        tempo.append('atempo=0.5');speed *= 2
    while speed > 2:
        tempo.append('atempo=2');speed /= 2
    tempo.append('atempo=' + numeric(speed))
    return ','.join([f"atrim=start={numeric(item['in_frame']/FPS)}:end={numeric(item['out_frame']/FPS)}",
                     'asetpts=PTS-STARTPTS', *tempo, 'aresample=48000',
                     'aformat=sample_fmts=fltp:channel_layouts=stereo', 'apad'])


def segment_argv(native, item, output, source, index, with_audio):
    """Compile a closed clip into generated-file-only picture and sound controls."""
    argv = [native['tools']['ffmpeg'], '-hide_banner', '-loglevel', 'error', '-nostdin', '-y',
            '-protocol_whitelist', 'file,pipe', '-i', str(source)]
    retained = with_audio and item.get('audio', 'MUTE') == 'RETAIN' and edit_metadata(source, native['tools'])['audio']
    if with_audio and not retained:
        argv += ['-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo']
    argv += ['-map', '0:v:0', '-vf', clip_filters(item, output)]
    if with_audio:
        argv += ['-map', '0:a:0' if retained else '1:a:0', '-af', audio_filters(item) if retained else 'anull',
                 '-c:a', 'aac', '-b:a', '128k', '-ar', '48000', '-ac', '2']
    else:
        argv += ['-an']
    argv += ['-frames:v', str(output_frames(item)), '-t', numeric(output_frames(item)/FPS),
             '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '23', '-pix_fmt', 'yuv420p', f'part{index}.mp4']
    return argv


def render(folder, value, sources, alive):
    """Encode normalized selected slices and sound, then join internal segment names."""
    value = definition(value);native = capability()
    if native['status'] != 'READY':raise Invalid(native['repair'])
    folder = Path(folder);deadline = time.monotonic() + RENDER_SECONDS
    with_audio = any(c.get('audio', 'MUTE') == 'RETAIN' for c in value['clips'])
    for index, item in enumerate(value['clips']):
        alive()
        argv = segment_argv(native, item, value['output'], sources[source_key(item['source'])], index, with_audio)
        invoke(argv, folder, alive, deadline)
    (folder/'segments.txt').write_text(''.join(f"file 'part{index}.mp4'\n" for index in range(len(value['clips']))), encoding='ascii')
    invoke([native['tools']['ffmpeg'], '-hide_banner', '-loglevel', 'error', '-nostdin', '-y',
            '-f', 'concat', '-safe', '1', '-i', 'segments.txt', '-c', 'copy', '-movflags', '+faststart', 'video.mp4'],
           folder, alive, deadline)
    output = folder/'video.mp4'
    return output, validate(output, value, native['tools'])
