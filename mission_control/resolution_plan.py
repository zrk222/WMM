"""Read-only issue and action proposals derived from current app-owned sources."""
from .common import digest
from .aeo_transport import public_url,ReadError
from .marketing_agent_manifest import operating_manifest
from .resolution_catalog import GOALS,TOOL_COPY,issue_kind,ordered_tools
from .automatic_preparation import check_scope


def website(app):
    """A malformed or absent destination is an explicit prerequisite, never a guess."""
    try:return public_url(app['data'].get('website'))
    except (ReadError,ValueError,TypeError):return None


def executable_options(app,collection,insights,experiments,reuse=None):
    """Fixed typed options; no network, credentials, body counts or invented inputs."""
    options=[dict(tool='collect_sources',parameters={'collection_hash':collection['source_hash']},
                  ready=bool(collection['tasks']),prerequisite='connections'),
             dict(tool='inspect_site',parameters={'url':website(app)},
                  ready=website(app) is not None,prerequisite='app')]
    if reuse:
        options.append(dict(tool='reuse_observation',parameters={k:v for k,v in reuse.items() if k!='repair_codes'},ready=True,prerequisite='app'))
    for source in insights['sources'][:3]:
        options.append(dict(tool='refresh_analytics',ready=source['status'] not in ('DISCONNECTED','CLEANUP_REQUIRED','PERMISSION_REQUIRED'),
            prerequisite='connections',parameters={'source_id':source['id'],'source_version':source['version'],
                'configuration_hash':digest(source['data']),'provider':source['provider']}))
    for test in experiments[:3]:
        if test['state'] in ('PLANNED','CANCELLED'):continue
        cohort=test['data']['control']['cohort']
        if cohort['release']!=app['data'].get('release') or cohort['locale']!=app['data'].get('locale'):continue
        options.append(dict(tool='evaluate_experiment',ready=True,prerequisite='experiments',
            parameters={'experiment_id':test['id'],'definition_hash':test['hash'],'name':test['data']['name']}))
    return options


def decorate(option):
    """Every choice explains evidence, authority, verification and recovery."""
    result={**TOOL_COPY[option['tool']],**option}
    result['id']=digest({'tool':option['tool'],'parameters':option['parameters']})
    result['cost']='No publication or ad spend; existing provider read quotas apply'
    result['stop']='Stop on changed identity/policy, denial, expiry, cancellation or exhausted read limits'
    result['status']='READY_FOR_APPROVAL' if option['ready'] else 'ACCESS_OR_TARGET_REQUIRED'
    return result


def grouped_issues(app,workflow):
    """Group identical gaps and retain every affected stage without hiding dependencies."""
    groups={}
    for step in workflow['steps']:
        messages=[*step['direct_needs'],*step['critical_findings']]
        for message in messages:
            kind=issue_kind(message,step['primary']['id'])
            key=(kind,message)
            if key not in groups:
                groups[key]=dict(id=digest({'app_id':app['id'],'kind':kind,'message':message}),kind=kind,
                    gap=message,goal=GOALS[kind],stages=[],verification=step['verify'])
            groups[key]['stages'].append(step['id'])
    return list(groups.values())


def prepare(app,records,workflow,collection,insights,experiments,reuse=None):
    """Attach explained options to all unverified inputs, without approving or running."""
    check_scope(app,records,())
    options=[decorate(o) for o in executable_options(app,collection,insights,experiments,reuse)]
    source=digest(dict(app=app,records=sorted((r['id'],r['hash'],r['version']) for r in records),
                       policy=digest(operating_manifest(app)),options=options))
    issues=grouped_issues(app,workflow)
    for issue in issues:
        original=ordered_tools(issue['kind'])
        order=tuple(t for key in original if key!='reuse_observation' for t in (('reuse_observation',key) if key=='inspect_site' else (key,)))
        issue['options']=sorted(options,key=lambda o:(not o['ready'],order.index(o['tool'])))
        issue['source_hash']=digest(dict(source=source,issue={k:v for k,v in issue.items() if k!='options'}))
        issue['setup_options']=[dict(id='connections',title='Review or approve source access'),
                                dict(id='app',title='Review or edit the app target')]
    return dict(schema='growth.agent-resolutions.v1',app_id=app['id'],manifest_version=app['version'],
                source_hash=source,record_sources=sorted([r['id'],r['hash'],r['version']] for r in records),
                issues=issues,automatic_external_writes=False,spend_minor=0)
