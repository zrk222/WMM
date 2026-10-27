"""Bind Forge QA function slices to exact changed source; preserve untouched ASTs."""
from pathlib import Path
import ast,json,hashlib,textwrap,subprocess,os
R=Path(__file__).resolve().parents[2];os.chdir(R)
P=Path('.factory/content-packaging-t3');S=P/'qa-scope';S.mkdir(exist_ok=True)
BASE='4395f10'

def functions(tree,prefix=''):
    result={}
    for node in tree.body:
        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):result[prefix+node.name]=node
        if isinstance(node,ast.ClassDef):result.update(functions(node,prefix+node.name+'.'))
    return result

bindings=[];unchanged=[]
for module,expected in [('server',{'owner_domain_post','Handler.post','Handler.retry_worker','Handler.get_history'}),('operation_catalog',{'catalog'})]:
    rel='mission_control/'+module+'.py';text=Path(rel).read_text(encoding='utf-8');prior=subprocess.check_output(['git','show',BASE+':'+rel]).decode('utf-8');base=functions(ast.parse(prior));current=functions(ast.parse(text))
    changed={name for name,node in current.items() if name not in base or ast.dump(node,include_attributes=False)!=ast.dump(base[name],include_attributes=False)}
    assert changed==expected,(changed,expected)
    segments=[]
    if module=='operation_catalog':
        node=next(n for n in ast.parse(text).body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='OPERATIONS' for t in n.targets));segments.append(textwrap.dedent(''.join(text.splitlines(keepends=True)[node.lineno-1:node.end_lineno])))
    for name in sorted(changed):
        node=current[name];segment=textwrap.dedent(''.join(text.splitlines(keepends=True)[node.lineno-1:node.end_lineno]));assert ast.dump(ast.parse(segment).body[0],include_attributes=False)==ast.dump(node,include_attributes=False);segments.append(segment)
        bindings.append(dict(original=rel,original_sha256=hashlib.sha256(text.encode()).hexdigest(),symbol=name,line=node.lineno,end_line=node.end_lineno,extracted_sha256=hashlib.sha256(segment.encode()).hexdigest()))
    (S/(module+'.py')).write_bytes(('\n\n'.join(segments).rstrip()+'\n').encode())
    unchanged.extend(dict(path=rel,symbol=name,ast_sha256=hashlib.sha256(ast.dump(node,include_attributes=False).encode()).hexdigest()) for name,node in current.items() if name not in changed)
(P/'qa-source-bindings.json').write_bytes(json.dumps(dict(base=BASE,bindings=bindings,unchanged=unchanged),indent=2).encode())
modules=[]
for name in ['packaging_access','packaging_http','packaging_contract','operation_catalog','operation_runtime','automation_requirements','server','discovery_http']:
    path=str(S/(name+'.py')).replace('\\','/') if name in ['server','operation_catalog'] else 'mission_control/'+name+'.py';tree=ast.parse(Path(path).read_text(encoding='utf-8'));modules.append(dict(name=name,path=path,language='python',functions=[dict(name=n.name,args=[a.arg for a in n.args.args],returns='object') for n in tree.body if isinstance(n,ast.FunctionDef)]))
Path('specs/content-packaging-t3.ssat.yaml').write_bytes(json.dumps(dict(name='content-packaging-t3',language='python',modules=modules),indent=2).encode())
