"""Reproduce scoped read-only checklist checks with exact source evidence."""
from pathlib import Path
import ast,json,os,shutil,subprocess
R=Path.cwd();P=Path('.factory/content-packaging-t5/checklist');P.mkdir(exist_ok=True)
def run(name,args,**options):
    q=subprocess.run(args,capture_output=True,**options)
    output=(q.stdout+q.stderr).decode('utf-8',errors='replace')
    for prefix in [str(Path.home()),Path.home().as_posix()]:output=output.replace(prefix,'<LOCAL_PROFILE>')
    (P/(name+'.log')).write_bytes(('\n'.join(s.rstrip() for s in output.splitlines())+'\n').encode())
    print(name,q.returncode,flush=True);assert q.returncode==0
    return q
source='mission_control/packaging_handoff.py';tree=ast.parse(Path(source).read_text(encoding='utf-8'))
modules=[dict(name='packaging_handoff',path=source,language='python',functions=[dict(name=n.name,args=[a.arg for a in n.args.args],returns='object') for n in tree.body if isinstance(n,ast.FunctionDef)])]
Path('specs/content-packaging-checklist.ssat.yaml').write_bytes(json.dumps(dict(name='content-packaging-checklist',language='python',modules=modules),indent=2).encode())
run('regressions',['python','-m','unittest','tests.test_packaging_handoff','tests.test_packaging','tests.test_managed_media_store'])
q=run('qa',['forge','qa','content-packaging-checklist','--ssat','specs/content-packaging-checklist.ssat.yaml','--strict']);(P/'qa.json').write_bytes(q.stdout)
run('lint',['ruff','check','--select','F,E9',source,'tests/test_packaging_handoff.py'])
run('build',['python','-m','py_compile',source,'tests/test_packaging_handoff.py'])
security=P/'security-scope';shutil.copytree('.factory/packaging-integration/security-scope',security,dirs_exist_ok=True)
(security/source).write_bytes(Path(source).read_bytes())
env=dict(os.environ,PYTHONPATH=str(R.parent/'WMM-cf-sqlite'))
q=run('security',['python','-m','factoryline.cli','audit','security','--root',str(security.resolve()),'--json'],cwd=R.parent/'WMM-cf-sqlite',env=env)
d=json.loads(q.stdout);(P/'security.json').write_bytes((json.dumps(d,indent=2)+'\n').encode())
assert d['state']=='CLEAN' and d['audit_coverage']['complete'] and not d['database_context']['gaps'] and not d['findings']
print('security sources',d['files_scanned'],flush=True)
