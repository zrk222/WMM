"""Actual protected owner/SQLite manager lifecycle with controlled native objects."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from types import SimpleNamespace
import copy
import threading
import time
import unittest
from unittest.mock import patch
from mission_control.common import Invalid
from mission_control.db import connection
from mission_control.operation_authority import bound_owner,REQUEST,PROTECTED
from mission_control.operation_outcome import EffectUncertain
from mission_control.operator_identity import Identities
from mission_control.review_access import Access
from mission_control import hypit_studio_sessions as target
from tests import test_hypit_studio_factory as factory_fixture
from tests.test_hypit_studio_factory import APP
from tests.test_verified_review import OWNER


class ControlledBroker:
    def __init__(self,store,app,identity,session,admit):
        self.app=app;self.id=identity;self.session=session;self.admit=admit
        self.sent=0;self.uncertain=False;self.start_entered=None;self.start_release=None

    def check(self,action,body=None):
        return self.admit(action,dict(app_id=self.app,project_id=self.id,request=body or {}))

    def start(self):
        self.check('start');self.session.started=True
        if self.start_entered:self.start_entered.set();self.start_release.wait(10)
        self.check('start')
        return dict(controls={'revision':1},source_head={'version':1})

    def read(self):self.check('read');return dict(controls={'revision':1})
    def inspect(self):self.check('inspect');return dict(attempts=[dict(status='UNCERTAIN')] if self.uncertain else [])
    def edit(self,body):
        self.check('edit',body)
        if self.uncertain:return dict(attempt=dict(status='UNCERTAIN'),execution='NOT_RESENT')
        self.sent+=1
        return dict(attempt=dict(status='APPLIED'),execution='OBSERVED')


class ObservedLock:
    """Signal the second lock attempt before it waits behind the first caller."""
    def __init__(self):
        self.lock=threading.RLock();self.guard=threading.Lock();self.count=0;self.second=threading.Event()
    def __enter__(self):
        with self.guard:
            self.count+=1
            if self.count==2:self.second.set()
        self.lock.acquire();return self
    def __exit__(self,*_):self.lock.release()


class ManagerTests(unittest.TestCase):
    def setUp(self):
        self.fixture=factory_fixture.FactoryTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.store=self.fixture.store;self.registry=self.fixture.registry
        Access(self.store).bootstrap(APP,OWNER,dict(confirm_owner=True))
        self.identities=Identities();self.token='synthetic-owner-session';self.login()
        self.manager=target.Manager(self.store);self.created=[];self.brokers=[]
        self.addCleanup(self.manager.shutdown)
        self.patchers=[patch.object(self.manager.factory,'create',side_effect=self.create),
            patch.object(target,'ParameterBroker',side_effect=self.broker)]
        for p in self.patchers:p.start();self.addCleanup(p.stop)

    def login(self):self.identities.sessions[self.token]=dict(user=OWNER,token='PRIVATE_SYNTHETIC',expires=time.time()+900)

    def envelope(self,action,body=None,identity=None):
        value=dict(app_id=APP,operation='studio.'+action,input=body or {})
        if identity is not None:value['resource_id']=identity
        return value

    def call(self,action,body=None,identity=None,manager=None):
        envelope=self.envelope(action,body,identity)
        with bound_owner(self.store,envelope,self.identities,self.token,OWNER):
            return (manager or self.manager).dispatch(envelope)

    def startup(self,key='one'):
        plan=self.call('plan',self.fixture.body)
        return dict(self.fixture.body,summary_hash=plan['summary_hash'],request_key=key)

    def create(self,app,identity,version,alive):
        self.assertEqual(self.registry.read(app,identity)['state'],'PREPARED')
        alive();session=SimpleNamespace(started=False,closed=False,admitted=True,cleanup_receipt=None)
        session.process=SimpleNamespace(poll=lambda:0 if session.closed else None)
        def close():session.closed=True;session.cleanup_receipt=dict(worker='stopped')
        session.close=close;self.created.append(session);return session

    def broker(self,*args):
        value=ControlledBroker(*args);self.brokers.append(value);return value

    def test_start_read_edit_close_and_no_startup_replay(self):
        body=self.startup();started=self.call('start',body);identity=started['session']['id']
        self.assertEqual(started['session']['state'],'ACTIVE')
        self.assertEqual(self.call('start',body)['execution'],'NOT_RESTARTED');self.assertEqual(len(self.created),1)
        self.assertEqual(self.call('read',identity=identity)['controls']['revision'],1)
        edit=dict(request_key='edit-one',base_version=1,base_hash='a'*64,parameter={'value':46})
        self.assertEqual(self.call('edit',edit,identity)['attempt']['status'],'APPLIED')
        self.assertEqual(self.call('close',identity=identity)['session']['state'],'CLOSED')
        self.assertTrue(self.created[0].closed);self.assertEqual(self.manager.objects,{})
        self.assertEqual(self.call('close',identity=identity)['execution'],'NO_NATIVE_OBJECT')
        self.assertIsNone(REQUEST.get());self.assertIsNone(PROTECTED.get());self.assertIsNone(target.CALL.get())

    def test_missing_context_and_closed_envelope_reject(self):
        with self.assertRaises(PermissionError):self.manager.dispatch(self.envelope('sessions'))
        for change in ({'pid':1},{'input':{'path':'PRIVATE'}},{'operation':'studio.unrecognized'}):
            with self.assertRaises(Invalid):self.manager.dispatch(dict(self.envelope('sessions'),**change))

    def test_source_rights_change_denies_owned_read_but_allows_admitted_close(self):
        result=self.call('start',self.startup());identity=result['session']['id']
        with patch.object(target,'source',side_effect=Invalid('Synthetic rights revoked')):
            with self.assertRaises(Invalid):self.call('read',identity=identity)
            self.assertEqual(self.call('close',identity=identity)['session']['state'],'CLOSED')

    def test_uncertain_retained_edit_returns_unknown_without_another_send(self):
        identity=self.call('start',self.startup())['session']['id'];broker=self.brokers[0]
        broker.uncertain=True
        edit=dict(request_key='same',base_version=1,base_hash='a'*64,parameter={'value':46})
        for _ in range(2):
            with self.assertRaises(EffectUncertain):self.call('edit',edit,identity)
        self.assertEqual(broker.sent,0)
        self.assertEqual(self.registry.read(APP,identity)['state'],'UNKNOWN')
        self.assertEqual(self.call('inspect',identity=identity)['attempts'][0]['status'],'UNCERTAIN')

    def test_revocation_during_start_closes_owned_object_and_retains_outcome(self):
        body=self.startup();original=ControlledBroker.start
        def revoke(broker):
            broker.check('start');broker.session.started=True;self.identities.logout(self.token)
            broker.check('start')
        with patch.object(ControlledBroker,'start',revoke):
            with self.assertRaises(EffectUncertain):self.call('start',body)
        self.assertTrue(self.created[0].closed)
        self.assertEqual(self.registry.list(APP)[0]['state'],'CLOSED')
        self.login();self.assertEqual(self.call('start',body)['execution'],'NOT_RESTARTED')

    def test_cleanup_and_finalizer_failure_keep_unresolved_capacity(self):
        result=self.call('start',self.startup());identity=result['session']['id'];entry=self.manager.objects[identity]
        with patch.object(entry['session'],'close',side_effect=OSError('PRIVATE_CLEANUP')):
            with self.assertRaises(EffectUncertain):self.call('close',identity=identity)
        self.assertEqual(self.registry.read(APP,identity)['state'],'CLEANUP_REQUIRED')
        with patch.object(self.manager.registry,'transition',side_effect=OSError('PRIVATE_STORAGE')):
            with self.assertRaises(EffectUncertain):self.call('close',identity=identity)
        self.assertEqual(self.manager.pending[identity]['persistence'],'UNCONFIRMED')
        self.assertTrue(self.registry.read(APP,identity)['capacity_reserved'])
        self.assertEqual(self.call('close',identity=identity)['session']['state'],'CLOSED')

    def test_revocation_during_close_preserves_cleanup_but_returns_unknown(self):
        identity=self.call('start',self.startup())['session']['id'];session=self.created[0];close=session.close
        def revoke_close():close();self.identities.logout(self.token)
        with patch.object(session,'close',side_effect=revoke_close):
            with self.assertRaises(EffectUncertain):self.call('close',identity=identity)
        self.assertTrue(session.closed);self.assertEqual(self.registry.read(APP,identity)['state'],'CLOSED')

    def test_restart_does_not_adopt_active_metadata_or_start_again(self):
        body=self.startup();identity=self.call('start',body)['session']['id']
        other=target.Manager(self.store)
        with patch.object(other.factory,'plan',side_effect=self.manager.factory.plan):
            with self.assertRaises(EffectUncertain):self.call('start',body,manager=other)
        with self.assertRaises(EffectUncertain):self.call('read',identity=identity,manager=other)
        listing=self.call('sessions',manager=other)['items'][0]
        self.assertEqual(listing['recovery'],'INSPECTION_REQUIRED_NO_NATIVE_ADOPTION')
        self.assertEqual(len(self.created),1)

    def test_shutdown_blocks_admission_closes_owned_and_reports_pending_work(self):
        self.call('start',self.startup())
        result=self.manager.shutdown()
        self.assertEqual(result['shutdown'],'CONFIRMED');self.assertTrue(self.created[0].closed)
        with self.assertRaises(PermissionError):self.call('sessions')

    def test_concurrent_startup_key_only_creates_one_object(self):
        body=self.startup()
        def call(_):
            try:return self.call('start',body)
            except EffectUncertain:return {'execution':'UNCONFIRMED_INFLIGHT'}
        with ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(call,range(3)))
        self.assertEqual(len(self.created),1)
        self.assertEqual(sum(r.get('session',{}).get('launch_allowed',False) for r in results),0)
        self.assertEqual(len(self.registry.list(APP)),1)

    def test_callback_cannot_borrow_another_action_or_body(self):
        identity=self.call('start',self.startup())['session']['id'];entry=self.manager.objects[identity]
        envelope=self.envelope('read',identity=identity)
        with bound_owner(self.store,envelope,self.identities,self.token,OWNER),target.protected(self.store,envelope),self.manager.call(envelope,identity):
            with self.assertRaises(PermissionError):
                self.manager.callback(APP,identity,entry['row']['intent'],'edit',dict(app_id=APP,project_id=identity,request={}))

    def test_shutdown_coordinates_inflight_start_without_holding_manager_lock(self):
        body=self.startup();entered=threading.Event();release=threading.Event()
        def start(broker):
            broker.check('start');broker.session.started=True;entered.set()
            self.assertTrue(release.wait(10));broker.check('start')
            return dict(controls={},source_head={})
        with patch.object(ControlledBroker,'start',start),ThreadPoolExecutor(max_workers=2) as pool:
            future=pool.submit(self.call,'start',body)
            self.assertTrue(entered.wait(10))
            result=self.manager.shutdown(timeout=.01)
            self.assertEqual(result['shutdown'],'UNCONFIRMED_ACTIVE_CALLS')
            # Admission/map lock remains obtainable while the native start is blocked.
            with self.manager.condition:self.assertEqual(self.manager.active,1)
            release.set()
            with self.assertRaises(EffectUncertain):future.result(timeout=10)
        self.assertEqual(self.manager.shutdown()['shutdown'],'CONFIRMED')
        self.assertTrue(self.created[0].closed)

    def test_stale_concurrent_close_entry_never_creates_unresolved_pending_state(self):
        identity=self.call('start',self.startup())['session']['id'];entry=self.manager.objects[identity]
        closed=self.call('close',identity=identity)
        with entry['lock']:again=self.manager.cleanup(entry,raise_unknown=True)
        self.assertEqual(again['execution'],'OWNED_CLEANUP_ALREADY_CONFIRMED')
        self.assertEqual(again['session']['version'],closed['session']['version'])
        self.assertEqual(self.manager.pending,{})
        self.assertEqual(self.manager.shutdown()['shutdown'],'CONFIRMED')

    def test_two_close_calls_capture_one_entry_and_only_one_terminal_transition(self):
        identity=self.call('start',self.startup())['session']['id'];entry=self.manager.objects[identity]
        entry['lock']=ObservedLock()
        entered=threading.Event();release=threading.Event();close=entry['session'].close;calls=[]
        def slow_close():
            calls.append(1);entered.set();self.assertTrue(release.wait(10));close()
        with patch.object(entry['session'],'close',side_effect=slow_close),ThreadPoolExecutor(max_workers=2) as pool:
            first=pool.submit(self.call,'close',None,identity);self.assertTrue(entered.wait(10))
            second=pool.submit(self.call,'close',None,identity)
            self.assertTrue(entry['lock'].second.wait(10));release.set()
            results=[first.result(timeout=10),second.result(timeout=10)]
        self.assertTrue(all(r['session']['state']=='CLOSED' for r in results))
        self.assertEqual(len(calls),1)
        history=self.registry.read(APP,identity)['history']
        self.assertEqual(sum(x['state']=='CLOSED' for x in history),1)
        self.assertEqual(self.manager.objects,{});self.assertEqual(self.manager.pending,{})

    def test_simultaneous_shutdown_calls_preserve_confirmed_cleanup(self):
        identity=self.call('start',self.startup())['session']['id'];session=self.created[0]
        lock=ObservedLock();self.manager.objects[identity]['lock']=lock
        entered=threading.Event();release=threading.Event();close=session.close
        def slow_close():entered.set();self.assertTrue(release.wait(10));close()
        with patch.object(session,'close',side_effect=slow_close),ThreadPoolExecutor(max_workers=2) as pool:
            first=pool.submit(self.manager.shutdown);self.assertTrue(entered.wait(10))
            second=pool.submit(self.manager.shutdown);self.assertTrue(lock.second.wait(10));release.set()
            self.assertEqual(first.result(timeout=10)['shutdown'],'CONFIRMED')
            self.assertEqual(second.result(timeout=10)['shutdown'],'CONFIRMED')
        self.assertEqual(self.registry.read(APP,identity)['state'],'CLOSED')
        self.assertEqual(self.manager.pending,{})


if __name__=='__main__':unittest.main()
