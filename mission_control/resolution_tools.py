"""Closed read-only resolution dispatch; no prompt-generated commands or writes."""
import json
from .common import Invalid,digest,iso_time,now
from .db import connection
from .marketing_agent_manifest import operating_manifest


def guard(store,app_id,frozen):
    """Reject changed authority or targets before and after the actual tool."""
    app=store.app(app_id)
    if frozen['app_id']!=app_id or app['version']!=frozen['manifest_version'] or digest(app['data'])!=frozen['app_hash']:
        raise Invalid('App changed; approve a new resolution proposal')
    policy=operating_manifest(app)
    if digest(policy)!=frozen['policy_hash'] or frozen['tool'] not in policy['supported_resolution_tools']:
        raise Invalid('Agent operating manifest changed or does not permit this resolution')
    if iso_time(now())>iso_time(frozen['expires_at']):
        raise Invalid('Resolution approval expired; review a current proposal')
    sources=sorted([r['id'],r['hash'],r['version']] for r in store.records(app_id))
    if sources!=frozen['record_sources']:
        raise Invalid('Resolution evidence sources changed; review the current proposal')
    return app


def source_guard(store,app_id,frozen,request_key=None):
    """Connection grants and immutable experiment definitions cannot drift silently."""
    p=frozen['parameters'];tool=frozen['tool']
    if tool=='refresh_analytics':
        analytics_guard(store,app_id,p)
    if tool=='evaluate_experiment':
        experiment_guard(store,app_id,p)
    if tool=='inspect_tracking':
        from .tracking_resolution import validate
        validate(store,app_id,p)
    if tool=='reuse_observation':
        reuse_guard(store,app_id,p,request_key)


def reuse_guard(store,app_id,p,request_key=None):
    """Reject a superseded source even when the referenced artifact itself still exists."""
    from .agent_feedback import reuse_candidate
    current=reuse_candidate(store,store.app(app_id),exclude_request_key='resolution-'+request_key if request_key else None)
    if not current or {k:v for k,v in current.items() if k!='repair_codes'}!=p:
        raise Invalid('Saved observation changed, expired or was superseded; review current reuse options')


def analytics_guard(store,app_id,p):
    """Bind a read to the exact app-owned analytics configuration version."""
    with connection(store.path) as db:
        row=db.execute('SELECT version,data FROM insight_sources WHERE app_id=? AND id=?',(app_id,p['source_id'])).fetchone()
    if row is None or row['version']!=p['source_version'] or digest(json.loads(row['data']))!=p['configuration_hash']:
        raise Invalid('Analytics source changed; approve its current configuration')


def experiment_guard(store,app_id,p):
    """Analysis cannot borrow a different or cancelled experiment definition."""
    with connection(store.path) as db:
        row=db.execute('SELECT hash,state FROM experiments WHERE app_id=? AND id=?',(app_id,p['experiment_id'])).fetchone()
    if row is None or row['hash']!=p['definition_hash'] or row['state']=='CANCELLED':
        raise Invalid('Experiment is changed, cancelled or belongs to another app')


def result(summary,artifacts,next_actions,status='EVIDENCE_GATHERED'):
    """A tool result never implicitly closes the original evidence requirement."""
    return dict(status=status,summary=summary,artifacts=artifacts,next_actions=next_actions,
                proof_status='PARTIAL' if status=='EVIDENCE_GATHERED' else 'NOT_VERIFIED',
                automatically_verified=False,external_writes=False,spend_minor=0)


def collect(store,app_id,frozen,request_key=None,on_job=None):
    """Queue fixed child reads without inventing their completion or coverage."""
    from .campaign_inputs import CampaignInputs
    service=CampaignInputs(store)
    if 'retry_candidates' in frozen['parameters']:
        queued=service.retry(app_id,frozen['parameters'],request_key,on_job)
    else:
        queued=service.start(app_id,dict(manifest_version=frozen['manifest_version'],
                    source_hash=frozen['parameters']['collection_hash']),on_job)
    children=[t['job']['id'] for t in queued['tasks'] if t['job']]
    return dict(result('Provider source collection dispatched; inspect the child results',
        [dict(job_id=identity) for identity in children],
        ['Wait for the source reads, inspect returned coverage, then resolve remaining proof gaps'],
        'WAITING_FOR_SOURCES'),children=children)


def inspect_site(store,app_id,frozen,app):
    """Reuse pinned, bounded, credential-free site inspection and its native evidence."""
    from .aeo_workflows import Checks
    row=Checks(store).run(app_id,dict(app_version=app['version'],app_hash=digest(app['data']),
        url=frozen['parameters']['url'],intent_id=None,intent_hash=None))
    return result('Public destination check recorded; authenticated and native journeys remain unverified',
        [dict(kind='aeo_check',id=row['id'],sha256=row['hash'])],
        [*row['data']['repairs'],'Run the remaining actual app, account, device and billing checks'])


