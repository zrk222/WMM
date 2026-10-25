"""Actual admitted request boundaries and transaction-time revocation rollback."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import copy
import tempfile
from pathlib import Path
import time
import unittest
from unittest.mock import patch
from mission_control import operation_authority as target
from mission_control.agent_review_dispatch import ReviewedDispatch
from mission_control.agent_checkpoints import Checkpoints
from mission_control.common import Invalid
from mission_control.db import connection
from mission_control.operator_identity import Identities
from mission_control.review_access import Access
from mission_control.automation_execution import execute_admitted
from mission_control.store import Store
from tests import test_agent_review_dispatch as reviewed
from tests import test_automation_execution as standing
from tests import test_verified_review as identities


class RequestTests(reviewed.ReviewedDispatchTests):
    # Reuse actual HTTP-backed datastore fixture, not inherited test cases.
    def test_protected_requires_request_and_exact_envelope(self):
        with self.assertRaises(PermissionError):
            with target.protected(self.store,self.input):pass
        approval=self.approve(self.prepare())
        def execute(service,envelope):
            changed=copy.deepcopy(envelope);changed['input']['id']='other'
            with self.assertRaises(PermissionError):
                with target.protected(self.store,changed):pass
            with target.protected(self.store,envelope) as actor:
                self.assertEqual(actor,'grant:'+self.issued['grant']['id'])
            return {}
        with patch('mission_control.agent_review_dispatch.execute',side_effect=execute):done=self.resume(approval)
        self.assertEqual(done['checkpoint']['state'],'SUCCEEDED')
        self.assertIsNone(target.REQUEST.get());self.assertIsNone(target.PROTECTED.get())

    def test_review_cancellation_rejects_during_protected_execution(self):
        approval=self.approve(self.prepare())
        def execute(service,envelope):
            with target.protected(self.store,envelope):
                def cancel():
                    row=self.checkpoints.inspect('sample-one','review-one')
                    self.checkpoints.cancel('sample-one','review-one',identities.OWNER['principal'],row['revision'])
                with ThreadPoolExecutor(max_workers=1) as pool:pool.submit(cancel).result(timeout=15)
                with connection(self.store.path) as db:
                    db.execute("INSERT INTO audit(app_id,action,detail,created) VALUES('sample-one','cancelled.write','{}','synthetic')")
        with patch('mission_control.agent_review_dispatch.execute',side_effect=execute):done=self.resume(approval)
        self.assertEqual(done['checkpoint']['state'],'CANCEL_REQUESTED')
        with connection(self.store.path) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM audit WHERE action='cancelled.write'").fetchone()[0],0)
        self.assertIsNone(target.REQUEST.get());self.assertIsNone(target.PROTECTED.get())

    def test_protected_authority_cannot_cross_store(self):
        issued=self.grants.issue('sample-one',identities.OWNER,dict(self.body(),review_operations=[]))
        envelope=self.envelope();admission=self.grants.admit(issued['token'],envelope)
        with tempfile.TemporaryDirectory() as temporary:
            other=Store(Path(temporary)/'other.sqlite',seed=False)
            with target.bound_agent(self.store,envelope,admission):
                with self.assertRaises(PermissionError):
                    with target.protected(other,envelope):pass
                with target.protected(self.store,envelope):
                    with self.assertRaises(PermissionError):
                        with connection(other.path):pass

    def test_review_checker_revocation_rolls_back_business_transaction(self):
        approval=self.approve(self.prepare())
        def execute(service,envelope):
            with target.protected(self.store,envelope):
                with connection(self.store.path) as db:
                    db.execute("UPDATE operator_roles SET status='REVOKED' WHERE principal=?",(identities.CHECKER['principal'],))
                    db.execute("INSERT INTO audit(app_id,action,detail,created) VALUES('sample-one','must.rollback','{}','synthetic')")
            return {}
        with patch('mission_control.agent_review_dispatch.execute',side_effect=execute):done=self.resume(approval)
        self.assertEqual(done['checkpoint']['state'],'FAILED')
        with connection(self.store.path) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM audit WHERE action='must.rollback'").fetchone()[0],0)
            self.assertEqual(db.execute('SELECT status FROM operator_roles WHERE principal=?',(identities.CHECKER['principal'],)).fetchone()[0],'ACTIVE')

    def test_ordinary_grant_current_checks_do_not_consume_quota(self):
        issued=self.grants.issue('sample-one',identities.OWNER,dict(self.body(),review_operations=[],max_calls=1))
        envelope=self.envelope()
        admission=self.grants.admit(issued['token'],envelope)
        with target.bound_agent(self.store,envelope,admission):
            with target.protected(self.store,envelope):
                with connection(self.store.path) as db:
                    self.assertEqual(db.execute('SELECT used FROM agent_grants WHERE id=?',(issued['grant']['id'],)).fetchone()[0],1)
            with patch.object(target,'utc',return_value=target.utc()+timedelta(days=2)):
                with self.assertRaises(PermissionError):
                    with target.protected(self.store,envelope):pass
        self.grants.revoke('sample-one',identities.OWNER,dict(id=issued['grant']['id'],version=1))
        with target.bound_agent(self.store,envelope,admission):
            with self.assertRaises(PermissionError):
                with target.protected(self.store,envelope):pass

    def test_human_local_logout_expiry_replacement_and_role_guard(self):
        identity=Identities();session='synthetic-owner'
        identity.sessions[session]=dict(user=identities.OWNER,token='PRIVATE_SYNTHETIC',expires=time.time()+900)
        with patch('mission_control.operator_identity.github_read',side_effect=AssertionError('No provider I/O during checks')):
            with target.bound_owner(self.store,self.input,identity,session,identities.OWNER):
                with target.protected(self.store,self.input):
                    identity.logout(session)
                    with self.assertRaises(PermissionError):
                        with connection(self.store.path):pass
            for user,expires in ((identities.CHECKER,time.time()+900),(identities.OWNER,time.time()-1)):
                identity.sessions[session]=dict(user=user,token='PRIVATE_SYNTHETIC',expires=expires)
                with self.assertRaises(PermissionError):identity.local(session,identities.OWNER['principal'])
        self.assertIsNone(target.REQUEST.get());self.assertIsNone(target.PROTECTED.get())

    def test_same_principal_new_login_cannot_replace_admitted_session(self):
        identity=Identities();session='synthetic-owner'
        identity.sessions[session]=dict(user=identities.OWNER,token='PRIVATE_SYNTHETIC',expires=time.time()+900)
        with target.bound_owner(self.store,self.input,identity,session,identities.OWNER):
            identity.sessions[session]=dict(user=identities.OWNER,token='PRIVATE_REPLACEMENT',expires=time.time()+900)
            with self.assertRaises(PermissionError):
                with target.protected(self.store,self.input):pass

    def test_owner_role_revocation_before_commit_rolls_back_write(self):
        identity=Identities();session='synthetic-owner'
        identity.sessions[session]=dict(user=identities.OWNER,token='PRIVATE_SYNTHETIC',expires=time.time()+900)
        with target.bound_owner(self.store,self.input,identity,session,identities.OWNER):
            with self.assertRaises(PermissionError):
                with target.protected(self.store,self.input):
                    with connection(self.store.path) as db:
                        db.execute("UPDATE operator_roles SET status='REVOKED' WHERE principal=?",(identities.OWNER['principal'],))
                        db.execute("INSERT INTO audit(app_id,action,detail,created) VALUES('sample-one','owner.must.rollback','{}','synthetic')")
        with connection(self.store.path) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM audit WHERE action='owner.must.rollback'").fetchone()[0],0)


class StandingRequestTests(standing.StandingExecutionTests):
    def test_actual_standing_dispatch_binds_protected_authority(self):
        issued=self.activate();envelope=self.write()
        def execute(service,request):
            with target.protected(self.store,request) as actor:
                self.assertEqual(actor,'grant:'+issued['grant']['id'])
                with connection(self.store.path):pass
            return {}
        with patch('mission_control.operation_runtime.execute',side_effect=execute):self.dispatch(issued,envelope)
        self.assertEqual(self.saved(issued)[0]['status'],'SUCCEEDED')
        self.assertIsNone(target.REQUEST.get());self.assertIsNone(target.PROTECTED.get())

    def test_standing_execution_cannot_borrow_an_unbound_admission(self):
        issued=self.activate();envelope=self.write()
        def execute(service,request):
            original=target.REQUEST.get()
            token=target.REQUEST.set(dict(original,execution_id=None))
            try:
                with self.assertRaises(PermissionError):
                    with target.protected(self.store,request):pass
            finally:target.REQUEST.reset(token)
            return {}
        with patch('mission_control.operation_runtime.execute',side_effect=execute):self.dispatch(issued,envelope)
        self.assertIsNone(target.REQUEST.get());self.assertIsNone(target.PROTECTED.get())


if __name__=='__main__':unittest.main()
