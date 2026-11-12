"""Build an explicit WMM folder bundle; never collect operational workspace data."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
DATA = ('mission_control/static', 'mission_control/sdk')
SEEDS = ('app-profiles.json', 'research-ledger.json', 'acquisition-profiles.json')


def command():
    """Freeze the existing app and optional MCP adapter, not the user's Python environment."""
    argv = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir',
            '--name', 'WMM', '--distpath', str(ROOT/'dist/desktop'),
            '--workpath', str(ROOT/'.factory/desktop-build'),
            '--specpath', str(ROOT/'.factory/desktop-build'),
            '--paths', str(ROOT), '--collect-submodules', 'mission_control',
            '--collect-all', 'tzdata', '--copy-metadata', 'mcp',
            '--collect-submodules', 'mcp.server', '--collect-submodules', 'mcp.shared',
            '--collect-submodules', 'mcp.client', '--exclude-module', 'mcp.cli']
    if sys.platform.startswith('linux'):
        argv += ['--collect-all', 'secretstorage', '--collect-submodules', 'jeepney']
    if sys.platform == 'win32':
        argv += ['--collect-all', 'truststore']
    if sys.platform == 'darwin':
        argv += ['--collect-submodules', 'keyring.backends.macOS', '--copy-metadata', 'keyring']
    # A console-enabled executable is needed for stdio MCP/CLI transport.
    # Windows users launch the terminal-free .vbs shortcut supplied alongside it.
    for path in DATA:
        argv += ['--add-data', str(ROOT/path) + ':' + path]
    for name in SEEDS:
        argv += ['--add-data', str(ROOT/'package'/name) + ':package']
    for name in ('LICENSE', 'NOTICE'):
        argv += ['--add-data', str(ROOT/name) + ':.']
    return argv + [str(ROOT/'mission_control/desktop.py')]


def build_native_window(folder):
    """Build the window against the exact frozen engine staged in this folder."""
    if sys.platform not in ('win32', 'darwin') and not sys.platform.startswith('linux'):
        raise RuntimeError('Native Mission Control packaging requires Windows, Ubuntu or macOS')
    suffix = '.exe' if sys.platform == 'win32' else ''
    engine = folder / ('WMM' + suffix)
    if not engine.is_file() or engine.is_symlink():
        raise RuntimeError('Build the exact frozen WMM engine before its native window')
    with engine.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    target = ROOT / '.factory/native-window-build'
    env = dict(os.environ, WMM_NATIVE_ENGINE_SHA256=digest, CARGO_TARGET_DIR=str(target))
    subprocess.run(['cargo', 'build', '--locked', '--release', '--manifest-path',
                    str(ROOT/'desktop/src-tauri/Cargo.toml')], cwd=ROOT, env=env, check=True)
    name = 'WMM-Mission-Control' + suffix
    shutil.copy2(target / 'release' / ('wmm-mission-control' + suffix), folder / name)
    return name


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', action='store_true')
    parser.add_argument('--native-window', action='store_true', help='Include the native Mission Control window')
    args = parser.parse_args()
    argv = command()
    if args.plan:
        print(json.dumps(dict(command=argv, operational_data_included=False, native_window=args.native_window)))
        return
    subprocess.run(argv, cwd=ROOT, check=True)
    folder = ROOT/'dist/desktop/WMM'
    binary = build_native_window(folder) if args.native_window else ('WMM.exe' if sys.platform == 'win32' else 'WMM')
    if sys.platform == 'win32':
        (folder/'Open WMM.vbs').write_text(
            'Set shell = CreateObject("WScript.Shell")\n'
            'Set fs = CreateObject("Scripting.FileSystemObject")\n'
            'folder = fs.GetParentFolderName(WScript.ScriptFullName)\n'
            f'shell.Run Chr(34) & folder & "\\{binary}" & Chr(34), 0, False\n', encoding='utf-8')
    else:
        launcher = folder/'Open WMM.sh'
        launcher.write_text(f'#!/bin/sh\ncd -- "$(dirname -- "$0")" || exit 1\nexec ./{binary}\n')
        launcher.chmod(0o755)
    entry = (
        'Mission Control opens the private workspace in its own window. Close that window to stop the local engine. '
        'This preview requires WebView2 on Windows or WebKitGTK 4.1 on Ubuntu.'
        if args.native_window else
        'A controller opens the private workspace in your browser. Quit from that controller to stop approved local work.'
    )
    (folder/'START-HERE.txt').write_text(
        'Wize Marketing Machine\n\nExtract this entire folder, then open Open WMM. '
        f'No system Python or terminal commands are required. {entry}\n\n'
        'Data is saved in your user application-data directory, outside this folder. '
        'Keep it private and back it up. Updating this folder does not migrate keys or delete your data.\n\n'
        'Linux needs a graphical desktop, browser and an unlocked Secret Service for protected keys. '
        'Optional video/native tools and provider setup remain separate. This bundle is unsigned; '
        'operating-system trust prompts may appear. No auto-updater or startup registration is installed.\n',
        encoding='utf-8')


if __name__ == '__main__':
    main()
