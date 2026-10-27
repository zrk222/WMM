"""Closed source-frame timeline data and deterministic shared edit commands."""
from copy import deepcopy
from fractions import Fraction
import re
from .common import Invalid, required

MAX_CLIPS = 24
MAX_FRAMES = 1440
FPS = 24
PROFILES = {'PORTRAIT': (720, 1280), 'LANDSCAPE': (1280, 720), 'SQUARE': (720, 720)}
ROLES = ('HOOK', 'PROBLEM', 'DEMO', 'PROOF', 'OBJECTION', 'CTA', 'OTHER')


def exact(value, fields):
    """Reject hidden fields before data can enter saved source or render contracts."""
    if not isinstance(value, dict) or set(value) != set(fields):
        raise Invalid('Use exactly the documented video project fields')


def integer(value, minimum, maximum, name):
    """Bool, fractional and unbounded values cannot silently alter frame timing."""
    if type(value) is not int or not minimum <= value <= maximum:
        raise Invalid(name + ' is outside its supported integer range')
    return value


def identifier(value):
    """Keep project and clip identifiers separate from paths, query and code."""
    if not isinstance(value, str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,79}', value):
        raise Invalid('Use a lowercase video project or clip identifier')
    return value


def source(value):
    """Native artifact references are identities, never user-supplied file paths."""
    exact(value, ('kind', 'id', 'sha256'))
    if value['kind'] not in ('NATIVE', 'MANAGED'):
        raise Invalid('Choose an existing native or owner-reviewed uploaded video')
    if not isinstance(value['id'], str) or not re.fullmatch(r'[a-f0-9-]{36}', value['id']):
        raise Invalid('Choose an existing native render identifier')
    if not isinstance(value['sha256'], str) or not re.fullmatch(r'[a-f0-9]{64}', value['sha256']):
        raise Invalid('Choose the exact saved source artifact hash')
    return deepcopy(value)


def transform(value):
    """Represent finite crop, orientation, fit and color without filter expressions."""
    exact(value, ('crop', 'rotation', 'flip_x', 'flip_y', 'fit', 'background'))
    crop_bounds(value['crop'])
    if type(value['rotation']) is not int or value['rotation'] not in (0, 90, 180, 270):
        raise Invalid('Choose a quarter-turn rotation')
    if any(type(value[key]) is not bool for key in ('flip_x', 'flip_y')):
        raise Invalid('Flip controls must be explicit booleans')
    if value['fit'] not in ('CONTAIN', 'COVER'):
        raise Invalid('Choose contained or covered framing')
    if not isinstance(value['background'], str) or not re.fullmatch(r'#[A-Fa-f0-9]{6}', value['background']):
        raise Invalid('Use an RGB background color')
    return deepcopy(value)


def crop_bounds(crop):
    """Crop coordinates are finite basis points contained in the original frame."""
    exact(crop, ('x', 'y', 'width', 'height'))
    for key in ('x', 'y'):integer(crop[key], 0, 10000, 'Crop position')
    for key in ('width', 'height'):integer(crop[key], 1, 10000, 'Crop size')
    if crop['x'] + crop['width'] > 10000 or crop['y'] + crop['height'] > 10000:
        raise Invalid('Crop must stay inside the source frame')


def effects(value):
    """Keep effect values data-only and within declared numeric ranges."""
    exact(value, ('brightness', 'contrast', 'saturation'))
    integer(value['brightness'], -100, 100, 'Brightness')
    for key in ('contrast', 'saturation'):integer(value[key], 0, 250, key)
    return deepcopy(value)


def clip(value):
    """Normalize one exact source slice; speed must resolve to whole output frames."""
    exact(value, ('id', 'source', 'role', 'in_frame', 'out_frame', 'speed_percent', 'transform', 'effects', *(['audio'] if 'audio' in value else [])))
    if value.get('audio', 'MUTE') not in ('RETAIN', 'MUTE'):
        raise Invalid('Choose retained or muted source audio')
    identifier(value['id']);source(value['source'])
    if value['role'] not in ROLES:raise Invalid('Choose a supported scene role')
    integer(value['in_frame'], 0, MAX_FRAMES, 'Source in frame')
    integer(value['out_frame'], 1, MAX_FRAMES, 'Source out frame')
    if value['out_frame'] <= value['in_frame']:raise Invalid('Clip end must follow its start')
    integer(value['speed_percent'], 25, 400, 'Playback speed percentage')
    if value['speed_percent'] % 25:raise Invalid('Playback speed uses increments of 25 percent')
    transform(value['transform']);effects(value['effects'])
    output_frames(value)
    return deepcopy(value)


