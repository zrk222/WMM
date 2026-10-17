"""Local ledger derivation for agent context; financial rows remain local and only sanitized status enters the prompt."""
from .common import Invalid,digest
from .db import connection
from .ledger import Ledger

LIMIT=100


def derive(store,app):
    """Use the existing ledger semantics and reject an oversized cohort index."""
    with connection(store.path) as db:
        count=db.execute('SELECT count(*) FROM growth_cohorts WHERE app_id=?',(app['id'],)).fetchone()[0]
    if count>LIMIT:
        raise Invalid('Agent ledger index exceeds100 cohorts; narrow or archive cohort scope before reviewing a new proposal')
    reports=Ledger(store.path).reports(app['id'])
    if len(reports)>LIMIT:
        raise Invalid('Agent ledger index changed beyond100 cohorts; review a narrower scope')
    selected=[r for r in reports if r['cohort']['release']==app['data'].get('release')]
    rows=sorted((dict(state=r['status'],source_sha256=r['source_hash']) for r in selected),key=lambda r:r['source_sha256'])
    state='UNAVAILABLE' if not rows else 'SUPPLIED_RECONCILED' if all(r['state']=='SUPPLIED_RECONCILED' for r in rows) else 'INCONCLUSIVE'
    value=dict(state=state,cohort_count=len(rows),sources=rows,source_sha256=digest(rows),
        scope='Selected-app imported ledger derivation only; provider signatures, completeness and causal lift remain unverified',
        excluded=['amounts','subject identities','raw events','cohort names','source descriptions'])
    if state!='SUPPLIED_RECONCILED':
        value['resolution']='Collect the missing consented outcomes and cost receipts, or wait for declared maturity; review current evidence actions'
    return reports,value
