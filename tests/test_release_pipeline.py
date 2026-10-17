"""Synthetic source-linked promotion selection, atomicity and current workflow truth."""
import copy
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from mission_control.common import Invalid,digest,now
from mission_control.store import Store
from mission_control.service import Service
from mission_control.worker import run_once,jobs
from mission_control.release_inventory import read_inventory
from mission_control.release_readiness import readiness,report_problem,inventory_state
from mission_control.release_selection import choose
from mission_control.pipeline import evaluate
from mission_control.guided_workflow import guide
from mission_control.automatic_preparation import prepare
from tests.test_release_inventory import fixtures,FakeReader,BINDING


def observed(state='READY_FOR_SALE'):
    pages=fixtures(); report=read_inventory(FakeReader(pages),'123','version-1')
    report['review_state']=state
    report['locales'][0]['metadata']['keywords']='synthetic'
    hashes=[digest(page) for page in pages]
    return dict(report,app_id='sample-one',provider='app_store',store_app_id='123',observed_at=now(),
                page_source_hashes=hashes,source_hash=digest(hashes),external_writes=False)


class ReleasePipeline(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.store=Store(Path(self.tmp.name)/'test.sqlite'); self.service=Service(self.store)
        app=self.store.app('sample-one'); self.store.save_app('sample-one',{**app['data'],'store_app_id':'123','release':'synthetic build42','locale':'en-US'},app['version'])
        self.binding=self.store.save_record('sample-one',{'kind':'connection','title':'Synthetic App Store','source':'Synthetic only','data':BINDING})
        self.statuses={self.binding['id']:{'status':'CONFIGURED_UNTESTED'}}

    def tearDown(self): self.tmp.cleanup()

    def queue_read(self, report=None, failure=None):
        body={'action':'sync','data':{'connection_id':self.binding['id'],'connection_version':self.binding['version'],'options':{'operation':'release_inventory','version_id':'version-1'}},'request_key':now()}
        job=self.service.queue('sample-one',body)
        with patch('mission_control.worker.read_report',return_value=report or observed(),side_effect=failure): run_once(self.store)
        return next(row for row in jobs(self.store,'sample-one') if row['id']==job['id'])

    def select(self, job):
        body={'manifest_version':self.store.app('sample-one')['version'],'connection_id':self.binding['id'],'connection_version':self.binding['version'],'job_id':job['id'],'report_hash':job['result']['source_hash']}
        return choose(self.store,'sample-one',body)

    def view(self):
        return readiness(self.store.app('sample-one'),self.store.records('sample-one'),jobs(self.store,'sample-one'),self.statuses)

    def test_selection_requires_explicit_intent_and_keeps_remaining_proof(self):
        job=self.queue_read(); self.assertEqual(self.view()['state'],'SELECTION_NEEDED')
        result=self.select(job); self.assertFalse(result['external_writes'])
        view=self.view(); self.assertEqual(view['state'],'INVENTORY_CHECKED'); self.assertTrue(view['inventory_verified'])
        self.assertEqual(view['selection']['local_release'],'synthetic build42')
        self.assertIn('separate evidence',view['reason'])
        self.assertEqual(self.store.history('sample-one')[0]['action'],'release.selected')

    def test_pipeline_guide_preparation_and_worker_share_pending_review(self):
        job=self.queue_read(observed('WAITING_FOR_REVIEW')); self.select(job)
        app=self.store.app('sample-one'); records=self.store.records('sample-one'); release=self.view()
        self.assertEqual(release['state'],'REVIEW_PENDING'); self.assertFalse(release['inventory_verified'])
        stages=evaluate(app,records,release=release); workflow=guide(app,records,stages,release=release); packet=prepare(app,records,release=release)
        self.assertTrue(any('Verify selected App Store release:' in line for line in stages[4]['missing']))
        self.assertEqual(workflow['steps'][4]['primary']['id'],'release')
        self.assertEqual(packet['outputs'][4]['missing'],stages[4]['missing'])
        before=packet['source_hash']; changed=copy.deepcopy(release); changed['reason']='Updated provider observation'
        self.assertNotEqual(before,prepare(app,records,release=changed)['source_hash'])
        pipeline=self.service.queue('sample-one',{'action':'pipeline','data':{'stage':5},'request_key':'pipeline-fixture'})
        run_once(self.store); result=next(row for row in jobs(self.store,'sample-one') if row['id']==pipeline['id'])
        self.assertEqual(result['result']['outputs'][0]['missing'],stages[4]['missing'])
        self.assertEqual(result['result']['external_execution'],'NOT_RUN')

    def test_maximum_failed_pending_cancelled_attempt_masks_success(self):
        self.select(self.queue_read()); self.assertTrue(self.view()['inventory_verified'])
        failed=self.queue_read(failure=Invalid('Synthetic timeout'))
        self.assertEqual(self.view()['state'],'READ_BLOCKED'); self.assertEqual(self.view()['job_id'],failed['id'])
        self.select(self.queue_read()); self.assertTrue(self.view()['inventory_verified'])
        queued=self.service.queue('sample-one',{'action':'sync','data':{'connection_id':self.binding['id'],'options':{'operation':'release_inventory','version_id':'version-1'}},'request_key':'pending-fixture'})
        self.assertEqual(self.view()['state'],'READ_PENDING')
        self.service.cancel('sample-one',queued['id']); self.assertEqual(self.view()['state'],'READ_BLOCKED')

    def test_bound_release_locale_app_and_connection_changes_invalidate(self):
        self.select(self.queue_read()); app=self.store.app('sample-one'); rows=self.store.records('sample-one'); attempts=jobs(self.store,'sample-one')
        for key,value in (('release','new local release'),('locale','th'),('store_app_id','999')):
            changed=copy.deepcopy(app); changed['data'][key]=value
            self.assertFalse(readiness(changed,rows,attempts,self.statuses)['inventory_verified'])
        rotated=copy.deepcopy(rows); rotated[0]['version']+=1
        self.assertEqual(readiness(app,rotated,attempts,self.statuses)['state'],'SELECTION_NEEDED')
        blocked={self.binding['id']:{'status':'DISCONNECTED'}}
        self.assertEqual(readiness(app,rows,attempts,blocked)['state'],'CONNECTION_BLOCKED')

    def test_source_envelope_freshness_and_foreign_context(self):
        job=self.queue_read(); self.select(job); app=self.store.app('sample-one'); rows=self.store.records('sample-one')
        for field,value in (('app_id','sample-two'),('store_app_id','999'),('source_hash','0'*64),('external_writes',True),('requests',True),('locales',{})):
            changed=copy.deepcopy(job); changed['result'][field]=value
            self.assertEqual(readiness(app,rows,[changed],self.statuses)['state'],'READ_BLOCKED')
        for shift in (-86401,60):
            changed=copy.deepcopy(job); changed['result']['observed_at']=(datetime.now(timezone.utc)+timedelta(seconds=shift)).isoformat()
            self.assertEqual(readiness(app,rows,[changed],self.statuses)['state'],'STALE')
        with self.assertRaises(Invalid): evaluate(app,rows,release={'app_id':'sample-two'})

    def test_gaps_partial_processing_build_and_unknown_status(self):
        job=self.queue_read(); self.select(job); selected=self.view()['selection']
        cases=[('PARTIAL',lambda r:r.update(coverage='PARTIAL')),
               ('LOCALE_NEEDED',lambda r:r.update(locales=[])),
               ('METADATA_NEEDED',lambda r:r['locales'][0]['metadata'].update(description='')),
               ('SCREENSHOTS_NEEDED',lambda r:r['locales'][0].update(screenshot_sets=[])),
               ('FILES_PROCESSING',lambda r:r['locales'][0]['screenshot_sets'][0]['screenshots'][0].update(delivery_state='UPLOADING')),
               ('BUILD_NEEDED',lambda r:r['build'].update(processing_state='PROCESSING')),
               ('RELEASE_CHANGED',lambda r:r['build'].update(id='new-build')),
               ('STATUS_REVIEW_NEEDED',lambda r:r.update(review_state='FUTURE_STATUS'))]
        for expected,alter in cases:
            report=observed(); alter(report)
            with self.subTest(expected=expected): self.assertEqual(inventory_state(report,selected)[0],expected)

    def test_selection_rejects_stale_versions_foreign_job_wrong_hash_and_older_success(self):
        job=self.queue_read(); base={'manifest_version':self.store.app('sample-one')['version'],'connection_id':self.binding['id'],'connection_version':1,'job_id':job['id'],'report_hash':job['result']['source_hash']}
        for change in ({'manifest_version':True},{'manifest_version':1},{'connection_version':2},{'report_hash':'bad'},{'job_id':'foreign'}):
            with self.subTest(change=change),self.assertRaises(Invalid): choose(self.store,'sample-one',{**base,**change})
        with self.assertRaises(Invalid): choose(self.store,'sample-two',base)
        self.queue_read(failure=Invalid('Synthetic newer failure'))
        with self.assertRaises(Invalid): choose(self.store,'sample-one',base)

    def test_selection_and_audit_rollback_together(self):
        job=self.queue_read(); before=self.store.app('sample-one'); history=self.store.history('sample-one')
        with patch('mission_control.release_selection.audit',side_effect=Invalid('Synthetic audit failure')),self.assertRaises(Invalid): self.select(job)
        self.assertEqual(self.store.app('sample-one'),before); self.assertEqual(self.store.history('sample-one'),history)

    def test_concurrent_selection_commits_once(self):
        job=self.queue_read(); body={'manifest_version':self.store.app('sample-one')['version'],'connection_id':self.binding['id'],'connection_version':1,'job_id':job['id'],'report_hash':job['result']['source_hash']}
        barrier=threading.Barrier(2); results=[]
        def execute():
            barrier.wait()
            try: choose(self.store,'sample-one',body); results.append('saved')
            except Invalid: results.append('changed')
        threads=[threading.Thread(target=execute) for _ in range(2)]
        for thread in threads: thread.start()
        for thread in threads: thread.join(timeout=10)
        self.assertCountEqual(results,['saved','changed'])

    def test_selection_body_rejects_unbound_shapes_without_mutation(self):
        before=self.store.app('sample-one')
        for body in (None,{},[],{'manifest_version':1}, {'manifest_version':2,'connection_id':'','connection_version':1,'job_id':'job','report_hash':'hash'}):
            with self.subTest(body=body),self.assertRaises(Invalid): choose(self.store,'sample-one',body)
        self.assertEqual(self.store.app('sample-one'),before)

    def test_source_rows_requires_current_owned_connection(self):
        job=self.queue_read(); before=self.store.app('sample-one')
        for changes in ({'auth_mode':'disconnected'},{'provider':'apple_ads'},{'store_app_id':'999'}):
            old=self.store.records('sample-one')[0]
            binding=self.store.save_record('sample-one',{**old,'data':{**BINDING,**changes}})
            body={'manifest_version':before['version'],'connection_id':binding['id'],'connection_version':binding['version'],'job_id':job['id'],'report_hash':job['result']['source_hash']}
            with self.subTest(changes=changes),self.assertRaises(Invalid): choose(self.store,'sample-one',body)
        self.assertEqual(self.store.app('sample-one'),before)

    def test_selected_target_requires_explicit_local_release_and_locale(self):
        job=self.queue_read(); original=self.store.app('sample-one')
        for field in ('release','locale'):
            current=self.store.app('sample-one'); self.store.save_app('sample-one',{**original['data'],field:''},current['version'])
            with self.subTest(field=field),self.assertRaises(Invalid): self.select(job)
        self.assertNotIn('promotion_release',self.store.app('sample-one')['data'])

    def test_report_problem_rejects_untyped_results_and_invalid_page_envelopes(self):
        job=self.queue_read(); self.select(job); app=self.store.app('sample-one'); records=self.store.records('sample-one')
        for value in (None,[], 'not a report'):
            changed=copy.deepcopy(job); changed['result']=value
            self.assertEqual(readiness(app,records,[changed],self.statuses)['state'],'READ_BLOCKED')
        for value in ([],['invalid hash'],['0'*64]*25):
            changed=copy.deepcopy(job); changed['result']['page_source_hashes']=value
            self.assertEqual(readiness(app,records,[changed],self.statuses)['state'],'READ_BLOCKED')
        failed=self.queue_read(failure=Invalid('Synthetic source unavailable'))
        with self.assertRaises(Invalid): self.select({**failed,'result':job['result']})

    def test_metadata_problem_and_sets_problem_do_not_infer_missing_media(self):
        self.select(self.queue_read()); selection=self.view()['selection']
        cases=[('READ_BLOCKED',lambda r:r['locales'][0].update(metadata=[])),
               ('READ_BLOCKED',lambda r:r['locales'][0].update(screenshot_sets={})),
               ('PARTIAL',lambda r:r['locales'][0]['screenshot_sets'][0].update(coverage='PARTIAL')),
               ('PARTIAL',lambda r:r['locales'][0].update(coverage='PARTIAL')),
               ('SCREENSHOTS_NEEDED',lambda r:r['locales'][0]['screenshot_sets'][0].update(screenshots=[]))]
        for expected,alter in cases:
            report=observed(); alter(report)
            with self.subTest(expected=expected): self.assertEqual(inventory_state(report,selection)[0],expected)

    def test_readiness_distinguishes_no_platform_no_connection_and_no_attempt(self):
        self.select(self.queue_read()); app=self.store.app('sample-one'); rows=self.store.records('sample-one')
        no_platform=copy.deepcopy(app); no_platform['data']['store_app_id']=None
        self.assertEqual(readiness(no_platform,rows,[],self.statuses)['state'],'NOT_APPLICABLE')
        self.assertEqual(readiness(app,[],[],self.statuses)['state'],'SETUP_NEEDED')
        self.assertEqual(readiness(app,rows,[],self.statuses)['state'],'READ_NEEDED')

    def test_fresh_report_rejects_missing_or_malformed_observation_time(self):
        job=self.queue_read(); self.select(job); app=self.store.app('sample-one'); rows=self.store.records('sample-one')
        for value in (None,'not a timestamp'):
            changed=copy.deepcopy(job); changed['result']['observed_at']=value
            self.assertEqual(readiness(app,rows,[changed],self.statuses)['state'],'STALE')


if __name__=='__main__': unittest.main()