def output_frames(value):
    """Use rational frame timing; reject truncation rather than shift later clips."""
    frames = Fraction((value['out_frame'] - value['in_frame']) * 100, value['speed_percent'])
    if frames.denominator != 1 or not 1 <= frames <= MAX_FRAMES:
        raise Invalid('Choose a trim and speed that produce whole supported output frames')
    return frames.numerator


def project_shape(value):
    """Keep optional reviewed packaging references within a closed project shape."""
    exact(value, ('title', 'purpose', 'locale', 'output', 'clips', *(['packaging'] if 'packaging' in value else [])))
    if 'packaging' in value:
        from .packaging_editor import provenance
        provenance(value['packaging'])


def definition(value):
    """A project timeline is ordered and bounded, with unique clip identities."""
    project_shape(value)
    for key in ('title', 'purpose', 'locale'):required(value[key], key, 2000 if key == 'purpose' else 200)
    if not isinstance(value['output'], str) or value['output'] not in PROFILES:
        raise Invalid('Choose portrait, landscape or square output')
    rows = value['clips']
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_CLIPS:
        raise Invalid('Keep the project between 1 and 24 clips')
    normalized = [clip(row) for row in rows]
    if len({row['id'] for row in normalized}) != len(rows):raise Invalid('Clip identifiers must be unique')
    if sum(output_frames(row) for row in normalized) > MAX_FRAMES:
        raise Invalid('Keep the edited project within 60 seconds')
    return dict(deepcopy(value), clips=normalized)


def selected(rows, identity):
    """A missing clip cannot accidentally address another list position."""
    identifier(identity)
    for index, row in enumerate(rows):
        if row['id'] == identity:return index
    raise Invalid('Clip does not belong to the current timeline')


def edit(value, command):
    """Apply one typed edit; callers atomically bind the expected saved revision."""
    result = definition(value);rows = result['clips']
    if not isinstance(command, dict) or 'operation' not in command:
        raise Invalid('Choose a documented timeline operation')
    operation = command['operation']
    if operation == 'insert':
        exact(command, ('operation', 'index', 'clip'))
        integer(command['index'], 0, len(rows), 'Insert position')
        rows.insert(command['index'], clip(command['clip']))
    elif operation in ('delete', 'duplicate', 'move', 'split', 'trim', 'replace'):
        change_clip(rows, command)
    else:
        raise Invalid('Choose insert, delete, duplicate, move, split, trim or replace')
    return definition(result)


def change_clip(rows, command):
    """Keep each command closed and validate the resulting complete timeline."""
    operation = command['operation']
    fields = {'delete': (), 'duplicate': ('new_id',), 'move': ('index',),
              'split': ('at_frame', 'new_id'), 'trim': ('in_frame', 'out_frame'), 'replace': ('clip',)}
    exact(command, ('operation', 'clip_id', *fields[operation]))
    index = selected(rows, command['clip_id']);current = rows[index]
    if operation == 'delete':rows.pop(index)
    elif operation == 'duplicate':
        rows.insert(index + 1, dict(deepcopy(current), id=identifier(command['new_id'])))
    elif operation == 'move':
        integer(command['index'], 0, len(rows) - 1, 'Move position')
        rows.insert(command['index'], rows.pop(index))
    elif operation == 'split':
        split_clip(rows, index, command)
    elif operation == 'trim':
        rows[index] = dict(current, in_frame=command['in_frame'], out_frame=command['out_frame'])
    elif operation == 'replace':
        replacement = clip(command['clip'])
        if replacement['id'] != current['id']:raise Invalid('Replacement retains the selected clip identifier')
        rows[index] = replacement


def split_clip(rows, index, command):
    """Split by original source frame without changing the combined source interval."""
    current = rows[index]
    integer(command['at_frame'], current['in_frame'] + 1, current['out_frame'] - 1, 'Split frame')
    left = dict(deepcopy(current), out_frame=command['at_frame'])
    right = dict(deepcopy(current), id=identifier(command['new_id']), in_frame=command['at_frame'])
    rows[index:index + 1] = [left, right]


def timing(value):
    """Return exact cumulative output timing for editor scrub and future compilation."""
    current = definition(value);cursor = 0;rows = []
    for item in current['clips']:
        duration = output_frames(item)
        rows.append(dict(id=item['id'], start_frame=cursor, end_frame=cursor + duration))
        cursor += duration
    return dict(fps=FPS, total_frames=cursor, clips=rows)


def source_key(value):
    """Keep legacy native keys while separating uploaded sources of the same ID."""
    return value['id'] if value['kind'] == 'NATIVE' else 'MANAGED:' + value['id']
