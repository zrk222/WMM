"""Real local action outcomes, bounded history, provenance and approval guards."""
import json,tempfile,unittest,uuid
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from mission_control.store import Store,decode
from mission_control.service import Service
from mission_control.resolutions import Resolutions
from mission_control.agent_feedback import feedback,reuse_candidate,valid_envelope,child_state,child_fingerprint
from mission_control.agent_context import snapshot
from mission_control.common import canonical,digest,now,iso_time,Invalid
from mission_control.db import connection
from mission_control.worker import run_once,jobs
from tests.test_aeo_workflows import CountingReader,ROOT
from tests.test_aeo_inspection import html
from tests import test_agent_tasks as agent_fixtures
from tests.test_agent_access import answer


def initialize(store):
    app=store.app('sample-one')
    store.save_app('sample-one',{**app['data'],'website':ROOT+'/page','release':'feedback-fixture','locale':'en-US'},app['version'])


def request(store,tool='inspect_site'):
    plan=Service(store).workspace('sample-one')['resolutions']
    issue=next(i for i in plan['issues'] if any(o['tool']==tool and o['ready'] for o in i['options']))
    option=next(o for o in issue['options'] if o['tool']==tool and o['ready'])
    return dict(issue_id=issue['id'],option_id=option['id'],source_hash=issue['source_hash'],target_url=None,request_key=str(uuid.uuid4()))


def inspect(store,fail=False):
    job=Resolutions(store).start('sample-one',request(store))
    reader=CountingReader(page=html('<p>PRIVATE_RAW_PAGE_6921</p>'))
    with patch('mission_control.aeo_workflows.PublicReader',return_value=reader,side_effect=Invalid('PRIVATE_ERROR_6921') if fail else None):
        assert run_once(store)
    return next(j for j in jobs(store,'sample-one') if j['id']==job['id'])


class FeedbackTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.store=Store(Path(tmp.name)/'feedback.sqlite3');initialize(self.store)

    def test_feedback_and_public_codes_use_native_artifact_without_raw_page(self):
        job=inspect(self.store);value=feedback(self.store,self.store.app('sample-one'))
        self.assertEqual(value['latest'][0]['state'],'EVIDENCE_GATHERED')
        self.assertIn('H1',value['reusable_public_observation']['repair_codes'])
        self.assertNotIn('PRIVATE_',canonical(snapshot(self.store,'sample-one')))
        self.assertEqual(value['reusable_public_observation']['source_job_id'],job['id'])

    def test_selected_public_job_new_failure_blocks_old_success(self):
        inspect(self.store);inspect(self.store,fail=True)
        value=feedback(self.store,self.store.app('sample-one'))
        self.assertIsNone(value['reusable_public_observation'])
        self.assertEqual(value['latest'][0]['state'],'BLOCKED')
        self.assertNotIn('PRIVATE_ERROR',canonical(value))

    def test_recent_history_partial_coverage_is_explicit(self):
        inspect(self.store);inspect(self.store)
        with patch('mission_control.agent_feedback.LIMIT',1):value=feedback(self.store,self.store.app('sample-one'))
        self.assertEqual((value['coverage'],value['inspected'],value['omitted']),('PARTIAL_RECENT_WINDOW',1,1))

    def test_foreign_app_and_agent_jobs_do_not_change_feedback(self):
        before=feedback(self.store,self.store.app('sample-one'))
        with connection(self.store.path) as db:
            for app,action in [('sample-two','resolution'),('sample-one','agent_run')]:
                identity=str(uuid.uuid4());db.execute('INSERT INTO jobs(id,app_id,action,data,status,created,updated,request_key) VALUES(?,?,?,?,?,?,?,?)',
                    (identity,app,action,'{}','SUCCEEDED',now(),now(),identity))
        self.assertEqual(before,feedback(self.store,self.store.app('sample-one')))

    def test_valid_envelope_and_observation_reject_corruption_without_raw_disclosure(self):
        job=inspect(self.store)
        self.assertTrue(valid_envelope(job,self.store.app('sample-one')))
        job['data']=[];self.assertFalse(valid_envelope(job,self.store.app('sample-one')))
        with connection(self.store.path) as db:db.execute('UPDATE jobs SET data=? WHERE id=?',(canonical({'envelope':['PRIVATE_CORRUPTION']}),job['id']))
        value=feedback(self.store,self.store.app('sample-one'))
        self.assertEqual(value['latest'][0]['state'],'INVALID_OR_STALE')
        self.assertNotIn('PRIVATE_',canonical(value))

    def test_imported_and_changed_app_artifacts_are_not_reusable(self):
        job=inspect(self.store);identity=job['result']['artifacts'][0]['id']
        with connection(self.store.path) as db:db.execute("UPDATE aeo_checks SET origin='IMPORTED_ASSERTION' WHERE id=?",(identity,))
        self.assertIsNone(reuse_candidate(self.store,self.store.app('sample-one')))
        self.assertEqual(feedback(self.store,self.store.app('sample-one'))['latest'][0]['state'],'ARTIFACT_NOT_CURRENT')
        app=self.store.app('sample-one');self.store.save_app('sample-one',{**app['data'],'release':'changed'},app['version'])
        self.assertIsNone(reuse_candidate(self.store,self.store.app('sample-one')))

    def test_child_state_and_child_fingerprint_keep_failure_and_report_changes(self):
        parent=dict(app_id='sample-one',result=dict(children=['child-fixture']))
        self.assertEqual(child_state(self.store,'sample-one',['child-fixture']),'NEEDS_RESOLUTION')
        with connection(self.store.path) as db:
            db.execute("INSERT INTO jobs(id,app_id,action,data,status,result,created,updated,request_key) VALUES('child-fixture','sample-one','sync','{}','SUCCEEDED','{}',?,?,?)",(now(),now(),'child-fixture'))
        before=child_fingerprint(self.store,parent)
        self.assertEqual(child_state(self.store,'sample-one',['child-fixture']),'EVIDENCE_GATHERED')
        with connection(self.store.path) as db:db.execute("UPDATE jobs SET result=? WHERE id='child-fixture'",(canonical({'public':'changed'}),))
        self.assertNotEqual(before,child_fingerprint(self.store,parent))

    def test_malformed_child_indices_are_closed_typed_failures(self):
        self.assertEqual(child_state(self.store,'sample-one',[{'private':'bad'}]),'NEEDS_RESOLUTION')
        self.assertEqual(child_fingerprint(self.store,dict(app_id='sample-one',result=dict(children=[{}]))),'INVALID_CHILD_INDEX')

    def test_artifact_corruption_changes_feedback_and_invalidates_current_claim(self):
        job=inspect(self.store);before=snapshot(self.store,'sample-one')
        identity=job['result']['artifacts'][0]['id']
        with connection(self.store.path) as db:db.execute("UPDATE aeo_checks SET hash='broken' WHERE id=?",(identity,))
        after=snapshot(self.store,'sample-one')
        self.assertNotEqual(before,after)
        source=next(s for s in after['sources'] if s['id']=='action_feedback')
        self.assertEqual(source['data']['latest'][0]['state'],'ARTIFACT_NOT_CURRENT')


class FeedbackApprovalTests(unittest.TestCase):
    setUp=agent_fixtures.AgentTaskTests.setUp
    approve=agent_fixtures.AgentTaskTests.approve

    def ready(self):
        initialize(self.store)
        with connection(self.store.path) as db:db.execute("UPDATE agent_connections SET status='TESTED' WHERE id=?",(self.identity,))
        self.access.routes('sample-one',dict(version=0,mode='byok',routes={'campaign_plan':self.identity}))

    def change(self):return Resolutions(self.store).start('sample-one',request(self.store))

    def test_new_action_before_inference_invalidates_context(self):
        self.ready();job=self.approve('campaign_plan');self.change()
        with patch('mission_control.agent_tasks.api_run') as call:run_once(self.store);call.assert_not_called()
        self.assertEqual(next(j for j in jobs(self.store,'sample-one') if j['id']==job['id'])['status'],'BLOCKED')

    def test_new_action_during_inference_rejects_output(self):
        self.ready();job=self.approve('campaign_plan')
        def provider(*args):self.change();return answer(),{}
        with patch('mission_control.agent_tasks.api_run',side_effect=provider):run_once(self.store)
        self.assertEqual(next(j for j in jobs(self.store,'sample-one') if j['id']==job['id'])['status'],'BLOCKED')


if __name__=='__main__':unittest.main()
