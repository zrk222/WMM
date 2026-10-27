"""Bind the synthetic CI clock repair to its exact tests and production context."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import subprocess

P = Path('.factory/source-progress-ci')
P.mkdir(parents=True, exist_ok=True)


def item(path, kind='log'):
    path = Path(path)
    return dict(path=path.as_posix(), sha256=hashlib.sha256(path.read_bytes()).hexdigest(), kind=kind)


def write(name, value):
    (P / name).write_bytes((json.dumps(value, indent=2) + '\n').encode())


def run(name, args):
    result = subprocess.run(args, capture_output=True, env=dict(os.environ, PYTHONUTF8='1', PYTHONIOENCODING='utf-8'), timeout=180)
    body = (result.stdout + result.stderr).decode('utf-8', errors='replace')
    (P / (name + '.log')).write_bytes(('\n'.join(line.rstrip() for line in body.splitlines()) + '\n').encode())
    if result.returncode:
        raise RuntimeError(name + ' failed: ' + str(result.returncode))
    return result.stdout


run('tests', ['python', '-m', 'unittest', 'tests.test_source_progress', 'tests.test_campaign_inputs', '-v'])
run('lint', ['ruff', 'check', '--select', 'F,E9', 'tests/test_source_progress.py'])
(P / 'scope.md').write_bytes(b'Test fixture holds the hourly proposal clock stable only while authorizing and dispatching a synthetic job. Production hourly expiry and approval checks are unchanged. Existing tests cover stale and foreign proposals. No UI, timing performance claim, network, provider write or production mutation is added.\n')
review = item(P / 'scope.md', 'review')
candidate = [item('tests/test_source_progress.py', 'test'), item('mission_control/campaign_inputs.py', 'source'),
             item('mission_control/resolution_tools.py', 'source'), item('tests/test_campaign_inputs.py', 'test'), item(P / 'seal.py', 'source')]
checks = [('happy', 'happy_path', 'Synthetic collection dispatch succeeds inside a stable approved hour'),
          ('validation', 'validation', 'Existing stale and foreign approval rejection remains tested'),
          ('recovery', 'failure_recovery', 'Existing tests retain failed results and expose repair'),
          ('state', 'state_consistency', 'Synthetic persisted child status remains app scoped across restart'),
          ('privacy', 'security_privacy', 'Foreign source jobs cannot satisfy collection and production authority is unchanged')]
categories = ['happy_path', 'validation', 'failure_recovery', 'state_consistency', 'security_privacy', 'performance', 'accessibility', 'external_effects']
profile = 'Windows-CPython-3.11-synthetic-SQLite'
contract = dict(schema='factory.workflow-audit.contract.v1', project_id='WMM-source-progress-ci-clock', candidate=candidate,
    applicability=[dict(category=c, applicable=c not in ('performance','accessibility','external_effects'), reason='See scoped test-only review', **({'review_evidence': review} if c in ('performance','accessibility','external_effects') else {})) for c in categories],
    checks=[dict(id=i, category=c, requirement=r, profiles=[profile]) for i,c,r in checks])
write('contract.json', contract)
artifacts = [item(P / 'tests.log'), item(P / 'lint.log')]
write('observations.json', dict(schema='factory.workflow-audit.observations.v1', contract_sha256=item(P / 'contract.json')['sha256'],
    candidate_sha256=hashlib.sha256(json.dumps(candidate, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
    observations=[dict(id=i, profile=profile, status='PASS', reason=r, execution_identity='python .factory/source-progress-ci/seal.py', observed_at=datetime.now(timezone.utc).isoformat(), artifacts=artifacts) for i,c,r in checks]))
raw = run('workflow', ['factory', 'audit', 'workflows', '--root', '.', '--contract', str(P / 'contract.json'), '--observations', str(P / 'observations.json'), '--json'])
assert json.loads(raw)['state'] == 'PASS'
print('Clock fixture workflow audit PASS')
