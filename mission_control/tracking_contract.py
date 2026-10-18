"""Exact provider configuration and aggregate-only experiment tracking contracts."""
import re
from .common import Invalid,digest,iso_time
from .insights_contract import project_scope

ARMS=('control','treatment')
EVENTS=('wmm_experiment_assignment','wmm_experiment_exposure')
COLUMNS=['arm','event','event_rows','subjects','cross_arm_subjects']
SCOPE='Provider tracking observation only; not launch, rendered-view verification, conversion or causal evidence'


def expected_flag(app,experiment):
    """Describe the intended provider assignment without issuing a provider change."""
    data=experiment['data'];allocation=data['treatment_allocation']
    if type(allocation) not in (int,float) or not 0<allocation<1:raise Invalid('Registered experiment allocation is invalid')
    identity=experiment['id']
    if not isinstance(identity,str) or not re.fullmatch(r'[a-f0-9-]{36}',identity):raise Invalid('Experiment identity is unsupported')
    properties=[dict(key='wmm_app_id',value=app['id'],operator='exact',type='person'),
                dict(key='wmm_release',value=app['data']['release'],operator='exact',type='person')]
    return dict(key='wmm-'+identity,active=True,ensure_experience_continuity=True,
        filters=dict(groups=[dict(properties=properties,rollout_percentage=100)],
          multivariate=dict(variants=[dict(key='control',rollout_percentage=round((1-allocation)*100,10)),
                                    dict(key='treatment',rollout_percentage=round(allocation*100,10))])))


def validate_sources(app,experiment,source):
    """Reject cross-app, disconnected, unsupported or altered saved source records."""
    data=experiment['data'];config=source['data']
    if experiment['app_id']!=app['id'] or source['app_id']!=app['id']:raise Invalid('Experiment and source must belong to this app')
    if source['provider']!='posthog' or config.get('provider')!='posthog':raise Invalid('Select this app\'s PostHog connection')
    if source['status'] in ('DISCONNECTED','CLEANUP_REQUIRED'):raise Invalid('Reconnect this analytics source before reading')
    project_scope(config)
    if digest(config)!=source['hash'] or digest(data)!=experiment['hash']:raise Invalid('Saved experiment or analytics integrity differs')
    if experiment['state']=='CANCELLED':raise Invalid('This experiment is cancelled; review retained results')


def validate_window(app,experiment):
    """Use the immutable registered release, locale and acquisition window."""
    cohort=experiment['data']['control']['cohort'];release=app['data'].get('release')
    if release!=cohort['release'] or app['data'].get('locale')!=cohort['locale']:raise Invalid('App release or locale changed; register a current experiment')
    start=iso_time(cohort['starts_at']).isoformat();end=iso_time(cohort['ends_at']).isoformat()
    if iso_time(start)>=iso_time(end):raise Invalid('Registered observation window is invalid')
    return cohort,release,start,end


def proposal(app, experiment, source) -> object:
    """Derive the exact current provider read contract without network or writes."""
    validate_sources(app,experiment,source)
    cohort,release,start,end=validate_window(app,experiment);config=source['data']
    flag=expected_flag(app,experiment)
    value=dict(schema='growth.experiment-tracking-plan.v1',app_id=app['id'],manifest_version=app['version'],
        experiment_id=experiment['id'],experiment_version=experiment['version'],experiment_hash=experiment['hash'],
        source_id=source['id'],source_version=source['version'],source_hash=source['hash'],
        project_id=config['project_id'],region=config['region'],release=release,locale=cohort['locale'],
        starts_at=start,ends_at=end,flag_key=flag['key'],expected_flag=flag,
        events=list(EVENTS),scope=SCOPE,spend_minor=0,provider_writes=False)
    return dict(value,proposal_hash=digest(value))


def literal(value):
    """Escape fixed contract strings as HogQL values, never identifiers or SQL fragments."""
    if not isinstance(value,str) or not value or len(value)>200 or not value.isprintable():raise Invalid('Tracking query value is unsupported')
    return "'"+value.replace('\\','\\\\').replace("'","\\'")+"'"


