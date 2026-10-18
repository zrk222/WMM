"""Exact-approved tracking dispatch, durable parent truth and cancellation boundaries."""
import json,unittest,uuid
from unittest.mock import patch
from mission_control.common import Invalid
from mission_control.db import connection
from mission_control.store import Store
from mission_control.sequence_store import Sequences
from mission_control.worker import run_once
from mission_control.experiment_tracking import Tracking
from mission_control.resolutions import Resolutions
from mission_control.tracking_resolution import options,validate,dispatch
from mission_control.source_progress import read_state
from tests import test_experiment_tracking as fixtures
from tests.test_tracking_contract import payload
from mission_control.tracking_contract import shape


class TrackingSequenceTests(unittest.TestCase):
    setUp=fixtures.ExperimentTrackingTests.setUp
    secret=fixtures.ExperimentTrackingTests.secret
    job=fixtures.ExperimentTrackingTests.job

    def approve(self):
        service=Sequences(self.store);_,proposal=service.proposal('sample-one')
        steps=[s for s in proposal['steps'] if s['tool']=='inspect_tracking']
        self.assertEqual(len(steps),1)
        body=dict(proposal_hash=proposal['proposal_hash'],selected_steps=[steps[0]['id']],
                  request_key=str(uuid.uuid4()))
        run=service.approve('sample-one',body)
        return service,run

    def dispatch(self):
        service,run=self.approve();self.assertTrue(run_once(self.store))
        child=self.tracking.list('sample-one')[0]
        return service,run,child

    def finish(self,value=None,side_effect=None):
        with patch('mission_control.experiment_tracking.Vault.get',return_value=self.secret()), \
             patch('mission_control.experiment_tracking.tracking_posthog.read',return_value=value or shape(payload()),side_effect=side_effect) as read:
            run_once(self.store)
        return read

    def test_proposal_exposes_exact_scope_and_rejects_stale_source(self):
        w=__import__('mission_control.service',fromlist=['Service']).Service(self.store).workspace('sample-one')
        choice=next(o for o in w['resolutions']['issues'][0]['options'] if o['tool']=='inspect_tracking')
        p=choice['parameters'];plan=p['tracking_plan']
        for field in ('experiment_id','source_id','release','locale','starts_at','ends_at'):
            self.assertIn(plan[field],p['name'])
        self.assertEqual(validate(self.store,'sample-one',p),plan)
        with connection(self.store.path) as db:db.execute("UPDATE insight_sources SET version=2 WHERE app_id='sample-one'")
        with self.assertRaises(Invalid):validate(self.store,'sample-one',p)
        with self.assertRaises(Invalid):validate(self.store,'sample-two',p)

    def test_options_are_bounded_and_never_offer_foreign_cancelled_or_denied_sources(self):
        insights=dict(sources=[self.source]*3)
        self.assertEqual(len(options(self.app,insights,[self.experiment]*3)),3)
        for change in ({'state':'CANCELLED'},{'app_id':'sample-two'}):
            self.assertEqual(options(self.app,insights,[{**self.experiment,**change}]),[])
        denied=options(self.app,dict(sources=[{**self.source,'status':'PERMISSION_REQUIRED'}]),[self.experiment])
        self.assertFalse(denied[0]['ready'])

    def test_dispatch_replays_once_and_preserves_original_expiry_and_restart(self):
        service,run,child=self.dispatch()
        parent=child['plan']['resolution_envelope']
        with connection(self.store.path) as db:
            data=json.loads(db.execute("SELECT data FROM jobs WHERE action='resolution'").fetchone()[0])
            links=db.execute('SELECT owned FROM sequence_jobs WHERE job_id=?',(child['job_id'],)).fetchall()
        self.assertEqual([r[0] for r in links],[1])
        self.assertEqual(child['expires'],parent['expires_at'])
        self.assertEqual(child['plan']['approved_at'],parent['approved_at'])
        again=dispatch(self.store,'sample-one',parent,data['original_request']['request_key'],None)
        self.assertEqual(again['children'],[child['job_id']]);self.assertEqual(len(self.tracking.list('sample-one')),1)
        self.assertEqual(Tracking(Store(self.store.path)).get('sample-one',child['id']),child)
        self.assertEqual(read_state(self.store,'sample-one',[child['job_id']]),'COLLECTING_SOURCES')
        self.assertEqual(service.history('sample-one')[0]['checkpoint'],0)

    def test_worker_finishes_native_tracking_before_parent_adopts_partial_evidence(self):
        service,run,child=self.dispatch();read=self.finish();self.assertEqual(read.call_count,1)
        self.assertEqual(read_state(self.store,'sample-one',[child['job_id']]),'EVIDENCE_GATHERED')
        run_once(self.store);result=service.history('sample-one')[0]
        self.assertEqual(result['state'],'EVIDENCE_REVIEW_REQUIRED')
        self.assertEqual(result['step_outcomes'][0]['state'],'EVIDENCE_GATHERED')
        self.assertFalse(result['automatically_verified'])
        self.assertEqual(self.tracking.get('sample-one',child['id'])['status'],'OBSERVED')

    def test_successful_worker_with_missing_setup_or_no_events_needs_resolution(self):
        for status in ('NEEDS_SETUP','NO_OBSERVATIONS','NEEDS_REVIEW'):
            with self.subTest(status=status):
                service,run,child=self.dispatch()
                self.finish(dict(status=status,next_actions=['Review setup']))
                run_once(self.store)
                self.assertEqual(service.history('sample-one')[0]['step_outcomes'][0]['state'],'NEEDS_RESOLUTION')

    def test_cancelled_sequence_stops_queued_child_before_network(self):
        service,run,child=self.dispatch()
        service.cancel('sample-one',run['id'],dict(confirm_cancel=True))
        read=self.finish();read.assert_not_called()
        self.assertEqual(self.job(child)['status'],'CANCELLED')
        self.assertEqual(read_state(self.store,'sample-one',[child['job_id']]),'NEEDS_RESOLUTION')

    def test_inflight_cancel_never_adopts_result(self):
        service,run,child=self.dispatch()
        def remote(*args):
            service.cancel('sample-one',run['id'],dict(confirm_cancel=True));return shape(payload())
        self.finish(side_effect=remote)
        self.assertIsNone(self.tracking.get('sample-one',child['id'])['result'])
        self.assertEqual(self.job(child)['status'],'CANCELLED')

    def test_parent_expiry_and_source_drift_prevent_network(self):
        _,_,child=self.dispatch()
        with patch('mission_control.experiment_tracking.now',return_value='2999-01-01T00:00:00+00:00'):
            read=self.finish()
        read.assert_not_called()
        _,_,child=self.dispatch()
        with connection(self.store.path) as db:db.execute("UPDATE insight_sources SET version=2 WHERE app_id='sample-one'")
        read=self.finish();read.assert_not_called()

    def test_direct_resolution_uses_same_approval_and_native_history(self):
        api=Resolutions(self.store);_,plan=api.proposal('sample-one');issue=plan['issues'][0]
        option=next(o for o in issue['options'] if o['tool']=='inspect_tracking')
        body=dict(issue_id=issue['id'],option_id=option['id'],source_hash=issue['source_hash'],target_url=None,request_key=str(uuid.uuid4()))
        api.start('sample-one',body);run_once(self.store);child=self.tracking.list('sample-one')[0]
        self.finish();history=api.history('sample-one')
        self.assertEqual(history[0]['status'],'EVIDENCE_GATHERED')
        self.assertEqual(history[0]['artifacts'][0]['id'],child['id'])
        self.assertFalse(history[0]['automatically_verified'])

    def test_tracking_state_corrupt_or_missing_native_receipt_cannot_satisfy_parent(self):
        _,_,child=self.dispatch();self.finish()
        with connection(self.store.path) as db:db.execute("UPDATE experiment_tracking_runs SET result_hash='wrong' WHERE id=?",(child['id'],))
        self.assertEqual(read_state(self.store,'sample-one',[child['job_id']]),'NEEDS_RESOLUTION')

    def test_atomic_child_registration_rolls_back_when_owner_rejects_link(self):
        _,_,child=self.dispatch();parent=child['plan']['resolution_envelope']
        def refuse(*args):raise Invalid('Owner cancelled before atomic registration')
        with self.assertRaises(Invalid):dispatch(self.store,'sample-one',parent,str(uuid.uuid4()),refuse)
        self.assertEqual(len(self.tracking.list('sample-one')),1)

    def test_require_body_identifier_fields_and_decoded_fields_reject_ambiguous_authority(self):
        from mission_control.experiment_tracking import require_body,identifier_fields,decoded_fields
        for value in ({'experiment_id':[], 'source_id':'source'}, {'experiment_id':'test','source_id':{}}):
            with self.assertRaises(Invalid):identifier_fields(value)
        with self.assertRaises(Invalid):require_body(dict(confirm_read=1))
        with self.assertRaises(ValueError):decoded_fields(dict(plan='[]',original_request='{}',result=None))

    def test_collect_preserves_owned_child_callback_and_truthful_waiting_state(self):
        from mission_control.resolution_tools import collect
        frozen=dict(manifest_version=7,parameters=dict(collection_hash='synthetic'))
        callback=lambda *args:None
        with patch('mission_control.campaign_inputs.CampaignInputs.start',return_value=dict(tasks=[dict(job=dict(id='synthetic-child'))])) as start:
            value=collect(self.store,'sample-one',frozen,on_job=callback)
        self.assertEqual(start.call_args.args,('sample-one',dict(manifest_version=7,source_hash='synthetic'),callback))
        self.assertEqual(value['status'],'WAITING_FOR_SOURCES')
        self.assertFalse(value['automatically_verified'])


if __name__=='__main__':unittest.main()
