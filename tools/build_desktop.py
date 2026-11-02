"""Build an explicit WMM folder bundle; never collect operational workspace data."""
import argparse
import json
from pathlib import Path
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
    # A console-enabled executable is needed for stdio MCP/CLI transport.
    # Windows users launch the terminal-free .vbs shortcut supplied alongside it.
    for path in DATA:
        argv += ['--add-data', str(ROOT/path) + ':' + path]
    for name in SEEDS:
        argv += ['--add-data', str(ROOT/'package'/name) + ':package']
    for name in ('LICENSE', 'NOTICE'):
        argv += ['--add-data', str(ROOT/name) + ':.']
    return argv + [str(ROOT/'mission_control/desktop.py')]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', action='store_true')
    args = parser.parse_args()
    argv = command()
    if args.plan:
        print(json.dumps(dict(command=argv, operational_data_included=False)))
        return
    subprocess.run(argv, cwd=ROOT, check=True)
    folder = ROOT/'dist/desktop/WMM'
    if sys.platform == 'win32':
        (folder/'Open WMM.vbs').write_text(
            'Set shell = CreateObject("WScript.Shell")\n'
            'Set fs = CreateObject("Scripting.FileSystemObject")\n'
            'folder = fs.GetParentFolderName(WScript.ScriptFullName)\n'
            'shell.Run Chr(34) & folder & "\\WMM.exe" & Chr(34), 0, False\n', encoding='utf-8')
    else:
        launcher = folder/'Open WMM.sh'
        launcher.write_text('#!/bin/sh\ncd -- "$(dirname -- "$0")" || exit 1\nexec ./WMM\n')
        launcher.chmod(0o755)
    (folder/'START-HERE.txt').write_text(
        'Wize Marketing Machine\n\nExtract this entire folder, then open Open WMM. '
        'No system Python or terminal commands are required. A controller opens the private workspace '
        'in your browser. Quit from that controller to stop approved local work.\n\n'
        'Data is saved in your user application-data directory, outside this folder. '
        'Keep it private and back it up. Updating this folder does not migrate keys or delete your data.\n\n'
        'Linux needs a graphical desktop, browser and an unlocked Secret Service for protected keys. '
        'Optional video/native tools and provider setup remain separate. This bundle is unsigned; '
        'operating-system trust prompts may appear. No auto-updater or startup registration is installed.\n',
        encoding='utf-8')


if __name__ == '__main__':
    main()
