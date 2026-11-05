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


def validate_grant_operations(names):
    if not isinstance(names,list) or not names or any(not isinstance(name,str) or name not in OPERATIONS for name in names):
        raise Invalid('Select only fixed local operation names')
    if set(names)&{'experiment.schedule','experiment.schedule-run'}:
        raise Invalid('Experiment monitoring requires a verified owner')
    if len(names)!=len(set(names)):raise Invalid('Grant operations must be unique')


def issue_data(body,observed):
    """Validate a finite exact operation scope and owner-selected lifetime/quota."""
    exact_keys(body,('agent_id','manifest_version','operations','expires','max_calls'),('review_operations','extended_expiry_consent'))
    path_segment(body['agent_id'])
    validate_grant_operations(body['operations'])
    agent_review_policy.validate(body)
    if type(body['max_calls']) is not int or not 1<=body['max_calls']<=10000:
        raise Invalid('Use a call ceiling from 1 through 10000')
    if 'extended_expiry_consent' in body and type(body['extended_expiry_consent']) is not bool:
        raise Invalid('Expiry consent must be an explicit boolean')
    from .authority_expiry import deadline
    deadline(body['expires'], observed, body.get('extended_expiry_consent'))


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
    if envelope['operation'] in ('experiment.schedule','experiment.schedule-run'):
        raise PermissionError('Experiment monitoring requires a verified owner')
    from .authority_expiry import effective_expiry
    expiry=effective_expiry(db,'AGENT_GRANT',row,row['expires'])['expires']
    if row['status']!='ACTIVE' or iso_time(expiry)<=observed:
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


def _batch_input(body,operation,plan_hash):
    if (operation!='creative.batch.create' or not isinstance(body,dict) or set(body)!={'plan','plan_hash','request_key'}
            or not isinstance(body['plan'],str) or body['plan_hash']!=plan_hash):
        raise PermissionError('Batch plan or expiry differs from the admitted request')


def _batch_request(envelope,operation,plan_hash,expires):
    body=envelope.get('input')
    _batch_input(body,operation,plan_hash)
    from .operator_client import strict_json
    try:plan=strict_json(body['plan'].encode('utf-8'))
    except (Invalid,UnicodeError):raise PermissionError('Batch plan is not canonical JSON') from None
    if (not isinstance(plan,dict) or canonical(plan)!=body['plan']
            or digest(plan)!=plan_hash or plan.get('expires')!=expires):
        raise PermissionError('Batch plan or expiry differs from the admitted request')


def _batch_envelope(store,app_id,operation,plan_hash,expires):
    from .operation_authority import PROTECTED,store_identity
    context=PROTECTED.get()
    if not context or context.get('store')!=store_identity(store):raise PermissionError('Protected batch admission is required')
    envelope=json.loads(context['envelope'])
    if envelope['app_id']!=app_id or envelope['operation']!=operation or not re.fullmatch('[a-f0-9]{64}',plan_hash or ''):
        raise PermissionError('Batch admission does not match the exact plan')
    _batch_request(envelope,operation,plan_hash,expires)
    return context,envelope


def _capture_standing_batch(db,result,deadline):
    from .automation_execution import execution_row, execution_deadline
    from .ios_agent_media import execution_hash
    from .authority_expiry import effective_expiry,initial_base
    row=execution_row(db,result['execution_id'])
    if deadline>execution_deadline(db,row):raise PermissionError('Batch deadline exceeds its standing execution')
    policy=db.execute('SELECT * FROM automation_policies WHERE id=?',(row['policy_id'],)).fetchone()
    proposal=json.loads(policy['proposal'])
    base=initial_base(proposal['limits']['expires'],policy['created'],proposal.get('extended_expiry_consent'))
    proof=effective_expiry(db,'AUTOMATION',policy,base)
    if deadline>iso_time(proof['expires']):raise PermissionError('Batch deadline exceeds standing approval')
    result['policy_consent_revision']=proof['revision']
    result['policy_consent_hash']=proof['receipt_hash']
    result['execution_hash']=execution_hash(row)


