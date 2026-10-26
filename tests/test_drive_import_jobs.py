"""Actual durable original-import worker, private progress and synthetic provider races."""
from contextlib import contextmanager
import json
import threading
import time
import unittest
from unittest.mock import patch
from mission_control import drive_import_jobs as module
from mission_control import drive_media_transport as transport
from mission_control.common import Invalid, canonical, now
from mission_control.db import connection
from mission_control.service import Service
from mission_control.worker import run_once, claim, jobs
from mission_control.workflow_telemetry import monitor
from mission_control.managed_media_store import Media
import tests.test_drive_media as fixtures


class DriveImportJobTests(unittest.TestCase):
    setUp=fixtures.DriveMediaTests.setUp
    start=fixtures.DriveMediaTests.start
    candidate=fixtures.DriveMediaTests.candidate
    adopt=fixtures.DriveMediaTests.adopt
    body=fixtures.DriveMediaTests.body

    def queued(self,body=None):
        return module.Imports(self.store).queue('sample-one',body or self.body(),'owner')

    @contextmanager
    def provider(self,download=None):
        def read(file_id,bearer):return fixtures.contract.metadata(fixtures.raw_metadata(self.originals[file_id],file_id),file_id)
        def fetch(selected,bearer,alive):
            alive()
            return self.originals[selected['id']]
        with patch('mission_control.drive_media.read_account',return_value=dict(permission_id='synthetic-account-one')), \
             patch.object(transport,'read_metadata',side_effect=read), \
             patch.object(transport,'download',side_effect=download or fetch)as calls:
            yield calls

    def test_private_queue_replay_worker_stages_and_original_are_retained(self):
        imports=module.Imports(self.store);queued=self.queued();self.assertEqual(queued['status'],'QUEUED')
        self.assertEqual(self.queued()['id'],queued['id']);self.assertEqual(queued['selection'],self.body())
        self.assertIsNone(queued['progress_percent']);self.assertIsNone(queued['cost_minor'])
        with self.provider()as download:self.assertTrue(run_once(self.store))
        download.assert_called_once()
        result=imports.read('sample-one',queued['id'],'owner');self.assertEqual(result['status'],'SUCCEEDED',result)
        self.assertEqual(result['result']['reuse_permission'],'UNKNOWN')
        self.assertEqual([e['code']for e in result['events']],['STARTED','DRIVE_ACCOUNT','DRIVE_METADATA','DRIVE_DOWNLOAD','DRIVE_RECHECK','DRIVE_VALIDATION','DRIVE_RETAINED','SUCCEEDED'])
        item,raw=self.media.original('sample-one',result['result']['media_id'],'owner')
        self.assertEqual(raw,self.originals['clip_red']);self.assertEqual(item['source_sha256'],result['result']['source_sha256'])
        self.assertEqual(len(imports.list('sample-one','owner')['items']),1)
        print('DRIVE_DURABLE_IMPORT '+json.dumps(dict(job_id=queued['id'],media_id=item['id'],sha256=item['source_sha256'],stages=[e['code']for e in result['events']])))

    def test_generic_job_reads_telemetry_submission_and_cancel_cannot_expose_or_control_import(self):
        queued=self.queued();self.assertEqual(jobs(self.store,'sample-one'),[])
        self.assertEqual(monitor(self.store,'sample-one')['runs'],[])
        service=Service(self.store)
        with self.assertRaises(Invalid):service.queue('sample-one',dict(action='drive_import',data=self.body(),request_key='generic-attempt'))
        with self.assertRaises(PermissionError):service.cancel('sample-one',queued['id'])
        self.assertEqual(module.Imports(self.store).read('sample-one',queued['id'],'owner')['status'],'QUEUED')
        with self.assertRaises(PermissionError):module.Imports(self.store).read('sample-one',queued['id'],'unknown-principal')

    def test_changed_retry_input_and_foreign_owner_are_denied(self):
        self.queued()
        with self.assertRaises(Invalid):self.queued(dict(self.body(),file_id='clip_blue'))
        with self.assertRaises(PermissionError):module.Imports(self.store).queue('sample-one',dict(self.body(),request_key='foreign'),'foreign')
        with self.assertRaises(PermissionError):module.Imports(self.store).list('sample-two','owner')

    def test_revoked_owner_after_queue_stops_before_provider_read(self):
        queued=self.queued()
        with connection(self.store.path)as db:db.execute("UPDATE operator_roles SET status='REVOKED',version=version+1 WHERE app_id=?",('sample-one',))
        with self.provider()as download:self.assertTrue(run_once(self.store))
        download.assert_not_called()
        with connection(self.store.path)as db:
            row=dict(db.execute('SELECT * FROM jobs WHERE id=?',(queued['id'],)).fetchone())
            self.assertEqual(row['status'],'BLOCKED');self.assertNotIn('synthetic-access',row['result'])
            self.assertEqual(db.execute('SELECT COUNT(*)FROM managed_media').fetchone()[0],0)

    def test_cancellation_during_download_prevents_commit_and_terminal_overwrite(self):
        imports=module.Imports(self.store);queued=self.queued()
        def cancel(selected,bearer,alive):
            imports.cancel('sample-one',queued['id'],'owner');alive()
            return self.originals[selected['id']]
        with self.provider(cancel):self.assertTrue(run_once(self.store))
        result=imports.read('sample-one',queued['id'],'owner');self.assertEqual(result['status'],'CANCELLED')
        self.assertIsNone(result['result']);self.assertEqual(self.media.list('sample-one')['items'],[])

    def test_owner_revocation_during_native_validation_prevents_original_commit(self):
        from mission_control import managed_media_store as managed
        queued=self.queued();original=managed.inspect
        def revoke(raw,suffix,**kwargs):
            with connection(self.store.path)as db:db.execute("UPDATE operator_roles SET status='REVOKED',version=version+1 WHERE app_id=?",('sample-one',))
            return original(raw,suffix,**kwargs)
        with self.provider(),patch.object(managed,'inspect',side_effect=revoke):self.assertTrue(run_once(self.store))
        with connection(self.store.path)as db:
            self.assertEqual(db.execute('SELECT status FROM jobs WHERE id=?',(queued['id'],)).fetchone()[0],'BLOCKED')
            self.assertEqual(db.execute('SELECT COUNT(*)FROM managed_media').fetchone()[0],0)

    def test_database_namespace_mismatch_rejects_before_provider_read(self):
        queued=self.queued()
        with connection(self.store.path)as db:
            data=json.loads(db.execute('SELECT data FROM jobs WHERE id=?',(queued['id'],)).fetchone()[0]);data['namespace']='0'*24
            db.execute('UPDATE jobs SET data=? WHERE id=?',(canonical(data),queued['id']))
        with self.provider()as download:self.assertTrue(run_once(self.store))
        download.assert_not_called();self.assertEqual(module.Imports(self.store).read('sample-one',queued['id'],'owner')['status'],'BLOCKED')

    def test_interrupted_result_recovers_committed_original_without_redownload(self):
        imports=module.Imports(self.store);queued=self.queued();job=claim(self.store)
        with self.provider()as download:first=imports.execute(job)
        download.assert_called_once()
        with connection(self.store.path)as db:db.execute('UPDATE jobs SET lease=0 WHERE id=?',(queued['id'],))
        with self.provider()as download:self.assertTrue(run_once(self.store))
        download.assert_not_called();result=imports.read('sample-one',queued['id'],'owner')
        self.assertEqual(result['status'],'SUCCEEDED');self.assertEqual(result['result']['media_id'],first['media_id'])
        self.assertEqual(len(self.media.list('sample-one')['items']),1);self.assertEqual(result['attempts'],2)

    def test_queue_is_not_authorized_after_role_revision_change_or_connection_replacement(self):
        queued=self.queued();job=claim(self.store);imports=module.Imports(self.store)
        with connection(self.store.path)as db:db.execute('UPDATE operator_roles SET version=version+1')
        with self.assertRaises(Invalid):imports.guard(job)
        with connection(self.store.path)as db:db.execute('UPDATE operator_roles SET version=version-1')
        stop=threading.Event();stop.set()
        with self.assertRaises(Invalid):imports.guard(job,stop)
        with connection(self.store.path)as db:db.execute('UPDATE drive_connections SET version=version+1')
        with self.assertRaises(Invalid):imports.guard(job)

    def test_owner_version_and_frozen_request_do_not_include_tokens(self):
        row=self.connections.row('sample-one')
        with connection(self.store.path)as db:version=module.owner_version(db,'sample-one','owner')
        frozen=module.frozen(self.store,row,self.body(),'owner',version)
        self.assertEqual(frozen['owner_version'],1);self.assertEqual(frozen['request'],self.body())
        self.assertNotIn('synthetic-access',canonical(frozen));self.assertNotIn('secret_ref',canonical(frozen))
        self.assertEqual(frozen['namespace'],module.namespace(self.store.path))

    def test_pulse_process_media_and_run_view_keep_owned_attempt_and_terminal_privacy(self):
        from mission_control.worker import process_media, failed_result
        from mission_control.workflow_telemetry import run_view
        queued=self.queued();job=claim(self.store);imports=module.Imports(self.store);last=[0]
        imports.pulse(job,None,last);self.assertGreater(last[0],0)
        with self.provider():result=process_media(self.store,job,None)
        self.assertEqual(result['reuse_permission'],'UNKNOWN')
        with connection(self.store.path)as db:
            value=run_view(db,'sample-one',{key:job[key]for key in ('id','status','attempts','created','updated')})
        self.assertEqual(value['latest']['code'],'DRIVE_RETAINED')
        failure,status,delay=failed_result(job,Invalid('synthetic-private-provider-detail'))
        self.assertEqual((status,delay),('BLOCKED',0));self.assertNotIn('synthetic-private-provider-detail',canonical(failure))

    def test_forged_worker_input_and_existing_ordinary_connection_guards_deny(self):
        from mission_control.worker import current_connection,process_evidence_job
        queued=self.queued();job=claim(self.store)
        changed={**job,'data':{**job['data'],'request':{**job['data']['request'],'file_id':'clip_blue'}}}
        with self.assertRaises(Invalid):module.Imports(self.store).guard(changed)
        service=Service(self.store)
        with self.assertRaises(Invalid):service.sync_data('sample-one',dict(connection_id='missing'))
        with self.assertRaises(Invalid):service.play_sync_data('sample-one',dict(data={}),{})
        with self.assertRaises(Invalid):current_connection(self.store,'sample-one',dict(connection_id='missing',connection_version=1))
        with patch('mission_control.experiment_tracking.Tracking.execute',return_value={'synthetic':'tracking'})as execute:
            self.assertEqual(process_evidence_job(self.store,dict(action='experiment_tracking')),{'synthetic':'tracking'})
        execute.assert_called_once()

    def test_renew_does_not_wait_on_original_commit_writer_but_still_checks_ownership(self):
        self.queued();job=claim(self.store);imports=module.Imports(self.store)
        with connection(self.store.path)as db:
            db.execute('BEGIN IMMEDIATE')
            started=time.monotonic();self.assertFalse(imports.renew(job));self.assertLess(time.monotonic()-started,1)
            imports.pulse(job,None,[0])
        self.assertTrue(imports.renew(job))
        imports.cancel('sample-one',job['id'],'owner')
        with self.assertRaises(Invalid):imports.renew(job)
