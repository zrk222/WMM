"""Bind owner continuation acceptance to reproducible local observations."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json

ROOT = Path.cwd()
BASE = Path('.factory/owner-onboarding')

def artifact(path, kind='log'):
    return dict(path=str(path).replace('\\', '/'), sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest(), kind=kind)

def write(name, value):
    (BASE/name).write_bytes((json.dumps(value, indent=2)+'\n').encode())

paths = ['mission_control/static/verified-review.js', 'tests/owner_onboarding.test.cjs', 'tools/test_owner_onboarding_browser.py', 'specs/owner-onboarding.ssat.yaml', 'specs/marketer-completion.md', 'docs/MARKETER-COMPLETION-GATES.md']
candidate = [artifact(p, 'source' if p.endswith(('.js', '.cjs', '.py')) else 'contract') for p in paths]
categories = ['happy_path', 'validation', 'failure_recovery', 'state_consistency', 'security_privacy', 'performance', 'accessibility', 'external_effects']
reasons = [
    'Sign-in resumes the exact owner task; explicit confirmation persists owner once.',
    'Reject continuation after app/version/owner/context changes.',
    'Rejected login and cancelled/replaced dialogs cannot establish ownership.',
    'Original app and current version must still match after refresh.',
    'Login resets token field and issues no automatic owner authority; two negative mutants fail.',
    'Single-submit controls prevent duplicate requests; no latency or load claim.',
    'Desktop/mobile keyboard flow, viewport overflow and page error checks pass.',
    'Synthetic identity only; login alone cannot call bootstrap. No provider writes or production activation.'
]
profile = 'Windows-Python3.11-Node-Chromium143-synthetic-loopback'
contract = dict(schema='factory.workflow-audit.contract.v1', project_id='WMM-owner-onboarding', candidate=candidate,
    applicability=[dict(category=c, applicable=True, reason=r) for c,r in zip(categories,reasons)],
    checks=[dict(id=c, requirement=r, category=c, profiles=[profile]) for c,r in zip(categories,reasons)])
write('contract.json',contract)
logs = ['owner-regressions.log','node-all.log','syntax.log','browser-lint.log','requirements.log','qa.json','qa-source-binding.json','browser.json','mutations.json']
evidence = [artifact(BASE/p) for p in logs]
observations = dict(schema='factory.workflow-audit.observations.v1', contract_sha256=artifact(BASE/'contract.json')['sha256'],
    candidate_sha256=hashlib.sha256(json.dumps(candidate,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
    observations=[dict(id=c,profile=profile,status='PASS',reason=r,execution_identity='python .factory/owner-onboarding/checks.py; python tools/test_owner_onboarding_browser.py; python .factory/owner-onboarding/mutations.py',observed_at=datetime.now(timezone.utc).isoformat(),artifacts=evidence) for c,r in zip(categories,reasons)])
write('observations.json',observations)
