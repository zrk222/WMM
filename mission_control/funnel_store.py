"""Immutable app-sales plans and upstream observations reuse existing domain evidence."""
from datetime import datetime,timezone
import json
from .common import Invalid,canonical,digest,identifier,iso_time
from .db import connection
from .pmf_contract import exact,count
from .funnel_contract import definition,observation,rows


def decoded(row):
    """Reject corrupt saved evidence instead of presenting it as current data."""
    result=dict(row);result['data']=json.loads(result['data'])
    if digest(result['data'])!=result['hash']:raise Invalid('Saved funnel evidence integrity changed')
    return result


def app_context(db,app_id,expected=None):
    """Read exact app context inside the caller's transaction."""
    row=db.execute('SELECT * FROM apps WHERE id=?',(app_id,)).fetchone()
    if row is None:raise Invalid('App workspace does not exist')
    if expected is not None:
        count(expected,1,2147483647)
        if row['version']!=expected:raise Invalid('App setup changed; review the current funnel')
    return dict(version=row['version'],hash=digest(json.loads(row['data'])),data=json.loads(row['data']))


def cohort_binding(db,app_id,plan,app):
    """Require one existing app-owned cohort with matching release, locale and currency."""
    row=db.execute('SELECT * FROM growth_cohorts WHERE app_id=? AND id=?',(app_id,plan['cohort_id'])).fetchone()
    if row is None:raise Invalid('Define the selected app cohort before saving this funnel')
    value=json.loads(row['data'])
    if digest(value)!=row['hash']:raise Invalid('Cohort evidence integrity changed')
    for key in ('release','locale','currency'):
        if value[key]!=plan[key] or app['data'].get(key)!=plan[key]:
            raise Invalid('Funnel and cohort must match current app release, locale and currency')
    for key in ('starts_at','ends_at'):
        if iso_time(value[key])!=iso_time(plan['attribution'][key]):
            raise Invalid('Funnel acquisition window differs from the declared cohort')
    return dict(id=plan['cohort_id'],sha256=row['hash'])


def creative_binding(db,store,app_id,ref):
    """Resolve the latest native brief and its current underlying app/source proof."""
    from .creative_briefs import stale_findings
    row=db.execute('SELECT * FROM creative_briefs WHERE app_id=? AND id=? ORDER BY version DESC LIMIT 1',(app_id,ref['id'])).fetchone()
    if row is None or row['version']!=ref['version']:raise Invalid('Creative source version changed or belongs to another app')
    data=json.loads(row['data'])
    if digest(data)!=row['hash'] or row['hash']!=ref['sha256']:raise Invalid('Creative source hash changed')
    if stale_findings(db,store,app_id,data):raise Invalid('Creative source proof needs review')
    return dict(ref)


def research_binding(db,app_id,ref,stamp):
    """Immutable customer workflows carry supplied evidence and explicit expiry."""
    from .customer_workflow import workflow_readout
    row=db.execute('SELECT * FROM customer_workflows WHERE app_id=? AND id=?',(app_id,ref['id'])).fetchone()
    if row is None or ref['version']!=1:raise Invalid('Customer evidence is missing or has an unsupported version')
    data=json.loads(row['data'])
    if digest(data)!=row['hash'] or row['hash']!=ref['sha256']:raise Invalid('Customer evidence hash changed')
    app=app_context(db,app_id)
    if any(data.get(key)!=app['data'].get(key)for key in ('release','locale','currency')):
        raise Invalid('Customer evidence does not match current app scope')
    if workflow_readout(data,stamp)['unavailable_source_ids']:raise Invalid('Customer evidence is expired or unavailable')
    return dict(ref)


def source_bindings(db,store,app_id,plan,stamp):
    """Bind selected source kinds to their authoritative current domain records."""
    result=[]
    for ref in [*plan['creative_refs'],*plan['outcome']['research_refs']]:
        if ref['kind']=='CREATIVE_BRIEF':value=creative_binding(db,store,app_id,ref)
        else:value=research_binding(db,app_id,ref,stamp)
        result.append(value)
    return result


def frozen(db,store,app_id,plan,version,stamp):
    """Freeze source and cohort hashes; the plan itself grants no execution authority."""
    app=app_context(db,app_id,version)
    return dict(definition=plan,manifest_version=app['version'],app_hash=app['hash'],
                cohort=cohort_binding(db,app_id,plan,app),sources=source_bindings(db,store,app_id,plan,stamp))


def current(db,store,app_id,data,stamp):
    """Current views never rewrite a historical plan when its evidence changes."""
    return frozen(db,store,app_id,data['definition'],data['manifest_version'],stamp)==data


