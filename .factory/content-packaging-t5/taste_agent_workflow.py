"""Seal actual R1 checks and their current source hashes."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess
P=Path('.factory/content-packaging-t5/taste-agent');E=P.as_posix()+'/'


def a(path,kind='log'):
    return dict(path=path,kind=kind,sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest())


def read(name):return json.loads((P/name).read_bytes())


def write(name,value):(P/name).write_bytes((json.dumps(value,indent=2)+'\n').encode('utf-8'))


s=read('security.json')
assert s['state']=='CLEAN' and s['audit_coverage']['complete'] and not s['findings'] and not s['database_context']['gaps']
for row in s['sources']:assert row['sha256']==a(row['path'])['sha256']
q=read('qa.json');assert q['passed'] and not q['findings'] and q['metrics']['max_complexity']<=10
assert 'Ran 36 tests' in (P/'regressions.log').read_text(encoding='utf-8')
assert len(read('mutations.json'))==2 and all(row['status']=='KILLED' for row in read('mutations.json'))
review='''# Scoped agent taste reads
+
+Actual owner HTTP, subprocess CLI and official MCP SDK read the same exact saved
+guidance and compact history. Empty pages, exact revision and discovery work.
+Closed/forged fields, unsupported owner approval operation, cross-app scope and
+revoked grants reject. Changed policy returns stale guidance without authority.
+Two source mutants replace read dispatch with owner save or change its declared
+read effect; the actual client tests reject both. All36 combined tests pass.
+
+No UI changed; accessibility is inapplicable in this backend transport packet.
+History is bounded to100 identities,2000 revisions and exact scoped offset.
+No measured latency, code-coverage percentage, growth or whole-product claim.
+Twenty-one exact Python files have complete bounded static analysis with no
+pattern findings or database coverage gaps. This is not penetration testing or
+all-language security certification. Source-level grants and actual clients are
+tested separately from static coverage. Owner review stays outside agent catalog.
+UI authoring, portable guidance export and real render consumption remain needed.
+No provider writes, rendering, deployment, spending or publication occurs.
+'''
(P/'review.md').write_bytes(review.encode('utf-8'))
for row in read('qa-source-bindings.json'):
    assert row['sha256']==a(row['source'])['sha256']
    assert row['extracted_sha256']==a(row['extracted'])['sha256']
extra=['tests/test_creative_taste_clients.py','tests/test_operation_catalog.py','specs/content-packaging-taste-agent.ssat.yaml','.factory/content-packaging-t5/taste_agent_checks.py','.factory/content-packaging-t5/taste_agent_mutations.py','.factory/content-packaging-t5/taste_agent_workflow.py']
candidate=[a(row['path'],'source')for row in s['sources']]+[a(path,'source')for path in extra]
candidate += [a(row['extracted'],'source') for row in read('qa-source-bindings.json')]
candidate += [a('.factory/content-packaging-t5/taste/security-config/factory.database.json','contract'),a('.factory/content-packaging-t5/taste/security-config/.factory/tenant-read-contract.json','contract'),a('.factory/content-packaging-t5/taste-agent-scope.md','contract'),a('specs/content-packaging-t5.md','contract'),a(E+'review.md','review')]
reasons=dict(happy_path='Owner HTTP, CLI and official MCP read identical guidance and history.',validation='Closed fields and limits, exact app/policy/example identities reject stale or forged input.',failure_recovery='Uncertain writes are observed without resubmission; restart retains history.',state_consistency='Reads preserve immutable owner guidance and create no worker jobs.',security_privacy='Scoped grants, revocation, no agent approval tool, complete21-source scan and two killed mutants.',performance='Bounded examples12 exclusions20 revisions100 app history2000; no latency claim.',external_effects='Synthetic temporary SQLite and loopback only; preferences grant no execution authority.')
profile='Windows-Python3.11-SQLite-owner-loopback'
app=[dict(category=k,applicable=True,reason=v)for k,v in reasons.items()]+[dict(category='accessibility',applicable=False,reason='Backend owner HTTP packet without UI change.',review_evidence=a(E+'review.md','review'))]
c=dict(schema='factory.workflow-audit.contract.v1',project_id='WMM-agent-creative-taste-reads',candidate=candidate,applicability=app,checks=[dict(id=k,category=k,requirement=v,profiles=[profile])for k,v in reasons.items()]);write('workflow-contract.json',c)
logs=['regressions.log','lint.log','qa.json','qa-source-bindings.json','security.json','mutations.json','mutation-dispatch.log','mutation-effect.log','review.md']
o=dict(schema='factory.workflow-audit.observations.v1',contract_sha256=a(E+'workflow-contract.json')['sha256'],candidate_sha256=hashlib.sha256(json.dumps(candidate,sort_keys=True,separators=(',',':')).encode()).hexdigest(),observations=[dict(id=k,profile=profile,status='PASS',reason=v,execution_identity=profile,observed_at=datetime.now(timezone.utc).isoformat(),artifacts=[a(E+name)for name in logs])for k,v in reasons.items()]);write('workflow-observations.json',o)
r=subprocess.run(['factory','audit','workflows','--root','.','--contract',E+'workflow-contract.json','--observations',E+'workflow-observations.json','--json'],capture_output=True)
d=json.loads(r.stdout);write('receipt.json',d);assert r.returncode==0 and d['state']=='PASS';print(d['state'])
