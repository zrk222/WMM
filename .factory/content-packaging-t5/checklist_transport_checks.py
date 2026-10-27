"""Exact scoped transport proof; no external effects."""
from pathlib import Path
import ast,hashlib,json,os,shutil,subprocess,textwrap
R=Path.cwd();P=Path('.factory/content-packaging-t5/transport');P.mkdir(exist_ok=True)
def run(name,args,**options):
    q=subprocess.run(args,capture_output=True,**options)
    s=(q.stdout+q.stderr).decode('utf-8',errors='replace').replace(str(Path.home()),'<LOCAL_PROFILE>')
    (P/(name+'.log')).write_bytes(('\n'.join(x.rstrip() for x in s.splitlines())+'\n').encode());print(name,q.returncode,flush=True)
    assert not q.returncode
    return q
run('regressions',['python','-m','unittest','tests.test_packaging_handoff_clients','tests.test_packaging_handoff','tests.test_packaging_clients','tests.test_operation_catalog','tests.test_complete_automation'])
scope=P/'qa-scope';scope.mkdir(exist_ok=True);modules=[];bindings=[]
for file,names in [('packaging_access',{'dispatch'}),('packaging_contract',{'agent_contract'})]:
    path=Path('mission_control')/(file+'.py');s=path.read_text(encoding='utf-8');tree=ast.parse(s)
    segments=[textwrap.dedent(ast.get_source_segment(s,n)) for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names]
    prior=ast.parse(subprocess.check_output(['git','show','HEAD:'+path.as_posix()]).decode('utf-8'))
    old={n.name:ast.dump(n,include_attributes=False) for n in prior.body if isinstance(n,ast.FunctionDef)}
    for n in tree.body:
        if isinstance(n,ast.FunctionDef) and n.name not in names:assert ast.dump(n,include_attributes=False)==old[n.name]
    target=scope/(file+'.py');target.write_bytes(('\n\n'.join(segments)+'\n').encode())
    bindings.append(dict(source=path.as_posix(),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),symbols=sorted(names),unchanged_other_functions=True,extracted=target.as_posix(),extracted_sha256=hashlib.sha256(target.read_bytes()).hexdigest()))
    modules.append(dict(name=file,path=target.as_posix(),language='python',functions=[dict(name=name,args=[],returns='object') for name in names]))
modules.append(dict(name='packaging_handoff',path='mission_control/packaging_handoff.py',language='python',functions=[]))
(P/'qa-source-bindings.json').write_bytes(json.dumps(bindings,indent=2).encode())
ssat=Path('specs/content-packaging-checklist-transport.ssat.yaml');ssat.write_bytes(json.dumps(dict(name='content-packaging-checklist-transport',language='python',modules=modules),indent=2).encode())
q=run('qa',['forge','qa','content-packaging-checklist-transport','--ssat',str(ssat),'--strict']);(P/'qa.json').write_bytes((json.dumps(json.loads(q.stdout),indent=2)+'\n').encode())
run('lint',['ruff','check','--select','F,E9','mission_control/packaging_access.py','mission_control/packaging_contract.py','mission_control/operation_catalog.py','mission_control/automation_requirements.py','tests/test_packaging_handoff_clients.py','tests/test_operation_catalog.py'])
security=P/'security-scope';shutil.copytree('.factory/content-packaging-t5/checklist/security-scope',security,dirs_exist_ok=True)
previous=json.loads(Path('.factory/content-packaging-t5/checklist/security.json').read_bytes())
for row in previous['sources']:(security/row['path']).write_bytes(Path(row['path']).read_bytes())
env=dict(os.environ,PYTHONPATH=str(R.parent/'WMM-cf-sqlite'))
q=run('security',['python','-m','factoryline.cli','audit','security','--root',str(security.resolve()),'--json'],cwd=R.parent/'WMM-cf-sqlite',env=env)
d=json.loads(q.stdout);(P/'security.json').write_bytes((json.dumps(d,indent=2)+'\n').encode())
assert d['state']=='CLEAN' and d['audit_coverage']['complete'] and not d['database_context']['gaps'] and not d['findings']
