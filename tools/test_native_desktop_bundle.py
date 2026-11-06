"""Verify the exact staged native shell and engine in disposable workspaces."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def run(shell, profile):
    environment_keys = ('PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'LANG', 'LC_ALL')
    env = {key: os.environ[key] for key in environment_keys if key in os.environ}
    env.update(LOCALAPPDATA=str(profile), XDG_DATA_HOME=str(profile), HOME=str(profile))
    return subprocess.run([str(shell), '--verify-bundled-engine'], cwd=shell.parent, env=env,
                          stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL, timeout=75).returncode


def verify_bundle(folder):
    folder = folder.resolve()
    suffix = '.exe' if sys.platform == 'win32' else ''
    shell, engine = (folder / (name + suffix) for name in ('WMM-Mission-Control', 'WMM'))
    if not shell.is_file() or not engine.is_file():
        raise ValueError('Native package must contain both the shell and frozen engine')
    with tempfile.TemporaryDirectory(prefix='wmm-native-package-') as temporary:
        isolated = Path(temporary)
        profile = isolated / 'accepted'
        if run(shell, profile) != 0:
            raise RuntimeError('Exact packaged engine verification failed')
        database = profile / 'Wize Marketing Machine' / 'mission-control.sqlite3'
        if not database.is_file():
            raise RuntimeError('Packaged engine did not open its disposable workspace')
        conn = sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)
        try:
            if conn.execute('SELECT COUNT(*) FROM jobs').fetchone()[0] != 0:
                raise RuntimeError('Disposable package check unexpectedly created work')
        finally:
            conn.close()

        altered = isolated / 'altered-bundle'
        altered.mkdir()
        shutil.copy2(shell, altered / shell.name)
        (altered / engine.name).write_bytes(b'disposable digest mismatch fixture')
        rejected = isolated / 'rejected'
        if run(altered / shell.name, rejected) == 0 or rejected.exists():
            raise RuntimeError('Native shell did not reject an altered engine before startup')
    return dict(status='PASS', shell_sha256=digest(shell), engine_sha256=digest(engine),
                exact_engine='VERIFIED', graceful_shutdown=True, altered_engine='REJECTED_BEFORE_START',
                profile='DISPOSABLE_SYNTHETIC', interactive_webview='NOT_RUN')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    print(json.dumps(verify_bundle(parser.parse_args().folder)))


if __name__ == '__main__':
    main()
