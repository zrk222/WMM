"""Ubuntu workflow preflight; actual Linux execution remains a separate gate."""
from pathlib import Path
import hashlib
import json
import subprocess
import yaml

P = Path('.factory/ubuntu-ci')
P.mkdir(parents=True, exist_ok=True)
source = Path('.github/workflows/checks.yml')
workflow = yaml.safe_load(source.read_text())
windows, ubuntu = (workflow['jobs'][name] for name in ('windows', 'ubuntu'))
assert windows['strategy'] == ubuntu['strategy']
assert 'python -X utf8 tools/run_ci_tests.py --shards 4 --index "$WMM_CI_SHARD"' in ubuntu['steps'][-1]['run']
assert ubuntu['steps'][-1]['env']['WMM_CI_SHARD'] == '${{ matrix.shard }}'
assert 'dbus-run-session -- bash -euo pipefail' in ubuntu['steps'][-1]['run']
assert 'mktemp -d "$RUNNER_TEMP/wmm-keyring.XXXXXX"' in ubuntu['steps'][-1]['run']
assert ubuntu['runs-on'] == 'ubuntu-24.04'
assert workflow['permissions'] == {'contents': 'read'}
assert all(not step.get('continue-on-error') for step in ubuntu['steps'])
bash = Path('C:/Program Files/Git/bin/bash.exe')
if bash.exists():
    for step in ubuntu['steps']:
        if 'run' in step:
            result = subprocess.run([str(bash), '-n'], input=step['run'].encode(), capture_output=True)
            assert result.returncode == 0, result.stderr.decode()
for path, command in [('runner.log', ['python', '-m', 'unittest', 'tests.test_ci_runner', '-v']), ('privacy.log', ['python', 'tools/check_distribution.py'])]:
    result = subprocess.run(command, capture_output=True)
    (P/path).write_bytes((result.stdout+result.stderr).replace(b'\r\n', b'\n'))
    assert result.returncode == 0, path
value = dict(source=source.as_posix(), sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
    yaml_valid=True, same_four_shards=True, same_regression_runner=True, read_only_permissions=True,
    failure_suppression=False, local_runner_tests=8, linux_execution='PENDING_GITHUB_CI',
    limits=['No standalone iOS claim', 'No native keyring acceptance claim', 'No actual Linux pass until remote jobs finish'])
(P/'preflight.json').write_bytes((json.dumps(value, indent=2)+'\n').encode())
print(json.dumps(value))
