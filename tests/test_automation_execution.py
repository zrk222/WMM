"""Actual dispatcher/queue/HTTP and SQLite race checks for standing local authority."""
from concurrent.futures import ThreadPoolExecutor
import json
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from mission_control.automation_execution import ACTIVE, bound, execute_admitted, finish, start, job_execution
from mission_control.common import Invalid, canonical
from mission_control.operation_outcome import EffectUncertain
from mission_control.db import connection
from mission_control.operator_client import OperatorClient, ClientError
from mission_control.server import Server
from mission_control.service import Service
from mission_control.worker import claim, enqueue, jobs, run_once
from mission_control.store import Store
from tests import test_complete_automation as fixtures
from tests import test_verified_review as identities
from tests.test_mission_control import evidence_data


class StandingExecutionTests(fixtures.AuthorityFixture, unittest.TestCase):
    def setUp(self):
        self.setup_authority()
        self.service = Service(self.store)

    def tearDown(self):
        self.assertIsNone(ACTIVE.get())
        self.cleanup_authority()

    def dispatch(self, issued, envelope):
        admission = self.grants.admit(issued['token'], envelope)
        return execute_admitted(self.service, envelope, admission)

    def saved(self, issued):
        return next(row['executions'] for row in self.automation.status('sample-one', identities.OWNER)['policies'] if row['id'] == issued['policy_id'])

    def pipeline(self, key='standing-pipeline'):
        return self.envelope('pipeline.prepare', dict(action='pipeline', data=dict(stage=1), request_key=key))

    def write(self):
        return self.envelope('evidence.save', dict(id='standing-evidence', manifest_version=1, kind='measurement',
                             title='Synthetic scope proof', source='Synthetic fixture', data=evidence_data('measurement')))

    def test_exact_dispatch_runs_real_service_and_prevents_replay_or_changed_envelope(self):
        issued = self.activate()
        envelope = self.write()
        admission = self.grants.admit(issued['token'], envelope)
        with self.assertRaises(PermissionError):
            execute_admitted(self.service, self.envelope('growth.history'), admission)
        result = execute_admitted(self.service, envelope, admission)
        self.assertEqual(result['id'], 'standing-evidence')
        receipt = self.saved(issued)[0]
        self.assertEqual(receipt['status'], 'SUCCEEDED')
        self.assertGreaterEqual(receipt['write_commits'], 1)
        self.assertTrue(receipt['result_hash'])
        with self.assertRaises(PermissionError):
            execute_admitted(self.service, envelope, admission)
        with self.assertRaises(Invalid):
            finish(self.store, receipt['id'], result={})

    def test_call_ceiling_is_atomic_under_racing_admissions(self):
        issued = self.activate(max_calls=1)
        def attempt(_):
            try:
                self.grants.admit(issued['token'], self.envelope('growth.history'))
                return True
            except PermissionError:
                return False
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(attempt, range(8)))
        self.assertEqual(sum(results), 1)
        self.assertEqual(len(self.saved(issued)), 1)

    def test_concurrency_preserves_idempotent_queue_read_and_cancel_controls(self):
        issued = self.activate(['local_evidence', 'pipeline_preparation'])
        first = self.dispatch(issued, self.pipeline())
        replay = self.dispatch(issued, self.pipeline())
        self.assertEqual(first['id'], replay['id'])
        self.assertEqual(len(jobs(self.store, 'sample-one')), 1)
        with self.assertRaises(PermissionError):
            self.grants.admit(issued['token'], self.write())
        self.assertEqual(len(self.dispatch(issued, self.envelope('jobs.read'))), 1)
        self.dispatch(issued, self.envelope('job.cancel', resource_id=first['id']))
        self.dispatch(issued, self.pipeline('new-after-cancel'))
        self.assertEqual(len(jobs(self.store, 'sample-one')), 2)

    def test_off_between_admission_and_dispatch_prevents_any_business_effect(self):
        issued = self.activate()
        envelope = self.write()
        admission = self.grants.admit(issued['token'], envelope)
        self.off(issued)
        with self.assertRaises(PermissionError):
            execute_admitted(self.service, envelope, admission)
        self.assertFalse(self.store.records('sample-one'))
        self.assertEqual(self.saved(issued)[0]['status'], 'CANCELLED')

    def test_off_before_commit_and_credential_changes_reject_business_transaction(self):
        issued = self.activate()
        envelope = self.write()
        admission = self.grants.admit(issued['token'], envelope)
        identity = start(self.store, admission, envelope)
        with connection(self.store.path) as db:
            db.execute('UPDATE agent_connections SET version=version+1')
        with self.assertRaises(PermissionError):
            with bound(self.store, identity):
                self.service.evidence('sample-one', envelope['input'])
        self.assertFalse(self.store.records('sample-one'))
        with connection(self.store.path) as db:
            db.execute('UPDATE agent_connections SET version=1')
        self.off(issued)
        with self.assertRaises(PermissionError):
            with bound(self.store, identity):
                self.service.evidence('sample-one', envelope['input'])
        self.assertFalse(self.store.records('sample-one'))

    def test_writer_commit_and_concurrent_off_have_a_real_serialized_order(self):
        issued = self.activate()
        envelope = self.write()
        identity = start(self.store, self.grants.admit(issued['token'], envelope), envelope)
        entered = threading.Event()
        def disable():
            entered.set()
            return self.off(issued)
        with ThreadPoolExecutor(max_workers=1) as pool:
            with bound(self.store, identity):
                with connection(self.store.path) as db:
                    db.execute('BEGIN IMMEDIATE')
                    db.execute("INSERT INTO audit(app_id,action,detail,created) VALUES('sample-one','synthetic.effect','{}',?)", (self.observed.isoformat(),))
                    future = pool.submit(disable)
                    self.assertTrue(entered.wait(2))
                    self.assertFalse(future.done())
            self.assertEqual(future.result(timeout=15)['status'], 'OFF')
        with connection(self.store.path) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM audit WHERE action='synthetic.effect'").fetchone()[0], 1)
        self.assertEqual(self.saved(issued)[0]['write_commits'], 1)

    def test_off_after_connection_check_but_before_write_rolls_back_at_commit(self):
        issued = self.activate()
        envelope = self.write()
        identity = start(self.store, self.grants.admit(issued['token'], envelope), envelope)
        with self.assertRaises(PermissionError):
            with bound(self.store, identity):
                with connection(self.store.path) as db:
                    with ThreadPoolExecutor(max_workers=1) as pool:
                        pool.submit(self.off, issued).result(timeout=15)
                    db.execute("INSERT INTO audit(app_id,action,detail,created) VALUES('sample-one','forbidden.commit','{}',?)", (self.observed.isoformat(),))
        with connection(self.store.path) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM audit WHERE action='forbidden.commit'").fetchone()[0], 0)

    def test_partial_commit_then_failure_is_unknown_and_repeat_is_blocked(self):
        issued = self.activate()
        envelope = self.write()
        def partial(*_):
            with connection(self.store.path) as db:
                db.execute("INSERT INTO audit(app_id,action,detail,created) VALUES('sample-one','synthetic.partial','{}',?)", (self.observed.isoformat(),))
            raise Invalid('Synthetic lost local result after a committed write')
        with patch('mission_control.operation_runtime.execute', side_effect=partial) as dispatch:
            with self.assertRaises(Invalid):
                self.dispatch(issued, envelope)
        self.assertEqual(dispatch.call_count, 1)
        self.assertEqual(self.saved(issued)[0]['status'], 'UNKNOWN')
        with self.assertRaises(PermissionError):
            self.grants.admit(issued['token'], envelope)

    def test_failed_validation_without_commit_and_unserializable_result_are_distinct(self):
        issued = self.activate()
        with patch('mission_control.operation_runtime.execute', side_effect=Invalid('Synthetic validation failure')):
            with self.assertRaises(Invalid):
                self.dispatch(issued, self.write())
        self.assertEqual(self.saved(issued)[0]['status'], 'FAILED')
        with patch('mission_control.operation_runtime.execute', return_value=object()):
            self.dispatch(issued, self.envelope('growth.history'))
        statuses = {row['operation']: row['status'] for row in self.saved(issued)}
        self.assertEqual(statuses['growth.history'], 'UNKNOWN')

    def test_uncertain_native_effect_without_local_commit_blocks_repeat(self):
        issued=self.activate();envelope=self.write()
        with patch('mission_control.operation_runtime.execute',side_effect=EffectUncertain()) as operation:
            with self.assertRaises(EffectUncertain):self.dispatch(issued,envelope)
        self.assertEqual(operation.call_count,1)
        saved=self.saved(issued)[0]
        self.assertEqual(saved['status'],'UNKNOWN');self.assertEqual(saved['write_commits'],0)
        with self.assertRaises(PermissionError):self.grants.admit(issued['token'],envelope)

    def test_cancelled_uncertain_native_effect_remains_unknown_without_local_commit(self):
        issued=self.activate()
        def processing(*_):
            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(self.off,issued).result(timeout=15)
            raise EffectUncertain()
        with patch('mission_control.operation_runtime.execute',side_effect=processing):
            with self.assertRaises(EffectUncertain):self.dispatch(issued,self.write())
        saved=self.saved(issued)[0]
        self.assertEqual(saved['status'],'UNKNOWN');self.assertEqual(saved['write_commits'],0)

    def test_owned_job_scope_survives_reopen_and_off_preserves_unrelated_jobs(self):
        issued = self.activate(['pipeline_preparation'])
        owned = self.dispatch(issued, self.pipeline())
        unrelated = enqueue(self.store, 'sample-one', 'pipeline', dict(stage=1), 'unrelated-local-job')
        with connection(self.store.path) as db:
            self.assertEqual(db.execute('SELECT job_id FROM automation_job_scopes').fetchone()[0], owned['id'])
        self.off(issued)
        with patch('mission_control.worker.process', return_value=dict(status='SYNTHETIC_PREPARATION')) as process:
            self.assertTrue(run_once(self.store))
        self.assertEqual(process.call_args.args[1]['id'], unrelated['id'])
        statuses = {job['id']: job['status'] for job in jobs(self.store, 'sample-one')}
        self.assertEqual(statuses[owned['id']], 'CANCELLED')
        self.assertEqual(statuses[unrelated['id']], 'SUCCEEDED')

    def test_worker_revocation_during_dispatch_stops_next_write_and_keeps_receipt(self):
        issued = self.activate(['pipeline_preparation'])
        queued = self.dispatch(issued, self.pipeline())
        def processing(store, job):
            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(self.off, issued).result(timeout=15)
            with connection(store.path) as db:
                db.execute("INSERT INTO audit(app_id,action,detail,created) VALUES('sample-one','forbidden.after.off','{}',?)", (self.observed.isoformat(),))
            return {}
        with patch('mission_control.worker.process', side_effect=processing):
            self.assertTrue(run_once(self.store))
        with connection(self.store.path) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM audit WHERE action='forbidden.after.off'").fetchone()[0], 0)
        self.assertEqual(jobs(self.store, 'sample-one')[0]['status'], 'CANCELLED')
        self.assertEqual(self.saved(issued)[0]['jobs'][0]['id'], queued['id'])

    def test_worker_checks_modified_job_and_existing_legacy_job_is_not_adopted(self):
        legacy = enqueue(self.store, 'sample-one', 'pipeline', dict(stage=1), 'standing-pipeline')
        issued = self.activate(['pipeline_preparation'])
        with self.assertRaises(PermissionError):
            self.dispatch(issued, self.pipeline())
        self.assertEqual(jobs(self.store, 'sample-one')[0]['id'], legacy['id'])
        owned = self.dispatch(issued, self.pipeline('scoped-new'))
        with connection(self.store.path) as db:
            db.execute("UPDATE jobs SET status='CANCELLED' WHERE id=?", (legacy['id'],))
            db.execute('UPDATE jobs SET data=? WHERE id=?', (canonical(dict(stage=2)), owned['id']))
        with patch('mission_control.worker.process', return_value={}) as process:
            self.assertTrue(run_once(self.store))
        process.assert_not_called()
        self.assertEqual(jobs(self.store, 'sample-one')[0]['status'], 'BLOCKED')

    def test_authenticated_http_owner_activation_bearer_dispatch_and_off_share_real_service(self):
        mock = patch('mission_control.operator_identity.github_read', side_effect=identities.synthetic_identity)
        mock.start()
        server = Server(('127.0.0.1', 0), self.store)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        origin = 'http://127.0.0.1:' + str(server.server_port)
        try:
            owner = OperatorClient(origin)
            owner.bootstrap()
            owner.request('POST', '/api/identity/login', dict(token=identities.OWNER_TOKEN))
            base = '/api/apps/sample-one/agent-grants/'
            preview = owner.request('POST', base+'automation-preview', self.proposal())
            issued = owner.request('POST', base+'automation-activate', dict(proposal=preview['proposal'], summary_hash=preview['summary_hash']))
            agent = OperatorClient(origin, grant_token=issued['token'])
            result = agent.call(self.write())
            self.assertEqual(result['id'], 'standing-evidence')
            with self.assertRaises((ClientError, Invalid)):
                agent.request('POST', base+'automation-off', dict(id=issued['policy_id'], version=1))
            request = Request(origin+base+'automation-off', data=json.dumps(dict(id=issued['policy_id'], version=1)).encode(),
                              headers={'Content-Type': 'application/json', 'Origin': origin, 'Authorization': 'Bearer '+issued['token']}, method='POST')
            with self.assertRaises(HTTPError) as rejected:
                urlopen(request, timeout=15)
            self.assertIn(rejected.exception.code, (400, 401, 403))
            owner.request('POST', base+'automation-off', dict(id=issued['policy_id'], version=1))
            with self.assertRaises(ClientError):
                agent.call(self.envelope('growth.history'))
            state = owner.request('POST', base+'automation-status', {})
            self.assertEqual(state['policies'][0]['status'], 'OFF')
            self.assertNotIn(issued['token'], json.dumps(state))
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
            mock.stop()

    def test_lost_execution_cross_store_and_changed_epoch_reject_business_writes(self):
        issued = self.activate()
        envelope = self.write()
        identity = start(self.store, self.grants.admit(issued['token'], envelope), envelope)
        other = Store(self.store.path.parent/'separate.sqlite', seed=False)
        with self.assertRaises(PermissionError):
            with bound(self.store, identity):
                with connection(other.path):
                    pass
        with connection(self.store.path) as db:
            db.execute('UPDATE automation_policies SET version=2')
        with self.assertRaises(PermissionError):
            with bound(self.store, identity):
                self.service.evidence('sample-one', envelope['input'])
        with connection(self.store.path) as db:
            db.execute('DELETE FROM automation_executions')
        with self.assertRaises(PermissionError):
            with bound(self.store, identity):
                with connection(self.store.path):
                    pass
        self.assertFalse(self.store.records('sample-one'))

    def test_worker_replaced_lease_and_completed_request_cannot_reuse_context(self):
        issued = self.activate(['pipeline_preparation'])
        self.dispatch(issued, self.pipeline())
        job = claim(self.store)
        with connection(self.store.path) as db:
            db.execute('UPDATE jobs SET attempts=attempts+1 WHERE id=?', (job['id'],))
        with self.assertRaises(PermissionError):
            with job_execution(self.store, job):
                self.fail('Replaced worker must not dispatch')
        execution = self.saved(issued)[0]['id']
        with self.assertRaises(PermissionError):
            with bound(self.store, execution):
                with connection(self.store.path):
                    pass

    def test_old_policy_job_cannot_be_adopted_by_replacement_policy(self):
        first = self.activate(['pipeline_preparation'])
        self.dispatch(first, self.pipeline())
        self.off(first)
        second = self.activate(['pipeline_preparation'])
        with self.assertRaises(PermissionError):
            self.dispatch(second, self.pipeline())
        self.assertEqual(len(jobs(self.store, 'sample-one')), 1)

    def test_off_during_dispatch_retains_cancelled_or_partial_unknown_result(self):
        for writes, expected in ((False, 'CANCELLED'), (True, 'UNKNOWN')):
            issued = self.activate()
            def processing(*_):
                if writes:
                    with connection(self.store.path) as db:
                        db.execute("INSERT INTO audit(app_id,action,detail,created) VALUES('sample-one','prior.effect','{}',?)", (self.observed.isoformat(),))
                with ThreadPoolExecutor(max_workers=1) as pool:
                    pool.submit(self.off, issued).result(timeout=15)
                with connection(self.store.path) as db:
                    db.execute("INSERT INTO audit(app_id,action,detail,created) VALUES('sample-one','rejected.effect','{}',?)", (self.observed.isoformat(),))
                return {}
            with patch('mission_control.operation_runtime.execute', side_effect=processing):
                with self.assertRaises(PermissionError):
                    self.dispatch(issued, self.write())
            self.assertEqual(self.saved(issued)[0]['status'], expected)

    def test_credential_access_loss_at_admission_does_not_consume_a_call(self):
        issued = self.activate()
        self.access.side_effect = Invalid('Synthetic protected access lost')
        with self.assertRaises(Invalid):
            self.grants.admit(issued['token'], self.envelope('growth.history'))
        self.assertFalse(self.saved(issued))
        self.assertEqual(self.grants.list('sample-one', identities.OWNER)['grants'][0]['used'], 0)

    def test_worker_rechecks_protected_access_before_dispatch(self):
        issued = self.activate(['pipeline_preparation'])
        self.dispatch(issued, self.pipeline())
        self.access.side_effect = Invalid('Synthetic protected access lost before worker dispatch')
        with patch('mission_control.worker.process', return_value={}) as process:
            self.assertTrue(run_once(self.store))
        process.assert_not_called()
        self.assertEqual(jobs(self.store, 'sample-one')[0]['status'], 'BLOCKED')
