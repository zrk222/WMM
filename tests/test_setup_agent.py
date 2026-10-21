"""Approved agent reads create drafts, never self-approved app changes."""
from copy import deepcopy
from datetime import timedelta
import uuid
from unittest.mock import patch
from mission_control.common import Invalid, digest, iso_time, now
from mission_control.resolutions import Resolutions
from mission_control.resolution_tools import execute
from mission_control.store import Store
from mission_control.worker import run_once, jobs
from tests.test_setup_discovery import SetupFixture
from tests.test_aeo_inspection import Reader, ROOT


class SetupAgentTests(SetupFixture):
    def request(self):
        resolver=Resolutions(self.store)
        app,plan=resolver.proposal('sample-one')
        issue=plan['issues'][0]
        option=next(item for item in issue['options'] if item['tool']=='discover_setup')
        self.assertTrue(option['ready'])
        return dict(issue_id=issue['id'],option_id=option['id'],source_hash=issue['source_hash'],
                    target_url=None,request_key=str(uuid.uuid4()))

    def test_worker_saves_reviewable_draft_without_manifest_mutation(self):
        before=self.store.app('sample-one')
        job=Resolutions(self.store).start('sample-one',self.request())
        with patch('mission_control.setup_discovery.PublicReader',return_value=Reader()):
            self.assertTrue(run_once(self.store))
        current=next(row for row in jobs(self.store,'sample-one') if row['id']==job['id'])
        self.assertEqual(current['status'],'SUCCEEDED')
        history=Resolutions(Store(self.store.path)).history('sample-one')[0]
        self.assertEqual(history['status'],'EVIDENCE_GATHERED')
        artifact=history['artifacts'][0]
        self.assertEqual(artifact['kind'],'setup_proposal')
        draft=self.service.get('sample-one',artifact['id'])
        self.assertEqual(draft['hash'],artifact['sha256'])
        self.assertEqual(draft['currentness'],'PENDING')
        self.assertEqual(self.store.app('sample-one'),before)
        self.assertFalse(history['automatically_verified'])

    def test_expired_changed_policy_and_foreign_scope_stop_before_read(self):
        job=Resolutions(self.store).start('sample-one',self.request())
        expired=deepcopy(job['data'])
        expired['envelope']['expires_at']=(iso_time(now())-timedelta(seconds=1)).isoformat()
        expired['envelope_hash']=digest(expired['envelope'])
        with patch('mission_control.setup_discovery.PublicReader') as read:
            with self.assertRaises(Invalid):execute(self.store,'sample-one',expired)
            with self.assertRaises(Invalid):execute(self.store,'sample-two',job['data'])
            with patch('mission_control.resolution_tools.operating_manifest',return_value={'policy_version':0}):
                with self.assertRaises(Invalid):execute(self.store,'sample-one',job['data'])
            app=self.store.app('sample-one')
            self.store.save_app('sample-one',{**app['data'],'name':'Changed'},app['version'])
            with self.assertRaises(Invalid):execute(self.store,'sample-one',job['data'])
            read.assert_not_called()

    def test_denied_robots_returns_resolution_and_no_applied_fields(self):
        reader=Reader(robots='User-agent: *\nDisallow: /')
        job=Resolutions(self.store).start('sample-one',self.request())
        with patch('mission_control.setup_discovery.PublicReader',return_value=reader):
            value=execute(self.store,'sample-one',job['data'])
        self.assertEqual(value['status'],'NEEDS_RESOLUTION')
        self.assertFalse(value['external_writes'])
        self.assertEqual(value['spend_minor'],0)
        self.assertEqual(reader.calls,[(ROOT+'/robots.txt',512000)])
        self.assertEqual(self.service.list('sample-one')['proposals'][0]['state'],'NEEDS_RESOLUTION')

    def test_no_arbitrary_url_edit_or_self_approval_authority(self):
        body=self.request()
        with self.assertRaises(Invalid):Resolutions(self.store).start('sample-one',{**body,'target_url':'https://foreign.example/'})
        with self.assertRaises(Invalid):Resolutions(self.store).start('sample-one',{**body,'changes':{'name':'Injected'}})
