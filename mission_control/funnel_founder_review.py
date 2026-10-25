"""Private founder review of app-sales evidence; sequential receipts grant no effects."""
from collections import Counter
from datetime import datetime,timezone
from .common import Invalid,digest
from .db import connection
from .pmf_contract import count
from .growth_review_contract import context_of
from .subscription_review import review_status
from .funnel_store import Funnels


def utc():
    """Use one declared observation time per review without freezing authorization."""
    return datetime.now(timezone.utc)


def findings(values,limit):
    """Bound output without concealing remaining findings or copying raw source data."""
    items=[{key:row[key]for key in ('area','id','stage_id','code','next_action')if key in row}for row in values[:limit]]
    return dict(items=items,total=len(values),shown=len(items),has_more=len(values)>len(items))


def base_review(store,app,stamp):
    """Reference the existing review; no second financial or customer-source ledger."""
    try:
        source=review_status(store,app['id'],clock=lambda:stamp,expected=app)
    except Invalid:
        return dict(status='UNAVAILABLE',source_hash=None,observed_at=stamp.isoformat(),evidence_states={},
                    findings=findings([dict(area='subscription_review',code='BASE_REVIEW_UNAVAILABLE',next_action='Inspect the existing subscription growth review and repair its source evidence in Results.')],100))
    return dict(status=source['status'],source_hash=source['source_hash'],observed_at=source['observed_at'],
                evidence_states=source['evidence_states'],findings=findings(source['issues'],100))


def identities(store,app_id,offset):
    """Read at most five immutable IDs; offset pagination discloses total coverage."""
    count(offset,0,10000)
    with connection(store.path) as db:
        total=db.execute('SELECT count(*) FROM growth_funnels WHERE app_id=?',(app_id,)).fetchone()[0]
        if offset>total:raise Invalid('Funnel history changed; restart the founder review')
        ids=[r[0]for r in db.execute('SELECT id FROM growth_funnels WHERE app_id=? ORDER BY created,id LIMIT 5 OFFSET ?',(app_id,offset))]
    return ids,dict(offset=offset,limit=5,evaluated=len(ids),total=total,next_offset=offset+len(ids)if offset+len(ids)<total else None)


def stage_projection(report):
    """Keep exact stage populations and counts; never add different cohort outcomes."""
    keys=('id','label','count','status','unit','denominator_definition','source_refs','evidence_hash')
    return [{key:row[key]for key in keys}for row in report['stages']]


def entry(flow,app_id,identity,stamp):
    """One unavailable source stays visible; authority failures are never swallowed."""
    try:
        report=flow.report(app_id,identity,as_of=stamp.isoformat())
    except (Invalid,KeyError):
        return dict(id=identity,state='UNAVAILABLE',definition_hash=None,report_hash=None,cohort_id=None,currency=None,
                    stages=None,stage_coverage=None,comparisons=None,
                    findings=findings([dict(code='FUNNEL_SOURCE_UNAVAILABLE',next_action='Open this exact saved funnel and inspect source integrity and current app setup. Retained evidence is unchanged.')],20))
    counts=Counter(row['status']for row in report['stages'])
    stages=stage_projection(report)
    comparable=sum(row['rate']is not None for row in report['edges'])
    return dict(id=identity,state=report['source_status'],definition_hash=report['definition_hash'],report_hash=report['source_hash'],
                cohort_id=report['cohort_id'],currency=report['currency'],stages=stages,stage_coverage=dict(counts),
                comparisons=dict(total=len(report['edges']),comparable=comparable,withheld=len(report['edges'])-comparable),
                findings=findings(report['findings'],20))


def local_status(base,entries,total):
    """Local review status is operational completeness, not acquisition or growth proof."""
    if base['status']=='UNAVAILABLE' or any(row['state']=='UNAVAILABLE'for row in entries):return 'NEEDS_REPAIR'
    if total==0 or base['findings']['total'] or any(row['findings']['total']for row in entries):return 'NEEDS_INPUT'
    return 'LOCAL_REVIEW_AVAILABLE'


def review(store,app_id,offset=0,clock=None):
    """Join only the selected app; current authority is rechecked by protected reads."""
    stamp=(clock or utc)();app=store.app(app_id);context=context_of(app)
    ids,coverage=identities(store,app_id,offset)
    base=base_review(store,app,stamp)
    flow=Funnels(store,clock=lambda:stamp)
    entries=[entry(flow,app_id,identity,stamp)for identity in ids]
    if context_of(store.app(app_id))!=context:raise Invalid('App setup changed during founder review; refresh without discarding history')
    issues=[]if coverage['total']else[dict(area='app_sales',code='NO_APP_SALES_PLAN',next_action='Create an app-sales plan in Results using a current creative brief and a matching event-ledger cohort.')]
    value=dict(schema='growth.app-sales-founder-review.v1',app_id=app_id,context=context,observed_at=stamp.isoformat(),
               status=local_status(base,entries,coverage['total']),status_scope='DISPLAYED_FUNNEL_PAGE_AND_CURRENT_SUBSCRIPTION_REVIEW',subscription_review=base,funnels=entries,coverage=coverage,
               findings=issues,execution_authority=False,external_writes=False,spend_minor=0,
               consistency='SEQUENTIAL_SOURCE_READS_APP_VERSION_CHECKED',change='NOT_COMPARED_WITH_PRIOR_REVIEW',
               scope='Displayed funnel page and bounded subscription findings only. Each cohort, currency and report remains separate. Complete stage details use the exact funnel report. No financial rollup, person-level transition, prior-review delta or causal sales lift is inferred.')
    return dict(value,source_hash=digest(value))
