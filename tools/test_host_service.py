"""Opt-in disposable Ubuntu CI user-manager lifecycle test; never provision a host."""
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import ProxyHandler, build_opener
from uuid import uuid4

BINARY = Path('/usr/lib/wize-marketing-machine/WMM')
UNIT = Path('/usr/share/wize-marketing-machine/wmm-worker.service')


def preflight(env):
    # All checks here are read-only: do not even create a temporary directory first.
    if (not sys.platform.startswith('linux') or env.get('CI') != 'true'
            or env.get('GITHUB_ACTIONS') != 'true'
            or env.get('WMM_HOST_SERVICE_CI') != '1'
            or env.get('WMM_ISOLATED_USER_MANAGER') != '1'):
        raise RuntimeError('Requires explicitly isolated disposable Ubuntu CI user manager')
    import pwd
    uid = os.geteuid()
    user = pwd.getpwuid(uid)
    runtime = Path(env.get('XDG_RUNTIME_DIR', '/nonexistent'))
    home = Path(env.get('HOME', '/nonexistent'))
    temp = Path(env.get('RUNNER_TEMP', '/nonexistent'))
    if (uid == 0 or not user.pw_name.startswith('wmm-ci-')
            or not home.is_absolute() or not temp.is_absolute()
            or not home.is_dir() or not temp.is_dir()
            or Path(user.pw_dir) != home or home.owner() != user.pw_name
            or not home.resolve().is_relative_to(temp.resolve())
            or runtime != Path('/run/user') / str(uid)
            or not runtime.is_dir() or runtime.stat().st_uid != uid
            or env.get('DBUS_SESSION_BUS_ADDRESS') != f'unix:path={runtime}/bus'
            or not (runtime / 'bus').exists()
            or not BINARY.is_file() or not os.access(BINARY, os.X_OK)
            or not UNIT.is_file() or not os.access(UNIT, os.R_OK)):
        raise RuntimeError('Disposable user, manager bus, temporary home or installed binary is invalid')
    # Do not interfere with any already-running listener on the fixed port.
    with socket.socket() as probe:
        try:
            probe.bind(('127.0.0.1', 8765))
        except OSError as exc:
            raise RuntimeError('Fixed WMM loopback port is occupied') from exc
    return runtime


def command(env, *args, check=True, timeout=75):
    return subprocess.run([str(x) for x in args], env=env, check=check,
                          capture_output=True, text=True, timeout=timeout)


def systemctl(env, *args, check=True):
    return command(env, 'systemctl', '--user', *args, check=check)


def wait_bootstrap(env, name):
    client = build_opener(ProxyHandler({}))
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        try:
            with client.open('http://127.0.0.1:8765/api/bootstrap', timeout=2) as response:
                if json.load(response).get('apps'):
                    return
        except (OSError, ValueError):
            time.sleep(.25)
    raise RuntimeError(f'{name} did not serve bootstrap before timeout')


def assert_stopped(env, name):
    state = systemctl(env, 'show', name, '--property=ActiveState', '--value').stdout.strip()
    pid = systemctl(env, 'show', name, '--property=MainPID', '--value').stdout.strip()
    result = systemctl(env, 'show', name, '--property=Result', '--value').stdout.strip()
    if (state, pid, result) != ('inactive', '0', 'success'):
        raise AssertionError(f'Service did not stop cleanly: {state}, pid={pid}, result={result}')


def main():
    env = dict(os.environ)
    runtime = preflight(env)
    # Ensure the selected bus really has a working user manager before writes.
    systemctl(env, 'show-environment')
    name = f'wmm-ci-{uuid4().hex}.service'
    link = runtime / 'systemd/user' / name
    if link.exists() or link.is_symlink():
        raise RuntimeError('Generated test unit name already exists')
    linked = False
    with tempfile.TemporaryDirectory(prefix='wmm-host-ci-', dir=env['HOME']) as folder:
        directory = Path(folder)
        # systemd environment assignment is deliberately restricted to simple paths.
        if not re.fullmatch(r'/[A-Za-z0-9_./-]+', str(directory)):
            raise RuntimeError('Disposable home path is not safe for a systemd assignment')
        unit = directory / name
        unit.write_text(UNIT.read_text(encoding='utf-8') +
                        f'\n[Service]\nEnvironment=XDG_DATA_HOME={directory}/data\n', encoding='utf-8')
        child_env = dict(env, XDG_DATA_HOME=str(directory / 'data'))
        try:
            systemctl(env, 'link', '--runtime', str(unit))
            linked = True
            if not link.is_symlink() or link.resolve() != unit.resolve():
                raise RuntimeError('Unexpected runtime unit link')
            systemctl(env, 'start', name)
            wait_bootstrap(env, name)
            workspace = directory / 'data/Wize Marketing Machine'
            database = workspace / 'mission-control.sqlite3'
            if not database.is_file() or database.stat().st_mode & 0o077:
                raise AssertionError('Service workspace database is not private')
            other = command(child_env, BINARY, '--headless', check=False, timeout=45)
            if (other.returncode == 0 or 'Workspace is already running' not in other.stderr
                    or systemctl(env, 'is-active', name).stdout.strip() != 'active'):
                raise AssertionError('A competing runtime was not excluded')
            systemctl(env, 'stop', name)
            assert_stopped(env, name)
            systemctl(env, 'start', name)
            wait_bootstrap(env, name)
            systemctl(env, 'stop', name)
            assert_stopped(env, name)
        finally:
            if linked or link.is_symlink():
                if not link.is_symlink() or link.resolve() != unit.resolve():
                    raise RuntimeError('Refusing to remove a changed test unit link')
                systemctl(env, 'stop', name)
                systemctl(env, 'reset-failed', name, check=False)
                state = systemctl(env, 'show', name, '--property=MainPID', '--value').stdout.strip()
                if state != '0':
                    raise RuntimeError('Refusing cleanup while test service process remains')
                link.unlink()
                systemctl(env, 'daemon-reload')
                if link.exists() or link.is_symlink():
                    raise AssertionError('Test unit link remains')
    print(json.dumps({'status': 'PASS', 'bootstrap': 'VERIFIED', 'workspace_exclusion': 'VERIFIED',
                      'stop_restart': 'VERIFIED', 'unit_cleanup': 'VERIFIED',
                      'data': 'DISPOSABLE_SYNTHETIC', 'provider': 'NOT_RUN'}))


if __name__ == '__main__':
    main()
