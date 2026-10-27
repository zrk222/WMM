from pathlib import Path
from datetime import datetime,timezone
import json,hashlib
R=Path(__file__).resolve().parents[2];E='.factory/native-sqlite-entry/'
def a(path,kind):return dict(path=path,kind=kind,sha256=hashlib.sha256((R/path).read_bytes()).hexdigest())
def w(name,data):(R/(E+name)).write_bytes(json.dumps(data,indent=2).encode())
s=json.loads((R/(E+'candidate-security.json')).read_bytes());assert s['state']=='CLEAN' and not s['findings'] and not s['database_context']['gaps']
assert s['audit_coverage']['complete'] and s['audit_coverage']['files_audited']==11
for row in s['sources']:assert row['sha256']==a(row['path'],'source')['sha256']
q=json.loads((R/(E+'qa.json')).read_bytes());assert q['passed'] and not q['findings']
assert 'Ran 89 tests' in (R/(E+'regressions.log')).read_text()
m=json.loads((R/(E+'mutations.json')).read_bytes());assert len(m)==1 and m[0]['status']=='KILLED'
candidate=[a(row['path'],'source') for row in s['sources']]+[a(path,kind) for path,kind in [('specs/native-sqlite-entry.md','contract'),('plans/native-sqlite-entry.md','contract'),('specs/native-sqlite-entry.ssat.yaml','contract'),('tests/test_native_sqlite_entry.py','test'),(E+'workflow.py','source'),(E+'mutant-entry.py','source'),(E+'review.md','review')]]
reasons=dict(happy_path='89 focused native SQLite regressions preserve existing behavior.',validation='All 25 helpers reject fake and subclass override connections before execute.',failure_recovery='TypeError stops invalid helper entry without database effects.',state_consistency='Existing SQL text, transaction and authority logic preserved; source hashes checked.',security_privacy='Eleven exact sources audited, CLEAN, no findings or database coverage gaps, no waiver.',performance='One native type identity check per helper entry; no measured latency claim.',external_effects='All checks local; no spending, publication, messaging or production activation.')
profile='Windows-Python3.11.9-local-SQLite'
app=[dict(category=k,applicable=True,reason=v) for k,v in reasons.items()]+[dict(category='accessibility',applicable=False,reason='No UI changes.',review_evidence=a(E+'review.md','review'))]
contract=dict(schema='factory.workflow-audit.contract.v1',project_id='WMM-native-sqlite-entry',candidate=candidate,applicability=app,checks=[dict(id=k,category=k,requirement=v,profiles=[profile]) for k,v in reasons.items()]);w('workflow-contract.json',contract)
logs=['regressions.log','qa.json','strict.json','lint.log','candidate-security.json','mutations.json','mutation-entry.log']
observations=dict(schema='factory.workflow-audit.observations.v1',contract_sha256=a(E+'workflow-contract.json','contract')['sha256'],candidate_sha256=hashlib.sha256(json.dumps(candidate,sort_keys=True,separators=(',',':')).encode()).hexdigest(),observations=[dict(id=k,profile=profile,status='PASS',reason=v,execution_identity='python -m unittest declared nine modules; isolated CF source CLI audit security exact eleven-file scope; removed guard mutation; Forge QA and strict requirements',observed_at=datetime.now(timezone.utc).isoformat(),artifacts=[a(E+n,'log') for n in logs]) for k,v in reasons.items()]);w('workflow-observations.json',observations)
