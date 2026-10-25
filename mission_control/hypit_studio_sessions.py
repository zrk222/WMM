"""Long-lived owned Studio objects with per-call protected authority and recovery."""
from contextlib import contextmanager
from contextvars import ContextVar
import json
import threading
import time
from .common import Invalid,canonical,digest
from .db import connection
from .operation_authority import protected,PROTECTED
from .automation_execution import ACTIVE
from .operation_outcome import EffectUncertain
from .hypit_studio_factory import Factory,source
from .hypit_studio_registry import Registry
from .hypit_parameter_broker import ParameterBroker

CALL=ContextVar('wmm_owned_studio_call',default=None)
FIELDS={'plan':{'source_job_id','manifest_version'},
        'start':{'source_job_id','manifest_version','summary_hash','request_key'},
        'sessions':set(),'read':set(),'inspect':set(),'close':set(),
        'edit':{'request_key','base_version','base_hash','parameter'}}


def envelope_data(value):
    if type(value) is not dict or not {'app_id','operation','input'}<=set(value):raise Invalid('Use exact Studio operation fields')
    operation=value['operation']
    if type(operation) is not str or not operation.startswith('studio.'):raise Invalid('Use a fixed Studio operation')
    action=operation[7:]
    if action not in FIELDS:raise Invalid('Studio operation is unavailable')
    resource=action in ('read','edit','inspect','close')
    allowed={'app_id','operation','input'}|({'resource_id'} if resource else set())
    if set(value)!=allowed or type(value['input']) is not dict or set(value['input'])!=FIELDS[action]:
        raise Invalid('Use the exact Studio operation envelope')
    return action,json.loads(canonical(value))


