"""Trusted-service bridge from scoped delegation to exact independently reviewed writes."""
from datetime import datetime,timezone
import json
from .common import Invalid,canonical,digest
from .db import connection
from .agent_grants import authenticated,consume,token_digest
from .agent_review_policy import operations
from .agent_checkpoints import prepare_in_db,claim_in_db,read_row,persist
from .operation_catalog import path_segment
from .operation_runtime import execute
from .operator_client import encode_body


def saved_request(db,app_id,identity):
    """Read only an exact app-owned request and check its frozen grant/input binding."""
    row=db.execute('SELECT * FROM agent_review_requests WHERE app_id=? AND id=?',(app_id,identity)).fetchone()
    if not row:raise Invalid('Reviewed agent request not found in this app')
    value=dict(row);value['envelope']=json.loads(value['envelope'])
    expected=digest(dict(grant_id=value['grant_id'],envelope=value['envelope']))
    if expected!=value['input_hash']:raise Invalid('Reviewed input integrity changed')
    return value


def scoped_request(db,token,app_id,identity):
    """Do not reveal request existence to a wrong token, app or replacement grant."""
    row=db.execute('SELECT r.id FROM agent_review_requests r JOIN agent_grants g ON g.id=r.grant_id WHERE r.app_id=? AND r.id=? AND g.token_hash=?',
        (app_id,identity,token_digest(token))).fetchone()
    if not row:raise PermissionError('Reviewed request is unavailable to this grant')
    return saved_request(db,app_id,identity)


def grant_for_request(db,token,request,stamp,check_quota=True):
    """A second grant with the same agent name cannot reuse this approval."""
    grant=authenticated(db,token,request['envelope'],stamp,check_quota=check_quota)
    if grant['id']!=request['grant_id']:raise PermissionError('Review belongs to a different grant')
    return grant


def request_view(db,request):
    """Include exact proposed input, current checkpoint and any durable result receipt."""
    checkpoint=read_row(db,request['app_id'],request['id'])
    if checkpoint['packet']['input_hash']!=request['input_hash']:
        raise Invalid('Checkpoint input binding changed')
    return dict(id=request['id'],envelope=request['envelope'],input_hash=request['input_hash'],
        checkpoint=checkpoint,result=json.loads(request['result']) if request['result'] else None,
        reconciliation_required=checkpoint['state'] in ('RUNNING','UNKNOWN','CANCEL_REQUESTED'))


def run_operation(service,envelope):
    """Record only known local validation failures as failed; other exceptions stay unknown."""
    try:
        value=execute(service,envelope)
    except (Invalid,PermissionError,KeyError):
        return dict(outcome='FAILED',error='LOCAL_VALIDATION_REJECTED')
    except Exception:
        return dict(outcome='UNKNOWN',error='LOCAL_RESULT_UNCONFIRMED')
    return result_receipt(value)


def result_receipt(value):
    """A write may have committed before its response fails serialization or size checks."""
    try:
        encode_body(value)
        return dict(outcome='SUCCEEDED',data=value)
    except Exception:
        return dict(outcome='UNKNOWN',error='LOCAL_RESULT_UNCONFIRMED')


class ReviewedDispatch:
    """No caller-supplied principal, replacement envelope or human approval capability."""
    def __init__(self,service,clock=None):
        self.service=service
        self.clock=clock or (lambda:datetime.now(timezone.utc))

    def prepare(self,token,identity,envelope):
        """Reserve preparation and freeze exact intent in one transaction."""
        path_segment(identity);encode_body(envelope)
        app_id=envelope.get('app_id') if isinstance(envelope,dict) else None
        with connection(self.service.store.path) as db:
            db.execute('BEGIN IMMEDIATE')
            grant=authenticated(db,token,envelope,self.clock())
            if envelope['operation'] not in operations(db,grant['id']):
                raise Invalid('This grant operation does not require a reviewed request')
            input_hash=digest(dict(grant_id=grant['id'],envelope=envelope))
            packet=dict(id=identity,agent_id=grant['agent_id'],operation=envelope['operation'],input_hash=input_hash,
                manifest_version=grant['app_version'],expires=grant['expires'])
            prepare_in_db(db,app_id,grant['owner'],packet,self.clock())
            old=db.execute('SELECT input_hash FROM agent_review_requests WHERE app_id=? AND id=?',(app_id,identity)).fetchone()
            if old and old['input_hash']!=input_hash:raise Invalid('Reviewed request identity is immutable')
            db.execute('INSERT OR IGNORE INTO agent_review_requests VALUES(?,?,?,?,?,NULL)',(app_id,identity,grant['id'],canonical(envelope),input_hash))
            consume(db,grant,envelope,self.clock())
            return request_view(db,saved_request(db,app_id,identity))

    def inspect(self,token,app_id,identity):
        """Current grant can inspect its receipt even after its call quota is exhausted."""
        with connection(self.service.store.path) as db:
            request=scoped_request(db,token,app_id,identity)
            grant_for_request(db,token,request,self.clock(),check_quota=False)
            return request_view(db,request)

    def resume(self,token,app_id,identity,revision,packet_hash):
        """Revalidate delegation and exclusively claim only the saved approved input."""
        with connection(self.service.store.path) as db:
            db.execute('BEGIN IMMEDIATE')
            request=scoped_request(db,token,app_id,identity)
            grant=grant_for_request(db,token,request,self.clock())
            view=request_view(db,request)
            if view['result'] is not None:raise Invalid('Reviewed request already has a receipt')
            claim_in_db(db,app_id,identity,grant['agent_id'],revision,packet_hash,self.clock())
            consume(db,grant,request['envelope'],self.clock())
        result=run_operation(self.service,request['envelope'])
        return self.complete(app_id,identity,grant['agent_id'],result)

    def complete(self,app_id,identity,agent_id,result):
        """Atomically retain effect receipt and cancellation-aware checkpoint transition."""
        with connection(self.service.store.path) as db:
            db.execute('BEGIN IMMEDIATE')
            request=saved_request(db,app_id,identity);checkpoint=read_row(db,app_id,identity)
            if request['result'] is not None or checkpoint['state'] not in ('RUNNING','CANCEL_REQUESTED') or checkpoint['packet']['agent_id']!=agent_id:
                raise Invalid('Only the claimed request may record its result once')
            db.execute('UPDATE agent_review_requests SET result=? WHERE app_id=? AND id=?',(canonical(result),app_id,identity))
            state='CANCEL_REQUESTED' if checkpoint['state']=='CANCEL_REQUESTED' else result['outcome']
            persist(db,checkpoint,state,agent_id,self.clock(),digest(result))
            return request_view(db,saved_request(db,app_id,identity))
