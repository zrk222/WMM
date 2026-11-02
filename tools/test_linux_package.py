"""Opt-in isolated Ubuntu CI package install, upgrade and removal verification."""
import importlib.util
import io
import json
import os
from pathlib import Path
import posixpath
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = 'wize-marketing-machine'
TIMEOUT_SECONDS = 180


def run(argv, env, check=True):
    return subprocess.run([str(x) for x in argv], check=check, env=env, text=True,
                          capture_output=True, timeout=TIMEOUT_SECONDS)


def inspect_archive(raw, control=False):
    """Reject maintainer scripts and payload paths outside the fixed WMM layout."""
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:*') as archive:
        for member in archive:
            name = member.name.removeprefix('./').rstrip('/')
            if name in ('', '.'):
                continue
            if control:
                if name not in ('control', 'md5sums') or not member.isfile():
                    raise RuntimeError('Package contains an unexpected control entry')
                continue
            allowed = ('usr', 'usr/lib', 'usr/bin', 'usr/share', 'usr/share/applications',
                       'usr/lib/wize-marketing-machine', 'usr/bin/wize-marketing-machine',
                       'usr/share/applications/wize-marketing-machine.desktop')
            if name not in allowed and not name.startswith('usr/lib/wize-marketing-machine/'):
                raise RuntimeError('Package payload escapes the WMM program layout')
            if posixpath.normpath(name) != name or name.startswith('/'):
                raise RuntimeError('Package payload path is not canonical')
            if member.issym() or member.islnk():
                target = posixpath.normpath(posixpath.join(posixpath.dirname(name), member.linkname))
                if member.linkname.startswith('/') or not target.startswith('usr/lib/wize-marketing-machine/'):
                    raise RuntimeError('Package link escapes the WMM runtime')
            elif not (member.isfile() or member.isdir()):
                raise RuntimeError('Package contains an unsupported entry')


def preflight(env):
    if (not sys.platform.startswith('linux') or os.geteuid() != 0 or env.get('CI') != 'true'
            or env.get('WMM_LINUX_PACKAGE_TEST') != '1' or env.get('WMM_ISOLATED_NATIVE_KEYRING') != '1'
            or not env.get('DBUS_SESSION_BUS_ADDRESS')):
        raise RuntimeError('Package testing requires an explicitly enabled isolated root Ubuntu CI keyring session')
    package = (ROOT / 'dist/linux/wize-marketing-machine_0.1.0_amd64.deb').resolve()
    if not package.is_file():
        raise RuntimeError('Build the exact WMM Debian package first')
    found = run(['dpkg-deb', '--field', package, 'Package'], env).stdout.strip()
    if found != PACKAGE:
        raise RuntimeError('Package identity does not match WMM')
    for option, control in (('--ctrl-tarfile', True), ('--fsys-tarfile', False)):
        payload = subprocess.check_output(['dpkg-deb', option, str(package)], env=env, timeout=TIMEOUT_SECONDS)
        inspect_archive(payload, control)
    existing = run(['dpkg-query', '-W', '-f=${db:Status-Status}', PACKAGE], env, check=False)
    if existing.returncode == 0 and existing.stdout.strip() not in ('', 'not-installed'):
        raise RuntimeError('WMM package already exists; refusing to alter it')
    targets = ('/usr/lib/wize-marketing-machine', '/usr/bin/wize-marketing-machine',
               '/usr/share/applications/wize-marketing-machine.desktop')
    if any(Path(path).exists() or Path(path).is_symlink() for path in targets):
        raise RuntimeError('WMM target path already exists; refusing to alter it')
    return package


def verify_binary(binary, env):
    for args in (['--check'], ['--self-test'], ['--vault-self-test'], ['--agent-cli', 'catalog']):
        result = json.loads(run([binary, *args], env).stdout)
        if args == ['--check'] and Path(result['data_directory']) != Path(env['XDG_DATA_HOME']) / 'Wize Marketing Machine':
            raise AssertionError('Installed runtime selected an unexpected workspace')
        if args in (['--self-test'], ['--vault-self-test']) and result.get('status') != 'PASS':
            raise AssertionError('Installed runtime self-test failed')
    spec = importlib.util.spec_from_file_location('wmm_bundle_smoke', ROOT / 'tools/smoke_desktop_bundle.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    import anyio
    anyio.run(module.mcp_smoke, binary, env['XDG_DATA_HOME'])


def main():
    env = dict(os.environ)
    package = preflight(env)
    attempted = False
    with tempfile.TemporaryDirectory(prefix='wmm-deb-ci-') as temporary:
        data = Path(temporary).resolve()
        env['XDG_DATA_HOME'] = str(data)
        workspace = data / 'Wize Marketing Machine'
        workspace.mkdir()
        marker = workspace / 'workspace-fixture.txt'
        marker.write_text('synthetic private workspace', encoding='utf-8')
        try:
            attempted = True
            run(['dpkg', '-i', package], env)
            binary = Path('/usr/lib/wize-marketing-machine/WMM')
            if not binary.is_file() or not Path('/usr/bin/wize-marketing-machine').is_file():
                raise AssertionError('Installed runtime is incomplete')
            verify_binary(binary, env)
            run(['dpkg', '-i', package], env)
            if marker.read_text(encoding='utf-8') != 'synthetic private workspace':
                raise AssertionError('Upgrade changed the workspace fixture')
        finally:
            if attempted:
                run(['dpkg', '-r', PACKAGE], env)
        if binary.exists() or marker.read_text(encoding='utf-8') != 'synthetic private workspace':
            raise AssertionError('Removal did not remove runtime or preserve workspace fixture')
    print(json.dumps(dict(status='PASS', install='VERIFIED', upgrade='VERIFIED', removal='VERIFIED',
                          workspace='SYNTHETIC_PRESERVED', provider='NOT_RUN')))


if __name__ == '__main__':
    main()
