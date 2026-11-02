"""Run the built executable from an unrelated directory, without installed source imports."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    binary = ROOT/'dist/desktop/WMM'/('WMM.exe' if sys.platform == 'win32' else 'WMM')
    with tempfile.TemporaryDirectory() as folder:
        for arguments in (['--check'], ['--self-test'], ['--agent-cli', 'catalog']):
            result = subprocess.run([str(binary), *arguments], cwd=folder, check=True,
                                    capture_output=True, text=True, timeout=90)
            value = json.loads(result.stdout)
            if arguments == ['--self-test']:
                assert value['status'] == 'PASS'
            print(json.dumps(dict(command=arguments, exit_code=result.returncode)))


if __name__ == '__main__':
    main()
