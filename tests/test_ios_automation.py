"""Native callback and real SQLite standing controls; no device acceptance claim."""
from datetime import datetime, timedelta, timezone
import json
import unittest
from unittest.mock import patch
from uuid import uuid4

from mission_control.common import Invalid
from mission_control.db import connection
from mission_control.ios_agent_access import NativeAgentAccess
from mission_control.ios_automation import NativeAutomation, native_access
from mission_control.ios_provider_access import NativeProviderAccess
from tests import test_ios_host as fixture
from tests.test_agent_access import body as provider_body


class NativeStandingTests(unittest.TestCase):
    setUp = fixture.NativeRuntimeTests.setUp
    verify = fixture.NativeRuntimeTests.verify
    creation = fixture.NativeRuntimeTests.creation

    def setup_standing(self):
        self.runtime.create_workspace(self.session, self.creation())
        self.values = {}
        self.vault_available = True
        self.adapter = NativeAutomation(self.runtime.service, self.runtime.identities, self.vault)
        provider = NativeProviderAccess(self.runtime.service, self.runtime.identities, self.vault)
        payload = json.dumps(dict(confirm_storage=True, profile=provider_body())).encode()
        saved = json.loads(provider.call(self.session, 'new-app', 'save', payload))
        self.profile = saved['connection']
        with connection(self.path) as db:
            db.execute("UPDATE agent_connections SET status='TESTED',last_test=? WHERE id=?",
                       (datetime.now(timezone.utc).isoformat(), self.profile))

    def vault(self, payload):
        request = json.loads(payload)
        if not self.vault_available:
            return b'{"ok":false,"value":null}'
        if request['action'] == 'put': self.values[request['target']] = request['value']
        if request['action'] == 'delete': self.values.pop(request['target'], None)
        return json.dumps(dict(ok=True, value=self.values.get(request['target']) if request['action'] == 'get' else None)).encode()

    def manage(self, action, body=None, app='new-app'):
        return json.loads(self.adapter.manage(self.session, app, action, json.dumps(body if body is not None else {}).encode()))

    def proposal(self, workflows=None):
        return dict(selection=dict(agent_id='native-agent', manifest_version=1,
                    workflows=workflows or ['local_evidence'], agent_connection_id=self.profile,
                    social_connection_ids=[]), purpose='Prepare synthetic local evidence',
                    limits=dict(expires=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),
                                max_calls=3, max_inflight=1, currency='USD', spend_limit_minor=0))

    def activate(self):
        preview = self.manage('preview', self.proposal())
        return self.manage('activate', dict(proposal=preview['proposal'], summary_hash=preview['summary_hash'], confirm_scope=True))

    def test_preview_activate_admit_status_and_off_use_real_shared_policy(self):
        self.setup_standing()
        issued = self.activate()
        self.assertEqual(issued['status'], 'ACTIVE')
        self.assertEqual(issued['native_execution_acceptance'], 'INCOMPLETE')
        agent = NativeAgentAccess(self.runtime.service, self.runtime.identities)
        request = json.dumps(dict(app_id='new-app', operation='workspace.read', input={})).encode()
        with native_access(self.runtime.service, self.runtime.identities, self.session, self.vault):
            result = json.loads(agent.call(self.session, issued['token'], request))
        self.assertEqual(result['app']['id'], 'new-app')
        status = self.manage('status')
        self.assertEqual(status['policies'][0]['usage']['used'], 1)
        blockers = {item['workflow']: item['reason'] for item in status['native_blockers']}
        self.assertNotIn('pipeline_preparation', blockers)
        self.assertEqual(blockers['native_screen_render'], 'NATIVE_SCREEN_RENDER_ADAPTER_REQUIRED')
        self.assertNotIn('local_evidence', blockers)
        self.assertNotIn(issued['token'], json.dumps(status))
        self.assertNotIn(provider_body()['api_key'], json.dumps(status))
        off = self.manage('off', dict(id=issued['policy_id'], version=1, confirm_off=True))
        self.assertEqual(off['status'], 'OFF')
        with native_access(self.runtime.service, self.runtime.identities, self.session, self.vault):
            with self.assertRaises(PermissionError): agent.call(self.session, issued['token'], request)

    def test_stale_scope_foreign_locked_and_desktop_provider_deny_without_grant(self):
        self.setup_standing()
        preview = self.manage('preview', self.proposal())
        confirm = dict(proposal=preview['proposal'], summary_hash=preview['summary_hash'], confirm_scope=True)
        with connection(self.path) as db: db.execute('UPDATE agent_connections SET version=version+1 WHERE id=?', (self.profile,))
        with self.assertRaises(Invalid): self.manage('activate', confirm)
        self.vault_available = False
        with self.assertRaises(Invalid): self.activate()
        self.vault_available = True
        with connection(self.path) as db: db.execute("UPDATE agent_connections SET data=json_set(data,'$.provider','codex') WHERE id=?", (self.profile,))
        with self.assertRaises(Invalid): self.activate()
        self.principal = str(uuid4())
        with self.assertRaises(PermissionError): self.manage('status')
        self.available = False
        with self.assertRaises(PermissionError): self.manage('status')
        with connection(self.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM automation_policies').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT count(*) FROM agent_grants').fetchone()[0], 0)

    def test_fixed_envelopes_and_unsupported_workflows_fail_closed(self):
        self.setup_standing()
        for workflow in ('native_screen_render', 'video_authoring_editing'):
            preview = self.manage('preview', self.proposal([workflow]))
            self.assertEqual(preview['native_readiness'], 'BLOCKED')
            self.assertTrue(preview['blockers'][0]['reason'].startswith('NATIVE_'))
            with self.assertRaises(Invalid):
                self.manage('activate', dict(proposal=preview['proposal'], summary_hash='x', confirm_scope=True))
        for action, body in [('status', {'principal':'owner'}), ('off', {'id':'x','version':1}),
                             ('activate', {'proposal':{},'summary_hash':'x','confirm_scope':True,'token':'x'}),
                             ('shell', {})]:
            with self.subTest(action=action), self.assertRaises(Invalid): self.manage(action, body)

    def test_lock_before_commit_rolls_back_grant_and_verifier_context_restores(self):
        import mission_control.complete_automation as core
        self.setup_standing()
        original = core.audit
        def lock_after_audit(db, app, action, data):
            original(db, app, action, data)
            if action == 'automation.owner_confirmed': self.available = False
        with patch.object(core, 'audit', side_effect=lock_after_audit):
            with self.assertRaises(PermissionError): self.activate()
        self.assertIsNone(core.ACCESS_VERIFIER.get())
        with connection(self.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM automation_policies').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT count(*) FROM agent_grants').fetchone()[0], 0)
        self.available = True
        with self.assertRaisesRegex(RuntimeError, 'synthetic'):
            with native_access(self.runtime.service, self.runtime.identities, self.session, self.vault):
                raise RuntimeError('synthetic')
        self.assertIsNone(core.ACCESS_VERIFIER.get())

    def test_vault_lock_before_commit_rolls_back_policy_and_grant(self):
        import mission_control.complete_automation as core
        self.setup_standing()
        original = core.audit
        def lock_after_audit(db, app, action, data):
            original(db, app, action, data)
            if action == 'automation.owner_confirmed': self.vault_available = False
        with patch.object(core, 'audit', side_effect=lock_after_audit):
            with self.assertRaises(Invalid): self.activate()
        with connection(self.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM automation_policies').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT count(*) FROM agent_grants').fetchone()[0], 0)

    def test_admission_rechecks_native_vault_quota_and_credential_revision(self):
        self.setup_standing()
        issued = self.activate()
        agent = NativeAgentAccess(self.runtime.service, self.runtime.identities)
        request = json.dumps(dict(app_id='new-app', operation='workspace.read', input={})).encode()
        def call():
            with native_access(self.runtime.service, self.runtime.identities, self.session, self.vault):
                return agent.call(self.session, issued['token'], request)
        self.vault_available = False
        with self.assertRaises(Invalid): call()
        self.assertEqual(self.manage('status')['policies'][0]['usage']['used'], 0)
        self.vault_available = True
        for _ in range(3): call()
        with self.assertRaises(PermissionError): call()
        with connection(self.path) as db:
            db.execute('UPDATE agent_connections SET version=version+1 WHERE id=?', (self.profile,))
        self.assertEqual(self.manage('status')['policies'][0]['effective_status'], 'BLOCKED')

    def test_vault_lock_during_standing_business_write_rolls_back_commit(self):
        from mission_control.growth_review_store import GrowthReviews
        from tests.test_aso_validation import listing
        self.setup_standing()
        issued = self.activate()
        agent = NativeAgentAccess(self.runtime.service, self.runtime.identities)
        data = dict(id='native-listing', manifest_version=1, kind='ASO_LISTING',
                    data=dict(release='build-1', listing=listing()))
        request = json.dumps(dict(app_id='new-app', operation='growth.save', input=data)).encode()
        original = GrowthReviews.commit
        def lock_after_write(reviews, *args):
            result = original(reviews, *args)
            self.vault_available = False
            return result
        with patch.object(GrowthReviews, 'commit', lock_after_write):
            with native_access(self.runtime.service, self.runtime.identities, self.session, self.vault):
                with self.assertRaises(Invalid): agent.call(self.session, issued['token'], request)
        with connection(self.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM growth_review_entries').fetchone()[0], 0)

    def test_standing_pipeline_queue_run_and_off_are_owner_and_scope_bound(self):
        from mission_control.ios_jobs import NativeJobs, native_pipeline_context
        self.setup_standing()
        preview = self.manage('preview', self.proposal(['pipeline_preparation']))
        issued = self.manage('activate', dict(proposal=preview['proposal'], summary_hash=preview['summary_hash'], confirm_scope=True))
        agent = NativeAgentAccess(self.runtime.service, self.runtime.identities)
        missing_host = json.dumps(dict(app_id='new-app', operation='pipeline.prepare',
            input=dict(action='pipeline', data=dict(stage=1), request_key='missing-host'))).encode()
        with native_access(self.runtime.service, self.runtime.identities, self.session, self.vault):
            with self.assertRaises(PermissionError): agent.call(self.session, issued['token'], missing_host)
        with connection(self.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM jobs').fetchone()[0], 0)
        payload = json.dumps(dict(app_id='new-app', operation='pipeline.prepare',
            input=dict(action='pipeline', data=dict(stage=1), request_key='native-standing-1'))).encode()
        with native_access(self.runtime.service, self.runtime.identities, self.session, self.vault):
            with native_pipeline_context(self.runtime.service, self.runtime.identities, self.session):
                queued = json.loads(agent.call(self.session, issued['token'], payload))
        self.assertEqual(queued['data']['native_runtime'], 'IOS_LOCAL_V1')
        self.assertIn('source_hash', queued['data'])
        jobs = NativeJobs(self.runtime.service, self.runtime.identities)
        with native_access(self.runtime.service, self.runtime.identities, self.session, self.vault):
            result = json.loads(jobs.call(self.session, 'new-app', 'run', json.dumps(dict(id=queued['id'])).encode()))
        self.assertEqual(result['status'], 'SUCCEEDED')
        self.assertEqual(result['attempts'], 1)
        with connection(self.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM automation_job_scopes WHERE job_id=?', (queued['id'],)).fetchone()[0], 1)
        self.manage('off', dict(id=issued['policy_id'], version=1, confirm_off=True))
        with native_access(self.runtime.service, self.runtime.identities, self.session, self.vault):
            with self.assertRaises(PermissionError): agent.call(self.session, issued['token'], payload)

    def test_standing_pipeline_off_lock_foreign_and_live_lease_deny(self):
        from mission_control.ios_jobs import NativeJobs, native_pipeline_context
        self.setup_standing()
        preview = self.manage('preview', self.proposal(['pipeline_preparation']))
        issued = self.manage('activate', dict(proposal=preview['proposal'], summary_hash=preview['summary_hash'], confirm_scope=True))
        agent = NativeAgentAccess(self.runtime.service, self.runtime.identities)
        def enqueue(key):
            payload = json.dumps(dict(app_id='new-app', operation='pipeline.prepare',
                input=dict(action='pipeline', data=dict(stage=1), request_key=key))).encode()
            with native_access(self.runtime.service, self.runtime.identities, self.session, self.vault):
                with native_pipeline_context(self.runtime.service, self.runtime.identities, self.session):
                    return json.loads(agent.call(self.session, issued['token'], payload))
        queued = enqueue('standing-off')
        jobs = NativeJobs(self.runtime.service, self.runtime.identities)
        payload = json.dumps(dict(id=queued['id'])).encode()
        self.vault_available = False
        with native_access(self.runtime.service, self.runtime.identities, self.session, self.vault):
            with self.assertRaises(Invalid): jobs.call(self.session, 'new-app', 'run', payload)
        self.vault_available = True
        original = self.principal
        self.principal = str(uuid4())
        with self.assertRaises(PermissionError): jobs.call(self.session, 'new-app', 'run', payload)
        self.principal = original
        import time
        with connection(self.path) as db:
            db.execute("UPDATE jobs SET status='RUNNING',attempts=1,lease=? WHERE id=?", (time.time()+60, queued['id']))
        with native_access(self.runtime.service, self.runtime.identities, self.session, self.vault):
            with self.assertRaises(Invalid): jobs.call(self.session, 'new-app', 'run', payload)
        self.manage('off', dict(id=issued['policy_id'], version=1, confirm_off=True))
        with connection(self.path) as db:
            self.assertEqual(db.execute('SELECT status FROM jobs WHERE id=?', (queued['id'],)).fetchone()[0], 'CANCELLED')

    def test_standing_worker_expiring_lease_fences_progress_and_unrelated_job(self):
        import time
        from types import SimpleNamespace
        from mission_control import automation_execution, workflow_telemetry
        from mission_control.ios_jobs import NativeJobs, native_pipeline_context
        self.setup_standing()
        preview = self.manage('preview', self.proposal(['pipeline_preparation']))
        issued = self.manage('activate', dict(proposal=preview['proposal'], summary_hash=preview['summary_hash'], confirm_scope=True))
        agent = NativeAgentAccess(self.runtime.service, self.runtime.identities)
        payload = json.dumps(dict(app_id='new-app', operation='pipeline.prepare',
            input=dict(action='pipeline', data=dict(stage=1), request_key='expires'))).encode()
        with native_access(self.runtime.service, self.runtime.identities, self.session, self.vault):
            with native_pipeline_context(self.runtime.service, self.runtime.identities, self.session):
                queued = json.loads(agent.call(self.session, issued['token'], payload))
        jobs = NativeJobs(self.runtime.service, self.runtime.identities)
        unrelated = jobs.queue('new-app', self.runtime.identities.fresh(self.session), dict(stage=1, request_key='unrelated'))
        observed = [time.time()]
        emit = workflow_telemetry.emit
        def expire_before_emit(*args, **kwargs):
            observed[0] += 120
            return emit(*args, **kwargs)
        with patch.object(automation_execution, 'time', SimpleNamespace(time=lambda: observed[0])):
            with patch.object(workflow_telemetry, 'emit', expire_before_emit):
                with native_access(self.runtime.service, self.runtime.identities, self.session, self.vault):
                    with self.assertRaises(PermissionError):
                        jobs.call(self.session, 'new-app', 'run', json.dumps(dict(id=queued['id'])).encode())
        with connection(self.path) as db:
            self.assertEqual(db.execute('SELECT status FROM jobs WHERE id=?', (unrelated['id'],)).fetchone()[0], 'QUEUED')
            self.assertEqual(db.execute('SELECT status FROM jobs WHERE id=?', (queued['id'],)).fetchone()[0], 'RUNNING')

    def test_native_pipeline_refuses_desktop_connection_vault_and_changed_sources(self):
        from mission_control.ios_jobs import NativeJobs
        self.setup_standing()
        user = self.runtime.identities.fresh(self.session)
        jobs = NativeJobs(self.runtime.service, self.runtime.identities)
        queued = jobs.queue('new-app', user, dict(stage=1, request_key='source-bound'))
        with connection(self.path) as db:
            db.execute('INSERT INTO records VALUES(?,?,?,?,?,?,?,?,?,?)',
                ('source','new-app','connection','Synthetic',json.dumps(dict(credential_ref='synthetic')), 'test','test','hash',1,'2026-01-01'))
        with patch('mission_control.connection_setup.Vault', side_effect=AssertionError('desktop vault used')):
            with self.assertRaisesRegex(Invalid, 'NATIVE_CONNECTION_STATUS_ADAPTER_REQUIRED'):
                jobs.queue('new-app', user, dict(stage=1, request_key='blocked'))
            with self.assertRaisesRegex(Invalid, 'Source evidence changed'):
                jobs.call(self.session, 'new-app', 'run', json.dumps(dict(id=queued['id'])).encode())

    def test_standing_agent_can_cancel_only_its_policy_job(self):
        from mission_control.ios_jobs import NativeJobs, native_pipeline_context
        self.setup_standing()
        preview = self.manage('preview', self.proposal(['pipeline_preparation']))
        issued = self.manage('activate', dict(proposal=preview['proposal'], summary_hash=preview['summary_hash'], confirm_scope=True))
        agent = NativeAgentAccess(self.runtime.service, self.runtime.identities)
        def call(operation, body, resource=None):
            envelope = dict(app_id='new-app', operation=operation, input=body)
            if resource:envelope['resource_id'] = resource
            with native_access(self.runtime.service, self.runtime.identities, self.session, self.vault):
                with native_pipeline_context(self.runtime.service, self.runtime.identities, self.session):
                    return json.loads(agent.call(self.session, issued['token'], json.dumps(envelope).encode()))
        queued = call('pipeline.prepare', dict(action='pipeline', data=dict(stage=1), request_key='owned'))
        jobs = NativeJobs(self.runtime.service, self.runtime.identities)
        other = jobs.queue('new-app', self.runtime.identities.fresh(self.session), dict(stage=1, request_key='unrelated'))
        with self.assertRaises(PermissionError): call('job.cancel', {}, other['id'])
        self.assertEqual(call('job.cancel', {}, queued['id'])['status'], 'CANCELLED')
        with connection(self.path) as db:
            self.assertEqual(db.execute('SELECT status FROM jobs WHERE id=?', (other['id'],)).fetchone()[0], 'QUEUED')


if __name__ == '__main__': unittest.main()
