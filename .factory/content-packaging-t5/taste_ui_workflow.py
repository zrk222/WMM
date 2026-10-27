"""Seal actual owner UI workflows and the exact current implementation."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess
P=Path('.factory/content-packaging-taste-ui');E=P.as_posix()+'/'


def a(path,kind='log'):return dict(path=path,kind=kind,sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest())


def read(name):return json.loads((P/name).read_bytes())


def write(name,data):(P/name).write_bytes((json.dumps(data,indent=2)+'\n').encode('utf-8'))


def run(name,args):
    r=subprocess.run(args,capture_output=True)
    value=(r.stdout+r.stderr).decode('utf-8',errors='replace').replace(str(Path.home()),'<LOCAL_PROFILE>')
    (P/name).write_bytes(('\n'.join(line.rstrip()for line in value.splitlines())+'\n').encode('utf-8'))
    assert r.returncode==0,name


run('node-all.log',['node','--test',*map(str,sorted(Path('tests').glob('*.test.*')))])
run('browser-tool-lint.log',['ruff','check','--select','F,E9','tools/test_creative_taste_browser.py'])
for name in ['packaging-model','packaging-ui','app','ui-stories']:
    run(name+'-syntax.log',['node','--check','mission_control/static/'+name+'.js'])
assert '# fail 0' in (P/'node-all.log').read_text(encoding='utf-8')
qa=read('qa.json');assert qa['passed'] and not qa['findings'] and qa['metrics']['max_complexity']<=10
for row in read('qa-source-bindings.json'):
    assert a(row['source'])['sha256']==row['sha256']
    assert a(row['extracted'])['sha256']==row['extracted_sha256']
assert len(read('mutations.json'))==2 and all(row['status']=='KILLED' for row in read('mutations.json'))
for name in ['design-audit.json','critique.json','challenge.json','render-audit.json']:assert read(name)['passed']
browser=read('browser-observations.json');assert browser['status']=='PASS'
assert {row['width']for row in browser['observations']}=={1440,390}
for row in browser['observations']:
    for key in ['example_slot12','complete_voice','uncertain_write_observed_once','json_csv_pdf','keyboard','app_switch','no_overflow','no_page_errors']:assert row[key]
review='''# Owner creative-direction UI acceptance

Actual temporary SQLite owner HTTP and Chromium1440/390 exercise create, slot12
example selection, exact saved readback and revision. A route returns503 only
after the real server commits the second save. The UI retains and reconciles
the exact request without resending. Actual downloaded JSON/CSV and decoded PDFs
retain the long VOICE_END marker, example interpretation and exact revision.
Unrelated private workspace sentinel is absent from PDF. Keyboard, app-switch
cleanup and no horizontal overflow pass; no page errors. Mobile is Chromium
emulation, not native iOS. No external provider, rendering or publication occurs.

All browser logic suites pass. Closed input/source/receipt validation, escaping,
CSV formula neutralization and late response rejection are tested. Two source
mutants remove cross-app receipt or late-read admission; tests kill both. The
UMD factory bodies are unchanged by QA extraction except public export markers.
Actual snapshot design audit, strict critique, challenge and render audit pass.
Private PNG/PDF captures and synthetic downloaded reports stay outside Git.

Plain JavaScript has no transpilation or TypeScript build in this packet; syntax,
Node suites, scoped Forge and actual browser execution apply. No numerical code
coverage, latency, conversion or all-language security claim. Python runtime is
unchanged. Browser fixture uses synthetic verified identity, temporary DB and
loopback reads/writes only. This does not prove real-account provider acceptance.
Current owner/agent guidance alone does not fulfill actual editor/render handoff.
'''
(P/'review.md').write_bytes(review.encode('utf-8'))
# Git stores normalized UTF8 LF; seal those same receipt bytes.
for path in P.glob('*.json'):
    raw=path.read_text(encoding='utf-8').replace(str(Path.home()).replace('\\','/'),'<LOCAL_PROFILE>')
    raw=raw.replace(str(Path.home()).replace('\\','\\\\'),'<LOCAL_PROFILE>')
    path.write_bytes((json.dumps(json.loads(raw),indent=2)+'\n').encode('utf-8'))
files=['mission_control/static/packaging-model.js','mission_control/static/packaging-ui.js','mission_control/static/app.js','mission_control/static/ui-stories.js','tests/packaging_model.test.cjs','tests/packaging_ui.test.cjs','tools/test_creative_taste_browser.py','specs/content-packaging-taste-ui.ssat.yaml','.factory/content-packaging-t5/taste_ui_qa.py','.factory/content-packaging-t5/taste_ui_mutations.py','.factory/content-packaging-t5/taste_ui_design.py','.factory/content-packaging-t5/taste_ui_workflow.py']
candidate=[a(path,'source')for path in files]+[a(row['extracted'],'source')for row in read('qa-source-bindings.json')]+[a('.factory/content-packaging-t5/taste-ui-scope.md','contract'),a(E+'review.md','review')]
reasons=dict(happy_path='Owner browser creates and revises exact video direction then exports JSON/CSV/PDF.',validation='All12 examples, bounded exclusions and exact scope/policy/source receipts.',failure_recovery='Actual lost response after commit reconciles without a second write.',state_consistency='Late responses and app switches clear private UI; revisions retain the selected guidance.',security_privacy='Escape text, neutralize CSV, scoped owner writes and two killed admission mutants.',performance='Existing bounded history and at most12 examples; no measured latency claim.',accessibility='Actual desktop/mobile keyboard, labels, focus and no overflow; prescribed design checks.',external_effects='Synthetic local owner data and user report downloads only; no provider/render/publish.')
profile='Windows-Node-Chromium1440-390-synthetic-owner'
c=dict(schema='factory.workflow-audit.contract.v1',project_id='WMM-owner-taste-ui',candidate=candidate,applicability=[dict(category=k,applicable=True,reason=v)for k,v in reasons.items()],checks=[dict(id=k,category=k,requirement=v,profiles=[profile])for k,v in reasons.items()]);write('workflow-contract.json',c)
names=['node-all.log','browser-tool-lint.log','packaging-model-syntax.log','packaging-ui-syntax.log','app-syntax.log','ui-stories-syntax.log','qa.json','qa-source-bindings.json','mutations.json','mutation-receipt.log','mutation-late-response.log','browser-observations.json','rendered-modal.html','design-audit.json','critique.json','challenge.json','render-audit.json','review.md']
o=dict(schema='factory.workflow-audit.observations.v1',contract_sha256=a(E+'workflow-contract.json')['sha256'],candidate_sha256=hashlib.sha256(json.dumps(candidate,sort_keys=True,separators=(',',':')).encode()).hexdigest(),observations=[dict(id=k,profile=profile,status='PASS',reason=v,execution_identity=profile,observed_at=datetime.now(timezone.utc).isoformat(),artifacts=[a(E+name)for name in names])for k,v in reasons.items()]);write('workflow-observations.json',o)
r=subprocess.run(['factory','audit','workflows','--root','.','--contract',E+'workflow-contract.json','--observations',E+'workflow-observations.json','--json'],capture_output=True);d=json.loads(r.stdout);write('receipt.json',d);assert r.returncode==0 and d['state']=='PASS';print(d['state'])
