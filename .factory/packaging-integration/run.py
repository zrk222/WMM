"""Frozen source integration check of packaging and current WMM base."""
from pathlib import Path
import hashlib,json,os,subprocess,sys
R=Path.cwd();P=Path('.factory/packaging-integration');P.mkdir(exist_ok=True)
def manifest():
    files=[p for folder in ['mission_control','tests','tools'] for p in Path(folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix in ['.py','.js','.cjs','.mjs','.css','.html']]
    return {p.as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}
if len(sys.argv)==1:
    (P/'source-before.json').write_bytes(json.dumps(manifest(),indent=2).encode())
    print('Frozen source inventory recorded',flush=True)
else:
    index=sys.argv[1]
    args=['python','-X','utf8','tools/run_ci_tests.py','--shards','4','--index',index] if index!='node' else ['node','--test',*[str(p) for p in Path('tests').iterdir() if p.name.endswith(('.test.cjs','.test.mjs'))]]
    env=dict(os.environ,PYTHONUTF8='1',PYTEST_DISABLE_PLUGIN_AUTOLOAD='1')
    q=subprocess.run(args,capture_output=True,env=env)
    text=(q.stdout+q.stderr).decode('utf-8',errors='replace').replace(str(Path.home()),'<LOCAL_PROFILE>')
    (P/('shard-'+index+'.log')).write_bytes(('\n'.join(line.rstrip() for line in text.splitlines())+'\n').encode())
    before=json.loads((P/'source-before.json').read_bytes());same=before==manifest()
    (P/('shard-'+index+'.json')).write_bytes(json.dumps(dict(command=args,exit=q.returncode,source_unchanged=same),indent=2).encode())
    print(dict(shard=index,exit=q.returncode,source_unchanged=same,tail=text[-200:]),flush=True)
    raise SystemExit(q.returncode if same else 2)
