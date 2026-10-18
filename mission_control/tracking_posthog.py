"""Fixed PostHog reads with authority checks around every remote request."""
from urllib.parse import urlencode
from .common import Invalid,digest
from .insights_contract import project_scope
from .insights_transport import request
from .tracking_contract import query,shape,SCOPE


def fetch(url,token,guard,body=None):
    """Reject revoked or cancelled authority before another read and before adoption."""
    guard();result=request(url,token,body);guard();return result


def flag_rows(payload,key):
    """Accept only one exact complete flag lookup, with no cross-project pagination."""
    if not isinstance(payload,dict) or payload.get('next'):raise Invalid('Flag lookup is incomplete')
    rows=payload.get('results')
    if not isinstance(rows,list) or len(rows)>1 or payload.get('count')!=len(rows):raise Invalid('Flag lookup is ambiguous')
    if not rows:return rows
    flag=rows[0]
    if not isinstance(flag,dict) or flag.get('key')!=key:raise Invalid('Provider returned another experiment flag')
    return rows


def flag_findings(payload,expected):
    """Retain mismatch descriptions, never arbitrary flag properties or account metadata."""
    rows=flag_rows(payload,expected['key'])
    if not rows:return ['Expected experiment flag is not provisioned']
    flag=rows[0]
    issues=[]
    for name in ('active','ensure_experience_continuity','filters'):
        if flag.get(name)!=expected[name]:issues.append('Provider '+name+' differs from the reviewed experiment setup')
    if flag.get('deleted') or flag.get('archived'):issues.append('Provider flag is deleted or archived')
    return issues


def read(plan, token, guard) -> object:
    """Read fixed PostHog project, flag and tracking aggregates under current authority."""
    project_scope(dict(provider='posthog',project_id=plan['project_id'],region=plan['region']))
    base='https://'+plan['region']+'.posthog.com/api/projects/'+plan['project_id']+'/'
    identity=fetch(base,token,guard)
    if not isinstance(identity,dict) or str(identity.get('id'))!=plan['project_id']:raise Invalid('Provider returned another project identity')
    flags=fetch(base+'feature_flags/?'+urlencode(dict(key=plan['flag_key'],limit=2)),token,guard)
    findings=flag_findings(flags,plan['expected_flag'])
    if not flags['results']:
        return dict(status='NEEDS_SETUP',flag_findings=findings,observed_counts=None,scope=SCOPE,
            next_actions=['Review the expected provider flag setup','Install app-owned assignment and rendered-exposure instrumentation','Approve a current tracking read after setup'])
    payload=fetch(base+'query/',token,guard,dict(query=dict(kind='HogQLQuery',query=query(plan))))
    result=shape(payload)
    return dict(result,flag_findings=findings,provider_config_sha256=digest({k:flags['results'][0].get(k) for k in ('key','active','filters','ensure_experience_continuity')}),
        next_actions=['Resolve any provider configuration findings','Review event coverage and cross-arm contamination','Complete delivery, consent and outcome verification before evaluating a test'])
