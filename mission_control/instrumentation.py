"""Credential-free, source-bound browser integration artifacts; never an installer."""
from pathlib import Path
from io import BytesIO
import hashlib,json,zipfile
from .common import Invalid,canonical,digest
from .aeo_transport import public_url,origin

FIELDS={'schema','app_id','manifest_version','experiment_id','experiment_version','experiment_hash',
        'source_id','source_version','source_hash','project_id','region','release','locale','starts_at',
        'ends_at','flag_key','expected_flag','events','scope','spend_minor','provider_writes','proposal_hash','origin'}
CONFIG=('app_id','release','locale','experiment_id','experiment_hash','flag_key','starts_at','ends_at','origin')

GUIDE='''# Browser experiment integration

This package is prepared, not installed. It does not launch an experiment.

1. Verify the manifest and config against the exact app release and registered
   experiment. Commit these files only through your app's normal reviewed change.
2. Use an existing initialized PostHog browser client, remote evaluation,
   `person_profiles: "always"`, and no bootstrapped flags. Only public project
   capture tokens belong in app code; never use a personal/secret API key.
3. Use the app's current consent and identified opaque internal user ID. The app
   must identify that user after consent and reset PostHog on logout/account
   change. Do not enable person profiles or change identity without that consent.
4. Bind `context()` to current app_id, release, locale, id and identified:true.
   Bind `consent()` to the actual current permission. The module never signs in,
   requests consent, installs a dependency or initializes provider credentials.
5. Call assign(), render exactly the returned variant, then call expose(element,
   variant) on its connected visible element. An assignment is not an exposure.
   Stop the tracker when the surface unmounts or consent/account changes.
6. Inspect typed errors and retain the normal app fallback. Missing SDK features,
   IndexedDB, fresh flags, visible content or identity are explicit recovery needs.

## Verification and boundaries
Exercise denied/revoked consent, logout/account switch, disabled flags, window
boundaries, repeated render, multiple tabs, changed variant and storage failure.
Check project, flag and query permissions separately in WMM's tracking review.
Read actual scoped provider events before asserting instrumentation is live.

`QUEUED_NOT_DELIVERED` means the SDK accepted an event, not that the network or
provider accepted it. Stable UUIDs survive retries and same-origin tabs; SDK and
provider delivery remain asynchronous. IndexedDB state does not synchronize
across devices. Browser DOM visibility is not confirmed human attention.

This adapter does not establish randomization quality, concurrent-experiment
interference controls, attribution, conversion, mature outcomes or causal lift.
Native mobile adapters, app-repo installation, flag creation/launch/pause and a
genuine provider pilot remain separate work. Retain this distinction in UI.

Reference: https://posthog.com/docs/feature-flags/creating-feature-flags
Reference: https://posthog.com/docs/libraries/js/usage
'''

EXAMPLE='''import {createTracker} from './experiment-client.mjs';
import config from './config.json' with {type: 'json'};

// Bind these callbacks to the real app. This example does not initialize PostHog.
export async function renderMeasuredVariant({posthog, consent, context, render}) {
  const tracker=createTracker(config,posthog,{consent,context});
  try {
    const assignment=await tracker.assign();
    const element=await render(assignment.variant);
    await tracker.expose(element,assignment.variant);
    return tracker; // Call stop() on unmount, logout or consent withdrawal.
  } catch(error) {tracker.stop();throw error;}
}
'''


def configuration(plan):
    """Accept only the recomputable tracking contract plus an owned HTTPS origin."""
    if not isinstance(plan,dict) or set(plan)!=FIELDS:raise Invalid('Use the exact current tracking proposal and app origin')
    proposed={k:v for k,v in plan.items() if k not in ('origin','proposal_hash')}
    if digest(proposed)!=plan['proposal_hash']:raise Invalid('Tracking proposal integrity differs')
    if proposed['schema']!='growth.experiment-tracking-plan.v1' or proposed['provider_writes'] is not False or proposed['spend_minor']!=0:
        raise Invalid('Instrumentation cannot grant provider writes or spending')
    address=public_url(plan['origin'])
    if origin(address)!=plan['origin']:raise Invalid('Use the app exact HTTPS origin')
    return dict(schema='growth.browser-instrumentation.v1',**{key:plan[key] for key in CONFIG})

def bundle(plan) -> object:
    """Return credential-free source-bound browser integration files and their hashes."""
    config=configuration(plan)
    source=Path(__file__).resolve().parent/'sdk/experiment-client.mjs'
    values={'experiment-client.mjs':source.read_text(encoding='utf-8'),
            'config.json':canonical(config)+'\n','example.mjs':EXAMPLE,'README.md':GUIDE}
    files=[dict(name=name,sha256=hashlib.sha256(content.encode()).hexdigest(),content=content) for name,content in sorted(values.items())]
    value=dict(schema='growth.instrumentation-bundle.v1',status='PREPARED_NOT_INSTALLED',app_id=config['app_id'],
        experiment_id=config['experiment_id'],proposal_hash=plan['proposal_hash'],config_sha256=digest(config),
        files=files,provider_writes=False,spend_minor=0,
        next_actions=['Review and integrate these exact files through the app repository workflow',
                      'Verify actual consent, identity, provider events and rendered variants before launch'])
    return dict(value,bundle_hash=digest(value))


def archive(value):
    """Produce only the fixed reviewed files and a content-hash manifest in memory."""
    expected={k:v for k,v in value.items() if k!='bundle_hash'}
    if digest(expected)!=value['bundle_hash']:raise Invalid('Instrumentation bundle changed before download')
    if sorted(r['name'] for r in value['files'])!=['README.md','config.json','example.mjs','experiment-client.mjs']:
        raise Invalid('Instrumentation archive accepts only the fixed integration files')
    for row in value['files']:
        if hashlib.sha256(row['content'].encode()).hexdigest()!=row['sha256']:raise Invalid('Integration file hash changed')
    manifest={k:v for k,v in value.items() if k!='files'}
    manifest['files']=[{k:v for k,v in row.items() if k!='content'} for row in value['files']]
    files=[(r['name'],r['content']) for r in value['files']]+[('manifest.json',canonical(manifest)+'\n')]
    output=BytesIO()
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED) as zipped:
        for name,content in files:
            info=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0));info.external_attr=0o644<<16
            zipped.writestr(info,content.encode(),compress_type=zipfile.ZIP_DEFLATED)
    return output.getvalue()


def prepare(store,app_id,experiment_id,source_id,proposal_hash):
    """Recompute current app-owned inputs; downloads cannot smuggle an edited package."""
    from .experiment_tracking import Tracking
    plan=Tracking(store).prepare(app_id,dict(experiment_id=experiment_id,source_id=source_id))
    if plan['proposal_hash']!=proposal_hash:raise Invalid('Tracking setup changed; review it again before downloading')
    app=store.app(app_id);address=origin(public_url(app['data'].get('website')))
    return bundle(dict(plan,origin=address))
