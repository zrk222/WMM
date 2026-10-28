"""Owner-approved native inference over the shared source-bound draft contract.

The shared public HTTPS transport pins DNS/TLS and refuses redirects. Only
configured API profiles run here; desktop CLI/subscription routes never execute.
"""
import time
from .common import Invalid, canonical, now
from .db import connection
from .ios_bridge import decode_document, encode_response


class NativeInference:
    def __init__(self,service,identities,vault_callback,transport=None,clock=time.time):
        self.service=service;self.identities=identities;self.vault_callback=vault_callback
        self.transport=transport;self.clock=clock

    def call(self,session,app_id,action,payload):
        from .operation_authority import bound_owner,protected
        from .agent_tasks import proposal,AgentWork
        from .store import audit
        body=decode_document(payload)
        fields={'prepare':{'task','focus','connection_id'},'start':{'task','focus','connection_id','source_hash','request_key','confirm_transmission'},
                'run':{'id'},'read':{'id'},'history':set(),'mode':{'version','confirm_api_mode'}}
        if action not in fields or not isinstance(body,dict) or set(body)!=fields[action]:
            raise Invalid('Use an exact native inference action')
        user=self.identities.fresh(session)
        envelope=dict(app_id=app_id,operation='native.inference.'+action,input=body)
        with bound_owner(self.service.store,envelope,self.identities,session,user):
            with protected(self.service.store,envelope):
                if action=='mode':
                    from .agent_access import AgentAccess
                    if body['confirm_api_mode'] is not True:raise Invalid('Confirm switching this app to API mode and clearing prior routes')
                    result=AgentAccess(self.service.store).routes(app_id,dict(version=body['version'],mode='byok',routes={}))
                elif action=='prepare':
                    result=proposal(self.service.store,app_id,body)
                    self.supported(result['proposal']['provider'])
                    from .agent_access import AgentAccess
                    profile=AgentAccess(self.service.store).get(app_id,result['proposal']['connection_id'])
                    result['destination']=profile['data']['endpoint']
                elif action=='start':
                    if body['confirm_transmission'] is not True:raise Invalid('Approve the exact reviewed prompt and provider charge scope')
                    original={key:body[key] for key in fields['start']-{'confirm_transmission'}}
                    prepared=proposal(self.service.store,app_id,{key:body[key] for key in fields['prepare']})
                    self.supported(prepared['proposal']['provider'])
                    def bind_owner(db,job):
                        audit(db,app_id,'native.inference.approved',dict(id=job['id'],owner=user['principal']))
                    result=AgentWork(self.service.store,on_start=bind_owner).start(app_id,original)
                    with connection(self.service.store.path) as db:self.owned(db,app_id,user,result['id'])
                elif action=='history':
                    with connection(self.service.store.path) as db:
                        rows=db.execute("SELECT j.id,j.status,j.created,j.updated,json_extract(j.data,'$.envelope.task') AS task FROM jobs j WHERE j.app_id=? AND j.action='agent_run' AND EXISTS (SELECT 1 FROM audit a WHERE a.app_id=j.app_id AND a.action='native.inference.approved' AND json_extract(a.detail,'$.id')=j.id AND json_extract(a.detail,'$.owner')=?) ORDER BY j.created DESC LIMIT 100",(app_id,user['principal'])).fetchall()
                        result=dict(items=[dict(row) for row in rows])
                elif action=='read':
                    from .worker import json_job
                    with connection(self.service.store.path) as db:result=json_job(self.owned(db,app_id,user,body['id']))
                else:result=self.run(app_id,user,body['id'])
        return encode_response(result)

    @staticmethod
    def supported(provider):
        from .ios_provider_access import NativeProviderAccess
        if provider not in NativeProviderAccess.SUPPORTED:
            raise Invalid('This native inference host supports configured HTTPS API profiles only')

    def owned(self,db,app_id,user,identity):
        row=db.execute("SELECT * FROM jobs WHERE app_id=? AND id=? AND action='agent_run'",(app_id,identity)).fetchone()
        proof=db.execute("SELECT 1 FROM audit WHERE app_id=? AND action='native.inference.approved' AND json_extract(detail,'$.id')=? AND json_extract(detail,'$.owner')=?",
                         (app_id,identity,user['principal'])).fetchone()
        if row is None or proof is None:raise PermissionError('Use an inference request approved by this native owner')
        return row

    def run(self,app_id,user,identity):
        from .worker import json_job
        from .agent_tasks import execute,complete,guard
        from .agent_access import AgentAccess,target
        from .ios_provider_access import NativeVault
        from .workflow_telemetry import append
        store=self.service.store
        with connection(store.path) as db:
            db.execute('BEGIN IMMEDIATE')
            row=self.owned(db,app_id,user,identity)
            if row['status'] not in ('QUEUED','RUNNING'):return json_job(row)
            if row['status']=='RUNNING':
                if row['lease']>self.clock():raise Invalid('Inference still has a live lease; inspect before recovery')
                # An interrupted model request may already have consumed allowance.
                # Record uncertainty instead of resending the approved request.
                result=dict(status='RECONCILE_REQUIRED',external_execution='MODEL_REQUEST_MAY_HAVE_OCCURRED',
                    publication='NOT_RUN',next_action='Inspect provider usage; approve a new request only if needed')
                db.execute("UPDATE jobs SET status='UNKNOWN',lease=0,result=?,updated=? WHERE id=?",(canonical(result),now(),identity))
                return json_job(db.execute('SELECT * FROM jobs WHERE id=?',(identity,)).fetchone())
            job=json_job(row);self.supported(job['data']['envelope']['provider'])
            guard(store,app_id,job['data']['envelope'])
            db.execute("UPDATE jobs SET status='RUNNING',attempts=1,lease=?,updated=? WHERE id=?",(self.clock()+60,now(),identity))
            job=json_job(db.execute('SELECT * FROM jobs WHERE id=?',(identity,)).fetchone())
            append(db,job,'STARTED')
        prefix=target(store,app_id,'placeholder').rsplit('/',1)[0]+'/'
        access=AgentAccess(store,vault_factory=lambda:NativeVault(self.vault_callback,prefix))
        try:
            result=execute(store,job,access=access,transport=self.transport)
            status='SUCCEEDED'
        except Exception:
            # No raw provider exception, prompt echo or credential enters a receipt.
            result=dict(status='RECONCILE_REQUIRED',external_execution='MODEL_REQUEST_MAY_HAVE_OCCURRED',
                        publication='NOT_RUN',next_action='Inspect the provider and current source context before approving another request')
            status='UNKNOWN'
        with connection(store.path) as db:
            db.execute('BEGIN IMMEDIATE')
            current=self.owned(db,app_id,user,identity)
            if current['status']!='RUNNING' or current['attempts']!=1:raise Invalid('Inference job changed before result commit')
            if status=='SUCCEEDED':guard(store,app_id,job['data']['envelope'])
            db.execute('UPDATE jobs SET status=?,lease=0,result=?,updated=? WHERE id=?',(status,canonical(result),now(),identity))
            complete(db,job,result,status)
            append(db,job,'SUCCEEDED' if status=='SUCCEEDED' else 'BLOCKED')
            return json_job(db.execute('SELECT * FROM jobs WHERE id=?',(identity,)).fetchone())
