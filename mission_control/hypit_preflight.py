"""Read-only guided Hypit preflight and explicit content-bound reuse."""
import shutil
from .common import Invalid, digest
from .creative_rendering import render_request
from .db import connection
from .hypit_authoring import FPS, project
from .hypit_jobs import artifact_file, brief_scene, capability, current_inputs, saved
from .media_native import SHAPES, capability as media_capability

SCAN_LIMIT = 50
CANDIDATE_LIMIT = 5
MAX_ENVELOPE_CHARS = 1048576


def inputs(store, app_id, body):
    """Resolve precisely the same currently approved request and scene as queue."""
    store.app(app_id)
    with connection(store.path) as db:
        request = render_request(db, store, app_id, body)
    return dict(request=request, scene=brief_scene(request))


def source_hashes(scene):
    """Hash the fixed authored files without staging or launching a runtime."""
    return project(scene)['receipt']['source_hashes']


def timeline(scene):
    """Report finite scene timings and transparent, advisory text density."""
    start = 0
    windows = []
    for index, item in enumerate(scene['scenes']):
        seconds = item['seconds']; words = len(item['text'].split())
        rate = round(words / seconds, 2)
        windows.append(dict(index=index + 1, start_seconds=start, end_seconds=start + seconds,
                            duration_seconds=seconds, start_frame=start * FPS,
                            end_frame_exclusive=(start + seconds) * FPS,
                            characters=len(item['text']), words=words,
                            words_per_second=rate, density_advisory='REVIEW' if rate > 2.5 else 'NO_FLAG'))
        start += seconds
    width, height = SHAPES[scene['shape']]
    return dict(shape=scene['shape'], width=width, height=height, frame_rate=FPS,
                duration_seconds=start, scenes=windows)


def readiness():
    """Inspect only local file presence; never start the CLI or a media process."""
    launcher = capability(); media = media_capability()
    tools = media.get('tools', {}); node_detected = bool(shutil.which('node'))
    issues = []
    if launcher['status'] != 'DETECTED':issues.append('Install the optional Hypit CLI before starting a new render.')
    if not node_detected:issues.append('Node was not detected; verify the installed launcher requirements.')
    if not tools.get('ffmpeg') or not tools.get('ffprobe'):issues.append('Install FFmpeg and FFprobe before starting a new render.')
    if not media.get('font'):issues.append('Provide a supported local font before starting a new render.')
    return dict(launcher=launcher['status'], launcher_sha256=launcher.get('launcher_sha256'),
                node_detected=node_detected, ffmpeg_detected=bool(tools.get('ffmpeg')), ffprobe_detected=bool(tools.get('ffprobe')),
                font_detected=bool(media.get('font')), compiler='NOT_CHECKED',
                browser_and_endpoints='NOT_CHECKED', render_readiness='NOT_CONFIRMED', remediation=issues)


def check_sources(data, expected_sources):
    receipt = data.get('receipt')
    source = receipt.get('source') if isinstance(receipt, dict) else None
    if not isinstance(source, dict) or source.get('source_hashes') != expected_sources:
        raise Invalid('Saved Hypit authored source differs or cannot be verified')
    if source.get('scene_hash') != digest(data['inputs']['scene']):
        raise Invalid('Saved Hypit scene does not match its source receipt')
    if receipt.get('artifact') != data.get('artifact'):
        raise Invalid('Saved Hypit result and artifact receipts differ')


def checked_artifact(path, data):
    artifact = data.get('artifact')
    if not isinstance(artifact, dict):raise Invalid('Hypit artifact receipt is unavailable')
    try:
        size = path.stat().st_size
    except OSError:
        raise Invalid('Hypit artifact is no longer available') from None
    if type(artifact.get('bytes')) is not int or artifact['bytes'] != size:
        raise Invalid('Hypit artifact size does not match its retained receipt')
    return artifact


def check_candidate(store, app_id, render_id, expected_inputs, expected_sources):
    """Recheck exact app, record, current proof, authored source and artifact bytes."""
    try:
        path, data = artifact_file(store, app_id, render_id)
    except (KeyError, TypeError, ValueError, OSError):
        raise Invalid('Saved Hypit artifact is unavailable or changed') from None
    stored_inputs = data.get('inputs')
    if stored_inputs != expected_inputs or digest(stored_inputs) != digest(expected_inputs):
        raise Invalid('Saved Hypit inputs differ from this current request')
    check_sources(data, expected_sources)
    with connection(store.path) as db:
        current_inputs(db, store, app_id, stored_inputs)
    artifact = checked_artifact(path, data)
    return dict(render_id=render_id, artifact_hash=artifact['sha256'], artifact_bytes=artifact.get('bytes'),
                input_hash=digest(stored_inputs), source_hash=digest(expected_sources),
                authoring_mode='APPROVED_BRIEF_CAPTIONS', visual_review='REQUIRED', publication='NOT_RUN')


def candidates(store, app_id, current, sources):
    """Bound inventory and only hash artifact bytes for at most five matching rows."""
    with connection(store.path) as db:
        rows = db.execute('SELECT * FROM hypit_renders WHERE app_id=? ORDER BY created DESC,id LIMIT ?',
                          (app_id, SCAN_LIMIT + 1)).fetchall()
    found = []; checked = 0; unavailable = 0; truncated = len(rows) > SCAN_LIMIT
    for row in rows[:SCAN_LIMIT]:
        try:
            if len(row['data']) > MAX_ENVELOPE_CHARS:continue
            data = saved(row)['data']
            if data.get('inputs') != current:continue
            if checked >= CANDIDATE_LIMIT:
                truncated = True;break
            checked += 1
            found.append(check_candidate(store, app_id, row['id'], current, sources))
        except (Invalid, OSError, KeyError, TypeError, ValueError):
            unavailable += 1
    return dict(items=found, scanned=min(len(rows), SCAN_LIMIT), verified_attempts=checked,
                unavailable=unavailable, truncated=truncated)


def plan(store, app_id, body):
    if not isinstance(body, dict) or set(body) != {'data'}:
        raise Invalid('Hypit preflight needs exactly the guided brief fields')
    current = inputs(store, app_id, body['data']); sources = source_hashes(current['scene'])
    return dict(input_hash=digest(current), source_hash=digest(sources),
                source_hash_scope='Fixed authored files only; local font and runtime are separate.',
                scene=timeline(current['scene']), readiness=readiness(),
                readability=dict(kind='ADVISORY_HEURISTIC', threshold_words_per_second=2.5,
                    method='Whitespace-separated words divided by scene seconds.',
                    note='A flag prompts visual and listening review; no flag is not a quality or accessibility pass.'),
                reuse_candidates=candidates(store, app_id, current, sources),
                authoring_mode='APPROVED_BRIEF_CAPTIONS', visual_review='REQUIRED', publication='NOT_RUN',
                next_steps=['Explicitly reuse a verified candidate or queue a new guided captions render.',
                            'For richer authored visuals or sound, continue in the existing Hypit Studio workflow.',
                            'Inspect frames and playback before choosing a final export.'])


def reuse(store, app_id, body):
    if not isinstance(body, dict) or set(body) != {'data','render_id','source_hash'}:
        raise Invalid('Choose exact guided fields, saved render and current source hash')
    current = inputs(store, app_id, body['data']); sources = source_hashes(current['scene'])
    if body['source_hash'] != digest(sources):
        raise Invalid('Hypit source changed since preflight; review it again')
    receipt = check_candidate(store, app_id, body['render_id'], current, sources)
    return dict(receipt, reused=True, job_created=False, build_started=False)