def refresh_analytics(store,app_id,frozen):
    """Read only the previously configured dedicated source, preserving denial states."""
    from .insights import Insights
    p=frozen['parameters'];value=Insights(store).refresh(app_id,p['source_id'],{'confirm_read':True})
    if value['status']!='CONNECTED':
        return result('Analytics read needs source resolution: '+value['status'],[],
            ['Review source access and current configuration; preserve earlier successful evidence'],'NEEDS_RESOLUTION')
    return result('Connected measurement refreshed; aggregates do not prove event semantics or mature outcomes',
        [dict(kind='analytics_report',source_id=p['source_id'],sha256=digest(value['report']))],
        ['Verify event meaning, consent, release scope, eligible cohort denominators and actual costs'])


def evaluate_experiment(store,app_id,frozen):
    """Use the existing preregistered analysis and report its actual maturity state."""
    from .experiments import Experiments
    value=Experiments(store).evaluate(app_id,frozen['parameters']['experiment_id'])
    analysis=value.get('result',value)
    if analysis['status']=='AWAITING_ANALYSIS':
        return result('Registered experiment has not reached its declared analysis time',[],
            ['Wait until '+analysis['analysis_at']+' before approving analysis'],'WAITING_FOR_MATURITY')
    return result('Registered experiment analysis: '+analysis['status'],
        [dict(kind='experiment_assessment',experiment_id=frozen['parameters']['experiment_id'],sha256=value['hash'])],
        analysis.get('issues') or ['Inspect assignment evidence, uncertainty and guardrails before choosing another test'],
        'EVIDENCE_GATHERED' if analysis['status']=='EVALUATED' else 'NEEDS_RESOLUTION')


def reuse_observation(store,app_id,frozen):
    """Return an existing native artifact without any provider or website request."""
    from .feedback_artifacts import public_artifact,public_codes
    p=frozen['parameters'];row=public_artifact(store,app_id,p['artifact_id'],p['artifact_hash'],p['url'])
    return result('Saved public observation reused; no fresh website request or app journey verification',
        [dict(kind='aeo_check',id=row['id'],sha256=row['hash'])],
        ['Resolve public repair codes: '+', '.join(public_codes(row)),
         'Plan the next missing proof; explicitly approve a fresh recheck if the page changed'])


def discover_setup(store,app_id,frozen):
    """Produce a review draft; the approved read cannot approve its own suggestions."""
    from .setup_discovery import SetupDiscovery
    from .aeo_transport import public_url
    app=store.app(app_id)
    if frozen['parameters']!={'website':public_url(app['data'].get('website'))}:
        raise Invalid('Setup discovery target changed; approve the saved app website')
    row=SetupDiscovery(store).start(app_id,dict(app_id=app_id,app_version=app['version'],
        app_hash=digest(app['data']),confirm_read=True))
    available=row['state']=='PENDING'
    return result('App setup suggestions collected for human review' if available else 'Public app source needs resolution',
        [dict(kind='setup_proposal',id=row['id'],sha256=row['hash'])],
        ['Open the saved draft, review sources and approve only selected fields',
         'Collect separate proof for release, activation, ownership and product behavior'],
        'EVIDENCE_GATHERED' if available else 'NEEDS_RESOLUTION')


def execute(store,app_id,data,on_job=None):
    """Dispatch one immutable approved read; arbitrary tools never enter execution."""
    if set(data)!={'envelope','envelope_hash','original_request'} or digest(data['envelope'])!=data['envelope_hash']:
        raise Invalid('Resolution envelope integrity failed')
    frozen=data['envelope'];app=guard(store,app_id,frozen);source_guard(store,app_id,frozen,data['original_request']['request_key'])
    tools={'refresh_analytics':refresh_analytics,'evaluate_experiment':evaluate_experiment,'reuse_observation':reuse_observation,'discover_setup':discover_setup}
    if frozen['tool']=='collect_sources':value=collect(store,app_id,frozen,data['original_request']['request_key'],on_job)
    elif frozen['tool']=='inspect_tracking':
        from .tracking_resolution import dispatch
        value=dispatch(store,app_id,frozen,data['original_request']['request_key'],on_job)
    elif frozen['tool']=='inspect_site':value=inspect_site(store,app_id,frozen,app)
    else:value=tools[frozen['tool']](store,app_id,frozen)
    guard(store,app_id,frozen);source_guard(store,app_id,frozen,data['original_request']['request_key'])
    return value
