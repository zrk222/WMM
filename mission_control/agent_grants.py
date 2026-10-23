"""Owner-issued local operation credentials; independent human review stays separate."""
from datetime import datetime,timedelta,timezone
import hashlib
import json
import re
import secrets
from .common import Invalid,canonical,digest,iso_time,uid
from .db import connection
from .operation_catalog import OPERATIONS,exact_keys,path_segment,request_data
from .review_access import member,exact_role
from .store import audit
from . import agent_review_policy


def token_digest(token):
    """Validate only the delegated credential format; never persist plaintext tokens."""
    if not isinstance(token,str) or not re.fullmatch(r'wmmg_[A-Za-z0-9_-]{43}',token):
        raise PermissionError('A valid scoped WMM agent grant is required')
    return hashlib.sha256(token.encode()).hexdigest()


def issue_data(body,observed):
    """Validate a finite exact operation scope and owner-selected lifetime/quota."""
    exact_keys(body,('agent_id','manifest_version','operations','expires','max_calls'),('review_operations',))
    path_segment(body['agent_id'])
    names=body['operations']
    if not isinstance(names,list) or not names or any(not isinstance(name,str) or name not in OPERATIONS for name in names):
        raise Invalid('Select only fixed local operation names')
    if len(names)!=len(set(names)):raise Invalid('Grant operations must be unique')
    agent_review_policy.validate(body)
    if type(body['max_calls']) is not int or not 1<=body['max_calls']<=10000:
        raise Invalid('Use a call ceiling from 1 through 10000')
    if not observed<iso_time(body['expires'])<=observed+timedelta(hours=24):
        raise Invalid('Grant expiry must be in the next 24 hours')


def public(row):
    """Return public delegation metadata, excluding credential hashes as well as secrets."""
    names=('id','app_id','agent_id','owner','owner_version','app_version','app_hash','expires','max_calls','used','status','version','created','updated')
    return dict({key:row[key] for key in names},operations=json.loads(row['operations']))


def app_scope(db,app_id):
    """Read the exact app revision and content hash inside the authorization transaction."""
    app=db.execute('SELECT * FROM apps WHERE id=?',(app_id,)).fetchone()
    if not app:raise Invalid('Grant app does not exist')
    return app['version'],digest(json.loads(app['data']))


def current(db,row,envelope,observed,check_quota=True):
    """Check delegated scope, owner membership and quota before reserving admission."""
    if row['status']!='ACTIVE' or iso_time(row['expires'])<=observed:
        raise PermissionError('Agent grant is revoked or expired')
    if row['app_id']!=envelope['app_id'] or envelope['operation'] not in json.loads(row['operations']):
        raise PermissionError('Agent grant does not allow this app or operation')
    exact_role(db,row['app_id'],row['owner'],row['owner_version'],'OWNER')
    if app_scope(db,row['app_id'])!=(row['app_version'],row['app_hash']):
        raise PermissionError('Agent grant app scope changed; request a new grant')
    if check_quota and row['used']>=row['max_calls']:raise PermissionError('Agent grant call ceiling is exhausted')


def authenticated(db,token,envelope,observed,check_quota=True):
    """Resolve delegated identity and current scope inside the admission transaction."""
    request_data(envelope)
    row=db.execute('SELECT * FROM agent_grants WHERE token_hash=?',(token_digest(token),)).fetchone()
    if not row:raise PermissionError('Agent grant is unknown')
    current(db,row,envelope,observed,check_quota=check_quota)
    return row


def consume(db,row,envelope,observed):
    """Record one reserved attempt after all admission checks have passed."""
    db.execute('UPDATE agent_grants SET used=used+1,updated=? WHERE id=?',(observed.isoformat(),row['id']))
    audit(db,row['app_id'],'agent_grant.admitted',dict(grant_id=row['id'],agent_id=row['agent_id'],operation=envelope['operation'],attempt=row['used']+1))
    return dict(grant_id=row['id'],agent_id=row['agent_id'],attempt=row['used']+1)


class Grants:
    """Serialize delegation changes and admissions without granting human identity."""
    def __init__(self,store,clock=None):
        self.store=store
        self.clock=clock or (lambda:datetime.now(timezone.utc))

    def issue(self,app_id,user,body):
        """The HTTP adapter must supply its freshly verified owner, never a body identity."""
        observed=self.clock();issue_data(body,observed)
        token='wmmg_'+secrets.token_urlsafe(32)
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE')
            owner=member(db,app_id,user['principal'],'OWNER')
            version,app_hash=app_scope(db,app_id)
            if type(body['manifest_version']) is not int or body['manifest_version']!=version:
                raise Invalid('App version changed before grant issuance')
            stamp=observed.isoformat();identity=uid()
            row=dict(id=identity,app_id=app_id,agent_id=body['agent_id'],owner=user['principal'],owner_version=owner['version'],
                app_version=version,app_hash=app_hash,operations=canonical(sorted(body['operations'])),token_hash=token_digest(token),
                expires=iso_time(body['expires']).isoformat(),max_calls=body['max_calls'],used=0,status='ACTIVE',version=1,created=stamp,updated=stamp)
            db.execute('INSERT INTO agent_grants VALUES('+','.join('?' for _ in row)+')',tuple(row.values()))
            agent_review_policy.save(db,identity,body)
            audit(db,app_id,'agent_grant.issued',dict(grant_id=identity,agent_id=body['agent_id'],owner=user['principal']))
        return dict(grant=dict(public(row),review_operations=agent_review_policy.validate(body)),token=token,token_delivery='ONCE_ONLY')

    def list(self,app_id,user):
        """Owner-only operational metadata; snapshot imports cannot create grants."""
        with connection(self.store.path) as db:
            member(db,app_id,user['principal'],'OWNER')
            return dict(grants=[dict(public(row),review_operations=agent_review_policy.operations(db,row['id'])) for row in db.execute('SELECT * FROM agent_grants WHERE app_id=? ORDER BY created,id',(app_id,))])

    def revoke(self,app_id,user,body):
        """Block future admissions with exact optimistic revision; do not claim cancellation."""
        exact_keys(body,('id','version'))
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE');member(db,app_id,user['principal'],'OWNER')
            row=db.execute('SELECT * FROM agent_grants WHERE app_id=? AND id=?',(app_id,body['id'])).fetchone()
            if not row or type(body['version']) is not int or row['version']!=body['version']:
                raise Invalid('Grant revision changed; reload')
            db.execute("UPDATE agent_grants SET status='REVOKED',version=version+1,updated=? WHERE id=?",(self.clock().isoformat(),body['id']))
            audit(db,app_id,'agent_grant.revoked',dict(grant_id=body['id'],owner=user['principal']))
            return public(db.execute('SELECT * FROM agent_grants WHERE id=?',(body['id'],)).fetchone())

    def admit(self,token,envelope):
        """Consume one attempt atomically; a later business failure does not refund it."""
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE')
            row=authenticated(db,token,envelope,self.clock())
            agent_review_policy.ordinary_dispatch(db,row['id'],envelope['operation'])
            return consume(db,row,envelope,self.clock())
