"""Revalidate native public evidence without networking or protected-storage access."""
import re
from .common import Invalid,digest,now,iso_time
from .db import connection
from .aeo_workflows import decode,validate_data,currentness

FRESH_SECONDS=86400


def public_artifact(store,app_id,identity,expected_hash,target):
    """Only exact current native observations can support an explicitly approved reuse."""
    with connection(store.path) as db:
        row=db.execute('SELECT * FROM aeo_checks WHERE app_id=? AND id=?',(app_id,identity)).fetchone()
        if row is None:raise Invalid('Saved public observation is missing; approve a fresh inspection')
        row=decode(row);data=row['data']
        if row['hash']!=expected_hash or digest(data)!=expected_hash:
            raise Invalid('Saved public observation changed; inspect its integrity before reuse')
        validate_data(data,app_id)
        if currentness(db,store,app_id,row)!='CURRENT':
            raise Invalid('Saved observation is imported or stale; approve a fresh inspection')
    if data['binding']['target']!=target:
        raise Invalid('Saved observation targets a different page; review the exact target')
    age=(iso_time(now())-iso_time(data['observed_at'])).total_seconds()
    if not 0<=age<=FRESH_SECONDS:raise Invalid('Saved observation is over86400 seconds old; approve a fresh inspection')
    return row


def public_codes(row):
    """Return computed public repair codes, never arbitrary repair text or page content."""
    codes=sorted({r['code'] for r in row['data']['repairs']})
    if len(codes)>32 or any(not re.fullmatch(r'[A-Za-z0-9_:-]{1,80}',c) for c in codes):
        raise Invalid('Saved repair codes are malformed; inspect the source observation')
    return codes
