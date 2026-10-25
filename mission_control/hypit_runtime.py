"""Owned local declarative Hypit execution; never accept commands or component code."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import time
from .agent_process import capture
from .common import Invalid
from .hypit_authoring import project
from .hypit_media import validate_video
from .media_native import capability

COMMAND_TIMEOUT = 180
FOLLOW_WAIT_MS = 45000
POLL_SECONDS = 1
BUILD_TIMEOUT = 150


def identity():
    """Identify the installed launcher without installing or reading account stores."""
    launcher = shutil.which('hypit')
    if not launcher or not Path(launcher).is_file():
        raise Invalid('Install the optional Hypit CLI and prepare its local browser before rendering')
    path = Path(launcher).resolve()
    return dict(launcher=str(path), launcher_sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def invoke(runtime, folder, arguments, alive=lambda: None):
    """Only adapter-owned argv reaches the existing bounded, restricted runner."""
    if identity() != runtime:
        raise Invalid('Hypit launcher changed; inspect the retained project before another render')
    try:
        result = capture([runtime['launcher'], *arguments, '--json'], folder=folder, alive=alive, timeout=COMMAND_TIMEOUT)
    except (OSError, ValueError):
        raise Invalid('Hypit command interrupted; inspect the retained project before repeating work') from None
    if result['code']:
        raise Invalid('Hypit command failed; inspect the retained project diagnostics before retrying')
    try:
        value = json.loads(result['stdout'])
        if not isinstance(value, dict):
            raise ValueError()
    except (ValueError, TypeError):
        raise Invalid('Hypit returned an unsupported command receipt') from None
    if identity() != runtime:
        raise Invalid('Hypit launcher changed during rendering; inspect the retained project')
    return value


def stage(folder, scene):
    """Exclusive fixed files in an empty caller-owned job directory; font is host-selected."""
    folder = Path(folder)
    if folder.is_symlink() or not folder.is_dir() or any(folder.iterdir()):
        raise Invalid('Hypit needs an exclusive empty job directory; inspect existing work before retrying')
    authored = project(scene)
    font = capability().get('font')
    if not font:
        raise Invalid('Prepare a verified local font before Hypit rendering')
    for name, text in authored['files'].items():
        with (folder / name).open('xb') as destination:
            destination.write(text.encode())
    with (folder / 'font.ttf').open('xb') as destination:
        destination.write(Path(font).read_bytes())
    return dict(authored['receipt'], font_sha256=hashlib.sha256((folder / 'font.ttf').read_bytes()).hexdigest())


def local_graph(value):
    """Require a complete local plan before the single build submission."""
    if not isinstance(value.get('preflight'), dict) or value.get('ok') is not True or value['preflight'].get('ok') is not True:
        raise Invalid('Hypit local plan is not ready')
    local_counters(value)
    endpoints = selected_endpoints(value.get('needs'))
    if not endpoints or not endpoints <= {'html.local', 'media.local'}:
        raise Invalid('Hypit plan selected an unapproved endpoint')


def local_counters(value):
    """Every planned request must be explicitly local, resolved and supported."""
    keys = ('requestIssueCount', 'producerFailureCount', 'providerRequestCount', 'unresolvedRequestCount', 'unsupportedRequestCount')
    if any(type(value.get(key)) is not int or value[key] != 0 for key in keys):
        raise Invalid('Hypit plan requires unsupported, unresolved or provider work')
    if type(value.get('requestCount')) is not int or value['requestCount'] < 1 or value.get('localRequestCount') != value['requestCount']:
        raise Invalid('Hypit must select a nonempty local-only graph')


def selected_endpoints(value):
    """Read fixed endpoint facts from the bounded parsed plan, not marketing summaries."""
    if isinstance(value, list):
        return set().union(*(selected_endpoints(item) for item in value))
    if isinstance(value, dict):
        found = {value['endpoint']} if isinstance(value.get('endpoint'), str) else set()
        return found | set().union(*(selected_endpoints(item) for item in value.values()))
    return set()


def build_identity(value):
    """Retain only actual generated identities before they enter status/cancel argv."""
    build = value.get('build', {})
    key = build.get('id') if isinstance(build, dict) else None
    if not isinstance(key, str) or not re.fullmatch(r'bld_[A-Za-z0-9_]{8,100}', key):
        raise Invalid('Hypit build identity is unavailable; inspect the retained project before resubmission')
    return key


def recover_build(runtime, folder):
    """Inspect only this exclusive project/runtime after an uncertain submission."""
    history = invoke(runtime, folder, ['builds'])
    activity = invoke(runtime, folder, ['activity', '--runtime', 'runtime.json'])
    if history.get('next') or activity.get('omittedBuilds'):
        raise Invalid('Hypit build inventory is incomplete; inspect this project before retrying')
    keys = set()
    for value in (history, activity):
        rows = value.get('builds')
        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
            raise Invalid('Hypit build inventory could not be confirmed')
        keys.update(build_identity(dict(build=row)) for row in rows)
    if len(keys) != 1:
        raise Invalid('Hypit submission identity is uncertain; inspect this project without resubmitting')
    return keys.pop()


def submit(runtime, folder, alive):
    """A lost command response triggers inventory inspection, never another submission."""
    try:
        response = invoke(runtime, folder, ['build', 'build.svrun', '--runtime', 'runtime.json', '--max-wait-ms', str(FOLLOW_WAIT_MS)], alive)
        return build_identity(response), 'DIRECT'
    except Invalid:
        alive()
        return recover_build(runtime, folder), 'RECOVERED_FROM_PRIVATE_PROJECT'


def observe(runtime, folder, key, alive):
    """Poll the same durable build; an observation timeout never submits another build."""
    deadline = time.monotonic() + BUILD_TIMEOUT
    while time.monotonic() < deadline:
        alive()
        value = invoke(runtime, folder, ['status', key, '--runtime', 'runtime.json'], alive)
        if build_identity(value) != key:
            raise Invalid('Hypit returned a different build identity')
        build = value['build']
        if build.get('work', {}).get('state') == 'done':
            if build.get('result', {}).get('state') != 'complete' or build.get('work', {}).get('outcome') != 'complete':
                raise Invalid('Hypit build did not complete; inspect its saved diagnostics')
            return value
        time.sleep(POLL_SECONDS)
    raise Invalid('Hypit observation timed out; inspect the same retained build before retrying')


def cleanup(runtime, folder, key, unfinished):
    """Always shut down only this project runtime, even if cancellation fails."""
    cancelled = True
    if key and unfinished:
        try:
            invoke(runtime, folder, ['cancel', key, '--runtime', 'runtime.json'])
        except Invalid:
            cancelled = False
    stopped = invoke(runtime, folder, ['runtime', 'down', '--runtime', 'runtime.json'])
    if stopped.get('worker') != 'stopped' or not cancelled:
        raise Invalid('Hypit cleanup could not be confirmed; inspect the retained private runtime')
    return dict(worker='STOPPED', cancellation='REQUESTED' if key and unfinished else 'NOT_NEEDED')


def render(folder, scene, alive=lambda: None, submitted=lambda key: None):
    """Submit once, retain source/build history and return only actually decoded output."""
    runtime = identity()
    receipt = stage(folder, scene)
    folder = Path(folder).resolve()
    key = None
    complete = False
    try:
        check = invoke(runtime, folder, ['check', 'build.svrun'], alive)
        if check.get('ok') is not True:
            raise Invalid('Hypit source did not pass its installed compiler')
        local_graph(invoke(runtime, folder, ['plan', 'build.svrun', '--runtime', 'runtime.json'], alive))
        key, admission = submit(runtime, folder, alive)
        submitted(key)
        observe(runtime, folder, key, alive)
        complete = True
        invoke(runtime, folder, ['get', key, '--output', 'final.video', '--to', 'video.mp4'], alive)
        alive()
        artifact = validate_video(folder / 'video.mp4', scene['shape'], receipt['duration_seconds'])
        source_current(folder, receipt)
    finally:
        shutdown = cleanup(runtime, folder, key, not complete)
    return dict(build_id=key, submission_receipt=admission, source=receipt, artifact=artifact, runtime=runtime, cleanup=shutdown,
                authoring_mode='VALIDATED_DECLARATIVE_SCENE', publication='NOT_RUN', visual_review='REQUIRED')


def source_current(folder, receipt):
    """Refuse an artifact if retained editable source/font changed during execution."""
    hashes = dict(receipt['source_hashes'], **{'font.ttf': receipt['font_sha256']})
    if any(hashlib.sha256((folder / name).read_bytes()).hexdigest() != expected for name, expected in hashes.items()):
        raise Invalid('Hypit project source changed during rendering; inspect this build before retrying')
