"""Execute the closed shared timeline through fixed offline native media argv."""
import hashlib
from pathlib import Path
import time
from .common import Invalid
from .media_native import capability, invoke, video_metadata
from .video_edit_contract import definition, timing, output_frames, PROFILES, FPS, clip

MAX_BYTES = 8388608
RENDER_SECONDS = 180


def numeric(value):
    """Emit only adapter-computed numeric literals, never user filter syntax."""
    return format(value, '.10g')


def clip_filters(item, output):
    """Compile validated crop, orientation, fit and color fields in a fixed order."""
    item = clip(item)
    if not isinstance(output, str) or output not in PROFILES:raise Invalid('Choose a supported edited-video output profile')
    crop = item['transform']['crop'];transform = item['transform'];effect = item['effects']
    filters = [f"trim=start_frame={item['in_frame']}:end_frame={item['out_frame']}",
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


def validate(path, value, tools=None):
    """Accept only decoded silent H264 with exact requested fps, shape and timing."""
    value = definition(value);size = path.stat().st_size
    if not 0 < size <= MAX_BYTES:raise Invalid('Edited video exceeds the supported artifact size')
    metadata = video_metadata(path, tools)
    if (metadata['width'], metadata['height']) != PROFILES[value['output']]:
        raise Invalid('Edited video dimensions do not match the project')
    if (metadata['codec'], metadata['pixel_format'], metadata['frame_rate'], metadata['audio']) != ('h264', 'yuv420p', '24/1', False):
        raise Invalid('Edited video encoding does not match the project profile')
    if abs(metadata['duration_seconds'] - timing(value)['total_frames'] / FPS) > 1 / FPS:
        raise Invalid('Edited video timing does not match the project')
    return dict(bytes=size, sha256=hashlib.sha256(path.read_bytes()).hexdigest(), metadata=metadata)


def render(folder, value, sources, alive):
    """Encode finite verified source clips, then concatenate internal segment names."""
    value = definition(value);native = capability()
    if native['status'] != 'READY':raise Invalid(native['repair'])
    folder = Path(folder);deadline = time.monotonic() + RENDER_SECONDS
    for index, item in enumerate(value['clips']):
        argv = [native['tools']['ffmpeg'], '-hide_banner', '-loglevel', 'error', '-nostdin', '-y',
                '-protocol_whitelist', 'file,pipe', '-i', str(sources[item['source']['id']]),
                '-vf', clip_filters(item, value['output']), '-frames:v', str(output_frames(item)),
                '-an', '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '23', '-pix_fmt', 'yuv420p', f'part{index}.mp4']
        invoke(argv, folder, alive, deadline)
    (folder/'segments.txt').write_text(''.join(f"file 'part{index}.mp4'\n" for index in range(len(value['clips']))), encoding='ascii')
    invoke([native['tools']['ffmpeg'], '-hide_banner', '-loglevel', 'error', '-nostdin', '-y',
            '-f', 'concat', '-safe', '1', '-i', 'segments.txt', '-c', 'copy', '-movflags', '+faststart', 'video.mp4'],
           folder, alive, deadline)
    output = folder/'video.mp4'
    return output, validate(output, value, native['tools'])
