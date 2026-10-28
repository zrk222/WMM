"""Codemagic native simulator runner; selects only actual available device IDs."""
from pathlib import Path
import json,platform,subprocess,sys

IOS=Path(__file__).resolve().parents[1]

def simulator_architecture(machine):
    # CPython's pinned install helper selects lib-$ARCHS, one architecture only.
    if machine not in ('arm64','x86_64'):
        raise ValueError('Unsupported Apple simulator host architecture')
    return machine

def select_devices(inventory):
    available=[d for runtime,devices in inventory['devices'].items() if 'iOS' in runtime
               for d in devices if d.get('isAvailable') is True]
    chosen=[]
    for family in ('iPhone','iPad'):
        matches=[d for d in available if d.get('name','').startswith(family) and d.get('udid')]
        if not matches:raise ValueError(f'No available {family} simulator; install its platform before claiming coverage')
        # Inventory order is not a contract. Keep selection reproducible within a host.
        chosen.append(sorted(matches,key=lambda d:(d['name'],d['udid']))[0])
    return chosen

def main():
    if platform.system()!='Darwin':raise SystemExit('Simulator tests NOT_RUN: Apple host required')
    architecture=simulator_architecture(platform.machine())
    evidence=IOS/'build-evidence';evidence.mkdir(exist_ok=True)
    raw=subprocess.check_output(['xcrun','simctl','list','devices','available','-j'],text=True)
    inventory=json.loads(raw);devices=select_devices(inventory)
    (evidence/'selected-simulators.json').write_text(json.dumps(devices,indent=2),encoding='utf-8')
    outcomes=[]
    for device in devices:
        family='iphone' if device['name'].startswith('iPhone') else 'ipad'
        result=evidence/f'{family}.xcresult'
        if result.exists():raise SystemExit(f'Existing {result.name} retained; use a fresh build workspace')
        subprocess.run(['xcrun','simctl','boot',device['udid']],check=device.get('state')!='Booted')
        subprocess.run(['xcrun','simctl','bootstatus',device['udid'],'-b'],check=True)
        argv=['xcodebuild','test','-project',str(IOS/'WMM.xcodeproj'),'-scheme','WMM',
              '-destination',f'platform=iOS Simulator,id={device["udid"]}',
              '-derivedDataPath',str(IOS/'DerivedData'),'-resultBundlePath',str(result),
              'CODE_SIGNING_ALLOWED=YES','CODE_SIGN_IDENTITY=-','CODE_SIGNING_REQUIRED=YES','ONLY_ACTIVE_ARCH=YES',f'ARCHS={architecture}']
        completed=subprocess.run(argv)
        outcomes.append(dict(family=family,device=device,command=argv,exit_code=completed.returncode,
                             xcresult_exists=result.is_dir(),physical_device_acceptance='NOT_RUN'))
        (evidence/'simulator-outcomes.json').write_text(json.dumps(outcomes,indent=2),encoding='utf-8')
        if not result.is_dir():raise SystemExit('xcodebuild produced no xcresult; acceptance incomplete')
    # A phone assertion failure must remain a failure without hiding tablet
    # evidence. Collect both actual inventories and retain each exit code.
    failed=next((item['exit_code'] for item in outcomes if item['exit_code']),0)
    if failed:raise SystemExit(failed)
    print('iPhone and iPad simulator test commands passed; inspect xcresult coverage. Physical device acceptance NOT_RUN.')

if __name__=='__main__':main()
