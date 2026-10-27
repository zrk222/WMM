"""Recheck and seal the production checklist UI packet without external effects."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import subprocess

ROOT = Path.cwd()
P = Path('.factory/content-packaging-checklist-ui')
PREFIX = P.as_posix() + '/'


def artifact(path, kind='log'):
    return dict(path=path, kind=kind, sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest())


def write(name, value):
    (P / name).write_bytes((json.dumps(value, indent=2) + '\n').encode('utf-8'))


def load(name):
    return json.loads((P / name).read_bytes())


def run(name, argv):
    result = subprocess.run(argv, capture_output=True)
    text = (result.stdout + result.stderr).decode('utf-8', errors='replace')
    text = text.replace(str(Path.home()), '<LOCAL_PROFILE>')
    (P / name).write_bytes(('\n'.join(line.rstrip() for line in text.splitlines()) + '\n').encode('utf-8'))
    assert result.returncode == 0, name


run('node-all.log', ['node', '--test', *map(str, sorted(Path('tests').glob('*.test.cjs')))])
assert '# fail 0' in (P / 'node-all.log').read_text(encoding='utf-8')
run('syntax.log', ['node', '--check', 'mission_control/static/packaging-model.js'])
for name in ['packaging-ui', 'ui-stories']:
    run(name + '-syntax.log', ['node', '--check', 'mission_control/static/' + name + '.js'])
qa = load('qa.json')
assert qa['passed'] and not qa['findings'] and qa['metrics']['max_complexity'] <= 10
for row in load('qa-source-bindings.json'):
    assert artifact(row['source'])['sha256'] == row['sha256']
    assert artifact(row['extracted'])['sha256'] == row['extracted_sha256']
assert all(row['status'] == 'KILLED' for row in load('mutations.json'))
for name in ['design-audit.json', 'critique.json', 'challenge.json', 'render-audit.json']:
    assert load(name)['passed'], name
browser = load('browser-observations.json')
assert browser['desktop']['bodyFits'] and all(browser['mobile'][key] for key in ['bodyFits', 'dialogFits', 'actions', 'focused'])
assert browser['exports']['printInvoked'] and browser['exports']['noSession']
assert browser['exports']['csvMissing'] and browser['exports']['csvUnknown']
review = '''# Scoped checklist UI acceptance

Actual Windows Chromium owner workflow used an isolated synthetic app and temporary
SQLite. Desktop 1440 and mobile 390 viewport checks, keyboard visible focus,
JSON/CSV Blob downloads and the real shared PDF print view were inspected.
OS PDF file save and native iOS acceptance remain NOT_RUN. No provider, render,
publication or production activation occurred. See browser-observations.json.

The UI checks exact app/manifest/shot reference, rejects foreign or late receipts,
escapes displayed text and neutralizes CSV formula prefixes. Receipt and late
response mutations are killed. This does not recompute the server checklist hash
or certify all JavaScript security. Backend 20-source Python complete coverage
is a separate unchanged-source proof, not JavaScript analyzer coverage.

Build/type applicability: plain browser JavaScript has no compile/transpile or
TypeScript profile. Node syntax, Forge exported-factory-body QA, all Node tests,
design audits and actual browser execution apply. Numerical test coverage was
not measured; no 80/99 percent code coverage or product readiness claim.

Existing modal/report/CSS lifecycle is reused. Bounded receipt rows (at most100)
are checked; no latency or conversion improvement is measured. The generated
render snapshot contains only synthetic local DOM, not customer media/research.
Screen captures remain private and are excluded from Git under AGENTS.md.
Saved research/checklist status never grants reuse, execution or publication.
Full T5 editable production handoff and original/additive goal remain incomplete.
'''
(P / 'review.md').write_bytes(review.encode('utf-8'))
# Normalize textual receipts before hashes; redact the local profile path only.
for file in P.glob('*.json'):
    value = file.read_text(encoding='utf-8').replace(str(Path.home()).replace('\\', '/'), '<LOCAL_PROFILE>')
    value = value.replace(str(Path.home()).replace('\\', '\\\\'), '<LOCAL_PROFILE>')
    file.write_bytes((json.dumps(json.loads(value), indent=2) + '\n').encode('utf-8'))
sources = ['mission_control/static/packaging-model.js', 'mission_control/static/packaging-ui.js', 'mission_control/static/ui-stories.js', 'tests/packaging_model.test.cjs', 'tests/packaging_ui.test.cjs', 'specs/content-packaging-checklist-ui.ssat.yaml', '.factory/content-packaging-t5/checklist_ui_qa.py', '.factory/content-packaging-t5/checklist_ui_mutations.py', '.factory/content-packaging-t5/checklist_ui_proof.py', '.factory/content-packaging-t5/checklist_browser.py']
candidate = [artifact(path, 'source') for path in sources]
candidate += [artifact(row['extracted'], 'source') for row in load('qa-source-bindings.json')]
candidate += [artifact('.factory/content-packaging-t5/checklist-ui-scope.md', 'contract'), artifact(PREFIX + 'review.md', 'review')]
reasons = dict(happy_path='Inspect exact saved SHOTS and export JSON, CSV and PDF print view.', validation='Reject foreign app/manifest/shot receipts; escape markup and CSV formulas.', failure_recovery='Late replies cannot reopen closed or changed contexts; errors retain existing lifecycle.', state_consistency='Read-only current evidence inspection grants no production authority.', security_privacy='Exact receipt identity, safe output and private synthetic browser fixtures; no whole-product security claim.', performance='At most100 receipt rows; no latency, savings or conversion claim.', accessibility='Desktop/mobile emulation, visible keyboard focus and existing live status modal controls.', external_effects='Local read-only inspection and user-initiated report downloads/print view only.')
profile = 'Windows-Node-Chromium-desktop1440-mobile390-synthetic-loopback'
contract = dict(schema='factory.workflow-audit.contract.v1', project_id='WMM-production-checklist-ui', candidate=candidate, applicability=[dict(category=key, applicable=True, reason=value) for key, value in reasons.items()], checks=[dict(id=key, category=key, requirement=value, profiles=[profile]) for key, value in reasons.items()])
write('workflow-contract.json', contract)
names = ['node-all.log', 'syntax.log', 'packaging-ui-syntax.log', 'ui-stories-syntax.log', 'qa.json', 'qa-source-bindings.json', 'mutations.json', 'mutation-receipt.log', 'mutation-late-response.log', 'browser-observations.json', 'rendered-modal.html', 'design-audit.json', 'critique.json', 'challenge.json', 'render-audit.json', 'review.md']
observations = dict(schema='factory.workflow-audit.observations.v1', contract_sha256=artifact(PREFIX + 'workflow-contract.json')['sha256'], candidate_sha256=hashlib.sha256(json.dumps(candidate, sort_keys=True, separators=(',', ':')).encode()).hexdigest(), observations=[dict(id=key, profile=profile, status='PASS', reason=value, execution_identity=profile, observed_at=datetime.now(timezone.utc).isoformat(), artifacts=[artifact(PREFIX + name) for name in names]) for key, value in reasons.items()])
write('workflow-observations.json', observations)
result = subprocess.run(['factory', 'audit', 'workflows', '--root', '.', '--contract', PREFIX + 'workflow-contract.json', '--observations', PREFIX + 'workflow-observations.json', '--json'], capture_output=True)
receipt = json.loads(result.stdout)
write('receipt.json', receipt)
assert result.returncode == 0 and receipt['state'] == 'PASS'
print(json.dumps(dict(state=receipt['state'], checks=receipt['checks'], candidate=len(candidate))))
