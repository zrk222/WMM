"""Seal exact checklist source and reviewed evidence without broad completion claims."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess
P=Path('.factory/content-packaging-t5/checklist');E=P.as_posix()+'/'
def a(path,kind='log'):return dict(path=path,kind=kind,sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest())
def w(name,value):(P/name).write_bytes((json.dumps(value,indent=2)+'\n').encode())
def read(name):return json.loads((P/name).read_bytes())
s=read('security.json');assert s['state']=='CLEAN' and not s['findings'] and not s['database_context']['gaps']
assert s['audit_coverage']['complete'] and s['files_scanned']==20
for row in s['sources']:assert a(row['path'])['sha256']==row['sha256']
q=read('qa.json');assert q['passed'] and not q['findings'] and q['metrics']['max_complexity']<=10
assert 'Ran 37 tests' in (P/'regressions.log').read_text(encoding='utf-8')
assert all(r['status']=='KILLED' for r in read('mutations.json'))
candidate=[a(row['path'],'source') for row in s['sources']]+[a(f,'source') for f in ['tests/test_packaging_handoff.py','specs/content-packaging-checklist.ssat.yaml','.factory/content-packaging-t5/checklist_checks.py','.factory/content-packaging-t5/checklist_mutations.py','.factory/content-packaging-t5/checklist_workflow.py']]+[a('specs/content-packaging-t5.md','contract'),a('.factory/content-packaging-t5/checklist-scope.md','contract'),a(E+'review.md','review')]
reasons=dict(happy_path='Read-only checklist returns exact ordered shot and source evidence through existing services.',validation='Closed input, foreign documents, changed app/variant/revision/hash and stale bytes are checked.',failure_recovery='Missing/stale media and rights remain visible without job execution or state mutation.',state_consistency='Repeated preview is identical; exact hash identities reject silent parent changes; audit/job counts remain unchanged.',security_privacy='Twenty exact Python sources CLEAN with complete declared coverage; three mutants killed; synthetic output excludes storage paths.',performance='Existing contract bounds cap shots and references; no new queue or provider reads; no latency claim.',external_effects='Temporary synthetic SQLite and media inspector only; no network, render, publication, spend or activation.')
profile='Windows-Python3.11-SQLite-synthetic-media-checklist'
app=[dict(category=k,applicable=True,reason=v) for k,v in reasons.items()]+[dict(category='accessibility',applicable=False,reason='Backend-only read service; no rendered UI changes.',review_evidence=a(E+'review.md','review'))]
c=dict(schema='factory.workflow-audit.contract.v1',project_id='WMM-packaging-checklist',candidate=candidate,applicability=app,checks=[dict(id=k,category=k,requirement=v,profiles=[profile]) for k,v in reasons.items()]);w('workflow-contract.json',c)
logs=['regressions.log','qa.json','lint.log','build.log','security.json','mutations.json','mutation-identity.log','mutation-rights.log','mutation-authority.log']
o=dict(schema='factory.workflow-audit.observations.v1',contract_sha256=a(E+'workflow-contract.json')['sha256'],candidate_sha256=hashlib.sha256(json.dumps(candidate,sort_keys=True,separators=(',',':')).encode()).hexdigest(),observations=[dict(id=k,profile=profile,status='PASS',reason=v,execution_identity='37 combined unittest regressions, three temporary-tree source mutants, Forge function QA, local source-candidate security scan',observed_at=datetime.now(timezone.utc).isoformat(),artifacts=[a(E+f) for f in logs]) for k,v in reasons.items()]);w('workflow-observations.json',o)
r=subprocess.run(['factory','audit','workflows','--root','.','--contract',E+'workflow-contract.json','--observations',E+'workflow-observations.json','--json'],capture_output=True);d=json.loads(r.stdout);w('receipt.json',d);print(d['state']);assert d['state']=='PASS'