def capture_batch_authority(db,store,app_id,operation,plan_hash,expires):
    """Capture finite, secret-free provenance only from an exact protected admission."""
    from .operation_authority import check
    observed=datetime.now(timezone.utc);deadline=iso_time(expires)
    context,envelope=_batch_envelope(store,app_id,operation,plan_hash,expires)
    if not observed<deadline:raise Invalid('Batch authority must have a future expiry')
    check(db,context)
    version,app_hash=app_scope(db,app_id)
    result=dict(schema='growth.batch-authority.v1',app_id=app_id,operation=operation,plan_hash=plan_hash,
                envelope_hash=digest(envelope),expires=deadline.isoformat(),app_version=version,app_hash=app_hash)
    if 'grant_id' not in context:
        if deadline>observed+timedelta(hours=24):raise Invalid('Owner batch authority remains limited to 24 hours')
        result.update(kind='OWNER',principal=context['principal'],role_version=context['role_version'])
        return result
    grant=db.execute('SELECT * FROM agent_grants WHERE id=?',(context['grant_id'],)).fetchone()
    from .authority_expiry import effective_expiry
    grant_proof=effective_expiry(db,'AGENT_GRANT',grant,grant['expires'])
    if deadline>iso_time(grant_proof['expires']):raise PermissionError('Batch deadline exceeds the source grant')
    result.update(kind='AGENT',grant_id=grant['id'],grant_version=grant['version'],agent_id=grant['agent_id'],
                  attempt=context['attempt'],review=context['review'],execution_id=context.get('execution_id'),
                  native_host_required=context.get('host_check') is not None,
                  grant_consent_revision=grant_proof['revision'],grant_consent_hash=grant_proof['receipt_hash'])
    if result['execution_id']:
        _capture_standing_batch(db,result,deadline)
    return result


def check_batch_authority(db,store,app_id,reference,plan_hash):
    """Recheck retained owner, grant, checkpoint and standing scope without reviving a session."""
    from .review_access import exact_role
    observed=datetime.now(timezone.utc)
    if (not isinstance(reference,dict) or reference.get('schema')!='growth.batch-authority.v1'
            or reference.get('app_id')!=app_id or reference.get('plan_hash')!=plan_hash
            or iso_time(reference.get('expires'))<=observed
            or app_scope(db,app_id)!=(reference.get('app_version'),reference.get('app_hash'))):
        raise PermissionError('Batch authority changed or expired')
    if reference.get('kind')=='OWNER':
        exact_role(db,app_id,reference['principal'],reference['role_version'],'OWNER')
        return
    if reference.get('kind')!='AGENT':raise PermissionError('Unknown batch authority')
    row=db.execute('SELECT * FROM agent_grants WHERE id=?',(reference.get('grant_id'),)).fetchone()
    if not row or row['version']!=reference.get('grant_version') or row['agent_id']!=reference.get('agent_id'):
        raise PermissionError('Batch source grant changed')
    current(db,row,dict(app_id=app_id,operation=reference['operation']),observed,check_quota=False)
    if reference.get('native_host_required'):
        from .ios_host import NativeIdentities
        from .operation_authority import PROTECTED,check,store_identity
        host=PROTECTED.get()
        if (not host or not isinstance(host.get('identities'),NativeIdentities) or host.get('store')!=store_identity(store)
                or host.get('principal')!=row['owner'] or json.loads(host['envelope']).get('app_id')!=app_id):
            raise PermissionError('Fresh native owner and host verification are required')
        check(db,host)
    if type(reference.get('attempt')) is not int or not 1<=reference['attempt']<=row['used']:
        raise PermissionError('Batch source admission is unavailable')
    review=reference.get('review')
    if review is None:
        agent_review_policy.ordinary_dispatch(db,row['id'],reference['operation'])
    else:
        from .agent_review_dispatch import saved_request
        from .agent_checkpoints import read_row,current as checkpoint_current
        request=saved_request(db,app_id,review['id']);checkpoint=read_row(db,app_id,review['id'])
        if (request['grant_id']!=row['id'] or request['input_hash']!=review['input_hash']
                or digest(request['envelope'])!=reference['envelope_hash'] or checkpoint['state']!='SUCCEEDED'
                or checkpoint['hash']!=review['packet_hash'] or checkpoint['packet']['input_hash']!=request['input_hash']
                or checkpoint['packet']['agent_id']!=row['agent_id']):
            raise PermissionError('Batch review is no longer current')
        checkpoint_current(db,checkpoint,observed)
    identity=reference.get('execution_id')
    policy=db.execute('SELECT id FROM automation_policies WHERE grant_id=?',(row['id'],)).fetchone()
    if identity:
        from .automation_execution import execution_row
        from .ios_agent_media import execution_hash
        from .complete_automation import checked_policy,ACCESS_VERIFIER
        if reference.get('native_host_required') and not callable(ACCESS_VERIFIER.get()):
            raise PermissionError('Fresh native protected-access verification is required')
        execution=execution_row(db,identity)
        if (not policy or policy['id']!=execution['policy_id'] or execution['status']!='SUCCEEDED'
                or execution['grant_id']!=row['id'] or execution_hash(execution)!=reference.get('execution_hash')):
            raise PermissionError('Batch standing execution requires reconciliation')
        checked,_=checked_policy(db,execution['policy_id'],observed)
        if checked['version']!=execution['policy_version']:raise PermissionError('Batch standing authority changed')
    elif policy:
        raise PermissionError('Batch standing execution provenance is unavailable')


