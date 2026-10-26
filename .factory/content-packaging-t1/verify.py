"""Reproduce local T1 checks and meaningful source mutations without external writes."""
import ast
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'.factory/content-packaging-t1'
SOURCE=['mission_control/packaging_contract.py','mission_control/packaging_bindings.py','mission_control/packaging_store.py','mission_control/db.py']


def redacted(text):
    """Keep local user profile paths out of tracked verification evidence."""
    home=Path.home()
    for prefix in (json.dumps(str(home))[1:-1],str(home),home.as_posix()):
        text=text.replace(prefix,'<LOCAL_PROFILE>')
    return '\n'.join(line.rstrip() for line in text.split('\n'))


def run(name, argv, expected=0):
    result=subprocess.run(argv,cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace')
    (OUT/name).write_text(redacted('$ '+subprocess.list2cmdline(argv)+'\n'+result.stdout+result.stderr),encoding='utf-8',newline='\n')
    if result.returncode!=expected:raise RuntimeError(f'{name}: exit {result.returncode}; inspect captured log')
    return result


def artifact(path, kind):
    return dict(path=path,sha256=hashlib.sha256((ROOT/path).read_bytes()).hexdigest(),kind=kind)


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False)


def write(path, value):
    (ROOT/path).write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8',newline='\n')


def ssat():
    modules=[]
    for path in SOURCE:
        tree=ast.parse((ROOT/path).read_text())
        functions=[dict(name=n.name,args=[a.arg for a in n.args.args],returns='object') for n in ast.walk(tree) if isinstance(n,ast.FunctionDef)]
        modules.append(dict(name=Path(path).stem,path=path,language='python',functions=functions))
    write('specs/content-packaging-t1.ssat.yaml',dict(name='content-packaging-t1',language='python',modules=modules,dependencies=[],invariants=[]))


def mutations():
    cases=[
        ('source-hash','mission_control/packaging_bindings.py',"if row['version']!=ref['version'] or row['hash']!=ref['sha256']:", 'if False:'),
        ('script-binding','mission_control/packaging_contract.py',"if hashed(value['segment_sha256'])!=segments[result['segment_id']]:", 'if False:'),
        ('manifest','mission_control/packaging_store.py',"app=app_context(db, app_id, body['manifest_version'])", 'app=app_context(db, app_id)'),
        ('precommit','mission_control/packaging_store.py',"if result['source_status']!='CURRENT':", 'if False:'),
        ('immutable-delete','mission_control/db.py',"CREATE TRIGGER IF NOT EXISTS packaging_immutable_delete BEFORE DELETE ON packaging_documents BEGIN SELECT RAISE(ABORT,'packaging history is append-only'); END;", ''),
        ('immutable-replace','mission_control/db.py',"CREATE TRIGGER IF NOT EXISTS packaging_immutable_insert BEFORE INSERT ON packaging_documents WHEN EXISTS(SELECT 1 FROM packaging_documents WHERE app_id=NEW.app_id AND id=NEW.id AND version=NEW.version) BEGIN SELECT RAISE(ABORT,'packaging history is append-only'); END;", ''),
        ('immutable-rowid','mission_control/db.py',"CREATE TRIGGER IF NOT EXISTS packaging_no_rowid_replace BEFORE INSERT ON packaging_documents WHEN EXISTS(SELECT 1 FROM packaging_documents WHERE rowid=NEW.rowid) BEGIN SELECT RAISE(ABORT,'packaging history is append-only'); END;", ''),
    ]
    results=[]
    for name,path,before,after in cases:
        target=ROOT/path;raw=target.read_bytes();text=raw.decode('utf-8')
        if text.count(before)!=1:raise RuntimeError('Mutation anchor must be unique: '+name)
        try:
            target.write_text(text.replace(before,after),encoding='utf-8')
            result=subprocess.run([sys.executable,'-B','-m','unittest','tests.test_packaging','-v'],cwd=ROOT,capture_output=True,text=True)
            (OUT/f'mutation-{name}.log').write_text(redacted(result.stdout+result.stderr),encoding='utf-8',newline='\n')
            killed=result.returncode!=0 and ('FAIL:' in result.stderr or 'ERROR:' in result.stderr)
            results.append(dict(name=name,killed=killed,exit_code=result.returncode))
        finally:target.write_bytes(raw)
    write('.factory/content-packaging-t1/mutations.json',results)
    if not all(row['killed'] for row in results):raise RuntimeError('Source mutation survived')


