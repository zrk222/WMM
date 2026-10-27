"""Seal current backend handoff proof without implying complete product execution."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess
P=Path('.factory/content-packaging-t5/editor');E=P.as_posix()+'/'


def a(path,kind='log'):return dict(path=path,kind=kind,sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest())


def read(name):return json.loads((P/name).read_bytes())


def write(name,value):(P/name).write_bytes((json.dumps(value,indent=2)+'\n').encode('utf-8'))


s=read('security-current.json')
assert s['state']=='CLEAN'and s['audit_coverage']['complete']and not s['findings']and not s['database_context']['gaps']
for row in s['sources']:assert a(row['path'])['sha256']==row['sha256']
q=read('qa.json');assert q['passed']and not q['findings']and q['metrics']['max_complexity']<=10
assert 'Ran 35 tests' in (P/'regressions.log').read_text(encoding='utf-8')
assert 'Ran 6 tests' in (P/'final-handoff.log').read_text(encoding='utf-8')
assert len(read('mutations.json'))==3 and all(row['status']=='KILLED'for row in read('mutations.json'))
for row in read('qa-source-bindings.json'):
    assert a(row['source'])['sha256']==row['sha256']
    assert a(row['extracted'])['sha256']==row['extracted_sha256']
review='''# Packaging editor backend review

This packet creates a typed editable definition with exact current SHOTS, latest
owner taste, app, authentic original brief and app proof. Initial clips cover
every shot in order with explicitly chosen original source-frame/audio controls.
Existing Projects.save binds the same provenance in its transaction. Later
split/edit/history and existing render-admission saved_data checks revalidate it.
Research timing cannot become original footage trim; unselected media, wrong
app/manifest/taste/shot references and discarded provenance reject. Changed script
requires reviewed segment hashes and a new shot plan; old editor proof rejects.
Revoked original-media rights invalidate preparation and saved project proof.

Six focused tests use real temporary SQLite, owner HTTP guidance and synthetic
inspected uploaded bytes. These media bytes are NOT decoded-video render proof.
The broader35-test editor/render/checklist suite passes separately using its
existing native synthetic render profile. It does not prove packaging-created
media rendering. Three source mutants remove exact taste, origin and explicit
audio rules; all fail. All affected functions have exact-body scoped QA with
maximum complexity9. Native SQLite guards preserve real connection behavior.
The head upsert uses equivalent bound update values instead of excluded.column.

Complete current24-file bounded Python AST coverage has zero pattern findings
and no database coverage gaps. Initial broader25-file analysis is retained in
security.json/security.log with incomplete receiver/nested-scope evidence.
Unmodified video_edit_jobs.py has an unsupported nested callback in that broader
scanner profile. It is retained as an exact dependency, tested by regressions,
and is NOT claimed to have complete static coverage. No exception makes it pass.
This is not penetration testing, whole-product security or release authority.

No rendered UI changes, so accessibility is inapplicable here. The backend helper
is not yet in the operation catalog or UI; transport, approved autonomous handoff,
actual multi-clip picture/audio production and native/device acceptance remain
required. No provider writes, spend, publication, deployment or customer data.
No measured latency, numerical code coverage or business outcome claim.
'''
(P/'review.md').write_bytes(review.encode('utf-8'))
extra=['tests/test_packaging_editor.py','specs/content-packaging-editor.ssat.yaml','.factory/content-packaging-t5/editor_checks.py','.factory/content-packaging-t5/editor_mutations.py','.factory/content-packaging-t5/editor_workflow.py']
candidate=[a(row['path'],'source')for row in s['sources']]+[a(path,'source')for path in extra]+[a('mission_control/video_edit_jobs.py','source')]
candidate += [a(row['extracted'],'source')for row in read('qa-source-bindings.json')]
candidate += [a('specs/content-packaging-t5.md','contract'),a('.factory/content-packaging-t5/editor-scope.md','contract'),a(E+'review.md','review'),a('.factory/content-packaging-t5/taste/security-config/factory.database.json','contract'),a('.factory/content-packaging-t5/taste/security-config/.factory/tenant-read-contract.json','contract')]
reasons=dict(happy_path='Prepare exact original-media definition and save/split it through existing Projects service.',validation='Current shots, script hashes, taste and selected original media/audio reject stale or foreign inputs.',failure_recovery='Existing project revisions, request-key semantics and restart persistence remain supported.',state_consistency='Saved and edited projects retain packaging provenance; existing source proof rechecks before render.',security_privacy='Native SQLite receivers, parameterized SQL, affected24-source scan and three killed boundary mutants.',performance='At most24 clips and1440 output frames; no measured speed or savings claim.',external_effects='Synthetic local storage and existing isolated native render tests only; no public or provider effects.')
profile='Windows-Python3.11-SQLite-existing-native-editor-test-profile'
app=[dict(category=k,applicable=True,reason=v)for k,v in reasons.items()]+[dict(category='accessibility',applicable=False,reason='Backend definition/provenance packet with no rendered UI.',review_evidence=a(E+'review.md','review'))]
c=dict(schema='factory.workflow-audit.contract.v1',project_id='WMM-packaging-editor-backend',candidate=candidate,applicability=app,checks=[dict(id=k,category=k,requirement=v,profiles=[profile])for k,v in reasons.items()]);write('workflow-contract.json',c)
logs=['regressions.log','final-handoff.log','lint.log','qa.json','qa-source-bindings.json','security-current.json','security.json','security.log','mutations.json','mutation-taste.log','mutation-origin.log','mutation-audio.log','review.md']
o=dict(schema='factory.workflow-audit.observations.v1',contract_sha256=a(E+'workflow-contract.json')['sha256'],candidate_sha256=hashlib.sha256(json.dumps(candidate,sort_keys=True,separators=(',',':')).encode()).hexdigest(),observations=[dict(id=k,profile=profile,status='PASS',reason=v,execution_identity=profile,observed_at=datetime.now(timezone.utc).isoformat(),artifacts=[a(E+name)for name in logs])for k,v in reasons.items()]);write('workflow-observations.json',o)
r=subprocess.run(['factory','audit','workflows','--root','.','--contract',E+'workflow-contract.json','--observations',E+'workflow-observations.json','--json'],capture_output=True);d=json.loads(r.stdout);write('receipt.json',d);assert r.returncode==0 and d['state']=='PASS';print(d['state'])