def _batch_review_pending(db,reference):
    review=reference.get('review')
    if isinstance(review,dict):
        row=db.execute('SELECT data FROM agent_checkpoints WHERE app_id=? AND id=?',(reference.get('app_id'),review.get('id'))).fetchone()
        if row:
            try:
                if json.loads(row['data']).get('state')=='RUNNING':return True
            except (ValueError,TypeError,AttributeError):pass
    identity=reference.get('execution_id')
    if identity:
        row=db.execute('SELECT status FROM automation_executions WHERE id=?',(identity,)).fetchone()
        if row and row['status']=='DISPATCHED':return True
    return False


def batch_authority_pending(db,reference):
    """Defer a queued child while its exact parent is still completing; grants no authority."""
    if not isinstance(reference,dict) or reference.get('kind')!='AGENT':return False
    try:
        if iso_time(reference.get('expires'))<=datetime.now(timezone.utc):return False
    except (Invalid,TypeError,ValueError):return False
    grant=db.execute('SELECT * FROM agent_grants WHERE id=?',(reference.get('grant_id'),)).fetchone()
    if not grant or grant['status']!='ACTIVE' or grant['version']!=reference.get('grant_version'):return False
    try:
        from .authority_expiry import effective_expiry
        if iso_time(effective_expiry(db,'AGENT_GRANT',grant,grant['expires'])['expires'])<=datetime.now(timezone.utc):return False
    except (Invalid,TypeError,ValueError):return False
    return _batch_review_pending(db,reference)


def issue_in_db(db,app_id,user,body,observed,token):
    """Issue inside an existing owner transaction, allowing atomic policy attachment."""
    issue_data(body,observed)
    owner=member(db,app_id,user['principal'],'OWNER')
    version,app_hash=app_scope(db,app_id)
    if type(body['manifest_version']) is not int or body['manifest_version']!=version:raise Invalid('App version changed before grant issuance')
    stamp=observed.isoformat();identity=uid()
    from .authority_expiry import record_initial
    requested=iso_time(body['expires']).astimezone(timezone.utc)
    base=min(requested,observed+timedelta(hours=24))
    row=dict(id=identity,app_id=app_id,agent_id=body['agent_id'],owner=user['principal'],owner_version=owner['version'],
        app_version=version,app_hash=app_hash,operations=canonical(sorted(body['operations'])),token_hash=token_digest(token),
        expires=base.isoformat(),max_calls=body['max_calls'],used=0,status='ACTIVE',version=1,created=stamp,updated=stamp)
    db.execute('INSERT INTO agent_grants VALUES('+','.join('?' for _ in row)+')',tuple(row.values()))
    agent_review_policy.save(db,identity,body)
    record_initial(db,'AGENT_GRANT',row,row['expires'],requested.isoformat(),user['principal'],owner['version'],body,observed)
    audit(db,app_id,'agent_grant.issued',dict(grant_id=identity,agent_id=body['agent_id'],owner=user['principal']))
    return dict(grant=dict(public(row),expires=requested.isoformat(),review_operations=agent_review_policy.validate(body)),token=token,token_delivery='ONCE_ONLY')


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
            result=issue_in_db(db,app_id,user,body,self.clock(),token)
        return result

    def list(self,app_id,user):
        """Owner-only operational metadata; snapshot imports cannot create grants."""
        with connection(self.store.path) as db:
            member(db,app_id,user['principal'],'OWNER')
            from .authority_expiry import effective_expiry
            grants=[]
            for row in db.execute('SELECT * FROM agent_grants WHERE app_id=? ORDER BY created,id',(app_id,)):
                try:proof=effective_expiry(db,'AGENT_GRANT',row,row['expires'])
                except PermissionError:proof=dict(expires=None,revision=None)
                grants.append(dict(public(row),permission_expires_at=proof['expires'],
                                   consent_revision=proof['revision'],review_operations=agent_review_policy.operations(db,row['id'])))
                if proof['expires'] is not None:grants[-1]['expires']=proof['expires']
            return dict(grants=grants)

    def authority_status(self,grant_id,app_id):
        """Return current, secret-free grant facts after an authenticated admission."""
        from .authority_expiry import effective_expiry
        with connection(self.store.path) as db:
            row=db.execute('SELECT * FROM agent_grants WHERE id=? AND app_id=?',(grant_id,app_id)).fetchone()
            if not row:raise PermissionError('Agent grant is unavailable')
            names=json.loads(row['operations'])
            if not names:raise PermissionError('Agent grant has no operations')
            current(db,row,dict(app_id=app_id,operation=names[0]),self.clock(),check_quota=False)
            proof=effective_expiry(db,'AGENT_GRANT',row,row['expires'])
            return dict(grant_id=row['id'],effective_expires=proof['expires'],used=row['used'],
                        max_calls=row['max_calls'],remaining_calls=max(0,row['max_calls']-row['used']),
                        consent_revision=proof['revision'])

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
            from .complete_automation import reserve
            execution=reserve(db,self.store,row,envelope,self.clock())
            result=consume(db,row,envelope,self.clock())
            return dict(result,automation_execution_id=execution) if execution else result
