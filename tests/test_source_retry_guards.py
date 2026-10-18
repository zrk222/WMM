"""Direct source and authority boundary checks used by approved retry execution."""
from copy import deepcopy
import unittest,uuid
from mission_control.common import Invalid,digest
from mission_control.db import connection
from mission_control.worker import jobs
from mission_control.campaign_inputs import CampaignInputs,enqueue_task,task_options,usable_binding,derive_tasks
from mission_control.marketing_agent_manifest import operating_manifest,authorize_source,authorize_operation,authorize_release
from mission_control.resolution_catalog import issue_kind,ordered_tools
from mission_control.resolution_plan import collection_options,executable_options,decorate
from mission_control.resolution_tools import guard,source_guard,analytics_guard,experiment_guard,reuse_guard
from mission_control.source_retry import prefix,identity,retry_rows
from mission_control.resolutions import Resolutions
from tests import test_source_retry as fixtures


class SourceRetryGuardTests(unittest.TestCase):
    setUp=fixtures.SourceRetryTests.setUp
    request=fixtures.SourceRetryTests.request
    dispatch=fixtures.SourceRetryTests.dispatch
    failed=fixtures.SourceRetryTests.failed
    parameters=fixtures.SourceRetryTests.parameters
    approval=fixtures.SourceRetryTests.approval

    def setup_source(self):
        self.failed()
        app=self.store.app('sample-one')
        source=next(r for r in self.store.records('sample-one') if r['kind']=='connection')
        return app,source

    def test_task_options_usable_binding_and_derive_tasks_keep_exact_read_scope(self):
        app,source=self.setup_source();policy=operating_manifest(app)
        self.assertTrue(usable_binding(app,source['data']))
        self.assertFalse(usable_binding(app,{**source['data'],'store_app_id':'other'}))
        self.assertEqual(task_options(app,source),[None,{'operation':'reviews'},{'operation':'subscription_catalog'}])
        records=[{**deepcopy(source),'id':'fixture-'+str(i)} for i in range(5)]
        tasks,excluded=derive_tasks(app,records,digest(policy))
        self.assertEqual(len(tasks),12);self.assertTrue(excluded)
        self.assertTrue(all(t['data']['agent_policy_sha256']==digest(policy) for t in tasks))

    def test_enqueue_task_replay_and_rotated_connection_are_transactional(self):
        self.failed();task=CampaignInputs(self.store).preview('sample-one')['tasks'][0]
        before=len(jobs(self.store,'sample-one'))
        with connection(self.store.path) as db:enqueue_task(db,'sample-one',task)
        self.assertEqual(len(jobs(self.store,'sample-one')),before)
        changed=deepcopy(task);changed['request_key']='synthetic-changed-request';changed['data']['connection_version']+=1
        with connection(self.store.path) as db:
            with self.assertRaises(Invalid):enqueue_task(db,'sample-one',changed)
        self.assertEqual(len(jobs(self.store,'sample-one')),before)

    def test_authorize_source_operation_and_release_fail_closed(self):
        app,source=self.setup_source();policy=operating_manifest(app)
        authorize_source(policy,source['data'])
        with self.assertRaises(Invalid):authorize_source(policy,{**source['data'],'auth_mode':'disconnected'})
        authorize_operation(policy,source['data'],{'options':{'operation':'reviews'}})
        with self.assertRaises(Invalid):authorize_operation(policy,source['data'],{'options':{'operation':'publish'}})
        with self.assertRaises(Invalid):authorize_release(policy,{'connection_id':source['id'],'connection_version':source['version'],'options':{'version_id':'other'}})

    def test_collection_options_executable_options_and_decorate_show_separate_approval(self):
        app,_=self.setup_source();collection=CampaignInputs(self.store).preview('sample-one')
        options=collection_options(collection)
        retry=next(o for o in options if 'retry_candidates' in o['parameters'])
        normal=next(o for o in options if 'retry_candidates' not in o['parameters'])
        self.assertTrue(retry['ready']);self.assertNotEqual(retry['parameters'],normal['parameters'])
        rendered=decorate(retry)
        self.assertIn('No publication',rendered['cost']);self.assertIn(collection['next_collection_at'],rendered['fallback'])
        self.assertEqual(rendered['id'],digest({'tool':retry['tool'],'parameters':retry['parameters']}))
        all_options=executable_options(app,collection,{'sources':[]},[])
        self.assertEqual(sum('retry_candidates' in o['parameters'] for o in all_options),1)

    def test_issue_kind_and_ordered_tools_preserve_access_alternatives(self):
        self.assertEqual(issue_kind('Add current readiness evidence that meets its checks','app'),'readiness')
        self.assertEqual(issue_kind('Unexpected source text','unknown'),'review')
        order=ordered_tools('readiness')
        self.assertEqual(order[0],'inspect_site');self.assertIn('collect_sources',order)
        self.assertEqual(len(order),len(set(order)))

    def test_guard_and_source_guard_do_not_let_retry_bypass_current_authority(self):
        self.failed();job=Resolutions(self.store).start('sample-one',self.approval());frozen=job['data']['envelope']
        self.assertEqual(guard(self.store,'sample-one',frozen)['id'],'sample-one')
        source_guard(self.store,'sample-one',frozen)
        app=self.store.app('sample-one')
        self.store.save_app('sample-one',{**app['data'],'release':'new-release'},app['version'])
        with self.assertRaises(Invalid):guard(self.store,'sample-one',frozen)

    def test_analytics_experiment_and_reuse_guards_reject_unowned_targets(self):
        self.failed()
        with self.assertRaises(Invalid):analytics_guard(self.store,'sample-one',{'source_id':'missing','source_version':1,'configuration_hash':'bad'})
        with self.assertRaises(Invalid):experiment_guard(self.store,'sample-one',{'experiment_id':'missing','definition_hash':'bad'})
        with self.assertRaises(Invalid):reuse_guard(self.store,'sample-one',{'artifact_id':'missing'})

    def test_prefix_identity_and_retry_rows_preserve_source_separation_and_integrity(self):
        self.failed();params=self.parameters();key=str(uuid.uuid4())
        base=params['retry_candidates'][0]['base_job_id']
        other={**params,'collection_hash':'other'}
        self.assertNotEqual(prefix(base),prefix('different'))
        self.assertNotEqual(identity(base,params,key),identity(base,other,key))
        service=CampaignInputs(self.store);saved=service.retry('sample-one',params,key)
        task=next(t for t in service.preview('sample-one')['tasks'] if t['retry_history'])
        root=next(j for j in jobs(self.store,'sample-one') if j['id']==base)
        with connection(self.store.path) as db:
            self.assertEqual(len(retry_rows(db,'sample-one',root,task['data'],3)),1)
            db.execute("UPDATE jobs SET action='pipeline' WHERE id=?",(saved['tasks'][0]['job']['id'],))
        with connection(self.store.path) as db:
            with self.assertRaises(Invalid):retry_rows(db,'sample-one',root,task['data'],3)

    def test_concurrent_approvals_cannot_duplicate_the_same_failed_read(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        self.failed();params=self.parameters();barrier=Barrier(2)
        def approve():
            barrier.wait(timeout=5)
            try:
                return CampaignInputs(self.store).retry('sample-one',params,str(uuid.uuid4()))
            except Invalid:
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            pending=[pool.submit(approve) for _ in range(2)]
            results=[future.result(timeout=15) for future in pending]
        self.assertEqual(sum(r is not None for r in results),1)
        self.assertEqual(len(jobs(self.store,'sample-one')),5)

    def test_partial_enqueue_failure_rolls_back_the_entire_approved_collection(self):
        from unittest.mock import patch
        ids=self.failed()
        with connection(self.store.path) as db:db.execute("UPDATE jobs SET status='BLOCKED' WHERE id=?",(ids[1],))
        params=self.parameters();self.assertEqual(len(params['retry_candidates']),2)
        count=0
        def broken(db,app_id,task):
            nonlocal count
            count+=1
            if count==2:raise Invalid('Synthetic enqueue interruption')
            return enqueue_task(db,app_id,task)
        with patch('mission_control.campaign_inputs.enqueue_task',side_effect=broken):
            with self.assertRaises(Invalid):CampaignInputs(self.store).retry('sample-one',params,str(uuid.uuid4()))
        self.assertEqual(count,2)
        self.assertEqual(len(jobs(self.store,'sample-one')),4)
        self.assertEqual(len(self.parameters()['retry_candidates']),2)


if __name__=='__main__':unittest.main()
