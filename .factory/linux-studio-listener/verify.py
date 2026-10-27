"""Reproducible bounded component checks; desktop/systemd admission is NOT_RUN."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'.factory/linux-studio-listener'


def run(name,argv,allowed=(0,)):
    result=subprocess.run(argv,cwd=ROOT,capture_output=True,text=True,encoding='utf-8',env=dict(os.environ,PYTHONUTF8='1'))
    (OUT/name).write_text(result.stdout+result.stderr,encoding='utf-8',newline='\n')
    if result.returncode not in allowed:raise RuntimeError(name+' failed; inspect retained log')
    return result


def artifact(path,kind):
    return dict(path=path,kind=kind,sha256=hashlib.sha256((ROOT/path).read_bytes()).hexdigest())


def write(name,value):
    (OUT/name).write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8',newline='\n')


def security():
    base=OUT/'security-scope';manifest=[]
    for name in ('studio_listener_linux','common'):
        source=ROOT/'mission_control'/(name+'.py');target=base/'mission_control'/(name+'.py')
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
        manifest.append(artifact(source.relative_to(ROOT).as_posix(),'source'))
    (base/'.factory').mkdir(exist_ok=True)
    (base/'.factory/tenant-read-contract.json').write_text(json.dumps(dict(schema='factory.tenant-read-contract.v1',reads=[])),encoding='utf-8')
    write('security-source-hashes.json',manifest)
    run('security.json',['factory','audit','security','--root',str(base.relative_to(ROOT)),'--json'])
    report=json.loads((OUT/'security.json').read_text())
    if report['state']!='CLEAN' or not report['audit_coverage']['complete']:raise RuntimeError('Scoped security incomplete')


def workflow():
    reasons={
        'happy_path':'Exact socket plus live retained member witness verified twice; unit branching and real container kernel component observations are distinct.',
        'validation':'Malformed framing, sender/sequence, truncation, ambiguity, stale/cookie/input and scope failure deny; all five traced requirements retain strict/mutation evidence.',
        'failure_recovery':'Exceptions close sockets, task/proc/cgroup descriptors and retain no PID authority; late death/migration and revoked owner deny.',
        'state_consistency':'Same inode/cookie and original live pidfd persist across two observations; same-scope inherited holders accepted, foreign/missing witness denied.',
        'security_privacy':'No process signalling, service-manager call, shell or selector activation; retained fd/callback scope only; bounded-source static security plus privacy checks.',
        'performance':'Explicit deadline, byte/message/member/fd limits are tested; native repeated observations preserve descriptor counts. No throughput or hard kernel-preemption guarantee.',
        'accessibility':'No UI or accessibility surface changed; component-only source/tests/specs.',
        'external_effects':'No provider write, process stop, service launch, backend activation or publication; kernel read-only observation and synthetic container sockets only.',
    }
    (OUT/'scope-review.md').write_text(json.dumps(reasons,indent=2)+'\nThe scoped security inventory covers listener and direct common dependency only. No custom app/SQL tenant read exists in these two modules; the empty tenant-read set is scoped to that fact, not a platform-isolation claim. Mock tests prove branching only. Container cgroup root is not a WMM transient unit. T1-T3/T6 native-host containment/admission/desktop support NOT_RUN. Parent reviewed component-only implementation and Astra deadline repair review found no concrete remaining P1/P2. Earlier Windows timing failures remain recorded; three unchanged ordered inventories now passed, including two without diagnostic wrappers. Cause remains unproven; no native desktop or full-platform acceptance claim.\n',encoding='utf-8',newline='\n')
    paths=['mission_control/studio_listener_linux.py','tests/test_studio_listener_linux.py','specs/linux-studio-listener.md','plans/linux-studio-listener.md','specs/linux-studio-listener.ssat.yaml']
    paths += ['.factory/linux-studio-listener/'+name for name in ['verify.py','mutations.py','kernel_component.py','run_kernel.py','native_diagnostic.py']]
    candidate=[artifact(p,'source' if p.endswith('.py') else 'contract') for p in paths]
    decisions=[];checks=[];observations=[]
    for category,reason in reasons.items():
        applies=category not in ('accessibility','external_effects');decision=dict(category=category,applicable=applies,reason=reason)
        if not applies:decision['review_evidence']=artifact('.factory/linux-studio-listener/scope-review.md','review')
        decisions.append(decision)
        if not applies:continue
        profiles=['Windows-Python3.11-branching-and-existing-Studio','Docker-Ubuntu-Python3.12-kernel-component-only']
        checks.append(dict(id=category,requirement=reason,category=category,profiles=profiles))
        for profile in profiles:
            logs=['unit.log','mutations.json','regressions.log'] if profile.startswith('Windows') else ['kernel-component.log','kernel-unit.log','image-identity.log']
            logs+=['security.json','privacy.log','qa.json']
            observations.append(dict(id=category,profile=profile,status='PASS',reason=reason+' Native desktop acceptance NOT_RUN.',
                execution_identity='python .factory/linux-studio-listener/verify.py',observed_at=datetime.now(timezone.utc).isoformat(),
                artifacts=[artifact('.factory/linux-studio-listener/'+name,'log') for name in logs]))
    contract=dict(schema='factory.workflow-audit.contract.v1',project_id='WMM-Linux-listener-component',candidate=candidate,applicability=decisions,checks=checks)
    write('workflow-contract.json',contract)
    write('workflow-observations.json',dict(schema='factory.workflow-audit.observations.v1',contract_sha256=artifact('.factory/linux-studio-listener/workflow-contract.json','contract')['sha256'],
        candidate_sha256=hashlib.sha256(json.dumps(candidate,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest(),observations=observations))
    run('workflow.json',['factory','audit','workflows','--root','.','--contract','.factory/linux-studio-listener/workflow-contract.json','--observations','.factory/linux-studio-listener/workflow-observations.json','--json'])


if __name__=='__main__':
    run('build.log',[sys.executable,'-m','compileall','-q','mission_control/studio_listener_linux.py'])
    run('lint.log',[sys.executable,'-m','ruff','check','mission_control/studio_listener_linux.py','tests/test_studio_listener_linux.py','--select','F'])
    run('unit.log',[sys.executable,'-m','unittest','tests.test_studio_listener_linux','-v'])
    run('regressions.log',[sys.executable,'-m','unittest','tests.test_studio_listener_linux','tests.test_studio_child','tests.test_studio_command','tests.test_hypit_studio_process','-v'])
    run('coverage-run.log',[sys.executable,'-m','coverage','run','--data-file=.factory/linux-studio-listener/coverage','--source=mission_control.studio_listener_linux','-m','unittest','tests.test_studio_listener_linux'])
    run('coverage.log',[sys.executable,'-m','coverage','report','--data-file=.factory/linux-studio-listener/coverage','--fail-under=80'])
    run('mutations-run.log',[sys.executable,'.factory/linux-studio-listener/mutations.py'])
    run('kernel-run.log',[sys.executable,'.factory/linux-studio-listener/run_kernel.py'])
    run('image-identity.log',['docker','image','inspect','wmm-ubuntu-workflows:local','--format','{{.Id}}'])
    run('kernel-unit.log',['docker','run','--rm','--network','none','--mount',f'type=bind,source={ROOT},target=/workspace,readonly','-e','PYTHONDONTWRITEBYTECODE=1','-e','PYTHONPATH=/workspace','-w','/workspace','--entrypoint','python3','wmm-ubuntu-workflows:local','-m','unittest','tests.test_studio_listener_linux','-v'])
    for name,args in [('strict.log',['specline','strict','linux-studio-listener','--root','.','--json']),
                      ('validators.log',['specline','verify-validators','linux-studio-listener','--root','.','--json']),
                      ('challenge.log',['specline','challenge','linux-studio-listener','--root','.','--out','.factory/linux-studio-listener/challenge.json']),
                      ('qa.json',['forge','qa','linux-studio-listener','--ssat','specs/linux-studio-listener.ssat.yaml','--root','.','--strict'])]:run(name,args)
    security();run('privacy.log',[sys.executable,'tools/check_distribution.py']);workflow()
    print('COMPONENT CHECKS PASS; native systemd/desktop acceptance NOT_RUN; parent review required before WIP commit.')
