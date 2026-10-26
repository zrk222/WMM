"""Hash-seal packaging owner/CLI/MCP controls and their exact proof scope."""
from pathlib import Path
from datetime import datetime,timezone
import json,hashlib
R=Path(__file__).resolve().parents[2];E='.factory/content-packaging-t3/'
def a(path,kind):return dict(path=path,kind=kind,sha256=hashlib.sha256((R/path).read_bytes()).hexdigest())
def w(name,value):(R/(E+name)).write_bytes(json.dumps(value,indent=2).encode())
s=json.loads((R/(E+'security.json')).read_bytes());assert s['state']=='CLEAN' and not s['findings'] and not s['database_context']['gaps']
assert s['audit_coverage']['complete'] and s['audit_coverage']['files_audited']==18 and s['audit_coverage']['measurement_state']=='complete'
assert not s['parse_errors'] and not s['unreadable_sources'] and not s['oversized_sources']
for row in s['sources']:assert row['sha256']==a(row['path'],'source')['sha256']
q=json.loads((R/(E+'qa.json')).read_bytes());assert q['passed'] and not q['findings'] and q['metrics']['max_complexity']<=10
assert 'Ran 85 tests' in (R/(E+'regressions.log')).read_text()
m=json.loads((R/(E+'mutations.json')).read_bytes());assert len(m)==3 and all(row['status']=='KILLED' for row in m)
b=json.loads((R/(E+'qa-source-bindings.json')).read_bytes())
for row in b['bindings']:assert row['original_sha256']==a(row['original'],'source')['sha256']
candidate=[a(row['path'],'source') for row in s['sources']]
for path,kind in [('tests/test_packaging_clients.py','test'),('tests/test_native_sqlite_entry.py','test'),('specs/content-packaging-t3.md','contract'),('specs/content-packaging-t3.ssat.yaml','contract'),('plans/content-packaging-t3.md','contract'),('plans/content-packaging.md','contract')]:candidate.append(a(path,kind))
for name in ['workflow.py','qa_scope.py','qa-scope/server.py','qa-scope/operation_catalog.py','mutant-authority.py','mutant-reconciliation.py','mutant-routing.py']:candidate.append(a(E+name,'source'))
candidate.append(a(E+'review.md','review'))
reasons=dict(happy_path='Real owner HTTP, CLI and official MCP stdio share variant/shot-list history.',validation='Foreign, stale, revoked, forged and noncanonical requests are denied.',failure_recovery='Observation-only reconciliation distinguishes matching, different and absent expected revisions without replay.',state_consistency='Exact current authority and independent review are rechecked through protected transactions.',security_privacy='Eighteen whole sources are audited CLEAN with complete coverage and no database gaps; three mutants are killed.',performance='Compact 100-row history pages avoid loading private script payloads; no latency claim.',external_effects='All tests use synthetic data and local SQLite/loopback; no provider or publishing calls.')
profile='Windows-Python3.11.9-owner-HTTP-CLI-official-MCP'
app=[dict(category=k,applicable=True,reason=v) for k,v in reasons.items()]+[dict(category='accessibility',applicable=False,reason='No rendered UI is changed by the transport packet.',review_evidence=a(E+'review.md','review'))]
c=dict(schema='factory.workflow-audit.contract.v1',project_id='WMM-content-packaging-T3',candidate=candidate,applicability=app,checks=[dict(id=k,category=k,requirement=v,profiles=[profile]) for k,v in reasons.items()]);w('workflow-contract.json',c)
logs=['regressions.log','qa.json','qa-full-modules.json','qa-source-bindings.json','security.json','strict.json','lint.log','build.log','mutations.json','mutation-authority.log','mutation-reconciliation.log','mutation-routing.log']
o=dict(schema='factory.workflow-audit.observations.v1',contract_sha256=a(E+'workflow-contract.json','contract')['sha256'],candidate_sha256=hashlib.sha256(json.dumps(candidate,sort_keys=True,separators=(',',':')).encode()).hexdigest(),observations=[dict(id=k,profile=profile,status='PASS',reason=v,execution_identity='85 unittest regressions including owner HTTP, subprocess CLI and official SDK MCP stdio; exact-source security; three source mutation children; scoped Forge QA with original-source AST bindings',observed_at=datetime.now(timezone.utc).isoformat(),artifacts=[a(E+n,'log') for n in logs]) for k,v in reasons.items()]);w('workflow-observations.json',o)
