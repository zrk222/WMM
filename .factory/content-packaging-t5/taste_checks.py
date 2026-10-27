"""Bounded R1 owner review proof through existing CF tools."""
from pathlib import Path
import ast
import hashlib
import json
import os
import shutil
import subprocess
import textwrap

R=Path.cwd();P=Path('.factory/content-packaging-t5/taste');P.mkdir(exist_ok=True)


def write(name,value):
    (P/name).write_bytes((json.dumps(value,indent=2)+'\n').encode('utf-8'))


def run(name,args,**options):
    q=subprocess.run(args,capture_output=True,**options)
    value=(q.stdout+q.stderr).decode('utf-8',errors='replace').replace(str(Path.home()),'<LOCAL_PROFILE>')
    (P/(name+'.log')).write_bytes(('\n'.join(line.rstrip() for line in value.splitlines())+'\n').encode('utf-8'))
    print(name,q.returncode,flush=True)
    assert q.returncode==0,name
    return q


run('regressions',['python','-m','unittest','tests.test_creative_taste_store','tests.test_packaging_handoff','tests.test_packaging_handoff_clients','tests.test_packaging','tests.test_packaging_clients'])
run('lint',['ruff','check','--select','F,E9','mission_control/creative_taste_store.py','mission_control/db.py','mission_control/packaging_access.py','tests/test_creative_taste_store.py'])
scope=P/'qa-scope';scope.mkdir(exist_ok=True);source=Path('mission_control/packaging_access.py');text=source.read_text(encoding='utf-8')
tree=ast.parse(text);target=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='dispatch')
extracted=scope/'packaging_access.py';extracted.write_bytes((textwrap.dedent(ast.get_source_segment(text,target))+'\n').encode('utf-8'))
write('qa-source-bindings.json',[dict(source=str(source).replace('\\','/'),sha256=hashlib.sha256(source.read_bytes()).hexdigest(),symbols=['dispatch'],extracted=extracted.as_posix(),extracted_sha256=hashlib.sha256(extracted.read_bytes()).hexdigest())])
spec=Path('specs/content-packaging-taste.ssat.yaml')
modules=[dict(name='creative_taste_store',path='mission_control/creative_taste_store.py',language='python',functions=[]),dict(name='packaging_access',path=extracted.as_posix(),language='python',functions=[dict(name='dispatch',args=[],returns='object')])]
spec.write_bytes((json.dumps(dict(name='content-packaging-taste',language='python',modules=modules),indent=2)+'\n').encode('utf-8'))
q=run('qa',['forge','qa','content-packaging-taste','--ssat',str(spec),'--strict']);qa=json.loads(q.stdout);write('qa.json',qa)
assert qa['passed'] and not qa['findings'] and qa['metrics']['max_complexity']<=10
security=P/'security-scope';shutil.copytree(P/'security-config',security,dirs_exist_ok=True)
prior=json.loads(Path('.factory/content-packaging-t5/transport/security.json').read_bytes())
for row in prior['sources']:
    target=security/row['path'];target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes(Path(row['path']).read_bytes())
new=Path('mission_control/creative_taste_store.py');(security/new).write_bytes(new.read_bytes())
cf=R.parent/'WMM-cf-sqlite'
q=run('security',['python','-m','factoryline.cli','audit','security','--root',str(security.resolve()),'--json'],cwd=cf,env=dict(os.environ,PYTHONPATH=str(cf)))
d=json.loads(q.stdout);write('security.json',d)
assert d['state']=='CLEAN' and d['audit_coverage']['complete'] and not d['findings'] and not d['database_context']['gaps']
