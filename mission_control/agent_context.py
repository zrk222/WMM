"""Bounded public campaign context; no network, credential or uploaded-file reads."""
from .common import Invalid, canonical, digest
from .db import connection
from .store import decode
from .agent_registry import FACTS
from .pipeline import evaluate
from .release_readiness import readiness as release_readiness
from .subscription_readiness import readiness as subscription_readiness
from .agent_economics import derive
from .agent_feedback import feedback
from .creative_taste import guidance as creative_taste

LIMIT = 100
MAX_CHARS = 32768
SCHEMA = 'growth.agent-context.v1'


def indexed(db, sql, app_id):
    """Reject overflow instead of silently omitting a newer failed observation."""
    rows = db.execute(sql, (app_id, LIMIT + 1)).fetchall()
    if len(rows) > LIMIT:
        raise Invalid('Agent source index exceeds100 entries; narrow or archive evidence, then review again')
    return [decode(row) for row in rows]


def saved_sources(store, app_id):
    """Load this app only; review content is replaced with a critical-count signal."""
    with connection(store.path) as db:
        records = indexed(db, "SELECT * FROM records WHERE app_id=? AND kind!='review' ORDER BY updated DESC,id LIMIT ?", app_id)
        reviews = db.execute("SELECT COUNT(*) FROM records WHERE app_id=? AND kind='review' AND json_extract(data,'$.confirmed')=1 AND json_extract(data,'$.severity')='P0'", (app_id,)).fetchone()[0]
        jobs = indexed(db, "SELECT * FROM jobs WHERE app_id=? AND action='sync' AND json_extract(data,'$.options.operation') IN ('release_inventory','subscription_catalog') ORDER BY created DESC,id LIMIT ?", app_id)
    if reviews:
        records.append(dict(id='critical-summary', app_id=app_id, kind='review',
                            title='Confirmed critical feature failure', data=dict(confirmed=True,severity='P0'),
                            hash=digest(reviews), version=1, updated=''))
    return records, jobs


def source(identity, classification, data):
    """Bind citations to exactly the sanitized values approved for transmission."""
    return dict(id=identity, classification=classification, data=data, sha256=digest(data))


def provider_source(identity, view):
    """Expose validator state and public identity, never raw reports or diagnostics."""
    report = view.get('report') or {}
    values = dict(state=view['state'], access='NOT_CHECKED',
                  scope='Saved provider observation only; no live access or product journey verified')
    for key in ('store_app_id','job_id'):
        if key in view: values[key] = view[key]
    for key in ('observed_at','review_state','coverage','version','platform'):
        if key in report: values[key] = report[key]
    if view['state'] not in ('NOT_APPLICABLE','INVENTORY_CHECKED','CATALOG_APPROVED'):
        values['resolution'] = 'Inspect this app saved provider read; reconnect or refresh it, then review a new proposal'
    return source(identity, 'SAVED_PROVIDER_OBSERVATION', values)


def stage_source(stage):
    """Use catalog instructions and counts, excluding operator-written diagnostics."""
    data = {key:stage[key] for key in ('id','title','status','inputs','dependencies','operations')}
    data.update(missing_count=len(stage['missing']), evidence_scope='OPERATOR_ASSERTIONS_AND_SAVED_PROVIDER_CHECKS',
                economics='Current imported-ledger derivation; amounts excluded and provider signatures not independently verified')
    return source('stage_'+str(stage['id']), 'WORKFLOW_DERIVATION', data)


def snapshot(store, app_id):
    """Assemble the selected public manifest and twelve current stage summaries."""
    app = store.app(app_id)
    records, jobs = saved_sources(store, app_id)
    release = release_readiness(app, records, jobs, {})
    subscriptions = subscription_readiness(app, records, jobs, {})
    ledger,economics = derive(store,app)
    fields = FACTS + ('brand_source','brand_visual','store_app_id','authorized_spend_minor')
    facts = {key:app['data'].get(key) for key in fields}
    facts['authorized_spend_minor'] = 0
    sources = [source('app_manifest','OWNER_SUPPLIED_PUBLIC_FACTS',facts)]
    sources += [stage_source(stage) for stage in evaluate(app,records,ledger_reports=ledger,catalog=subscriptions,release=release)]
    sources += [provider_source('release_observation',release),provider_source('subscription_observation',subscriptions)]
    sources += [source('ledger_state','LOCAL_IMPORTED_LEDGER_DERIVATION',economics)]
    sources += [source('action_feedback','TYPED_LOCAL_ACTION_OUTCOMES',feedback(store,app))]
    sources += [source('creative_taste','PRODUCT_ADVISORY_GUIDANCE',creative_taste())]
    value = dict(schema=SCHEMA,app_id=app_id,sources=sources,
                 excluded=['credentials','personal histories','uploaded files','customer review text','raw provider reports'],
                 external_execution='NOT_RUN')
    # Bind all selected evidence versions without transmitting their contents.
    value['evidence_fingerprint'] = digest(dict(records=[(r['id'],r.get('version'),r.get('hash')) for r in records],
        jobs=[(j['id'],j['status'],digest(j.get('result'))) for j in jobs]))
    if len(canonical(value)) > MAX_CHARS:
        raise Invalid('Agent context exceeds32768 characters; shorten public app facts and review again')
    return value
