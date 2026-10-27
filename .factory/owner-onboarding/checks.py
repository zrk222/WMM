"""Scope owner continuation to exact changed functions and actual browser evidence."""
from pathlib import Path
import hashlib,json,re,subprocess
P=Path('.factory/owner-onboarding');P.mkdir(parents=True,exist_ok=True)


def write(name,value):(P/name).write_bytes((json.dumps(value,indent=2)+'\n').encode('utf-8'))


def run(name,args):
    q=subprocess.run(args,capture_output=True)
    text=(q.stdout+q.stderr).decode('utf-8',errors='replace').replace(str(Path.home()),'<LOCAL_PROFILE>')
    (P/(name+'.log')).write_bytes(('\n'.join(line.rstrip()for line in text.splitlines())+'\n').encode('utf-8'))
    print(name,q.returncode,flush=True);assert q.returncode==0,name
    return q


run('owner-regressions',['python','-m','unittest','tests.test_verified_review','tests.test_agent_grants','tests.test_agent_setup_entrypoint','tests.test_provider_setup','tests.test_local_agent_access'])
run('node-all',['node','--test',*map(str,sorted(Path('tests').glob('*.test.*')))])
run('syntax',['node','--check','mission_control/static/verified-review.js'])
run('browser-lint',['ruff','check','--select','F,E9','tools/test_owner_onboarding_browser.py'])
run('requirements',['specline','strict','marketer-completion','--root','.','--json'])
source=Path('mission_control/static/verified-review.js');text=source.read_text(encoding='utf-8')
prior=subprocess.check_output(['git','show','bcb27c2:mission_control/static/verified-review.js']).decode('utf-8')


def functions(value):
    starts=list(re.finditer(r'(?m)^(?:async )?function (\w+)\(',value));result={}
    for index,match in enumerate(starts):
        end=starts[index+1].start()if index+1<len(starts)else value.index('document.addEventListener',match.start())
        result[match[1]]=re.sub(r'/\*\* [^\n]+ \*/\s*$','',value[match.start():end]).strip()
    return result


symbols=['identityLogin','accessBootstrap','ownerContinuation','verifiedRequest','verifiedSubmitted','verifiedSubmit']
now=functions(text);before=functions(prior)
for name,body in before.items():
    if name not in symbols:assert now[name]==body,name
notes={name:re.search(r'/\*\* ([^\n]+) \*/\n(?:async )?function '+name+r'\(',text)[1]for name in symbols}
target=P/'qa-scope.js';target.write_bytes(('\n\n'.join('/** '+name+': '+notes[name]+' */\nexport '+now[name]for name in symbols)+'\n').encode('utf-8'))
write('qa-source-binding.json',dict(source=source.as_posix(),sha256=hashlib.sha256(source.read_bytes()).hexdigest(),symbols=symbols,unchanged_other_functions=True,extracted=target.as_posix(),extracted_sha256=hashlib.sha256(target.read_bytes()).hexdigest()))
spec=Path('specs/owner-onboarding.ssat.yaml');spec.write_bytes((json.dumps(dict(name='owner-onboarding',language='javascript',modules=[dict(name='owner_onboarding',path=target.as_posix(),language='javascript',functions=[dict(name=name,args=[],returns='object')for name in symbols])]),indent=2)+'\n').encode('utf-8'))
q=run('qa',['forge','qa','owner-onboarding','--ssat',str(spec),'--strict']);d=json.loads(q.stdout);write('qa.json',d)
assert d['passed']and not d['findings']and d['metrics']['max_complexity']<=10