class Manager:
    def __init__(self,store):
        self.store=store;self.registry=Registry(store);self.factory=Factory(store)
        self.condition=threading.Condition();self.objects={};self.pending={};self.active=0;self.stopping=False

    @contextmanager
    def admission(self):
        with self.condition:
            if self.stopping:raise PermissionError('Studio service is stopping; no new operations are admitted')
            self.active+=1
        try:yield
        finally:
            with self.condition:self.active-=1;self.condition.notify_all()

    @contextmanager
    def call(self,envelope,identity):
        token=CALL.set(dict(manager=self,envelope=envelope,id=identity))
        try:yield
        finally:CALL.reset(token)

    def check(self):
        if self.stopping:raise PermissionError('Studio service is stopping')
        with connection(self.store.path):pass

    def live(self,app_id,identity,intent):
        context=CALL.get()
        if not context or context['manager'] is not self or context['id']!=identity or context['envelope']['app_id']!=app_id:
            raise PermissionError('Current selected Studio request is required')
        self.check()
        value=source(self.store,app_id,intent['source_job_id'],intent['manifest_version'])
        if (value['app_hash'],value['source_hash'])!=(intent['app_hash'],intent['source_hash']):
            raise PermissionError('Studio original source context changed')

    def callback(self,app_id,identity,intent,action,scope):
        self.live(app_id,identity,intent);context=CALL.get();envelope=context['envelope']
        expected=envelope['operation'][7:]
        body=envelope['input'] if expected=='edit' else {}
        if action!=expected or scope['app_id']!=app_id or scope['project_id']!=identity or scope['request']!=body:
            raise PermissionError('Studio callback differs from the admitted operation')
        with protected(self.store,envelope) as actor:return actor

    def dispatch(self,value):
        action,envelope=envelope_data(value)
        with self.admission(),protected(self.store,envelope):
            app_id=envelope['app_id'];body=envelope['input']
            if action=='plan':return self.factory.plan(app_id,body,self.check)
            if action=='sessions':return self.sessions(app_id)
            if action=='start':return self.start(envelope)
            return self.selected(envelope,action)

    def sessions(self,app_id):
        rows=self.registry.list(app_id)
        with self.condition:
            for row in rows:
                row['owned_object_present']=row['id'] in self.objects
                if not row['owned_object_present'] and row['state']!='CLOSED':row['recovery']='INSPECTION_REQUIRED_NO_NATIVE_ADOPTION'
        return dict(items=rows,public_reconciliation='NOT_IMPLEMENTED')

    def start(self,envelope):
        app_id=envelope['app_id'];body=envelope['input']
        plan=self.factory.plan(app_id,{k:body[k] for k in ('source_job_id','manifest_version')},self.check)
        if plan['summary_hash']!=body['summary_hash']:raise Invalid('Review the current Studio execution summary')
        row=self.registry.reserve(app_id,body['request_key'],plan['intent'])
        if not row['launch_allowed']:
            return self.retained_start(row)
        entry=dict(row=row,lock=threading.RLock(),session=None,broker=None)
        with self.condition:self.objects[row['id']]=entry
        with entry['lock'],self.call(envelope,row['id']):
            try:
                alive=lambda:self.live(app_id,row['id'],row['intent'])
                entry['session']=self.factory.create(app_id,row['id'],row['version'],alive)
                entry['broker']=ParameterBroker(self.store,app_id,row['id'],entry['session'],
                    lambda action,scope:self.callback(app_id,row['id'],row['intent'],action,scope))
                result=entry['broker'].start();self.live(app_id,row['id'],row['intent'])
                entry['row']=self.registry.transition(app_id,row['id'],row['version'],'ACTIVE')
                return dict(session=entry['row'],**result)
            except BaseException as error:
                self.cleanup(entry)
                if isinstance(error,Exception):raise EffectUncertain() from None
                raise

    def retained_start(self,row):
        if row['state'] not in ('ACTIVE','CLOSED'):raise EffectUncertain()
        with self.condition:present=row['id'] in self.objects
        if row['state']=='ACTIVE' and not present:raise EffectUncertain()
        return dict(session=row,execution='NOT_RESTARTED')

    def selected(self,envelope,action):
        app_id=envelope['app_id'];identity=envelope['resource_id']
        row=self.registry.read(app_id,identity)
        with self.condition:entry=self.objects.get(identity)
        if entry is None:
            if row['state']=='CLOSED':return dict(session=row,execution='NO_NATIVE_OBJECT')
            raise EffectUncertain()
        with entry['lock'],self.call(envelope,identity):
            if entry['row']['state']=='CLOSED':
                return dict(session=entry['row'],execution='NO_NATIVE_OBJECT')
            if action=='close':
                self.check()
                result=self.cleanup(entry,raise_unknown=True)
                try:self.check()
                except Exception:raise EffectUncertain() from None
                return result
            if entry['broker'] is None:raise EffectUncertain()
            return self.broker_call(entry,envelope,action)

    def broker_call(self,entry,envelope,action):
        try:
            result=getattr(entry['broker'],action)(envelope['input']) if action=='edit' else getattr(entry['broker'],action)()
            if action=='edit' and result.get('attempt',{}).get('status') in ('PREPARED','UNCERTAIN'):
                raise EffectUncertain()
            return dict(session=entry['row'],**result)
        except EffectUncertain:
            self.record(entry,'UNKNOWN');raise

    def record(self,entry,state,proof=None):
        """Fixed outcome persistence only; cannot invoke native or caller code here."""
        if state not in ('UNKNOWN','CLEANUP_REQUIRED','CLOSED'):raise Invalid('Recovery cannot grant active execution')
        row=entry['row'];protected_token=PROTECTED.set(None);standing_token=ACTIVE.set(None)
        try:
            value=self.registry.transition(row['app_id'],row['id'],row['version'],state,proof)
            entry['row']=value
            with self.condition:self.pending.pop(row['id'],None)
            return True
        except Exception:
            with self.condition:self.pending[row['id']]=dict(state=state,persistence='UNCONFIRMED')
            return False
        finally:
            ACTIVE.reset(standing_token);PROTECTED.reset(protected_token)

    def cleanup(self,entry,raise_unknown=False):
        """Only held actual objects can stop native resources, even after revocation."""
        if entry['row']['state']=='CLOSED':
            return dict(session=entry['row'],execution='OWNED_CLEANUP_ALREADY_CONFIRMED')
        stopped=self.stop_owned(entry['session'])
        state='CLOSED' if stopped else 'CLEANUP_REQUIRED'
        proof=dict(kind='OWNED_CLEANUP',child='STOPPED',worker='STOPPED',
            evidence_hash=digest(dict(session_id=entry['row']['id'],child='STOPPED',worker='STOPPED'))) if stopped else None
        retained=self.record(entry,state,proof)
        if stopped and retained:
            with self.condition:self.objects.pop(entry['row']['id'],None)
            return dict(session=entry['row'],execution='OWNED_CLEANUP_CONFIRMED')
        if raise_unknown:raise EffectUncertain()
        return dict(session=entry['row'],execution='CLEANUP_OR_PERSISTENCE_UNCONFIRMED')

    def stop_owned(self,session):
        try:
            if session is not None:
                session.close()
                child=session.process
                child_stopped=child is None or child.poll() is not None
                worker_stopped=not session.admitted or (session.cleanup_receipt or {}).get('worker')=='stopped'
                stopped=session.closed and child_stopped and worker_stopped
            else:stopped=True  # Factory creates files only; no object was returned to launch.
        except Exception:stopped=False
        return stopped

    def shutdown(self,timeout=180):
        """Stop admission, coordinate active calls, then clean only held owned objects."""
        deadline=time.monotonic()+timeout
        with self.condition:
            self.stopping=True
            while self.active and time.monotonic()<deadline:self.condition.wait(min(1,max(0,deadline-time.monotonic())))
            if self.active:return dict(shutdown='UNCONFIRMED_ACTIVE_CALLS',active=self.active)
            entries=list(self.objects.values())
        results=[]
        for entry in entries:
            with entry['lock']:results.append(self.cleanup(entry))
        with self.condition:
            return dict(shutdown='CONFIRMED' if not self.objects and not self.pending else 'CLEANUP_REQUIRED',sessions=results,persistence_pending=dict(self.pending))
