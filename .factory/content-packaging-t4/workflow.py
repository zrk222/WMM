"""Seal scoped packaging UI evidence, preserving explicit native/provider limits."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess
R=Path.cwd();P=Path('.factory/content-packaging-t4');E=P.as_posix()+'/'
def artifact(path,kind='log'):
    return dict(path=path,kind=kind,sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest())
def read(name):return json.loads((P/name).read_bytes())
def write(name,value):(P/name).write_bytes(json.dumps(value,indent=2).encode())
s=read('security.json')
assert s['state']=='CLEAN' and not s['findings'] and not s['database_context']['gaps']
assert s['audit_coverage']['complete'] and s['audit_coverage']['files_audited']==18
for row in s['sources']:assert row['sha256']==artifact(row['path'])['sha256']
q=read('qa.json');assert q['passed'] and not q['findings'] and 0<q['metrics']['max_complexity']<=10
for row in read('qa-source-bindings.json'):
    assert row['sha256']==artifact(row['source'])['sha256']
    assert row['extracted_sha256']==artifact(row['extracted'])['sha256']
assert all(r['status']=='KILLED' for r in read('mutations.json'))
assert 'Ran 49 tests' in (P/'regressions.log').read_text(encoding='utf-8')
assert '# fail 0' in (P/'node-all.log').read_text(encoding='utf-8')
for f in ['design-audit.json','critique.json','render-audit.json','challenge.json']:assert read(f)['passed']
assert 'PASS:' in (P/'privacy.log').read_text(encoding='utf-8')
files=['mission_control/packaging_contract.py','mission_control/server.py','mission_control/static/app.js','mission_control/static/index.html','mission_control/static/ui-stories.js','mission_control/static/packaging-model.js','mission_control/static/packaging-ui.js','mission_control/static/packaging.css','tests/packaging_model.test.cjs','tests/packaging_ui.test.cjs','tests/test_packaging_ui_http.py','specs/content-packaging-t4.md','specs/content-packaging-t4.ssat.yaml','plans/content-packaging-t4.md','plans/content-packaging.md']
candidate=[artifact(f,'source') for f in files]+[artifact(E+f,'source') for f in ['qa_scope.py','mutations.py','workflow.py','browser_server.py']]+[artifact(E+'review.md','review')]
candidate.extend(artifact(row['extracted'],'source') for row in read('qa-source-bindings.json'))
reasons=dict(happy_path='Owner saves variant/shot revisions and compares original creative using local evidence; backend HTTP/CLI/MCP regressions pass.',validation='Exact receipts, revisions, owner role, canonical hashes, timestamps, local image paths and formula-safe exports are checked.',failure_recovery='Uncertain saves freeze input; explicit reconciliation precedes one identical retry; no automatic replay.',state_consistency='Closing or changing app/principal aborts pending work and clears private dialog; duplicate saves blocked.',security_privacy='Eighteen Python sources CLEAN with complete declared coverage; JavaScript correctness inventory, three semantic mutants and local-only browser flows pass.',performance='History reads bounded compact pages; comparison limited to two or three reference cards. No latency or savings claim.',accessibility='390px and 1600px Chromium checks show no document overflow, visible keyboard focus, labelled fields and at least 44px mobile actions; native iOS remains NOT_RUN.',external_effects='Synthetic isolated loopback tests only; no provider writes, publication, spending or activation.')
profile='Windows-Python3.11-Node-Chromium-synthetic-owner-loopback'
c=dict(schema='factory.workflow-audit.contract.v1',project_id='WMM-content-packaging-T4',candidate=candidate,applicability=[dict(category=k,applicable=True,reason=v) for k,v in reasons.items()],checks=[dict(id=k,category=k,requirement=v,profiles=[profile]) for k,v in reasons.items()]);write('workflow-contract.json',c)
logs=['regressions.log','node-all.log','qa.json','qa-source-bindings.json','security.json','strict.log','lint-relevant.log','privacy.log','mutations.json','mutation-authority.log','mutation-scope.log','mutation-canonical-hash.log','design-audit.json','critique.json','challenge.json','render-audit.json','rendered-modal.html','browser-observations.json']
o=dict(schema='factory.workflow-audit.observations.v1',contract_sha256=artifact(E+'workflow-contract.json')['sha256'],candidate_sha256=hashlib.sha256(json.dumps(candidate,sort_keys=True,separators=(',',':')).encode()).hexdigest(),observations=[dict(id=k,profile=profile,status='PASS',reason=v,execution_identity='49 Python regressions; full Node CJS suite; scoped source-candidate security; semantic mutants; Chrome DevTools isolated fixture; Prestige static/render audits',observed_at=datetime.now(timezone.utc).isoformat(),artifacts=[artifact(E+f) for f in logs]) for k,v in reasons.items()]);write('workflow-observations.json',o)