def query(plan) -> str:
    """Build a fixed aggregate query without exporting subject identifiers."""
    filters=[f"properties.wmm_app_id = {literal(plan['app_id'])}",
             f"properties.wmm_experiment_hash = {literal(plan['experiment_hash'])}",
             f"properties.wmm_release = {literal(plan['release'])}",
             f"properties.wmm_locale = {literal(plan['locale'])}",
             f"timestamp >= toDateTime({literal(plan['starts_at'])})",
             f"timestamp < toDateTime({literal(plan['ends_at'])})","timestamp <= now()",
             'event IN ('+','.join(literal(e) for e in EVENTS)+')']
    return ('WITH scoped AS (SELECT distinct_id, properties.wmm_variant AS arm, event FROM events WHERE '+
        ' AND '.join(filters)+') SELECT arm, event, count() AS event_rows, uniqExact(distinct_id) AS subjects, '+
        '(SELECT count() FROM (SELECT distinct_id FROM scoped GROUP BY distinct_id HAVING uniqExact(arm) > 1)) '+
        'AS cross_arm_subjects FROM scoped GROUP BY arm, event ORDER BY arm, event')


def count(value):
    """Keep aggregate integers within the existing provider safe-number boundary."""
    if type(value) is not int or not 0<=value<=9007199254740991:raise Invalid('Tracking aggregate must be a nonnegative safe integer')
    return value


def row_value(row):
    """Reject unknown arms, event names, raw subjects and inconsistent counts."""
    if not isinstance(row,list) or len(row)!=5:raise Invalid('Tracking response columns differ')
    arm,event,total,subjects,cross=row
    if arm not in ARMS or event not in EVENTS:raise Invalid('Tracking contains an unregistered arm or event')
    total,subjects,cross=map(count,(total,subjects,cross))
    if subjects>total or subjects==0 and total>0:raise Invalid('Tracking subject counts are inconsistent')
    return dict(arm=arm,event=event,event_rows=total,subjects=subjects,cross_arm_subjects=cross)


def response_rows(payload):
    """Require exact columns and a complete bounded provider query before adopting rows."""
    if not isinstance(payload,dict) or payload.get('error') or payload.get('columns')!=COLUMNS:raise Invalid('Tracking query returned another schema')
    status=payload.get('query_status')
    if status and (not isinstance(status,dict) or status.get('complete') is not True):raise Invalid('Tracking query is incomplete; retry a current read')
    rows=payload.get('results')
    if not isinstance(rows,list) or len(rows)>len(ARMS)*len(EVENTS):raise Invalid('Tracking aggregate response is unbounded or missing')
    return rows


def cross_bound(values):
    """Cross-arm IDs cannot exceed the observed subject totals in either arm."""
    return min(sum(row['subjects'] for row in values if row['arm']==arm) for arm in ARMS)


def shape(payload) -> object:
    """Reject incomplete or unexpected provider aggregate columns and values."""
    rows=response_rows(payload)
    values=[row_value(r) for r in rows];keys={(r['arm'],r['event']) for r in values}
    if len(keys)!=len(values):raise Invalid('Tracking returned duplicate arm/event rows')
    cross={r['cross_arm_subjects'] for r in values}
    if len(cross)>1:raise Invalid('Cross-arm aggregate differs across rows')
    if cross and next(iter(cross))>cross_bound(values):raise Invalid('Cross-arm count exceeds the available arm subjects')
    return dict(status='OBSERVED' if values else 'NO_OBSERVATIONS',observed_counts=values,
        cross_arm_subjects=next(iter(cross),None),scope=SCOPE,
        limits=['Counts use provider distinct IDs, not verified people or confirmed human views.',
                'Events missing required app, experiment, release or locale metadata are not in this scoped query.',
                'This read does not verify consent, complete instrumentation, costs or outcomes.'])
