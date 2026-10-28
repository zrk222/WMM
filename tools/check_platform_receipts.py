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
    paths.update(('codemagic.yaml','specs/ios-client.md','plans/ios-client.md','package/acquisition_analysis.py',
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


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile',choices=['ios'],required=True)
    parser.add_argument('--evidence',type=Path,default=ROOT/'.factory/ios-acceptance')
    args=parser.parse_args()
    try:result=check(ROOT,args.evidence)
    except (OSError,ValueError,TypeError,KeyError,AttributeError):
        result=dict(state='INCOMPLETE',errors=['Unreadable or malformed receipt/source evidence'],certifies_runtime=False)
    print(json.dumps(result,indent=2))
    return 1 if result['state']=='INCOMPLETE' else 0


if __name__=='__main__':raise SystemExit(main())
