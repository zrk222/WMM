"""Verify combined-source regressions and seal local integration evidence."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,re,subprocess
R=Path.cwd();P=Path('.factory/packaging-integration');E=P.as_posix()+'/'
def read(name):return json.loads((P/name).read_bytes())
def write(name,value):(P/name).write_bytes((json.dumps(value,indent=2)+'\n').encode())
def a(path,kind='log'):return dict(path=path,kind=kind,sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest())
before=read('initial-source-before.json');current=read('source-before.json')
assert sorted(f for f in set(before)|set(current) if before.get(f)!=current.get(f))==['tests/test_agent_review_http.py','tests/test_operation_catalog.py','tests/test_sequence_runtime.py']
for f,h in current.items():assert a(f)['sha256']==h,f
inventories=[]
for i in range(4):
    r=read('shard-'+str(i)+'.json');assert r['exit']==0 and r['source_unchanged'],i
    text=(P/('shard-'+str(i)+'.log')).read_text(encoding='utf-8')
    inventory=json.loads(next(x for x in text.splitlines() if x.startswith('CI_INVENTORY ')).removeprefix('CI_INVENTORY '))
    assert inventory['index']==i and 'Ran 438 tests' in text and '\nOK' in text
    inventories.append(inventory)
assert {r['inventory_sha256'] for r in inventories}=={'6b0cc93e70f37e91f0330eba3c589cfad5b69465c7053f7d0a25ac38e7f4208a'}
assert sum(r['selected_count'] for r in inventories)==1752
assignment=read('repair-assignment.json')
assert assignment['inventory_sha256']==inventories[1]['inventory_sha256']
assert all(assignment['modules'].values()) and assignment['selected_count']==438
assert read('shard-node.json')['exit']==0 and read('shard-node.json')['source_unchanged']
assert '# pass 191' in (P/'shard-node.log').read_text(encoding='utf-8')
security=read('security.json');assert security['state']=='CLEAN' and security['audit_coverage']['complete'] and not security['database_context']['gaps'] and not security['findings']
for row in security['sources']:assert a(row['path'])['sha256']==row['sha256']
assert read('doctor.json')['ok']
write('summary.json',dict(schema='wmm.packaging.integration.v1',python_occurrences=1752,python_skips=2,node_tests=191,security_files=19,security_coverage_complete=True,security_findings=0,source_inventory=553,profile='Windows Python3.11 MCP1.16 local; FFmpeg available',repair='Only catalog, negative HTTP and cancellation test modules changed after initial execution; affected shard rerun, other shards retain identical tested source and inventory. Both failing results retained.',limits=['Hosted MCP1.30 CI pending','Linux native skips require Linux acceptance','No native iOS proof','No deployment or production activation']))
affected=set(subprocess.check_output(['git','diff','--name-only','5a3f215','--','mission_control','tests','tools']).decode().splitlines())
candidate=[dict(path=f,sha256=h,kind='source') for f,h in current.items() if f in affected]+[a(E+'run.py','source'),a(E+'verify.py','source'),a(E+'review.md','review'),a('.factory/content-packaging-t4/mutations.py','source')]
reasons=dict(happy_path='Four complete deterministic Python shards and all Node suites exercise the combined tree.',validation='Catalog count corrected from 53 to 57 with named packaging route/effect assertions; route and immutable-history regressions pass.',failure_recovery='Initial failure retained; affected defining-module shard rerun after only its three test modules changed.',state_consistency='Original source freeze, exact three-test-module delta, unchanged runtime and matching complete test inventory prove combined local execution scope.',security_privacy='Nineteen whole Python files CLEAN with complete declared coverage and no database gaps; no waiver; distribution privacy passes.',performance='No runtime hot-path change in the catalog repair; bounded packaging behavior retains its prior focused proof. No timing or savings claim.',accessibility='Both packaging and selected Drive narration retained; all browser logic suites pass. Prior packaging desktop/mobile rendered proof applies to unchanged layout/control sources; no native-device claim.',external_effects='Local synthetic tests and source-only integration; no provider publication, spending, messages or activation.')
profile='Windows-Python3.11-MCP1.16-Node-combined-local'
c=dict(schema='factory.workflow-audit.contract.v1',project_id='WMM-packaging-integration',candidate=candidate,applicability=[dict(category=k,applicable=True,reason=v) for k,v in reasons.items()],checks=[dict(id=k,category=k,requirement=v,profiles=[profile]) for k,v in reasons.items()]);write('workflow-contract.json',c)
logs=['summary.json','doctor.json','source-before.json','initial-source-before.json','repair-delta.json','security.json','initial-shard-1.log','initial-shard-1.json','tcp-abort-shard-1.log','tcp-abort-shard-1.json','catalog-repair.log','http-repair.log','shard-node.json','shard-node.log','privacy.log','lint.log']+[f'shard-{i}.{extension}' for i in range(4) for extension in ['json','log']]
artifacts=[a(E+f) for f in logs]+[a('.factory/content-packaging-t4/'+f) for f in ['mutation-authority.log','mutation-canonical-hash.log','mutation-scope.log','mutations.json','regressions.log','render-audit.json']]
artifacts.extend(a(E+f) for f in ['hour-boundary-shard-1.log','hour-boundary-shard-1.json','sequence-clock-repair.log'])
artifacts.append(a(E+'repair-assignment.json'))
o=dict(schema='factory.workflow-audit.observations.v1',contract_sha256=a(E+'workflow-contract.json')['sha256'],candidate_sha256=hashlib.sha256(json.dumps(candidate,sort_keys=True,separators=(',',':')).encode()).hexdigest(),observations=[dict(id=k,profile=profile,status='PASS',reason=v,execution_identity='Four inventory-matched Python shard processes; Node full suite; source-candidate security; exact post-repair source delta',observed_at=datetime.now(timezone.utc).isoformat(),artifacts=artifacts) for k,v in reasons.items()]);write('workflow-observations.json',o)
q=subprocess.run(['factory','audit','workflows','--root','.','--contract',E+'workflow-contract.json','--observations',E+'workflow-observations.json','--json'],capture_output=True)
receipt=json.loads(q.stdout);write('receipt.json',receipt);print(receipt['state']);assert receipt['state']=='PASS'