def workflow():
    review='.factory/content-packaging-t1/scope.md'
    candidates=[artifact(path,'source') for path in SOURCE]
    candidates += [artifact('tests/test_packaging.py','test'),artifact('specs/content-packaging.md','contract'),artifact('specs/content-packaging-t1.ssat.yaml','contract')]
    candidates += [artifact('plans/content-packaging.md','contract'),artifact('.factory/content-packaging-t1/scope.md','review'),
                   artifact('.factory/content-packaging-t1/verify.py','source'),artifact('.factory/content-packaging-t1/security_scope.py','source')]
    categories=['happy_path','validation','failure_recovery','state_consistency','security_privacy','performance','accessibility','external_effects']
    applicable={key:key not in {'performance','accessibility'} for key in categories}
    reasons={
        'happy_path':'Persist drafts and script shots with exact native bindings and restart readback.',
        'validation':'Reject stale, foreign, malformed and unsupported references and script segment hashes.',
        'failure_recovery':'Rollback source or app changes detected during save and retain prior history.',
        'state_consistency':'Immutable SQLite rows and script/source/rights revisions remain hash-bound.',
        'security_privacy':'Closed input and app-scoped evidence; synthetic fixtures and no credential fields.',
        'performance':'No performance or throughput claim in this foundational local storage packet; fixed row/page bounds are validation checks.',
        'accessibility':'No UI, rendering, keyboard or assistive technology surface changed in T1.',
        'external_effects':'Stored draft remains NOT_RUN with execution_authority false; no execution adapter added.',
    }
    decisions=[];checks=[];observations=[];profile='Windows-CPython-'+platform.python_version()+'-SQLite-synthetic-offline'
    for category in categories:
        decision=dict(category=category,applicable=applicable[category],reason=reasons[category])
        if not applicable[category]:decision['review_evidence']=artifact(review,'review')
        decisions.append(decision)
        if not applicable[category]:continue
        checks.append(dict(id=category,category=category,requirement=reasons[category],profiles=[profile]))
        evidence=[artifact('.factory/content-packaging-t1/tests.log','log'),artifact('.factory/content-packaging-t1/mutations.json','log')]
        if category=='security_privacy' and (OUT/'privacy-distribution.log').exists():
            evidence.append(artifact('.factory/content-packaging-t1/privacy-distribution.log','log'))
        observations.append(dict(id=category,profile=profile,status='PASS',reason=reasons[category]+' See named unittest cases and mutation failures.',
            execution_identity='python -m unittest tests.test_packaging -v',observed_at=datetime.now(timezone.utc).isoformat(),
            artifacts=evidence))
    contract=dict(schema='factory.workflow-audit.contract.v1',project_id='WMM-content-packaging-T1',candidate=candidates,applicability=decisions,checks=checks)
    path='.factory/workflow-audit-contract.json';write(path,contract)
    write('.factory/workflow-audit-observations.json',dict(schema='factory.workflow-audit.observations.v1',contract_sha256=artifact(path,'contract')['sha256'],
        candidate_sha256=hashlib.sha256(canonical(candidates).encode()).hexdigest(),observations=observations))


if __name__=='__main__':
    OUT.mkdir(parents=True,exist_ok=True);ssat()
    run('build.log',[sys.executable,'-m','compileall','-q',*SOURCE])
    run('lint.log',[sys.executable,'-m','ruff','check',*SOURCE,'--select','F'])
    run('tests.log',[sys.executable,'-m','unittest','tests.test_packaging','-v'])
    run('regressions.log',[sys.executable,'-m','unittest','tests.test_packaging','tests.test_creative_production','tests.test_discovery_intelligence','tests.test_managed_media_store','tests.test_distribution','-v'])
    run('coverage-run.log',[sys.executable,'-m','coverage','run','--data-file=.factory/content-packaging-t1/coverage','--source=mission_control.packaging_contract,mission_control.packaging_store,mission_control.packaging_bindings','-m','unittest','tests.test_packaging'])
    run('coverage.log',[sys.executable,'-m','coverage','report','--data-file=.factory/content-packaging-t1/coverage','--fail-under=80'])
    mutations();workflow()
    print('T1 local checks and source mutations passed; run CF QA/security/workflows separately against final hashes.')
