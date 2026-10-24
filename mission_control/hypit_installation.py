"""Read-only identity for the exact installed code a future Studio broker executes."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
from .agent_process import capture
from .common import Invalid, digest

MAX_FILES = 10000
MAX_FILE_BYTES = 134217728
MAX_TREE_BYTES = 268435456
DISCOVERY_TIMEOUT = 15
CHUNK_BYTES = 1048576
REVIEWED = {
    'start.ts': 'a942069e15a5a0cd678218c3bb8ffadd2f87b3d755234439ab8d202ff8d27f88',
    'mutation-origin.ts': '8ec8707d5eb30ae0037f078b1cc9b80dbbc20d255857b0491f9453f7ba9394a9',
    'shared.ts': 'c938e29ca3c68d4dc39fa243571b04a3093ae411b7b1d90b2b75c5a4e904c17a',
    'server.ts': '881f9cd3d0e50e55f92416318a8b2e593b26e094354f848fd269c18f38c6ebcf',
    'build-library.ts': '675af2c5f5d40958c1a8fb6431708339fc452776caa463382ca8777d72fc614d',
    'feedback-server.ts': '5e5b87a7ea295928cf14f19cb343287d8367a82941f39b4e464609091b211f23',
}


def plain(path, directory=False):
    """Reject Windows junctions as well as ordinary symlinks before resolving."""
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 1024:
        raise Invalid('Hypit installation contains a linked or reparse path')
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    if not expected(info.st_mode):
        raise Invalid('Hypit installation has an unsupported file type')
    return info


def file_hash(path):
    """Bound reads and reject replacement or growth while a fingerprint is read."""
    before = plain(path)
    if before.st_size > MAX_FILE_BYTES:
        raise Invalid('Hypit installation file exceeds its fingerprint bound')
    h, count = hashlib.sha256(), 0
    with path.open('rb') as stream:
        opened = os.fstat(stream.fileno())
        if signature(opened) != signature(before):
            raise Invalid('Hypit installation file changed before reading')
        for chunk in iter(lambda: stream.read(CHUNK_BYTES), b''):
            count += len(chunk)
            if count > MAX_FILE_BYTES:
                raise Invalid('Hypit installation file grew beyond its bound')
            h.update(chunk)
        if signature(os.fstat(stream.fileno())) != signature(before):
            raise Invalid('Hypit installation file changed while reading')
    if signature(plain(path)) != signature(before) or count != before.st_size:
        raise Invalid('Hypit installation file changed after reading')
    return h.hexdigest(), count


def signature(info):
    """Use filesystem identity, byte count and nanosecond mutation metadata."""
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def members(root):
    """Enumerate every installed file, without following directories or omitting caches."""
    plain(root, directory=True)
    result = []
    def failed(error):
        raise error
    for folder, dirs, files in os.walk(root, followlinks=False, onerror=failed):
        for name in dirs:
            plain(Path(folder) / name, directory=True)
        for name in files:
            path = Path(folder) / name
            plain(path)
            result.append(path.relative_to(root).as_posix())
            if len(result) > MAX_FILES:
                raise Invalid('Hypit installation has too many files')
    return sorted(result)


def manifest(path, name, version=None):
    """Read only bounded package metadata; never import package code to inspect it."""
    plain(path)
    if path.stat().st_size > CHUNK_BYTES:
        raise Invalid('Hypit package manifest exceeds its bound')
    with path.open('rb') as stream:
        raw = stream.read(CHUNK_BYTES + 1)
    if len(raw) > CHUNK_BYTES:
        raise Invalid('Hypit package manifest changed beyond its bound')
    value = json.loads(raw.decode('utf-8'))
    if not isinstance(value, dict) or value.get('name') != name:
        raise Invalid('Hypit package identity is unsupported')
    if version is not None and value.get('version') != version:
        raise Invalid('Inspect this Hypit version before enabling Studio')


def fingerprint(node, entrypoint):
    """Trusted internal paths only; this does not grant runtime execution authority."""
    try:
        node, entrypoint = Path(node), Path(entrypoint)
        plain(node)
        plain(entrypoint)
        root = entrypoint.parent.parent
        if entrypoint.name != 'hypit.mjs' or entrypoint.parent.name != 'bin':
            raise Invalid('Hypit entrypoint layout is unsupported')
        paths = members(root)
        manifest(root / 'package.json', '@hypit/hypit', '0.3.1')
        for name in ('tsx', 'vite', '@hypit/video'):
            manifest(root / 'node_modules' / name / 'package.json', name)
        hashes, stamps, total = {}, {}, 0
        node_stamp = signature(plain(node))
        node_hash, node_bytes = file_hash(node)
        for name in paths:
            stamps[name] = signature(plain(root / name))
            value, size = file_hash(root / name)
            total += size
            if total > MAX_TREE_BYTES:
                raise Invalid('Hypit installation exceeds its total fingerprint bound')
            hashes[name] = value
        for name, expected in REVIEWED.items():
            if hashes.get('node_modules/@hypit/studio/src/' + name) != expected:
                raise Invalid('Installed Studio source differs from the reviewed interface')
        if members(root) != paths:
            raise Invalid('Hypit installation membership changed while reading')
        if any(signature(plain(root / name)) != stamp for name, stamp in stamps.items()):
            raise Invalid('Hypit installation bytes changed while reading its tree')
        if signature(plain(node)) != node_stamp:
            raise Invalid('Node executable changed while reading the installation')
        value = dict(node=str(node.resolve()), entrypoint=str(entrypoint.resolve()),
                     root=str(root.resolve()), version='0.3.1', files=len(paths),
                     bytes=total, node_bytes=node_bytes, node_sha256=node_hash,
                     tree_sha256=digest(hashes), entrypoint_sha256=hashes['bin/hypit.mjs'])
        value['id'] = digest(value)
        return value
    except Invalid:
        raise
    except (OSError, ValueError, TypeError, KeyError):
        raise Invalid('Hypit installation could not be fingerprinted; inspect local files') from None


def volta_path(tool):
    """Only fixed read-only discovery names reach the existing Volta executable."""
    if tool not in ('hypit', 'node'):
        raise Invalid('Unsupported installation discovery name')
    launcher = shutil.which('volta')
    if not launcher:
        raise Invalid('Resolve the existing Hypit and Node installation before Studio')
    extra = {'PATHEXT': '.EXE;.CMD;.BAT;.COM'} if os.name == 'nt' else {}
    r = capture([launcher, 'which', tool], timeout=DISCOVERY_TIMEOUT, extra_env=extra)
    if r['code'] or len(r['stdout']) > 8192 or len(r['stderr']) > 8192:
        raise Invalid('Installed executable discovery failed')
    return Path(r['stdout'].strip())


def discover():
    """Recognize direct, npm and Volta layouts; never execute Hypit or install code."""
    try:
        hypit, node = shutil.which('hypit'), shutil.which('node')
        if not hypit or not node:
            raise Invalid('Install and inspect optional local Hypit and Node before Studio')
        hypit, node = Path(hypit), Path(node)
        if hypit.parent.name.lower() == 'bin' and hypit.parent.parent.name.lower() == 'volta':
            hypit, node = volta_path('hypit'), volta_path('node')
        elif node.parent.name.lower() == 'volta' or (
                node.parent.name.lower() == 'bin' and node.parent.parent.name.lower() == 'volta'):
            node = volta_path('node')
        direct = hypit.resolve()
        entry = direct if direct.name == 'hypit.mjs' else direct.parent / 'node_modules/@hypit/hypit/bin/hypit.mjs'
        return fingerprint(node.resolve(), entry)
    except Invalid:
        raise
    except (OSError, ValueError):
        raise Invalid('Resolve the existing local installation before opening Studio') from None


def revalidate(expected):
    """Compare all installed bytes and membership before later runtime admission."""
    if not isinstance(expected, dict) or set(expected) != {
            'node', 'entrypoint', 'root', 'version', 'files', 'bytes', 'node_bytes',
            'node_sha256', 'tree_sha256', 'entrypoint_sha256', 'id'}:
        raise Invalid('Expected Hypit installation fingerprint is invalid')
    if fingerprint(expected['node'], expected['entrypoint']) != expected:
        raise Invalid('Hypit installation changed; inspect before opening Studio')
    return expected


def public_summary(value):
    """Return evidence only; omit internal executable paths and any execution claim."""
    return dict(status='FINGERPRINTED_NOT_EXECUTED', version=value['version'],
                installation_id=value['id'], tree_sha256=value['tree_sha256'],
                node_sha256=value['node_sha256'], files=value['files'], bytes=value['bytes'],
                reviewed_abi='MATCH', runtime_acceptance='NOT_RUN')
