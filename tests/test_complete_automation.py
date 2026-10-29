"""Real isolated owner/policy transactions; protected access is a declared test adapter."""
from datetime import datetime, timedelta, timezone
import json
import unittest
from unittest.mock import patch

from mission_control import complete_automation as core
from mission_control.agent_grants import Grants, token_digest
from mission_control.common import Invalid, canonical, digest
from mission_control.db import connection
from mission_control.review_access import Access
from mission_control.store import Store
from tests import test_automation_requirements as fixtures
from tests.test_verified_review import OWNER, STRANGER


class AuthorityFixture:
    """Compose the synthetic DB fixture without duplicating its test discovery."""
    def setup_authority(self):
        self.fixture = fixtures.AutomationReadinessTests('test_workflow_states_preserve_every_incomplete_parent_workflow_as_blocked')
        self.fixture.setUp()
        self.store = self.fixture.store
        self.observed = datetime.now(timezone.utc)
        with connection(self.store.path) as db:
            db.execute('UPDATE agent_connections SET last_test=?', (self.observed.isoformat(),))
        self.clock_patch = patch('mission_control.complete_automation.utc', return_value=self.observed)
        self.clock_patch.start()
        self.access_patch = patch('mission_control.complete_automation.verify_access')
        self.access = self.access_patch.start()
        self.automation = core.Automation(self.store)
        self.grants = Grants(self.store, clock=lambda: self.observed)

    def cleanup_authority(self):
        self.access_patch.stop()
        self.clock_patch.stop()
        self.fixture.tearDown()

    def proposal(self, workflows=None, **limits):
        return dict(selection=self.fixture.body(workflows=workflows or ['local_evidence']),
                    purpose='Prepare useful local evidence for this synthetic app.',
                    limits=dict(dict(expires=(self.observed+timedelta(hours=1)).isoformat(),
                                     max_calls=20, max_inflight=1, currency='USD', spend_limit_minor=0), **limits))

    def activate(self, workflows=None, **limits):
        preview = self.automation.preview('sample-one', OWNER, self.proposal(workflows, **limits))
        return self.automation.activate('sample-one', OWNER, dict(proposal=preview['proposal'], summary_hash=preview['summary_hash']))

    def envelope(self, operation='workspace.read', body=None, **extra):
        return dict(app_id='sample-one', operation=operation, input=body or {}, **extra)

    def off(self, issued):
        return self.automation.off('sample-one', OWNER, dict(id=issued['policy_id'], version=issued['version']))


