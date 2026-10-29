"""Codemagic native simulator runner; selects only actual available device IDs."""
from pathlib import Path
import argparse,json,platform,subprocess,sys
from datetime import datetime,timezone

IOS=Path(__file__).resolve().parents[1]
BOOT_TIMEOUT=300
# Hosted Intel simulators have exceeded five minutes during cold boot readiness.
# Keep boot commands bounded separately; a readiness timeout remains a failure.
BOOT_READY_TIMEOUT=600
TEST_TIMEOUT=1200


def phase(evidence,family,name):
    value=dict(family=family,phase=name,observed_at=datetime.now(timezone.utc).isoformat())
    (evidence/f'{family}-phase.json').write_text(json.dumps(value,indent=2),encoding='utf-8')
    print('WMM_NATIVE_PHASE '+json.dumps(value),flush=True)


def run_device(device,architecture,evidence):
    family='iphone' if device['name'].startswith('iPhone') else 'ipad'
    result=evidence/f'{family}.xcresult'
    if result.exists():raise SystemExit(f'Existing {result.name} retained; use a fresh build workspace')
    argv=['xcodebuild','test','-project',str(IOS/'WMM.xcodeproj'),'-scheme','WMM',
          '-destination',f'platform=iOS Simulator,id={device["udid"]}',
          '-destination-timeout','180',
          '-derivedDataPath',str(IOS/'DerivedData'),'-resultBundlePath',str(result),
          'CODE_SIGNING_ALLOWED=YES','CODE_SIGN_IDENTITY=-','CODE_SIGNING_REQUIRED=YES','ONLY_ACTIVE_ARCH=YES',f'ARCHS={architecture}']
    state='boot';code=0
    try:
        phase(evidence,family,state)
        subprocess.run(['xcrun','simctl','boot',device['udid']],check=device.get('state')!='Booted',timeout=BOOT_TIMEOUT)
        state='boot readiness';phase(evidence,family,state)
        subprocess.run(['xcrun','simctl','bootstatus',device['udid'],'-b'],check=True,timeout=BOOT_READY_TIMEOUT)
        state='compile and test';phase(evidence,family,state)
        completed=subprocess.run(argv,timeout=TEST_TIMEOUT)
        code=completed.returncode
        state='completed' if code==0 else 'test failed'
        if not result.is_dir():code=code or 1;state='missing xcresult'
    except subprocess.TimeoutExpired:
        code=124;state+=' timeout'
    except subprocess.CalledProcessError as error:
        code=error.returncode or 1;state+=' failed'
    phase(evidence,family,state)
    return dict(family=family,device=device,command=argv,exit_code=code,phase=state,
                xcresult_exists=result.is_dir(),physical_device_acceptance='NOT_RUN')

def simulator_architecture(machine):
    # CPython's pinned install helper selects lib-$ARCHS, one architecture only.
    if machine not in ('arm64','x86_64'):
        raise ValueError('Unsupported Apple simulator host architecture')
    return machine

def select_devices(inventory,family=None):
    if family not in (None,'iphone','ipad'):raise ValueError('Select iphone or ipad explicitly')
    available=[d for runtime,devices in inventory['devices'].items() if 'iOS' in runtime
               for d in devices if d.get('isAvailable') is True]
    chosen=[]
    for prefix in (('iPhone','iPad') if family is None else (('iPhone',) if family=='iphone' else ('iPad',))):
        matches=[d for d in available if d.get('name','').startswith(prefix) and d.get('udid')]
        if not matches:raise ValueError(f'No available {prefix} simulator; install its platform before claiming coverage')
        # Inventory order is not a contract. Keep selection reproducible within a host.
        chosen.append(sorted(matches,key=lambda d:(d['name'],d['udid']))[0])
    return chosen

def main(family=None):
    if platform.system()!='Darwin':raise SystemExit('Simulator tests NOT_RUN: Apple host required')
    architecture=simulator_architecture(platform.machine())
    evidence=IOS/'build-evidence';evidence.mkdir(exist_ok=True)
    raw=subprocess.check_output(['xcrun','simctl','list','devices','available','-j'],text=True)
    inventory=json.loads(raw);devices=select_devices(inventory,family)
    (evidence/'selected-simulators.json').write_text(json.dumps(devices,indent=2),encoding='utf-8')
    outcomes=[]
    for device in devices:
        outcomes.append(run_device(device,architecture,evidence))
        (evidence/'simulator-outcomes.json').write_text(json.dumps(outcomes,indent=2),encoding='utf-8')
        # Release this exact simulator before booting the next family. Keeping
        # the phone running consumes the hosted runner's tablet boot resources.
        try:
            stopped=subprocess.run(['xcrun','simctl','shutdown',device['udid']],timeout=BOOT_TIMEOUT)
            outcomes[-1]['shutdown_exit_code']=stopped.returncode
        except subprocess.TimeoutExpired:
            outcomes[-1]['shutdown_exit_code']=124
        (evidence/'simulator-outcomes.json').write_text(json.dumps(outcomes,indent=2),encoding='utf-8')
    # A phone assertion failure must remain a failure without hiding tablet
    # evidence. Collect both actual inventories and retain each exit code.
    failed=next((item['exit_code'] for item in outcomes if item['exit_code']),0)
    if failed:raise SystemExit(failed)
    label='iPhone and iPad' if family is None else ('iPhone' if family=='iphone' else 'iPad')
    print(f'{label} simulator test commands passed; inspect xcresult coverage. Other profiles and physical device acceptance are not established by this command.')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--family',choices=('iphone','ipad'))
    main(parser.parse_args().family)
