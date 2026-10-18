"""Durable exact approval, guarded adoption, restart and cancellation proofs."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import concurrent.futures,copy,uuid,unittest
from mission_control.common import Invalid,canonical,digest,now
from mission_control.db import connection
from mission_control.store import Store
from mission_control.experiment_tracking import Tracking,current,decode,failure_result
from mission_control.insights_transport import ProviderFailure
from mission_control.worker import json_job,enqueue
from tests.test_tracking_contract import fixture,payload
from mission_control.tracking_contract import shape


class ExperimentTrackingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(Path(self.tmp.name)/'synthetic.sqlite3');self.tracking=Tracking(self.store)
        self.app,self.experiment,self.source=fixture(self.store)
        source=self.source;stamp=now()
        with connection(self.store.path) as db:
            db.execute('INSERT INTO insight_sources VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (source['app_id'],source['id'],source['provider'],canonical(source['data']),source['hash'],
                 'synthetic-scope','synthetic-key-ref',source['version'],'CONNECTED',0,0,None,stamp,stamp))

    def body(self):
        identifiers=dict(experiment_id=self.experiment['id'],source_id=self.source['id'])
        proposal=self.tracking.prepare('sample-one',identifiers)
        return dict(identifiers,proposal_hash=proposal['proposal_hash'],request_key=str(uuid.uuid4()),confirm_read=True)

    def approve(self):return self.tracking.approve('sample-one',self.body())

    def job(self,run):
        with connection(self.store.path) as db:return json_job(db.execute('SELECT * FROM jobs WHERE id=?',(run['job_id'],)).fetchone())

    def secret(self):return dict(api_key='SYNTHETIC_PRIVATE_KEY',binding=dict(app_id='sample-one',id=self.source['id'],hash=self.source['hash']))

    def execute(self,run,result=None,side_effect=None):
        with patch('mission_control.experiment_tracking.Vault.get',return_value=self.secret()), \
             patch('mission_control.experiment_tracking.tracking_posthog.read',return_value=result or shape(payload()),side_effect=side_effect) as read:
            value=self.tracking.execute(self.job(run))
        return value,read

    def test_approve_creates_one_owned_job_replay_and_restart_preserve_authority(self):
        body=self.body();run=self.tracking.approve('sample-one',body)
        self.assertEqual(self.tracking.approve('sample-one',body),run)
        self.assertEqual(Tracking(Store(self.store.path)).get('sample-one',run['id']),run)
        self.assertEqual(run['status'],'QUEUED');self.assertEqual(run['plan']['expires_at'],run['expires'])
        with connection(self.store.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM experiment_tracking_runs').fetchone()[0],1)
            self.assertEqual(db.execute("SELECT count(*) FROM jobs WHERE action='experiment_tracking'").fetchone()[0],1)
            current(self.store,db.execute('SELECT * FROM experiment_tracking_runs').fetchone())
        changed={**body,'source_id':'another-source'}
        with self.assertRaises(Invalid):self.tracking.approve('sample-one',changed)

    def test_concurrent_same_approval_has_one_run_and_job(self):
        body=self.body()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            rows=list(pool.map(lambda _:Tracking(self.store).approve('sample-one',body),range(2)))
        self.assertEqual(rows[0]['id'],rows[1]['id'])
        with connection(self.store.path) as db:self.assertEqual(db.execute('SELECT count(*) FROM jobs').fetchone()[0],1)

    def test_approval_rejects_foreign_source_stale_hash_extra_command_and_false_consent(self):
        body=self.body()
        for changed in ({**body,'proposal_hash':'stale'},{**body,'command':'publish'},{**body,'confirm_read':1},
                        {**body,'request_key':'not-a-uuid'},{**body,'source_id':'foreign'}):
            with self.subTest(changed=changed),self.assertRaises((Invalid,KeyError)):self.tracking.approve('sample-one',changed)
        with self.assertRaises((Invalid,KeyError)):self.tracking.approve('sample-two',body)
        self.assertEqual(self.tracking.list('sample-one'),[])
        with self.assertRaises(Invalid):enqueue(self.store,'sample-one','experiment_tracking',{},'bypass')

    def test_execute_adopts_only_guarded_result_once_without_keys_in_receipts(self):
        run=self.approve();result,read=self.execute(run)
        self.assertEqual(result['status'],'OBSERVED');self.assertEqual(read.call_count,1)
        self.assertEqual(result['result']['observed_counts'][0]['subjects'],20)
        self.assertNotIn('SYNTHETIC_PRIVATE_KEY',canonical(result))
        again,read=self.execute(run);self.assertEqual(result,again);read.assert_not_called()

    def test_cancel_is_scoped_idempotent_and_blocks_queued_reads(self):
        run=self.approve()
        with self.assertRaises(Invalid):self.tracking.cancel('sample-two',run['id'],dict(cancel_run=True))
        for body in ({},{'cancel_run':1},{'cancel_run':True,'other':True}):
            with self.assertRaises(Invalid):self.tracking.cancel('sample-one',run['id'],body)
        stopped=self.tracking.cancel('sample-one',run['id'],dict(cancel_run=True))
        self.assertEqual(stopped['status'],'CANCELLED')
        self.assertEqual(stopped,self.tracking.cancel('sample-one',run['id'],dict(cancel_run=True)))
        result,read=self.execute(run);read.assert_not_called();self.assertEqual(result['status'],'CANCELLED')
        self.assertEqual(self.job(run)['status'],'CANCELLED')

    def test_cancellation_in_flight_does_not_adopt_provider_results(self):
        run=self.approve()
        def remote(*args):
            self.tracking.cancel('sample-one',run['id'],dict(cancel_run=True))
            return shape(payload())
        result,read=self.execute(run,side_effect=remote)
        self.assertEqual(result['status'],'CANCELLED');self.assertIsNone(result['result'])
        self.assertEqual(read.call_count,1)

    def test_expired_and_tampered_expiry_stop_before_io(self):
        run=self.approve()
        with patch('mission_control.experiment_tracking.now',return_value='2999-01-01T00:00:00+00:00'):
            result,read=self.execute(run)
        read.assert_not_called();self.assertEqual(result['status'],'NEEDS_REVIEW')
        run=self.approve()
        with connection(self.store.path) as db:db.execute("UPDATE experiment_tracking_runs SET expires='2999-01-01T00:00:00+00:00' WHERE id=?",(run['id'],))
        with self.assertRaises(Invalid):self.tracking.get('sample-one',run['id'])
        self.assertEqual(self.tracking.list('sample-one')[0]['status'],'INTEGRITY_REVIEW_REQUIRED')

    def test_source_version_and_app_drift_stop_before_and_after_io(self):
        legacy=self.approve();plan=copy.deepcopy(legacy['plan']);proposal=plan['proposal']
        proposal['expected_flag']['filters']['groups'][0]['properties']=[p for p in proposal['expected_flag']['filters']['groups'][0]['properties'] if p['key']!='wmm_locale']
        proposal['proposal_hash']=digest({k:v for k,v in proposal.items() if k!='proposal_hash'})
        with connection(self.store.path) as db:
            db.execute('UPDATE experiment_tracking_runs SET plan=?,hash=? WHERE id=?',(canonical(plan),digest(plan),legacy['id']))
        result,read=self.execute(legacy);read.assert_not_called();self.assertEqual(result['status'],'NEEDS_REVIEW')
        run=self.approve()
        with connection(self.store.path) as db:db.execute('UPDATE insight_sources SET version=version+1')
        result,read=self.execute(run);read.assert_not_called();self.assertEqual(result['status'],'NEEDS_REVIEW')
        run=self.approve()
        def changed(*args):
            app=self.store.app('sample-one')
            self.store.save_app('sample-one',{**app['data'],'release':'changed-build'},app['version'])
            return shape(payload())
        result,read=self.execute(run,side_effect=changed)
        self.assertEqual(result['status'],'NEEDS_REVIEW');self.assertIsNone(result['result']['observed_counts'])

    def test_final_adoption_rechecks_authority_under_writer_lock(self):
        run=self.approve()
        with connection(self.store.path) as db:db.execute('UPDATE insight_sources SET version=version+1')
        with self.assertRaises(Invalid):self.tracking.save_result('sample-one',run['id'],shape(payload()),'OBSERVED',require_current=True)
        self.assertEqual(self.tracking.get('sample-one',run['id'])['status'],'QUEUED')

    def test_missing_or_foreign_protected_binding_never_calls_provider(self):
        run=self.approve()
        for secret in (None,{**self.secret(),'binding':dict(app_id='sample-two')}):
            with patch('mission_control.experiment_tracking.Vault.get',return_value=secret), \
                 patch('mission_control.experiment_tracking.tracking_posthog.read') as read:
                result=self.tracking.execute(self.job(run))
            read.assert_not_called();self.assertEqual(result['result']['failure_code'],'PROTECTED_ACCESS_REQUIRED')
            run=self.approve()

    def test_typed_provider_failure_does_not_copy_private_diagnostic(self):
        run=self.approve()
        result,_=self.execute(run,side_effect=ProviderFailure('PERMISSION_REQUIRED','PRIVATE KEY VALUE'))
        self.assertEqual(result['result']['failure_code'],'PERMISSION_REQUIRED')
        self.assertNotIn('PRIVATE KEY VALUE',canonical(result))
        self.assertTrue(result['result']['next_actions'])
        self.assertEqual(failure_result(OSError('secret'))['failure_code'],'KEY_STORAGE_UNAVAILABLE')

    def test_foreign_jobs_and_changed_receipts_are_not_adopted(self):
        run=self.approve();job=self.job(run)
        for changed in ({**job,'id':'foreign'},{**job,'app_id':'sample-two'},{**job,'data':{'tracking_run_id':run['id'],'command':'publish'}}):
            with self.assertRaises(Invalid):self.tracking.execute(changed)
        result,_=self.execute(run)
        with connection(self.store.path) as db:db.execute("UPDATE experiment_tracking_runs SET result='{}' WHERE id=?",(run['id'],))
        with self.assertRaises(Invalid):self.tracking.get('sample-one',run['id'])
        self.assertEqual(self.tracking.list('sample-one')[0]['status'],'INTEGRITY_REVIEW_REQUIRED')

    def test_exhausted_worker_is_recovery_not_permanent_queued_state(self):
        run=self.approve()
        with connection(self.store.path) as db:
            db.execute("UPDATE jobs SET status='FAILED',result=? WHERE id=?",(canonical(dict(error='PRIVATE_DIAGNOSTIC')),run['job_id']))
        saved=self.tracking.get('sample-one',run['id'])
        self.assertEqual(saved['status'],'READ_RECOVERY_REQUIRED');self.assertTrue(saved['next_actions'])
        self.assertNotIn('PRIVATE_DIAGNOSTIC',canonical(saved))
        result,read=self.execute(run);read.assert_not_called();self.assertEqual(result,saved)

    def test_invalid_identifier_types_are_validation_errors_not_database_failures(self):
        identifiers=dict(experiment_id=self.experiment['id'],source_id=self.source['id'])
        for field in identifiers:
            for value in (None,True,[],{},'x'*121,'../foreign'):
                with self.subTest(field=field,value=value),self.assertRaises(Invalid):
                    self.tracking.prepare('sample-one',{**identifiers,field:value})
        body=self.body()
        for value in ([],{},None,True,'bad'):
            with self.assertRaises(Invalid):self.tracking.approve('sample-one',{**body,'proposal_hash':value})

    def test_unknown_saved_state_cannot_enter_agent_context(self):
        from mission_control.experiment_tracking import feedback
        run=self.approve()
        with connection(self.store.path) as db:
            db.execute('UPDATE experiment_tracking_runs SET status=? WHERE id=?',('PRIVATE_PROMPT_INJECTION',run['id']))
        observed=feedback(self.store,'sample-one')
        self.assertEqual(observed['state'],'INTEGRITY_REVIEW_REQUIRED')
        self.assertNotIn('PRIVATE_PROMPT_INJECTION',canonical(observed))

    def test_restart_recovers_expired_reading_job_within_existing_attempt_limit(self):
        from mission_control.worker import run_once
        run=self.approve()
        with connection(self.store.path) as db:
            db.execute("UPDATE jobs SET status='RUNNING',lease=0,attempts=1 WHERE id=?",(run['job_id'],))
            db.execute("UPDATE experiment_tracking_runs SET status='READING' WHERE id=?",(run['id'],))
        restarted=Store(self.store.path)
        with patch('mission_control.experiment_tracking.Vault.get',return_value=self.secret()), \
             patch('mission_control.experiment_tracking.tracking_posthog.read',return_value=shape(payload())) as provider:
            self.assertTrue(run_once(restarted))
        provider.assert_called_once()
        self.assertEqual(Tracking(restarted).get('sample-one',run['id'])['status'],'OBSERVED')
        self.assertEqual(self.job(run)['attempts'],2)


if __name__=='__main__':unittest.main()
