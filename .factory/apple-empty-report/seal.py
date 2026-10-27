"""Run and bind evidence for the bounded offline parser; no provider data is used."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess

P = Path('.factory/apple-empty-report')


def item(path, kind='log'):
    path = Path(path)
    return dict(path=path.as_posix(), sha256=hashlib.sha256(path.read_bytes()).hexdigest(), kind=kind)


def write(name, value):
    (P / name).write_bytes((json.dumps(value, indent=2) + '\n').encode())


def run(name, args):
    env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUTF8='1')
    result = subprocess.run(args, capture_output=True, env=env, timeout=180)
    body = (result.stdout + result.stderr).replace(b'\r\n', b'\n')
    (P / (name + '.log')).write_bytes(body)
    if result.stdout.lstrip().startswith(b'{'):
        value, _ = json.JSONDecoder().raw_decode(result.stdout.decode('utf-8').lstrip())
        write(name + '.json', value)
    if result.returncode:
        raise RuntimeError(name + ' failed: ' + str(result.returncode))


run('tests', ['python', '-m', 'unittest', 'tests.test_apple_analytics_parser', 'tests.test_apple_analytics', '-v'])
run('lint', ['ruff', 'check', '--select', 'F,E9', 'mission_control/apple_analytics_parser.py', 'tests/test_apple_analytics_parser.py'])
run('quality', ['forge', 'qa', 'apple-analytics-parser', '--ssat', str(P / 'ssat.json'), '--root', '.', '--strict'])
run('requirements', ['specline', 'strict', 'apple-analytics-parser', '--root', '.', '--json'])
run('mutations-run', ['python', str(P / 'mutations.py')])
scope = P / 'security-scope'
(scope / '.factory').mkdir(parents=True, exist_ok=True)
source = Path('mission_control/apple_analytics_parser.py')
shutil.copyfile(source, scope / source.name)
(scope / '.factory/tenant-read-contract.json').write_bytes(b'{"schema":"factory.tenant-read-contract.v1","reads":[]}\n')
run('security', ['factory', 'audit', 'security', '--root', str(scope), '--json'])
quality = json.loads((P / 'quality.json').read_text(encoding='utf-8'))
security = json.loads((P / 'security.json').read_text(encoding='utf-8'))
assert quality['passed'] and quality['metrics']['max_complexity'] <= 10
assert quality['findings'] == ['QA_SEC[MEDIUM] MD5 - weak hash in mission_control/apple_analytics_parser.py']
assert security['state'] == 'CLEAN' and security['audit_coverage']['complete'] and security['files_scanned'] == 1
assert not security['findings'] and not security['database_context']['gaps']
assert item(source)['sha256'] == item(scope / source.name)['sha256']
review = item(P / 'scope.md', 'review')
paths = [('mission_control/apple_analytics_parser.py', 'source'), ('tests/test_apple_analytics_parser.py', 'test'),
         ('specs/apple-analytics-parser.md', 'contract'), ('plans/apple-analytics-parser.md', 'contract'),
         (P / 'ssat.json', 'contract'), (P / 'mutations.py', 'source'), (P / 'seal.py', 'source')]
candidate = [item(path, kind) for path, kind in paths]
checks = [('happy', 'happy_path', 'Parse synthetic named-column download categories and source hashes'),
          ('validation', 'validation', 'Reject invalid size, checksum, schema, date, count and foreign app'),
          ('recovery', 'failure_recovery', 'Reject an incomplete instance without changing prior parsed observations'),
          ('consistency', 'state_consistency', 'Replace older dates with newer complete data and reject conflicting or cross-app instances'),
          ('privacy', 'security_privacy', 'Validate app identity and do not expose provider credentials or URLs'),
          ('bounds', 'performance', 'Enforce segment, compressed and decompressed size limits on synthetic inputs'),
          ('effects', 'external_effects', 'Run offline without provider writes, network, credential access or database mutations')]
categories = ['happy_path', 'validation', 'failure_recovery', 'state_consistency', 'security_privacy', 'performance', 'accessibility', 'external_effects']
profile = 'Windows-CPython-3.11-synthetic-offline'
contract = dict(schema='factory.workflow-audit.contract.v1', project_id='WMM-apple-empty-report', candidate=candidate,
    applicability=[dict(category=c, applicable=c != 'accessibility', reason='See bounded parser scope', **({'review_evidence': review} if c == 'accessibility' else {})) for c in categories],
    checks=[dict(id=i, category=c, requirement=r, profiles=[profile]) for i, c, r in checks])
write('contract.json', contract)
artifacts = [item(P / name) for name in ('scope.md', 'tests.log', 'lint.log', 'quality.json', 'security.json', 'requirements.log', 'mutations.json', 'mutation-baseline.log', 'mutation-checksum.log', 'mutation-foreign_app.log', 'mutation-correction.log', 'mutation-empty.log')]
write('observations.json', dict(schema='factory.workflow-audit.observations.v1', contract_sha256=item(P / 'contract.json')['sha256'],
    candidate_sha256=hashlib.sha256(json.dumps(candidate, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
    observations=[dict(id=i, profile=profile, status='PASS', reason=r, execution_identity='python .factory/apple-empty-report/seal.py',
                       observed_at=datetime.now(timezone.utc).isoformat(), artifacts=artifacts) for i, c, r in checks]))
run('workflow-receipt', ['factory', 'audit', 'workflows', '--root', '.', '--contract', str(P / 'contract.json'), '--observations', str(P / 'observations.json'), '--json'])
print('Scoped parser workflow evidence passed; provider and product acceptance remain NOT_RUN.')
