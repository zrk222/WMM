"""Finite, source-bound execution proposals; unknown capabilities are not execution."""
import uuid
from .common import Invalid,digest
from .marketing_agent_manifest import operating_manifest


def useful(option, collection, cached):
    """Reuse known site evidence and avoid recollecting completed source jobs."""
    if not option['ready'] or option['tool']=='reuse_observation':return False
    if option['tool']=='inspect_site':return not cached
    if option['tool']!='collect_sources':return True
    if 'retry_candidates' in option['parameters']:return bool(option['parameters']['retry_candidates'])
    return any(t['job'] is None or t['job']['status'] in ('QUEUED','RUNNING') for t in collection['tasks'])


def choices(resolutions, collection, allowed):
    """Keep task-relevant order and one execution per exact current target."""
    options=[o for i in resolutions['issues'] for o in i['options']]
    cached=any(o['tool']=='reuse_observation' and o['ready'] for o in options)
    seen=set();steps=[]
    for issue in resolutions['issues']:
        for option in issue['options']:
            if option['id'] in seen or option['tool'] not in allowed:continue
            if not useful(option,collection,cached):continue
            seen.add(option['id'])
            steps.append(dict(id=option['id'],issue_id=issue['id'],source_hash=issue['source_hash'],
                tool=option['tool'],title=option['title'],parameters=option['parameters'],
                artifact=option['artifact'],limits=option['limits'],cost=option['cost']))
    return steps,cached

def prepare(app, resolutions, collection) -> object:
    """Derive the finite current evidence sequence without network or writes."""
    policy=operating_manifest(app)
    steps,cached=choices(resolutions,collection,policy['supported_resolution_tools'])
    proposal=dict(schema='growth.campaign-sequence-proposal.v1',app_id=app['id'],
        manifest_version=app['version'],source_hash=resolutions['source_hash'],
        policy_hash=digest(policy),steps=steps,approval_seconds=policy['resolution_approval_seconds'],
        execution_mode='LOCAL_SERVICE_REQUIRED',existing_site_evidence=cached,
        status='READY_FOR_REVIEW' if steps else 'SOURCE_OR_IMPLEMENTATION_REQUIRED',
        next_actions=['Review the listed actions and their limits before approving' if steps else
                      'Review source access or prepare implementation work for the remaining evidence gaps'],
        automatically_verified=False,spend_minor=0,external_writes=False)
    return dict(proposal,proposal_hash=digest(proposal))


def selected(proposal, body):
    """Edits may remove actions; they cannot supply commands or unreviewed targets."""
    ids=body.get('selected_steps')
    if not isinstance(ids,list) or not ids or not all(isinstance(i,str) for i in ids):
        raise Invalid('Select the current reviewed actions')
    if len(ids)!=len(set(ids)):raise Invalid('Select each action once')
    steps=[s for s in proposal['steps'] if s['id'] in ids]
    if [s['id'] for s in steps]!=ids:raise Invalid('Use the current reviewed action order and targets')
    return steps

def freeze(app, resolutions, proposal, body, run_id, operator) -> object:
    """Freeze exactly reviewed step envelopes and authority."""
    from .resolutions import choose,envelope
    steps=[]
    for index,step in enumerate(selected(proposal,body)):
        request=dict(issue_id=step['issue_id'],option_id=step['id'],source_hash=step['source_hash'],
                     target_url=None,request_key=str(uuid.uuid5(uuid.UUID(run_id),str(index))))
        issue,option=choose(resolutions,request)
        frozen=envelope(app,resolutions,issue,option,request,operator)
        data=dict(envelope=frozen,envelope_hash=digest(frozen),original_request=request)
        steps.append(dict(id=step['id'],title=step['title'],tool=step['tool'],data=data))
    first=steps[0]['data']['envelope']
    return dict(app_id=app['id'],proposal_hash=proposal['proposal_hash'],steps=steps,
                approved_by=operator,approved_at=first['approved_at'],expires_at=first['expires_at'])
