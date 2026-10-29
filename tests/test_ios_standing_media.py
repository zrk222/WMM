"""Real policy/SQLite/native-host interlocks, with synthetic media and protected keys."""
import json
import sqlite3
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from mission_control.db import connection
from mission_control.common import Invalid
from mission_control.ios_provider_access import NativeProviderAccess
from mission_control.ios_agent_media import NativeAgentTimeline
from tests import test_ios_agent_media as base
from tests import test_ios_automation as standing
from tests.test_agent_access import body as provider_body


class NativeStandingMediaTests(unittest.TestCase):
    setUp=base.NativeAgentMediaTests.setUp
    verify=base.NativeAgentMediaTests.verify
    creation=base.NativeAgentMediaTests.creation
    adapter=base.NativeAgentMediaTests.adapter
    owned=base.NativeAgentMediaTests.owned
    upload=base.NativeAgentMediaTests.upload
    decision=base.NativeAgentMediaTests.decision
    prepare_fixture=base.NativeAgentMediaTests.prepare_fixture
    scene=base.NativeAgentMediaTests.scene
    vault=standing.NativeStandingTests.vault
    proposal=standing.NativeStandingTests.proposal

    def activate(self):
        self.values={};self.vault_available=True;self.runtime.vault_callback=self.vault
        saved=json.loads(NativeProviderAccess(self.runtime.service,self.runtime.identities,self.vault).call(
            self.session,'new-app','save',json.dumps(dict(confirm_storage=True,profile=provider_body())).encode()))
        self.profile=saved['connection']
        with connection(self.path) as db:
            db.execute("UPDATE agent_connections SET status='TESTED',last_test=? WHERE id=?",(datetime.now(timezone.utc).isoformat(),self.profile))
        proposal=self.proposal(['native_video_authoring']);proposal['limits']['max_calls']=20
        preview=json.loads(self.runtime.native_automation(self.session,'new-app','preview',json.dumps(proposal).encode()))
        self.assertEqual(preview['native_readiness'],'READY_FOR_SCOPE_REVIEW')
        operations=preview['summary']['operations']
        self.assertIn('ios.scene.start',operations);self.assertIn('ios.timeline.queue',operations)
        for forbidden in ('editor.queue','native.queue','hypit.queue','studio.start'):
            self.assertNotIn(forbidden,operations)
        self.issued=json.loads(self.runtime.native_automation(self.session,'new-app','activate',json.dumps(
            dict(proposal=preview['proposal'],summary_hash=preview['summary_hash'],confirm_scope=True)).encode()))
        return self.issued['token']

    def agent(self,operation,body):
        return json.loads(self.runtime.native_agent_call(self.session,self.issued['token'],json.dumps(
            dict(app_id='new-app',operation=operation,input=body)).encode()))

    def queue_scene(self):
        self.runtime.create_workspace(self.session,self.creation());self.activate()
        project=self.agent('ios.scene.save',dict(project_id='standing-scene',base_revision=0,manifest_version=1,request_key='scene-save',scene=self.scene()))
        self.scene_body=dict(project_id='standing-scene',revision=1,source_hash=project['source_hash'],request_key='scene-render')
        return self.agent('ios.scene.start',self.scene_body)['job']

    def queue_timeline(self):
        self.prepare_fixture();self.activate()
        self.timeline_body=dict(project_id=self.project['id'],revision=1,project_hash=self.project['hash'],request_key='standing-timeline')
        return self.agent('ios.timeline.queue',self.timeline_body)['job']

    def host(self,kind,action,job,proof=None):
        body=json.dumps(dict(job_id=job['job_id'],packet_hash=job['packet_hash'])).encode()
        if proof is None:
            method=self.runtime.native_studio if kind=='scene' else self.runtime.native_agent_timeline
            return json.loads(method(self.session,'new-app',action,body))
        method=self.runtime.native_studio_finish if kind=='scene' else self.runtime.native_agent_timeline_finish
        return json.loads(method(self.session,'new-app',body,json.dumps(proof).encode()))

    def proof(self,job):
        return dict(artifact_id=job['job_id'],sha256='a'*64,bytes=100,frames=24,width=720,height=1280,audio=False)

    def off(self):
        return json.loads(self.runtime.native_automation(self.session,'new-app','off',json.dumps(
            dict(id=self.issued['policy_id'],version=1,confirm_off=True)).encode()))

    def test_scene_exact_standing_job_validates_finishes_and_preserves_owner_artifact_after_off(self):
        job=self.queue_scene()
        self.assertEqual(self.host('scene','validate',job)['packet_hash'],job['packet_hash'])
        self.assertEqual(self.host('scene','finish',job,self.proof(job))['status'],'SUCCEEDED')
        self.off()
        artifact=json.loads(self.runtime.native_studio(self.session,'new-app','artifact',json.dumps({'job_id':job['job_id']}).encode()))
        self.assertEqual(artifact['status'],'SUCCEEDED')

    def test_timeline_completion_and_owner_receipt_after_off(self):
        job=self.queue_timeline()
        self.assertEqual(self.host('timeline','validate',job)['packet_hash'],job['packet_hash'])
        self.assertEqual(self.host('timeline','finish',job,self.proof(job))['status'],'SUCCEEDED')
        self.off()
        result=json.loads(self.runtime.native_agent_timeline(self.session,'new-app','artifact',json.dumps({'job_id':job['job_id']}).encode()))
        self.assertEqual(result['result'],self.proof(job))

    def test_pending_native_jobs_occupy_scope_slot_until_cancel(self):
        for kind in ('scene','timeline'):
            with self.subTest(kind=kind):
                # Use a separate fixture/store for each native job family.
                if kind=='timeline':self.setUp()
                job=self.queue_scene() if kind=='scene' else self.queue_timeline()
                operation='ios.scene.start' if kind=='scene' else 'ios.timeline.queue'
                body=self.scene_body if kind=='scene' else self.timeline_body
                with self.assertRaisesRegex(PermissionError,'occupied'):
                    self.agent(operation,dict(body,request_key='second-native-job'))
                self.agent('ios.'+kind+'.cancel',{'job_id':job['job_id']})
                second=self.agent(operation,dict(body,request_key='second-native-job'))['job']
                self.assertNotEqual(second['job_id'],job['job_id'])

    def test_off_cancels_own_pending_render_and_denies_finish(self):
        job=self.queue_scene();self.off()
        state=json.loads(self.runtime.native_studio(self.session,'new-app','inspect',json.dumps({'job_id':job['job_id']}).encode()))
        self.assertEqual(state['status'],'CANCELLED')
        with self.assertRaises((Invalid,PermissionError)):self.host('scene','finish',job,self.proof(job))

    def test_missing_native_access_cannot_borrow_desktop_or_owner_authority(self):
        job=self.queue_timeline();body=json.dumps(dict(job_id=job['job_id'],packet_hash=job['packet_hash'])).encode()
        with self.assertRaisesRegex(PermissionError,'native protected-access'):
            NativeAgentTimeline(self.runtime.service,self.runtime.identities).call(self.session,'new-app','validate',body)
        self.vault_available=False
        with self.assertRaises((Invalid,PermissionError)):self.host('timeline','validate',job)
        self.vault_available=True;self.runtime.vault_callback=None
        with self.assertRaises((Invalid,PermissionError)):self.host('timeline','validate',job)

    def test_key_revocation_during_decode_rolls_back_output_commit(self):
        job=self.queue_timeline();original=NativeAgentTimeline.validate_inspection
        def revoke(*args):
            original(*args);self.vault_available=False
        with patch.object(NativeAgentTimeline,'validate_inspection',side_effect=revoke):
            with self.assertRaises((Invalid,PermissionError)):self.host('timeline','finish',job,self.proof(job))
        with connection(self.path) as db:
            self.assertEqual(db.execute('SELECT status FROM ios_agent_timeline_jobs WHERE id=?',(job['job_id'],)).fetchone()[0],'PREPARED')

    def test_provenance_cannot_be_replaced_deleted_or_replayed_under_new_execution(self):
        job=self.queue_scene()
        # Concurrency does not permit a new queue to adopt this pending intent.
        with self.assertRaises(PermissionError):self.agent('ios.scene.start',self.scene_body)
        with connection(self.path) as db:
            scope=dict(db.execute('SELECT rowid,* FROM ios_agent_media_standing').fetchone())
            origin=dict(db.execute('SELECT rowid,* FROM ios_agent_media_authority').fetchone())
        for table,row in [('ios_agent_media_standing',scope),('ios_agent_media_authority',origin)]:
            for sql,args in [(f'DELETE FROM {table} WHERE rowid=?',(row['rowid'],)),
                             (f'UPDATE {table} SET job_id=? WHERE rowid=?',('changed',row['rowid'])),
                             (f'INSERT OR REPLACE INTO {table}('+','.join(row)+') VALUES('+','.join('?' for _ in row)+')',tuple(row.values())),
                             (f'INSERT OR REPLACE INTO {table}('+','.join(row)+') VALUES('+','.join('?' for _ in row)+')',tuple(dict(row,job_id='changed-rowid-target').values()))]:
                with self.subTest(table=table,sql=sql), self.assertRaisesRegex(sqlite3.IntegrityError,'immutable'):
                    with connection(self.path) as db:db.execute(sql,args)
        self.assertEqual(self.host('scene','validate',job)['packet_hash'],job['packet_hash'])

    def test_completed_intent_cannot_be_adopted_by_a_new_standing_execution(self):
        job=self.queue_scene();self.host('scene','finish',job,self.proof(job))
        with connection(self.path) as db:original=db.execute('SELECT execution_id FROM ios_agent_media_standing').fetchone()[0]
        with self.assertRaisesRegex(PermissionError,'another standing execution'):
            self.agent('ios.scene.start',self.scene_body)
        with connection(self.path) as db:
            self.assertEqual(db.execute('SELECT execution_id FROM ios_agent_media_standing').fetchone()[0],original)

    def test_expired_scope_denies_pending_completion_and_owner_can_cancel(self):
        job=self.queue_scene()
        with patch('mission_control.complete_automation.utc',return_value=datetime.now(timezone.utc)+timedelta(hours=2)):
            with self.assertRaisesRegex(PermissionError,'expired'):self.host('scene','validate',job)
        result=json.loads(self.runtime.native_studio(self.session,'new-app','cancel',json.dumps({'job_id':job['job_id']}).encode()))
        self.assertEqual(result['status'],'CANCELLED')

    def test_timeline_source_read_requires_current_standing_key_and_scope(self):
        job=self.queue_timeline()
        body=json.dumps(dict(job_id=job['job_id'],packet_hash=job['packet_hash'],kind='MANAGED',source_id=self.item['id'],sha256=self.item['source_sha256'])).encode()
        result=json.loads(self.runtime.native_agent_timeline_source(self.session,'new-app',body))
        self.assertTrue(result['path'])
        self.vault_available=False
        with self.assertRaises((Invalid,PermissionError)):self.runtime.native_agent_timeline_source(self.session,'new-app',body)
        self.vault_available=True;self.off()
        with self.assertRaises((Invalid,PermissionError)):self.runtime.native_agent_timeline_source(self.session,'new-app',body)

    def test_native_readiness_requires_current_owner_and_exact_device_store(self):
        from types import SimpleNamespace
        from mission_control.automation_requirements import Readiness
        from mission_control.ios_execution_context import DEVICE_HOST,native_device_context
        self.queue_scene()
        reader=Readiness(self.runtime.service.store);owner=self.runtime.identities.fresh(self.session)
        selected=self.proposal(['native_video_authoring'])['selection']
        def readiness():return reader.report('new-app',owner,selected)['inventory']
        outside=readiness()
        self.assertEqual(outside['scope_status'],'BLOCKED')
        self.assertIn('CURRENT_NATIVE_DEVICE_HOST_REQUIRED',outside['workflows'][0]['blockers'])
        foreign=SimpleNamespace(store=SimpleNamespace(path=self.path.parent/'foreign.sqlite3'))
        with native_device_context(foreign,self.runtime.identities,self.session):
            self.assertEqual(readiness()['scope_status'],'BLOCKED')
        with native_device_context(self.runtime.service,self.runtime.identities,self.session):
            self.assertEqual(readiness()['scope_status'],'READY_FOR_SCOPE_REVIEW')
            self.available=False
            with self.assertRaises(PermissionError):readiness()
        self.available=True
        self.assertIsNone(DEVICE_HOST.get())
