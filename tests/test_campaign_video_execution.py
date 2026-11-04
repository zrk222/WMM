"""Real durable Reel state with synthetic assets/credentials and fake provider."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from mission_control import campaign_video_execution as video
from mission_control.campaign_contract import REEL_SCHEMA
from mission_control.campaign_locks import CampaignLockBusy
from mission_control.campaign_transport import Unconfirmed
from mission_control.common import Invalid, uid
from mission_control.db import connection
from mission_control.operation_authority import bound_owner, protected
from tests import test_organic_video_policy as fixtures

APP, OWNER = fixtures.APP, fixtures.OWNER


class Transport:
    def __init__(self):
        self.calls = []
        self.finished = False
        self.failure = None
        self.hook = lambda action: None
        self.processing = False

    def act(self, action, context):
        context.alive()
        self.calls.append(action)
        self.hook(action)
        if self.failure == action:
            raise Unconfirmed('Synthetic response lost')

    def create(self, page, metadata, context):
        self.act('create', context)
        return dict(video_id='456', state='CREATED')

    def upload(self, identity, artifact, context):
        self.act('upload', context)
        self.uploaded_hash = artifact['sha256']
        return dict(video_id=identity, state='UPLOAD_ACKNOWLEDGED')

    def publish(self, identity, metadata, context):
        self.finished = True
        self.act('publish', context)
        self.caption = metadata['caption']
        return dict(video_id=identity, state='PUBLISH_ACKNOWLEDGED')

    def read(self, identity, context):
        self.act('read', context)
        return dict(video_id=identity, video_status='processing' if self.processing else 'ready',
                    uploading_phase='complete', processing_phase='in_progress' if self.processing else 'complete',
                    publishing_phase='complete' if self.finished and not self.processing else 'not_started')


class ReelExecutionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.OrganicPolicyTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.store = self.fixture.store
        self.policy = self.fixture.create(dict(self.fixture.policy, max_calls=40))
        output = self.fixture.admission(self.policy, reserve_calls=40)
        self.admitted = self.fixture.call('admit', output)
        data = self.admitted['data']
        selected = data['output']
        self.body = dict(schema=REEL_SCHEMA, request_id=uid(), app_id=APP, page_id='123',
            policy_id=self.policy['id'], policy_hash=self.policy['hash'],
            admission_id=self.admitted['id'], admission_hash=self.admitted['hash'],
            artifact_id=selected['artifact_id'], artifact_sha256=selected['artifact_sha256'],
            caption=selected['caption'], rights_hashes=sorted({x['rights_hash'] for x in data['proofs']['sources']}))
        self.transport = Transport()
        self.patches = [patch.object(video, '_credentials', return_value=({}, 'synthetic-app-secret',
                       dict(access_token='synthetic-user-token', page_token='synthetic-page-token'))),
                       patch.object(video, 'facebook', side_effect=self.facebook),
                       patch.object(video, 'selected_page', side_effect=self.page)]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def facebook(self, config, secret, access, alive):
        alive()
        return SimpleNamespace(subject_id='fixture-subject', permissions=['pages_manage_posts', 'pages_show_list', 'pages_read_engagement'])

    def page(self, secret, access, identity, alive):
        alive()
        return dict(id='123', tasks=['CREATE_CONTENT']), 'synthetic-page-token'

    def call(self, action, body, actor=None):
        envelope = dict(app_id=APP, operation='organic-video.intent-' + action, input=body)
        with bound_owner(self.store, envelope, self.fixture.sessions, 'fixture-session', OWNER):
            with protected(self.store, envelope):
                if action == 'create':
                    return video.create_intent(self.store, APP, actor or OWNER['principal'], body)
                return getattr(video, action)(self.store, APP, actor or OWNER['principal'], body['intent_id'], self.transport)

    def intent(self):
        return self.call('create', self.body)

    def retained(self, identity):
        with connection(self.store.path) as db:
            return video._view(video._row(db, APP, identity))

    def test_exact_intent_execute_and_restart_do_not_repeat_effects_or_claim_public_result(self):
        intent = self.intent()
        self.assertEqual(self.intent()['id'], intent['id'])
        result = self.call('execute', dict(intent_id=intent['id']))
        self.assertEqual(result['stage'], 'PROVIDER_PHASE_COMPLETE')
        self.assertEqual(self.transport.calls, ['create', 'upload', 'read', 'publish', 'read'])
        self.assertEqual(result['calls_used'], 7)
        self.assertEqual(result['public_visibility'], 'NOT_VERIFIED')
        self.assertIsNone(result['measured_app_outcome'])
        self.assertEqual(self.call('execute', dict(intent_id=intent['id'])), result)
        self.assertEqual(len(self.transport.calls), 5)
        with connection(self.store.path) as db:
            serialized = '\n'.join(row[0] for row in db.execute('SELECT data FROM campaign_video_events'))
            self.assertNotIn('synthetic-page-token', serialized)
            self.assertNotIn('synthetic-app-secret', serialized)
            self.assertNotIn(str(self.store.path.parent), serialized)

    def test_conflicting_identity_and_second_intent_for_same_admission_reject(self):
        intent = self.intent()
        for changes in (dict(caption='Different'), dict(request_id=uid()), dict(admission_hash='0'*64),
                        dict(rights_hashes=['0'*64]), dict(app_id='other-app')):
            with self.subTest(changes=changes), self.assertRaises((Invalid, PermissionError)):
                self.call('create', dict(self.body, **changes))
        with self.assertRaises(PermissionError):
            self.call('execute', dict(intent_id=intent['id']), actor='github:999')
        self.assertEqual(self.transport.calls, [])

    def test_lost_create_keeps_one_admission_and_never_recreates(self):
        intent = self.intent()
        self.transport.failure = 'create'
        with self.assertRaises(Unconfirmed):
            self.call('execute', dict(intent_id=intent['id']))
        state = self.retained(intent['id'])
        self.assertEqual(state['stage'], 'CREATE_PENDING')
        self.assertIsNone(state['remote_id'])
        for _ in range(2):
            self.call('execute', dict(intent_id=intent['id']))
            self.call('reconcile', dict(intent_id=intent['id']))
        self.assertEqual(self.transport.calls, ['create'])
        self.assertEqual(self.intent()['id'], intent['id'])

    def test_lost_finish_and_repeated_processing_reads_cannot_finish_again(self):
        intent = self.intent()
        self.transport.failure = 'publish'
        with self.assertRaises(Unconfirmed):
            self.call('execute', dict(intent_id=intent['id']))
        self.transport.failure = None
        self.transport.processing = True
        state = self.call('reconcile', dict(intent_id=intent['id']))
        self.assertEqual(state['stage'], 'PUBLISH_UNRESOLVED')
        self.call('execute', dict(intent_id=intent['id']))
        self.transport.processing = False
        state = self.call('reconcile', dict(intent_id=intent['id']))
        self.assertEqual(state['stage'], 'PROVIDER_PHASE_COMPLETE')
        self.assertEqual(self.transport.calls.count('publish'), 1)

    def test_acknowledged_finish_remains_observable_without_publishing_again(self):
        intent = self.intent()
        def processing_after_finish(action):
            if action == 'publish':
                self.transport.processing = True
        self.transport.hook = processing_after_finish
        result = self.call('execute', dict(intent_id=intent['id']))
        self.assertEqual(result['stage'], 'FINISH_ACKNOWLEDGED')
        self.assertFalse(result['recovery_required'])
        self.assertEqual(self.call('execute', dict(intent_id=intent['id']))['stage'], 'FINISH_ACKNOWLEDGED')
        self.transport.processing = False
        self.assertEqual(self.call('execute', dict(intent_id=intent['id']))['stage'], 'PROVIDER_PHASE_COMPLETE')
        self.assertEqual(self.transport.calls.count('publish'), 1)

    def test_revoke_between_create_and_upload_stops_next_mutation_but_owner_can_read(self):
        intent = self.intent()
        def revoke(action):
            if action == 'create':
                self.fixture.call('revoke', dict(policy_id=self.policy['id'], policy_hash=self.policy['hash']))
        self.transport.hook = revoke
        with self.assertRaisesRegex(PermissionError, 'revoked'):
            self.call('execute', dict(intent_id=intent['id']))
        self.assertEqual(self.transport.calls, ['create'])
        result = self.call('reconcile', dict(intent_id=intent['id']))
        self.assertEqual(result['remote_id'], '456')
        with self.assertRaisesRegex(PermissionError, 'revoked'):
            self.call('execute', dict(intent_id=intent['id']))
        self.assertNotIn('publish', self.transport.calls)

    def test_lost_upload_reconciles_known_id_without_reupload(self):
        intent = self.intent()
        self.transport.failure = 'upload'
        with self.assertRaises(Unconfirmed):
            self.call('execute', dict(intent_id=intent['id']))
        self.transport.failure = None
        self.assertEqual(self.call('reconcile', dict(intent_id=intent['id']))['stage'], 'READY_TO_FINISH')
        self.call('execute', dict(intent_id=intent['id']))
        self.assertEqual(self.transport.calls.count('upload'), 1)
        self.assertEqual(self.transport.calls.count('publish'), 1)

    def test_call_allowance_shared_across_reconcile_and_connection_rotation_rejects(self):
        intent = self.intent()
        self.transport.processing = True
        self.call('execute', dict(intent_id=intent['id']))
        with connection(self.store.path) as db:
            db.execute('UPDATE campaign_video_intents SET calls=37 WHERE id=?', (intent['id'],))
        self.call('reconcile', dict(intent_id=intent['id']))
        with self.assertRaisesRegex(PermissionError, 'reservation exhausted'):
            self.call('reconcile', dict(intent_id=intent['id']))
        self.assertEqual(self.retained(intent['id'])['calls_used'], 40)
        with connection(self.store.path) as db:
            db.execute('UPDATE social_connections SET version=version+1 WHERE app_id=?', (APP,))
        with self.assertRaisesRegex(PermissionError, 'connection changed'):
            self.call('reconcile', dict(intent_id=intent['id']))

    def test_processing_is_finite_and_blocked_artifact_or_permission_prevents_mutation(self):
        intent = self.intent()
        self.transport.processing = True
        self.assertEqual(self.call('execute', dict(intent_id=intent['id']))['stage'], 'PROCESSING')
        self.assertEqual(self.transport.calls, ['create', 'upload', 'read'])
        from mission_control.hypit_jobs import artifact_file
        path, _ = artifact_file(self.store, APP, self.body['artifact_id'])
        path.write_bytes(b'changed')
        with self.assertRaises(Invalid):
            self.call('execute', dict(intent_id=intent['id']))
        self.assertNotIn('publish', self.transport.calls)

    def test_existing_intent_retry_after_revocation_remains_inspectable(self):
        intent = self.intent()
        self.fixture.call('revoke', dict(policy_id=self.policy['id'], policy_hash=self.policy['hash']))
        self.assertEqual(self.intent()['id'], intent['id'])
        with self.assertRaises(PermissionError):
            self.call('execute', dict(intent_id=intent['id']))

    def test_connection_rotation_between_create_and_upload_blocks_captured_token(self):
        intent = self.intent()
        def rotate(action):
            if action == 'create':
                with connection(self.store.path) as db:
                    db.execute('UPDATE social_connections SET version=version+1 WHERE app_id=?', (APP,))
        self.transport.hook = rotate
        with self.assertRaisesRegex(PermissionError, 'connection changed'):
            self.call('execute', dict(intent_id=intent['id']))
        self.assertEqual(self.transport.calls, ['create'])

    def test_lost_upload_with_no_completed_transfer_stays_explicitly_unresolved(self):
        intent = self.intent()
        self.transport.failure = 'upload'
        with self.assertRaises(Unconfirmed):
            self.call('execute', dict(intent_id=intent['id']))
        self.transport.failure = None
        for status in ('not_started', 'in_progress'):
            value = dict(video_id='456', video_status='uploading', uploading_phase=status,
                         processing_phase='not_started', publishing_phase='not_started')
            with patch.object(self.transport, 'read', return_value=value):
                self.assertEqual(self.call('reconcile', dict(intent_id=intent['id']))['stage'], 'UPLOAD_UNRESOLVED')
                self.assertEqual(self.call('execute', dict(intent_id=intent['id']))['stage'], 'UPLOAD_UNRESOLVED')
        self.assertEqual(self.transport.calls.count('upload'), 1)
        self.assertNotIn('publish', self.transport.calls)

    def test_revoked_source_after_upload_blocks_finish(self):
        intent = self.intent()
        def revoke(action):
            if action == 'upload':
                self.fixture.media.review(APP, self.fixture.source['id'],
                    dict(self.fixture.review, expected_version=1, status='REVOKED'), OWNER)
        self.transport.hook = revoke
        with self.assertRaises(Invalid):
            self.call('execute', dict(intent_id=intent['id']))
        self.assertEqual(self.transport.calls, ['create', 'upload'])
        self.assertEqual(self.retained(intent['id'])['remote_id'], '456')

    def test_missing_current_permissions_blocks_before_first_mutation(self):
        intent = self.intent()
        with patch.object(video, 'facebook', return_value=SimpleNamespace(subject_id='fixture-subject', permissions=[])):
            with self.assertRaisesRegex(PermissionError, 'permissions'):
                self.call('execute', dict(intent_id=intent['id']))
        self.assertEqual(self.transport.calls, [])
        self.assertEqual(self.retained(intent['id'])['stage'], 'NEW')

    def test_conflicting_phase_readback_does_not_become_complete(self):
        intent = self.intent()
        observed = dict(video_id='456', video_status='error', uploading_phase='error',
                        processing_phase='complete', publishing_phase='complete')
        with patch.object(self.transport, 'read', return_value=observed):
            result = self.call('execute', dict(intent_id=intent['id']))
        self.assertEqual(result['stage'], 'PROVIDER_ERROR')
        self.assertNotIn('publish', self.transport.calls)

    def test_concurrent_intent_creation_and_execution_have_one_winner(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            values = list(pool.map(lambda _: self.intent(), range(2)))
        self.assertEqual(values[0]['id'], values[1]['id'])
        intent = values[0]
        entered = threading.Event()
        release = threading.Event()
        self.transport.hook = lambda action: (entered.set(), release.wait(10)) if action == 'create' else None
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self.call, 'execute', dict(intent_id=intent['id']))
            self.assertTrue(entered.wait(5))
            try:
                with self.assertRaises(CampaignLockBusy):
                    self.call('execute', dict(intent_id=intent['id']))
            finally:
                release.set()
            self.assertEqual(future.result()['stage'], 'PROVIDER_PHASE_COMPLETE')
        self.assertEqual(self.transport.calls.count('create'), 1)


if __name__ == '__main__':
    unittest.main()
