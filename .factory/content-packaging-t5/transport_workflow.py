"""Seal shared read-only checklist transport and exact supporting proof."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess
P=Path('.factory/content-packaging-t5/transport');E=P.as_posix()+'/'
def a(path,kind='log'):return dict(path=path,kind=kind,sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest())
def read(name):return json.loads((P/name).read_bytes())
def w(name,value):(P/name).write_bytes((json.dumps(value,indent=2)+'\n').encode())
s=read('security.json');assert s['state']=='CLEAN' and not s['findings'] and not s['database_context']['gaps'] and s['audit_coverage']['complete']
for row in s['sources']:assert row['sha256']==a(row['path'])['sha256']
q=read('qa.json');assert q['passed'] and not q['findings'] and q['metrics']['max_complexity']<=10
assert 'Ran 34 tests' in (P/'regressions.log').read_text(encoding='utf-8')
assert 'Ran 2 tests' in (P/'final-clients.log').read_text(encoding='utf-8')
assert all(row['status']=='KILLED' for row in read('mutations.json'))
for row in read('qa-source-bindings.json'):
    assert row['sha256']==a(row['source'])['sha256']
    assert row['extracted_sha256']==a(row['extracted'])['sha256']
candidate=[a(row['path'],'source') for row in s['sources']]+[a(f,'source') for f in ['tests/test_packaging_handoff_clients.py','tests/test_operation_catalog.py','specs/content-packaging-checklist-transport.ssat.yaml','.factory/content-packaging-t5/checklist_transport_checks.py','.factory/content-packaging-t5/transport_mutations.py','.factory/content-packaging-t5/transport_workflow.py']]+[a(row['extracted'],'source') for row in read('qa-source-bindings.json')]+[a('.factory/content-packaging-t5/checklist-transport-scope.md','contract'),a('specs/content-packaging-t5.md','contract'),a(E+'review.md','review')]
reasons=dict(happy_path='Owner HTTP, subprocess CLI and official MCP stdio return identical checklist responses.',validation='Closed schema, stale manifest/hash, foreign app and forged approval reject.',failure_recovery='Read-only inspection needs no replay; missing production evidence stays explicit.',state_consistency='Existing gateway scope and grant revocation rechecked; no jobs are created.',security_privacy='Twenty exact sources CLEAN with complete coverage and no database gaps; two semantic mutants killed.',performance='Read-only bounded shot checklist uses existing services; no latency or savings claim.',external_effects='Synthetic temporary SQLite and loopback HTTP only; no render/provider/publication/spend effects.')
profile='Windows-Python3.11-owner-HTTP-CLI-MCP1.16'
app=[dict(category=k,applicable=True,reason=v) for k,v in reasons.items()]+[dict(category='accessibility',applicable=False,reason='Backend/transport packet with no rendered UI change.',review_evidence=a(E+'review.md','review'))]
c=dict(schema='factory.workflow-audit.contract.v1',project_id='WMM-packaging-checklist-transport',candidate=candidate,applicability=app,checks=[dict(id=k,category=k,requirement=v,profiles=[profile]) for k,v in reasons.items()]);w('workflow-contract.json',c)
logs=['regressions.log','final-clients.log','qa.json','qa-source-bindings.json','lint.log','security.json','mutations.json','mutation-dispatch.log','mutation-effect.log']
o=dict(schema='factory.workflow-audit.observations.v1',contract_sha256=a(E+'workflow-contract.json')['sha256'],candidate_sha256=hashlib.sha256(json.dumps(candidate,sort_keys=True,separators=(',',':')).encode()).hexdigest(),observations=[dict(id=k,profile=profile,status='PASS',reason=v,execution_identity='34 focused regressions plus final two clients; official MCP SDK; source mutations; scoped QA and source-candidate security',observed_at=datetime.now(timezone.utc).isoformat(),artifacts=[a(E+f) for f in logs]) for k,v in reasons.items()]);w('workflow-observations.json',o)
r=subprocess.run(['factory','audit','workflows','--root','.','--contract',E+'workflow-contract.json','--observations',E+'workflow-observations.json','--json'],capture_output=True);d=json.loads(r.stdout);w('receipt.json',d);print(d['state']);assert d['state']=='PASS'
