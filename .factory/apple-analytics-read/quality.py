"""Bind scoped static checks to exact candidate source; never infer runtime coverage."""
from pathlib import Path
import ast
import hashlib
import json
import subprocess

P = Path('.factory/apple-analytics-read')

def write(name, value):
    (P/name).write_bytes((json.dumps(value,indent=2)+'\n').encode())

def run(name, args):
    result=subprocess.run(args,capture_output=True)
    text=(result.stdout+result.stderr).decode(errors='replace')
    (P/(name+'.log')).write_bytes(('\n'.join(text.splitlines())+'\n').encode())
    print(name,result.returncode,flush=True)
    if result.stdout.lstrip().startswith(b'{'):
        write(name+'.json',json.loads(result.stdout))
    assert result.returncode==0,name

symbols={'mission_control/providers.py':['report_destination'], 'mission_control/provider_reports.py':['report_options','read_report']}
parts=[]; binding=[]
for name,names in symbols.items():
    source=Path(name).read_text(); tree=ast.parse(source)
    parts.extend(ast.get_source_segment(source,node) for node in tree.body if isinstance(node,ast.FunctionDef) and node.name in names)
    binding.append(dict(path=name,sha256=hashlib.sha256(Path(name).read_bytes()).hexdigest(),symbols=names))
target=P/'changed_functions.py'; target.write_bytes(('\n\n'.join(parts)+'\n').encode())
write('qa-binding.json',binding)
module=Path('mission_control/apple_analytics.py')
names=[node.name for node in ast.parse(module.read_text()).body if isinstance(node,ast.FunctionDef)]
spec=dict(name='apple-analytics-read',language='python',modules=[dict(name='apple_analytics',path=module.as_posix(),language='python',functions=[dict(name=n,args=[],returns='object') for n in names]),dict(name='changed_functions',path=target.as_posix(),language='python',functions=[dict(name=n,args=[],returns='object') for names in symbols.values() for n in names])])
Path('specs/apple-analytics-read.ssat.yaml').write_bytes((json.dumps(spec,indent=2)+'\n').encode())
run('lint',['ruff','check','--select','F,E9','mission_control/apple_analytics.py','mission_control/providers.py','mission_control/provider_reports.py','tests/test_apple_analytics.py'])
run('qa',['forge','qa','apple-analytics-read','--ssat','specs/apple-analytics-read.ssat.yaml','--root','.','--strict'])
scope=P/'security-scope'; scope.mkdir(exist_ok=True)
for source in [module,*map(Path,symbols)]:
    (scope/source.name).write_bytes(source.read_bytes())
write('security-binding.json',[dict(path=str(source).replace('\\','/'),sha256=hashlib.sha256(source.read_bytes()).hexdigest(),copy=(scope/source.name).as_posix()) for source in [module,*map(Path,symbols)]])
tenant = dict(schema='factory.tenant-read-contract.v2', reads=[
    dict(path='providers.py',reads=[dict(call=name,binding='position:1:app_id') for name in ('credential','protected_credential','read_report')]),
    dict(path='provider_reports.py',reads=[dict(call=name,binding='position:1:app_id') for name in ('google_report','providers.credential')])])
(scope/'.factory').mkdir(exist_ok=True)
(scope/'.factory/tenant-read-contract.json').write_bytes((json.dumps(tenant,indent=2)+'\n').encode())
run('security',['factory','audit','security','--root',str(scope),'--json'])
