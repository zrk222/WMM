"""Seal actual R1 checks and their current source hashes."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess
P=Path('.factory/content-packaging-t5/taste');E=P.as_posix()+'/'


def a(path,kind='log'):
    return dict(path=path,kind=kind,sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest())


def read(name):return json.loads((P/name).read_bytes())


def write(name,value):(P/name).write_bytes((json.dumps(value,indent=2)+'\n').encode('utf-8'))


s=read('security.json')
assert s['state']=='CLEAN' and s['audit_coverage']['complete'] and not s['findings'] and not s['database_context']['gaps']
for row in s['sources']:assert row['sha256']==a(row['path'])['sha256']
q=read('qa.json');assert q['passed'] and not q['findings'] and q['metrics']['max_complexity']<=10
assert 'Ran 40 tests' in (P/'regressions.log').read_text(encoding='utf-8')
assert 'Ran 7 tests' in (P/'final-owner.log').read_text(encoding='utf-8')
assert len(read('mutations.json'))==4 and all(row['status']=='KILLED' for row in read('mutations.json'))
review='''# Owner-reviewed creative guidance acceptance

Actual loopback HTTP uses synthetic verified owner identities and temporary
SQLite. Seven focused tests cover owner save/read, immutable revisions, restart,
lost-response observation, exact policy/app/example hashes, duplicate and bounded
fields, foreign/absent authority, role staleness and commit-time rollback. The
additive initialization test preserves existing app, role and audit rows.
Four source mutations remove owner checks, app freshness, optimistic revision
and immutable-update enforcement; all fail the real tests in disposable copies.

All40 combined tests pass. Exact new module plus changed dispatch function QA
passes with complexity7. Twenty-one declared Python files have complete bounded
AST analysis, zero pattern findings and no SQLite coverage gaps. This is not
penetration testing, all-language security or whole-product certification.

No rendered UI changes in this packet, so accessibility is inapplicable here.
Owner HTTP only approves guidance. CLI/MCP read/proposal integration, UI authoring,
portable guidance export and actual editor/render consumption remain required.
No numerical test coverage, latency, growth or savings claim. No provider writes,
deployment, spending or publication. Text examples remain untrusted preferences.
'''
(P/'review.md').write_bytes(review.encode('utf-8'))
for row in read('qa-source-bindings.json'):
    assert row['sha256']==a(row['source'])['sha256']
    assert row['extracted_sha256']==a(row['extracted'])['sha256']
extra=['tests/test_creative_taste_store.py','specs/content-packaging-taste.ssat.yaml','.factory/content-packaging-t5/taste_checks.py','.factory/content-packaging-t5/taste_mutations.py','.factory/content-packaging-t5/taste_workflow.py']
candidate=[a(row['path'],'source')for row in s['sources']]+[a(path,'source')for path in extra]
candidate += [a(row['extracted'],'source') for row in read('qa-source-bindings.json')]
candidate += [a(E+'security-config/factory.database.json','contract'),a(E+'security-config/.factory/tenant-read-contract.json','contract'),a('.factory/content-packaging-t5/taste-scope.md','contract'),a('specs/content-packaging-t5.md','contract'),a(E+'review.md','review')]
reasons=dict(happy_path='Protected owner HTTP saves and reads immutable taste revisions.',validation='Closed fields and limits, exact app/policy/example identities reject stale or forged input.',failure_recovery='Uncertain writes are observed without resubmission; restart retains history.',state_consistency='Optimistic revisions and additive migration preserve existing records; SQL history is immutable.',security_privacy='Actual owner identity, commit authority recheck, complete21-source scan and four killed mutants.',performance='Bounded examples12 exclusions20 revisions100 app history2000; no latency claim.',external_effects='Synthetic temporary SQLite and loopback only; preferences grant no execution authority.')
profile='Windows-Python3.11-SQLite-owner-loopback'
app=[dict(category=k,applicable=True,reason=v)for k,v in reasons.items()]+[dict(category='accessibility',applicable=False,reason='Backend owner HTTP packet without UI change.',review_evidence=a(E+'review.md','review'))]
c=dict(schema='factory.workflow-audit.contract.v1',project_id='WMM-owner-creative-taste',candidate=candidate,applicability=app,checks=[dict(id=k,category=k,requirement=v,profiles=[profile])for k,v in reasons.items()]);write('workflow-contract.json',c)
logs=['regressions.log','final-owner.log','lint.log','qa.json','qa-source-bindings.json','security.json','mutations.json','mutation-owner.log','mutation-app.log','mutation-revision.log','mutation-immutable.log','review.md']
o=dict(schema='factory.workflow-audit.observations.v1',contract_sha256=a(E+'workflow-contract.json')['sha256'],candidate_sha256=hashlib.sha256(json.dumps(candidate,sort_keys=True,separators=(',',':')).encode()).hexdigest(),observations=[dict(id=k,profile=profile,status='PASS',reason=v,execution_identity=profile,observed_at=datetime.now(timezone.utc).isoformat(),artifacts=[a(E+name)for name in logs])for k,v in reasons.items()]);write('workflow-observations.json',o)
r=subprocess.run(['factory','audit','workflows','--root','.','--contract',E+'workflow-contract.json','--observations',E+'workflow-observations.json','--json'],capture_output=True)
d=json.loads(r.stdout);write('receipt.json',d);assert r.returncode==0 and d['state']=='PASS';print(d['state'])
