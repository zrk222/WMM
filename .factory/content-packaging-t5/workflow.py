"""Hash-bound requirements-only packet; runtime proof remains unimplemented."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess
P=Path('.factory/content-packaging-t5');E=P.as_posix()+'/'
def a(path,kind):return dict(path=path,kind=kind,sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest())
def w(name,data):(P/name).write_bytes((json.dumps(data,indent=2)+'\n').encode())
assert json.loads((P/'doctor.json').read_bytes())['ok']
assert b'"passed": true' in (P/'strict.log').read_bytes()
assert b'all 6 requirement mutation(s) were killed' in (P/'validators.log').read_bytes()
assert b'"passed": true' in (P/'challenge.log').read_bytes()
candidate=[a('specs/content-packaging-t5.md','contract'),a('plans/content-packaging-t5.md','contract'),a(E+'workflow.py','source'),a(E+'review.md','review')]
reasons=dict(happy_path='Six source-informed requirements trace to six named acceptance scenarios.',validation='Strict requirement lint and all six deletion/inversion mutants pass.',security_privacy='Contract preserves app/source/authority boundaries; no runtime implementation or credentials added.',external_effects='Requirements-only local files; no external execution or activation.')
na=dict(failure_recovery='No executable behavior changed; recovery remains an explicit future runtime requirement.',state_consistency='No runtime or datastore changes; script/source/revision acceptance is required in the specification.',performance='No runtime change or performance claim.',accessibility='No UI rendered or changed; keyboard/responsive acceptance remains required for implementation.')
profile='Windows-SpecLine-requirements-only'
app=[dict(category=k,applicable=True,reason=v) for k,v in reasons.items()]+[dict(category=k,applicable=False,reason=v,review_evidence=a(E+'review.md','review')) for k,v in na.items()]
c=dict(schema='factory.workflow-audit.contract.v1',project_id='WMM-packaging-T5-requirements',candidate=candidate,applicability=app,checks=[dict(id=k,category=k,requirement=v,profiles=[profile]) for k,v in reasons.items()]);w('workflow-contract.json',c)
artifacts=[a(E+f,'log') for f in ['doctor.json','strict.log','validators.log','challenge.log']]
o=dict(schema='factory.workflow-audit.observations.v1',contract_sha256=a(E+'workflow-contract.json','contract')['sha256'],candidate_sha256=hashlib.sha256(json.dumps(candidate,sort_keys=True,separators=(',',':')).encode()).hexdigest(),observations=[dict(id=k,profile=profile,status='PASS',reason=v,execution_identity='SpecLine strict, verify-validators and challenge; source-informed requirement review only',observed_at=datetime.now(timezone.utc).isoformat(),artifacts=artifacts) for k,v in reasons.items()]);w('workflow-observations.json',o)
q=subprocess.run(['factory','audit','workflows','--root','.','--contract',E+'workflow-contract.json','--observations',E+'workflow-observations.json','--json'],capture_output=True);d=json.loads(q.stdout);w('receipt.json',d);print(d['state']);assert d['state']=='PASS'
