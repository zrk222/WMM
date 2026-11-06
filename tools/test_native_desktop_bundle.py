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


def isolated_environment(profile):
    environment_keys = ('PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'LANG', 'LC_ALL',
                        'ProgramFiles', 'ProgramFiles(x86)', 'ProgramData', 'SystemDrive')
    env = {key: os.environ[key] for key in environment_keys if key in os.environ}
    env.update(LOCALAPPDATA=str(profile), APPDATA=str(profile), USERPROFILE=str(profile),
               XDG_DATA_HOME=str(profile), HOME=str(profile))
    return env


def run(shell, profile):
    return subprocess.run([str(shell), '--verify-bundled-engine'], cwd=shell.parent,
                          env=isolated_environment(profile),
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


WINDOW_READY_AND_CLOSE = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
$window = Get-Process -Id ([int]$env:WMM_PROBE_PID)
$timer = [Diagnostics.Stopwatch]::StartNew()
while ($timer.Elapsed.TotalSeconds -lt 25) {
    $window.Refresh()
    if ($window.HasExited) { throw 'Mission Control exited before rendering' }
    if ($window.MainWindowHandle -ne 0 -and $window.MainWindowTitle -eq 'Wize Marketing Machine') {
        $root = [Windows.Automation.AutomationElement]::FromHandle($window.MainWindowHandle)
        $names = @($root.FindAll([Windows.Automation.TreeScope]::Descendants,
            [Windows.Automation.Condition]::TrueCondition) | ForEach-Object { $_.Current.Name })
        if ($names -contains 'Set your goal' -and $names -contains 'Watch the work' -and $names -contains 'Review results') {
            if (!$window.CloseMainWindow()) { throw 'Could not close the owned Mission Control window' }
            exit 0
        }
    }
    Start-Sleep -Milliseconds 250
}
throw 'Mission Control goal controls did not render in the native window'
"""


def verify_windows_window(folder):
    """Exercise the real Windows entry point and the operating system window-close event."""
    if sys.platform != 'win32':
        raise ValueError('Native window verification requires Windows')
    shell = folder.resolve(strict=True) / 'WMM-Mission-Control.exe'
    with tempfile.TemporaryDirectory(prefix='wmm-native-window-', ignore_cleanup_errors=True) as temporary:
        profile = Path(temporary)
        env = isolated_environment(profile)
        env['WEBVIEW2_USER_DATA_FOLDER'] = str(profile / 'webview')
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = 7  # SW_SHOWMINNOACTIVE
        child = subprocess.Popen([str(shell)], cwd=shell.parent, env=env, startupinfo=startup,
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            env['WMM_PROBE_PID'] = str(child.pid)
            subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', WINDOW_READY_AND_CLOSE],
                           env=env, check=True, timeout=35)
            exit_code = child.wait(timeout=50)
            if exit_code != 0:
                raise RuntimeError(f'Mission Control returned {exit_code} after its rendered window closed')
            if not (profile / 'Wize Marketing Machine' / 'mission-control.sqlite3').is_file():
                raise RuntimeError('Native window did not use its disposable workspace')
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=10)
    return dict(status='PASS', goal_controls='VERIFIED_WINDOWS_UI_AUTOMATION', exit_code=0,
                profile='DISPOSABLE_SYNTHETIC', shell_sha256=digest(shell))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    parser.add_argument('--windows-window', action='store_true')
    args = parser.parse_args()
    verify = verify_windows_window if args.windows_window else verify_bundle
    print(json.dumps(verify(args.folder)))


if __name__ == '__main__':
    main()