class Funnels:
    """Persist evidence locally; payment and downstream outcomes remain in the ledger."""
    def __init__(self,store,clock=None):
        self.store=store;self.clock=clock or (lambda:datetime.now(timezone.utc))

    def save(self,app_id,body):
        """Idempotent immutable identity; changed input needs a new reviewed plan ID."""
        exact(body,{'id','manifest_version','data'});identity=identifier(body['id'])
        plan=definition(body['data']);stamp=self.clock()
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE')
            value=frozen(db,self.store,app_id,plan,body['manifest_version'],stamp)
            old=db.execute('SELECT * FROM growth_funnels WHERE app_id=? AND id=?',(app_id,identity)).fetchone()
            if old:
                result=decoded(old)
                if result['data']!=value:raise Invalid('Funnel identity is immutable; save a new version ID')
                return result
            total=db.execute('SELECT count(*) FROM growth_funnels WHERE app_id=?',(app_id,)).fetchone()[0]
            if total>=1000:raise Invalid('Funnel history exceeds 1000 definitions')
            db.execute('INSERT INTO growth_funnels VALUES(?,?,?,?,?)',(app_id,identity,canonical(value),digest(value),stamp.isoformat()))
            return decoded(db.execute('SELECT * FROM growth_funnels WHERE app_id=? AND id=?',(app_id,identity)).fetchone())

    def list(self,app_id):
        """Show unchanged historical definitions and explicit current source status."""
        stamp=self.clock()
        with connection(self.store.path) as db:
            app_context(db,app_id)
            result=[]
            for row in db.execute('SELECT * FROM growth_funnels WHERE app_id=? ORDER BY created,id LIMIT 1000',(app_id,)):
                item=decoded(row)
                try:ready=current(db,self.store,app_id,item['data'],stamp)
                except (Invalid,KeyError):ready=False
                result.append(dict(item,source_status='CURRENT' if ready else 'SOURCE_REVIEW_NEEDED'))
        return dict(app_id=app_id,items=result,external_execution=False)

    def ingest(self,app_id,body):
        """Atomically admit bounded source observations against one exact current definition."""
        exact(body,{'funnel_id','funnel_hash','manifest_version','observations'})
        identity=identifier(body['funnel_id']);stamp=self.clock()
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE');app_context(db,app_id,body['manifest_version'])
            row=db.execute('SELECT * FROM growth_funnels WHERE app_id=? AND id=?',(app_id,identity)).fetchone()
            if row is None or row['hash']!=body['funnel_hash']:raise Invalid('Select the exact saved funnel and hash')
            plan=decoded(row)['data']
            if not current(db,self.store,app_id,plan,stamp):raise Invalid('Funnel sources changed; review a new plan')
            values=[observation(v,plan['definition'],stamp)for v in rows(body['observations'],500,'Funnel observations',1)]
            inserted=0
            for value in values:inserted+=self.insert(db,app_id,identity,value,stamp)
            total=db.execute('SELECT count(*) FROM funnel_observations WHERE app_id=? AND funnel_id=?',(app_id,identity)).fetchone()[0]
            if total>10000:raise Invalid('Funnel observation history exceeds 10000 rows; retain it and use a new declared window')
        return dict(inserted=inserted,duplicates=len(values)-inserted,funnel_id=identity,provenance='SUPPLIED_OBSERVATIONS_NOT_PROVIDER_VERIFIED')

    def insert(self,db,app_id,funnel_id,value,stamp):
        """One source event cannot silently move to a different funnel or overwrite counts."""
        content=dict(funnel_id=funnel_id,observation=value);hashed=digest(content)
        old=db.execute('SELECT hash FROM funnel_observations WHERE app_id=? AND source_ref=? AND event_id=?',(app_id,value['source_ref'],value['event_id'])).fetchone()
        if old:
            if old['hash']!=hashed:raise Invalid('Observation identity conflicts with existing source evidence')
            return 0
        db.execute('INSERT INTO funnel_observations VALUES(?,?,?,?,?,?,?)',(app_id,funnel_id,value['source_ref'],value['event_id'],canonical(content),hashed,stamp.isoformat()))
        return 1

    def observations(self,app_id,funnel_id):
        """Retain original supplied data after restart; no inferred conversion or payment."""
        identifier(funnel_id)
        with connection(self.store.path) as db:
            app_context(db,app_id)
            if db.execute('SELECT 1 FROM growth_funnels WHERE app_id=? AND id=?',(app_id,funnel_id)).fetchone() is None:
                raise Invalid('Funnel does not belong to this app')
            values=db.execute('SELECT * FROM funnel_observations WHERE app_id=? AND funnel_id=? ORDER BY created,source_ref,event_id',(app_id,funnel_id)).fetchall()
            return dict(items=[decoded(row)for row in values],payment_authority=False)


    def report(self,app_id,funnel_id,as_of=None):
        """Join the exact cohort ledger without copying or generating financial events."""
        from .ledger import Ledger
        from .funnel_reporting import calculate
        stamp=iso_time(as_of) if as_of else self.clock()
        if stamp>self.clock():raise Invalid('Funnel report cannot observe the future')
        items=self.list(app_id)['items'];saved=next((r for r in items if r['id']==funnel_id),None)
        if saved is None:raise Invalid('Funnel does not belong to this app')
        values=self.observations(app_id,funnel_id)['items']
        selected=saved['data']['definition']['cohort_id']
        reports=Ledger(self.store.path).reports(app_id,stamp.isoformat())
        ledger=next((r for r in reports if r['cohort']['cohort_id']==selected),None)
        with connection(self.store.path) as db:
            try:ready=current(db,self.store,app_id,saved['data'],self.clock())
            except (Invalid,KeyError):ready=False
        return calculate(saved,values,ledger,stamp.isoformat(),'CURRENT' if ready else 'SOURCE_REVIEW_NEEDED')
