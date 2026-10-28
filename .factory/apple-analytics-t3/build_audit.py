"""Rebuild candidate-bound CF evidence for the Apple analytics T3 slice."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / '.factory' / 'apple-analytics-t3'
PROFILE = 'Windows-CPython-3.11.9-SQLite-synthetic-offline'
BASE_COMMIT = '4d3fad78b8a16a4b31013a9c58055c64256c4420'


def sha(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def run(name, args):
    result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True,
                            encoding='utf-8', errors='replace')
    path = OUT / (name + '.log')
    output = result.stdout + result.stderr
    output = re.sub(r'(?i)\b[a-z]:[/\\]users[/\\][^\s"\']+', '[local path]', output)
    path.write_text('$ ' + ' '.join(map(str, args)) + '\n' + output,
                    encoding='utf-8')
    if result.returncode:
        raise SystemExit(f'{name} failed with exit {result.returncode}; inspect {path}')
    return path


def redact_historical_failure_paths():
    path = OUT / 'unittest-first-failure.log'
    if not path.exists():
        return
    payload = path.read_bytes()
    encoding = 'utf-16' if payload.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8-sig'
    text = payload.decode(encoding, errors='replace')
    text = re.sub(r'(?i)\b[a-z]:[/\\]users[/\\][^\s"\']+', '[local path]', text)
    path.write_bytes(text.encode(encoding))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    redact_historical_failure_paths()
    run('factory-doctor', ['factory', 'doctor', '--strict', '--json'])
    run('specline-strict', ['specline', 'strict', 'apple-analytics-metrics', '--root', '.', '--json'])
    run('specline-spec-gate', ['specline', 'gate', 'spec', 'apple-analytics-metrics', '--root', '.'])
    run('specline-plan-gate', ['specline', 'gate', 'plan', 'apple-analytics-metrics',
                               '--approver', 'codex-user-authorized', '--root', '.'])
    run('specline-tasks', ['specline', 'tasks', 'apple-analytics-metrics', '--root', '.'])
    run('specline-drift-audit', ['specline', 'audit', 'apple-analytics-metrics', '--root', '.',
        '--files', 'mission_control/apple_metrics.py', 'mission_control/apple_metrics_store.py',
        'mission_control/db.py', 'tests/test_apple_metrics.py', 'tests/test_apple_metrics_store.py',
        '--slice', 'mission_control', '--base-commit', BASE_COMMIT, '--json'])
    test_args = ['python', '-m', 'unittest', 'tests.test_apple_metrics',
        'tests.test_apple_metrics_store', 'tests.test_apple_metrics_contract',
        'tests.test_apple_analytics_parser', 'tests.test_apple_metrics_transport', '-v']
    test_log = run('unittest', test_args)
    t4_args = ['python', '-m', 'unittest', 'tests.test_apple_metrics_transport',
               'tests.test_apple_metrics', '-v']
    t4_log = run('t4-unittest', t4_args)

    candidates = [
        ('mission_control/apple_metrics.py', 'source'),
        ('mission_control/apple_metrics_store.py', 'source'),
        ('mission_control/apple_metrics_contract.py', 'source'),
        ('mission_control/common.py', 'source'),
        ('mission_control/db.py', 'source'),
        ('tests/test_apple_metrics.py', 'test'),
        ('tests/test_apple_metrics_store.py', 'test'),
        ('tests/test_apple_metrics_contract.py', 'test'),
        ('tests/test_apple_analytics_parser.py', 'test'),
        ('tests/test_apple_metrics_transport.py', 'test'),
        ('specs/apple-analytics-metrics.md', 'contract'),
        ('plans/apple-analytics-metrics.md', 'contract'),
        ('.factory/apple-analytics-t3/scope-review.md', 'review'),
        ('.factory/apple-analytics-t3/build_audit.py', 'audit_tool'),
    ]
    candidate = [dict(path=path, sha256=sha(path), kind=kind) for path, kind in candidates]
    review_path = '.factory/apple-analytics-t3/scope-review.md'
    categories = [
        dict(category='happy_path', applicable=True,
             reason='Parse complete report segments into dated app partitions and read them back after local persistence.'),
        dict(category='validation', applicable=True,
             reason='Reject malformed dates, schemas, foreign app identifiers, unsupported key fields, duplicate segments and unsafe dimensions.'),
        dict(category='failure_recovery', applicable=True,
             reason='Prove malformed reports do not persist and SQL failure rolls back every date in the report savepoint.'),
        dict(category='state_consistency', applicable=True,
             reason='Prove idempotence, newer correction replacement, stale no-op behavior, absent dates and explicit zero observations.'),
        dict(category='security_privacy', applicable=True,
             reason='Keep app scope and source provenance bound; exclude signed URL fields and reject URL-like observation labels; production ingestion stays disabled.'),
        dict(category='performance', applicable=True,
             reason='Enforce parser, partition-count, per-partition and per-app byte bounds before local persistence.'),
        dict(category='accessibility', applicable=False,
             reason='No UI, keyboard interaction, or assistive-technology behavior changes in this backend-only slice.',
             review_evidence=dict(path=review_path, sha256=sha(review_path), kind='review')),
        dict(category='external_effects', applicable=False,
             reason='The slice is offline and has no provider, network, subprocess, publication, or campaign side effect; production ingestion stays disabled.',
             review_evidence=dict(path=review_path, sha256=sha(review_path), kind='review')),
    ]
    requirements = {
        'happy_path': 'Parse a complete supported Apple App Downloads Standard instance, split observations by event date, and retain source provenance in a local app-scoped SQLite partition.',
        'validation': 'Reject malformed or foreign report data, invalid identity, repeated segments, and labels that could contain URLs or credential syntax.',
        'failure_recovery': 'Ensure parsing failure and a failed later-date SQLite write leave no partial partitions.',
        'state_consistency': 'Make duplicate reads idempotent, newer complete corrections replace without summing, and stale reads do not overwrite newer observations.',
        'security_privacy': 'Store only bounded app-scoped observations and source hashes; do not return signed URL fields or enable production ingestion.',
        'performance': 'Enforce complete-parser, partition-count, individual-partition byte, and aggregate per-app storage bounds.',
    }
    checks = [dict(id=name, category=name, requirement=requirements[name], profiles=[PROFILE])
              for name in requirements]
    contract = dict(schema='factory.workflow-audit.contract.v1',
        project_id='WMM-apple-analytics-parse-reconcile-T3', candidate=candidate,
        applicability=categories, checks=checks)
    contract_path = OUT / 'workflow-audit-contract.json'
    contract_path.write_text(json.dumps(contract, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    contract_hash = hashlib.sha256(contract_path.read_bytes()).hexdigest()
    candidate_hash = hashlib.sha256(json.dumps(candidate, ensure_ascii=False, sort_keys=True,
        separators=(',', ':')).encode('utf-8')).hexdigest()
    log_paths = [str(path.relative_to(ROOT)).replace('\\', '/')
                 for path in (test_log, t4_log)]
    reasons = {
        'happy_path': 'Named synthetic tests parse multi-day downloads and persist/read back source-bound app partitions.',
        'validation': 'Named tests reject malformed gzip/checksum/date/schema, foreign app identity, duplicate segment identity, closed-key violations, and URL-like dimensions.',
        'failure_recovery': 'A synthetic SQLite trigger fails the second event date and the test confirms the savepoint leaves zero partial rows.',
        'state_consistency': 'Tests verify INSERTED/UNCHANGED/REPLACED/STALE behavior, no summation, explicit zero, absent dates and persistence integrity.',
        'security_privacy': 'Tests confirm signed URL extras are absent from outputs, unsafe labels fail, and store ingestion remains disabled.',
        'performance': 'The parser and storage enforce segment, row, decompression, partition-count and local byte ceilings before accepting data.',
    }
    observations = []
    for name in requirements:
        observations.append(dict(id=name, profile=PROFILE, status='PASS',
            reason=reasons[name], execution_identity='; '.join(
                [' '.join(test_args), ' '.join(t4_args)]),
            observed_at=datetime.now(timezone.utc).isoformat(),
            artifacts=[dict(path=path, sha256=sha(path), kind='log') for path in log_paths]))
    observation_doc = dict(schema='factory.workflow-audit.observations.v1',
        contract_sha256=contract_hash, candidate_sha256=candidate_hash,
        observations=observations)
    observation_path = OUT / 'workflow-audit-observations.json'
    observation_path.write_text(json.dumps(observation_doc, ensure_ascii=False, indent=2) + '\n',
                                encoding='utf-8')
    command = [sys.executable, '-m', 'factoryline.cli', 'audit', 'workflows',
        '--root', str(ROOT), '--contract', '.factory/apple-analytics-t3/workflow-audit-contract.json',
        '--observations', '.factory/apple-analytics-t3/workflow-audit-observations.json', '--json']
    audit = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                           encoding='utf-8', errors='replace')
    receipt = OUT / 'workflow-audit-receipt.json'
    receipt.write_text(audit.stdout, encoding='utf-8')
    (OUT / 'workflow-audit.stderr.log').write_text(audit.stderr, encoding='utf-8')
    if audit.returncode:
        raise SystemExit(f'workflow audit failed with exit {audit.returncode}; inspect {receipt}')
    result = json.loads(audit.stdout)
    if result.get('state') != 'PASS':
        raise SystemExit(f'workflow audit did not PASS; inspect {receipt}')
    print(json.dumps(dict(contract=str(contract_path.relative_to(ROOT)),
        contract_sha256=contract_hash, candidate_sha256=candidate_hash,
        observed_categories=len(observations), test_logs=log_paths,
        receipt_sha256=hashlib.sha256(receipt.read_bytes()).hexdigest()), indent=2))


if __name__ == '__main__':
    main()