class StandingAuthorityTests(AuthorityFixture, unittest.TestCase):
    def setUp(self):
        self.setup_authority()

    def tearDown(self):
        self.cleanup_authority()

    def test_scope_summary_is_exact_read_only_and_explains_limits_actions_and_credentials(self):
        before = self.fixture.dump()
        preview = self.automation.preview('sample-one', OWNER, self.proposal())
        summary = preview['summary']
        self.assertEqual(preview['summary_hash'], digest(summary))
        self.assertEqual(summary['limits']['spend_limit_minor'], 0)
        self.assertEqual(summary['limits']['max_calls'], 20)
        self.assertIn('evidence.save', summary['operations'])
        self.assertEqual(summary['inventory']['inference']['id'], fixtures.PROFILE)
        self.assertEqual(summary['external_effects'], 'NONE_IN_CURRENT_EXECUTABLE_SCOPE')
        self.assertFalse(preview['authority_issued'])
        self.assertNotIn(fixtures.PRIVATE, json.dumps(preview))
        self.assertEqual(before, self.fixture.dump())
        self.access.assert_not_called()

    def test_atomic_activation_returns_token_once_and_snapshot_does_not_restore_authority(self):
        issued = self.activate()
        self.assertEqual(issued['status'], 'ACTIVE')
        with connection(self.store.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM automation_policies').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT token_hash FROM agent_grants').fetchone()[0], token_digest(issued['token']))
        public = self.automation.status('sample-one', OWNER)
        self.assertEqual(len(public['catalog']['workflows']),12)
        self.assertEqual(public['policies'][0]['usage']['used'],0)
        self.assertNotIn('token_hash',json.dumps(public))
        self.assertNotIn(issued['token'], json.dumps(public))
        self.assertNotIn(issued['token'], self.fixture.dump())
        exported = self.store.export('sample-one')
        self.assertNotIn('automation_policies', json.dumps(exported))
        self.assertNotIn('automation_executions', json.dumps(exported))
        clone = Store(self.store.path.parent / 'restored.sqlite', seed=False)
        clone.restore(exported)
        with connection(clone.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM automation_policies').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT count(*) FROM agent_grants').fetchone()[0], 0)
        self.access.assert_called_once_with(self.store, 'sample-one', fixtures.PROFILE)

    def test_stale_summary_failed_access_and_incomplete_workflows_create_no_grant(self):
        preview = self.automation.preview('sample-one', OWNER, self.proposal())
        with connection(self.store.path) as db:
            db.execute('UPDATE agent_connections SET version=2')
        with self.assertRaises(Invalid):
            self.automation.activate('sample-one', OWNER, dict(proposal=preview['proposal'], summary_hash=preview['summary_hash']))
        self.access.side_effect = Invalid('Synthetic access unavailable')
        with self.assertRaises(Invalid):
            self.activate()
        self.access.side_effect = None
        for workflows in (['social_publish'], ['local_evidence', 'video_authoring_editing']):
            with self.assertRaises(Invalid):
                self.activate(workflows)
        with connection(self.store.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM agent_grants').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT count(*) FROM automation_policies').fetchone()[0], 0)

    def test_owner_only_activation_and_no_duplicate_active_policy(self):
        Access(self.store).save('sample-one', OWNER, STRANGER, dict(login=STRANGER['login'], role='MAKER', status='ACTIVE', version=None))
        with self.assertRaises(PermissionError):
            self.automation.preview('sample-one', STRANGER, self.proposal())
        issued = self.activate()
        for user in (STRANGER,):
            with self.assertRaises(PermissionError):
                self.automation.off('sample-one', user, dict(id=issued['policy_id'], version=1))
            with self.assertRaises(PermissionError):
                self.automation.status('sample-one', user)
        with self.assertRaises(Invalid):
            self.activate()

    def test_limits_reject_unbounded_paid_expired_and_ambiguous_resource_values(self):
        for limits in (dict(max_calls=True), dict(max_calls=10001), dict(max_inflight=0),
                       dict(max_inflight=9), dict(spend_limit_minor=1), dict(spend_limit_minor=False),
                       dict(currency='usd'), dict(expires=self.observed.isoformat()),
                       dict(expires=(self.observed+timedelta(hours=25)).isoformat())):
            with self.subTest(limits=limits), self.assertRaises(Invalid):
                self.automation.preview('sample-one', OWNER, self.proposal(**limits))

    def test_off_requires_current_revision_and_revokes_bound_grant_only(self):
        issued = self.activate()
        for version in (2, True):
            with self.assertRaises(Invalid):
                self.automation.off('sample-one', OWNER, dict(id=issued['policy_id'], version=version))
        with self.assertRaises(Invalid):
            self.automation.off('sample-two', OWNER, dict(id=issued['policy_id'], version=1))
        self.assertEqual(self.off(issued)['status'], 'OFF')
        with self.assertRaises(PermissionError):
            self.grants.admit(issued['token'], self.envelope())
        self.assertEqual(self.automation.status('sample-one', OWNER)['policies'][0]['effective_status'], 'OFF')

    def test_changed_credentials_and_summary_integrity_block_current_authority(self):
        issued = self.activate()
        with connection(self.store.path) as db:
            db.execute('UPDATE agent_connections SET version=version+1')
        self.assertEqual(self.automation.status('sample-one', OWNER)['policies'][0]['effective_status'], 'BLOCKED')
        with self.assertRaises(PermissionError):
            self.grants.admit(issued['token'], self.envelope())
        with connection(self.store.path) as db:
            db.execute('UPDATE agent_connections SET version=1')
            db.execute("UPDATE automation_policies SET summary='{}'")
        with self.assertRaises(PermissionError):
            self.grants.admit(issued['token'], self.envelope())

    def test_real_access_checker_requires_pinned_signed_in_tool_without_paid_inference(self):
        self.access_patch.stop()
        try:
            with patch('mission_control.agent_native.identity', return_value=dict(fingerprint='fixed-fingerprint', login_state='SIGNED_IN')):
                issued = self.activate()
            self.off(issued)
            with patch('mission_control.agent_native.identity', return_value=dict(fingerprint='changed', login_state='SIGNED_IN')):
                with self.assertRaises(Invalid):
                    self.activate()
            with patch('mission_control.agent_native.identity', return_value=dict(fingerprint='fixed-fingerprint', login_state='SIGN_IN_REQUIRED')):
                with self.assertRaises(Invalid):
                    self.activate()
        finally:
            self.access = self.access_patch.start()

    def test_activation_rolls_back_grant_if_policy_audit_cannot_commit(self):
        with patch('mission_control.complete_automation.audit', side_effect=RuntimeError('Synthetic audit failure')):
            with self.assertRaises(RuntimeError):
                self.activate()
        with connection(self.store.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM agent_grants').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT count(*) FROM automation_policies').fetchone()[0], 0)

    def test_scope_deadline_cannot_outlive_saved_credential_freshness(self):
        with connection(self.store.path) as db:
            db.execute('UPDATE agent_connections SET last_test=?', ((self.observed-timedelta(hours=23, minutes=30)).isoformat(),))
        issued = self.activate(expires=(self.observed+timedelta(hours=2)).isoformat())
        self.assertEqual(issued['summary']['stops_at'], (self.observed+timedelta(minutes=30)).isoformat())
        self.assertEqual(issued['grant']['expires'], issued['summary']['stops_at'])
        self.observed += timedelta(minutes=31)
        self.clock_patch.target.utc.return_value = self.observed
        with self.assertRaises(PermissionError):
            self.grants.admit(issued['token'], self.envelope())

    def test_corrupt_summary_is_reported_blocked_and_owner_can_still_switch_off(self):
        issued = self.activate()
        for raw in ('synthetic-broken-'+fixtures.PRIVATE, canonical(dict(api_key=fixtures.PRIVATE))):
            with connection(self.store.path) as db:
                db.execute('UPDATE automation_policies SET summary=?', (raw,))
            state = self.automation.status('sample-one', OWNER)['policies'][0]
            self.assertEqual(state['effective_status'], 'BLOCKED')
            self.assertIsNone(state['summary'])
            self.assertNotIn(fixtures.PRIVATE, json.dumps(state))
        self.assertEqual(self.off(issued)['status'], 'OFF')

    def test_keyed_local_and_unsupported_native_access_are_checked_without_inference(self):
        self.access_patch.stop()
        try:
            with connection(self.store.path) as db:
                raw = json.loads(db.execute('SELECT data FROM agent_connections').fetchone()[0])
            api = dict(raw, provider='openai_api', model='synthetic-model')
            with connection(self.store.path) as db:
                db.execute('UPDATE agent_connections SET data=?', (canonical(api),))
            for value in (None, dict(api_key='')):
                with patch('mission_control.credential_vault.Vault.get', return_value=value):
                    with self.assertRaises(Invalid):
                        self.activate()
            with patch('mission_control.credential_vault.Vault.get', return_value=dict(api_key='synthetic-key-not-live')):
                self.off(self.activate())
            local = dict(api, provider='local_api')
            local.pop('credential_ref')
            with connection(self.store.path) as db:
                db.execute('UPDATE agent_connections SET data=?', (canonical(local),))
            with patch('mission_control.credential_vault.Vault.get', side_effect=AssertionError('No key required')):
                self.off(self.activate())
            with connection(self.store.path) as db:
                db.execute('UPDATE agent_connections SET data=?', (canonical(dict(raw, provider='kimi')),))
            with self.assertRaises(Invalid):
                self.activate()
        finally:
            self.access = self.access_patch.start()
