"""Source-bound editor integration proof, with whole affected-source analysis."""
from pathlib import Path
import ast,hashlib,json,os,shutil,subprocess,textwrap
R=Path.cwd();P=Path('.factory/content-packaging-t5/editor');P.mkdir(parents=True,exist_ok=True)


def write(name,value):(P/name).write_bytes((json.dumps(value,indent=2)+'\n').encode('utf-8'))


def run(name,args,**kw):
    q=subprocess.run(args,capture_output=True,**kw)
    value=(q.stdout+q.stderr).decode('utf-8',errors='replace').replace(str(Path.home()),'<LOCAL_PROFILE>')
    (P/(name+'.log')).write_bytes(('\n'.join(x.rstrip()for x in value.splitlines())+'\n').encode('utf-8'))
    print(name,q.returncode,flush=True);assert q.returncode==0,name
    return q


run('regressions',['python','-m','unittest','tests.test_packaging_editor','tests.test_video_edit_projects','tests.test_video_edit_render','tests.test_packaging_handoff'])
run('lint',['ruff','check','--select','F,E9','mission_control/packaging_editor.py','mission_control/video_edit_contract.py','mission_control/video_edit_projects.py','tests/test_packaging_editor.py'])
modules=[dict(name='packaging_editor',path='mission_control/packaging_editor.py',language='python',functions=[])]
bindings=[]
for name,symbols in [('video_edit_contract',['definition','project_shape']),('video_edit_projects',['revision','head','app_version','replay','append','current','saved_data','write'])]:
    path=Path('mission_control')/(name+'.py');source=path.read_text(encoding='utf-8')
    nodes=[n for n in ast.walk(ast.parse(source))if isinstance(n,ast.FunctionDef)and n.name in symbols]
    target=P/'qa-scope'/(name+'.py');target.parent.mkdir(exist_ok=True)
    target.write_bytes(('\n\n'.join(textwrap.dedent(ast.get_source_segment(source,n))for n in nodes)+'\n').encode('utf-8'))
    bindings.append(dict(source=path.as_posix(),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),symbols=symbols,extracted=target.as_posix(),extracted_sha256=hashlib.sha256(target.read_bytes()).hexdigest()))
    modules.append(dict(name=name,path=target.as_posix(),language='python',functions=[dict(name=n,args=[],returns='object')for n in symbols]))
write('qa-source-bindings.json',bindings)
spec=Path('specs/content-packaging-editor.ssat.yaml');spec.write_bytes((json.dumps(dict(name='content-packaging-editor',language='python',modules=modules),indent=2)+'\n').encode('utf-8'))
q=run('qa',['forge','qa','content-packaging-editor','--ssat',str(spec),'--strict']);qa=json.loads(q.stdout);write('qa.json',qa)
assert qa['passed'] and not qa['findings'] and qa['metrics']['max_complexity']<=10
scope=P/'security-current';shutil.copytree('.factory/content-packaging-t5/taste/security-config',scope,dirs_exist_ok=True)
old=json.loads(Path('.factory/content-packaging-t5/taste-agent/security.json').read_bytes())
sources=sorted({row['path']for row in old['sources']}|{'mission_control/packaging_editor.py','mission_control/video_edit_projects.py','mission_control/video_edit_contract.py'})
for name in sources:
    target=scope/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(Path(name).read_bytes())
cf=R.parent/'WMM-cf-sqlite';q=run('security-current',['python','-m','factoryline.cli','audit','security','--root',str(scope.resolve()),'--json'],cwd=cf,env=dict(os.environ,PYTHONPATH=str(cf)))
d=json.loads(q.stdout);write('security-current.json',d)
assert d['state']=='CLEAN'and d['audit_coverage']['complete']and not d['findings']and not d['database_context']['gaps']
