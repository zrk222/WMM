"""Check native acceptance receipt integrity; never certify runtime claims."""
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
KINDS={'xcresult_summary','signed_app','runtime','install','domain','keychain','media','lifecycle','accessibility','exports','provider_boundary'}


def sha(path):
    result=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1048576),b''):result.update(block)
    return result.hexdigest()


def source_inventory(root):
    """Bind shipped source/config, excluding build output and private account state."""
    paths=set()
    for folder in ('mission_control','ios'):
        for path in (root/folder).rglob('*'):
            relative=path.relative_to(root)
            if any(part in {'.build','DerivedData','build-evidence','Python.xcframework','__pycache__'} for part in relative.parts):continue
            if path.is_file() and path.suffix.lower() in {'.py','.swift','.m','.h','.sh','.plist','.entitlements','.pbxproj','.xcscheme','.xctestplan','.lock'}:
                paths.add(relative.as_posix())
    paths.update(('codemagic.yaml','.github/workflows/platform-checks.yml','specs/ios-client.md','plans/ios-client.md','package/acquisition_analysis.py',
                  'tools/check_platform_receipts.py','tests/ios_acceptance.md'))
    return [{'path':p,'sha256':sha(root/p)} for p in sorted(paths)]


def check(root,evidence):
    errors=[]
    requirements=re.findall(r'identified by `([^`]+)`',(root/'specs/ios-client.md').read_text(encoding='utf-8'))
    if len(requirements)!=16 or len(set(requirements))!=16:errors.append('Expected all 16 unique iOS requirements')
    inventory=source_inventory(root)
    candidate=hashlib.sha256(json.dumps(inventory,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    receipt=evidence/'receipt.json'
    if not receipt.is_file():return dict(state='INCOMPLETE',errors=errors+['Native receipt.json missing'],candidate_sha256=candidate,source_count=len(inventory),certifies_runtime=False)
    if receipt.stat().st_size>16777216:return dict(state='INCOMPLETE',errors=['Receipt exceeds 16 MiB'],certifies_runtime=False)
    value=json.loads(receipt.read_text(encoding='utf-8'))
    if value.get('schema')!='wmm.ios-acceptance.v1':errors.append('Unsupported acceptance receipt schema')
    if value.get('candidate_sha256')!=candidate:errors.append('Source candidate is stale or unbound')
    artifacts={}
    for item in value.get('artifacts',[]):
        identity=item.get('id');relative=item.get('path')
        if not isinstance(identity,str) or identity in artifacts or not isinstance(relative,str):
            errors.append('Duplicate or malformed artifact identity');continue
        path=(evidence/relative).resolve()
        if Path(relative).is_absolute() or not path.is_relative_to(evidence.resolve()):
            errors.append('Artifact path escapes evidence directory');continue
        if not path.is_file() or sha(path)!=item.get('sha256'):
            errors.append('Missing or changed artifact: '+identity);continue
        artifacts[identity]=item
    seen=set()
    for profile in value.get('profiles',[]):
        family=profile.get('family')
        if family not in ('iphone','ipad') or family in seen:errors.append('Duplicate or invalid physical family');continue
        seen.add(family)
        if profile.get('physical') is not True:errors.append(family+': simulator cannot establish physical acceptance')
        if profile.get('companion_offline') is not True:errors.append(family+': standalone operation not recorded')
        for field in ('device_model','os_version','xcode_version','sdk_version','python_version','bundle_id','signing_identity','observed_at'):
            if not isinstance(profile.get(field),str) or not profile[field].strip():errors.append(family+': missing '+field)
        required=set(requirements);observed=set();kinds=set()
        for row in profile.get('observations',[]):
            requirement=row.get('requirement')
            if requirement not in required or requirement in observed:errors.append(family+': unknown or duplicate requirement');continue
            observed.add(requirement)
            if row.get('status')!='PASS':errors.append(family+': '+requirement+' is not PASS')
            references=row.get('artifacts')
            if not isinstance(references,list) or not references:errors.append(family+': '+requirement+' has no evidence');continue
            for identity in references:
                artifact=artifacts.get(identity)
                if not artifact or artifact.get('family')!=family:errors.append(family+': missing or foreign evidence reference')
                else:kinds.add(artifact.get('kind'))
        if observed!=required:errors.append(family+': missing requirement observations')
        if not KINDS<=kinds:errors.append(family+': missing artifact categories: '+','.join(sorted(KINDS-kinds)))
    if seen!={'iphone','ipad'}:errors.append('Both physical iPhone and iPad receipts are required')
    return dict(state='INCOMPLETE' if errors else 'EVIDENCE_CURRENT_REVIEW_REQUIRED',errors=errors,
                candidate_sha256=candidate,source_count=len(inventory),certifies_runtime=False,
                limits='Hashes and declared coverage only. Inspect xcresult, signing, install/device, accessibility and workflow artifacts independently; this command does not authenticate observations or establish full product functionality.')


def check_ci_contract(root):
    """Inspect declared build wiring only; never assert an Apple run occurred."""
    errors=[]
    path=root/'.github/workflows/platform-checks.yml'
    value=json.loads(path.read_text(encoding='utf-8'))
    if value.get('permissions')!={'contents':'read'}:errors.append('Use read-only workflow permissions')
    if 'workflow_dispatch' not in value.get('on',{}):errors.append('Native verification needs an explicit dispatch entry')
    paths=value.get('on',{}).get('pull_request',{}).get('paths',[])
    if not isinstance(paths,list) or not {'ios/**','mission_control/**','package/**'}.issubset(paths):
        errors.append('Native pull-request checks must cover Swift and bundled shared engine changes')
    jobs=value.get('jobs',{})
    contract=jobs.get('contract',{})
    if not any(step.get('run')=='python tools/check_platform_receipts.py --ci-contract' for step in contract.get('steps',[])):
        errors.append('Missing contract validation job')
    native=jobs.get('native-simulators',{})
    strategy=native.get('strategy',{})
    if strategy.get('fail-fast') is not False or strategy.get('matrix')!={'family':['iphone','ipad']}:
        errors.append('Native families require independent mandatory iPhone/iPad workers with fail-fast disabled')
    if native.get('runs-on')!='macos-15-intel' or native.get('needs')!='contract':errors.append('Native profile needs its declared Apple host and contract gate')
    if native.get('if')!="github.event_name == 'workflow_dispatch' || github.event_name == 'pull_request'":errors.append('Native profile must run on reviewed pull requests and explicit dispatch')
    if type(native.get('timeout-minutes')) is not int or not 1<=native['timeout-minutes']<=120:errors.append('Native build needs a bounded timeout')
    runs=[step.get('run','') for step in native.get('steps',[])]
    if not any(step.get('uses','').startswith('actions/setup-python@') and step.get('with',{}).get('python-version')=='3.13' for step in native.get('steps',[])):
        errors.append('Pinned Apple build tools require the declared Python 3.13 host')
    combined='\n'.join(runs)
    if 'python3 ios/Build/run_simulators.py --family ${{ matrix.family }}' not in combined:
        errors.append('Each native worker must execute its exact matrix family')
    steps=native.get('steps',[])
    restores=[s for s in steps if s.get('uses','').startswith('actions/cache/restore@')]
    saves=[s for s in steps if s.get('uses','').startswith('actions/cache/save@')]
    if len(restores)!=1 or len(saves)!=1:
        errors.append('Exact runtime cache requires one restore and one save')
    else:
        restore=restores[0];save=saves[0];config=restore.get('with',{})
        for identity in ('runner.os','runner.arch','steps.toolchain.outputs.xcode','ios/Build/Runtime.lock','ios/Build/build_runtime.py'):
            if identity not in config.get('key',''):errors.append('Runtime cache missing identity: '+identity)
        expected_paths='ios/Python.xcframework\nios/runtime-cache.json'
        if config.get('path')!=expected_paths or save.get('with',{}).get('path')!=expected_paths or config.get('restore-keys'):
            errors.append('Runtime cache must use exact key and framework/receipt paths only')
        builds=[s for s in steps if 'python3 ios/Build/build_runtime.py' in s.get('run','')]
        tests=[s for s in steps if 'python3 ios/Build/run_simulators.py' in s.get('run','')]
        if len(builds)!=1 or len(tests)!=1 or not steps.index(restore)<steps.index(builds[0])<steps.index(save)<steps.index(tests[0]):
            errors.append('Verify restored runtime before saving and testing')
        if save.get('with',{}).get('key')!='${{ steps.runtime_cache.outputs.cache-primary-key }}' or save.get('if')!="steps.runtime_cache.outputs.cache-hit != 'true'":
            errors.append('Save only the exact verified runtime cache key')
    for script in ('build_runtime.py','generate_project.py','run_simulators.py'):
        if not (root/'ios/Build'/script).is_file() or not any('python3 ios/Build/'+script in run and run.startswith('set -euo pipefail\n') for run in runs):
            errors.append('Missing fail-closed native stage: '+script)
    for identity in ('git rev-parse HEAD','xcodebuild -version','xcrun simctl list devices available -j'):
        if identity not in combined:errors.append('Missing actual build identity: '+identity)
    uploads=[step for step in native.get('steps',[]) if step.get('uses','').startswith('actions/upload-artifact@')]
    if len(uploads)!=1:errors.append('Exactly one native evidence upload is required')
    else:
        upload=uploads[0];config=upload.get('with',{})
        if '${{ matrix.family }}' not in config.get('name',''):
            errors.append('Native artifacts must distinguish simulator families')
        if upload.get('if')!='always()' or config.get('if-no-files-found')!='error':errors.append('Retain failed runs and reject absent artifacts')
        for artifact in ('ios/build-evidence/**','ios/DerivedData/Logs/Test/**','ios/DerivedData/Build/Products/Debug-iphonesimulator/WMM.app'):
            if artifact not in config.get('path','').splitlines():errors.append('Missing native artifact: '+artifact)
    for job in jobs.values():
        if job.get('continue-on-error'):errors.append('Native gate failures must not be ignored')
        for step in job.get('steps',[]):
            if step.get('continue-on-error'):errors.append('Native gate failures must not be ignored')
            if 'uses' in step and not re.fullmatch(r'actions/(?:[a-z-]+|cache/(?:restore|save))@[0-9a-f]{40}',step['uses']):errors.append('Actions must use exact commit pins')
    return dict(state='INCOMPLETE' if errors else 'CI_CONTRACT_VALID',errors=errors,
                certifies_runtime=False,native_execution='NOT_ESTABLISHED',physical_acceptance='NOT_ESTABLISHED',
                limits='Configuration inspection only. A manual Apple-host execution and physical iPhone/iPad acceptance remain separate requirements.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--profile',choices=['ios'])
    mode.add_argument('--ci-contract',action='store_true')
    parser.add_argument('--evidence',type=Path,default=ROOT/'.factory/ios-acceptance')
    args=parser.parse_args()
    try:result=check_ci_contract(ROOT) if args.ci_contract else check(ROOT,args.evidence)
    except (OSError,ValueError,TypeError,KeyError,AttributeError):
        result=dict(state='INCOMPLETE',errors=['Unreadable or malformed receipt/source evidence'],certifies_runtime=False)
    print(json.dumps(result,indent=2))
    return 1 if result['state']=='INCOMPLETE' else 0


if __name__=='__main__':raise SystemExit(main())
