"""Durable source-bound setup proposals; synthetic robots/page responses, no external access."""
from datetime import timedelta
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch
from mission_control.common import Invalid, digest, iso_time
from mission_control.db import connection
from mission_control.store import Store
from mission_control.aeo_transport import ReadError
from mission_control.setup_discovery import SetupDiscovery
from tests.test_aeo_inspection import Reader, ROOT, resource


class SetupFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name)/'synthetic.sqlite', seed=False)
        data = dict(name='Synthetic', website=ROOT+'/page', store_app_id='123')
        for identity in ('sample-one', 'sample-two'):
            self.store.save_app(identity, data)
        self.service = SetupDiscovery(self.store)

    def body(self, identity='sample-one'):
        app = self.store.app(identity)
        return dict(app_id=identity, app_version=app['version'], app_hash=digest(app['data']), confirm_read=True)

    def start(self, reader=None):
        return self.service.start('sample-one', self.body(), reader or Reader())


class SetupDiscoveryTests(SetupFixture):
    def test_saved_proposal_is_not_a_manifest_edit_or_ownership_proof(self):
        app = self.store.app('sample-one')
        reader = Reader(page='<title>Declared title</title><script>RAW_BODY_SENTINEL</script><a href="https://apps.apple.com/app/id456">App</a>')
        row = self.start(reader)
        self.assertEqual(row['state'], 'PENDING')
        self.assertEqual(row['data']['projection']['fields']['store_app_id'][0]['value'], '456')
        self.assertEqual(self.store.app('sample-one'), app)
        self.assertEqual(row['data']['ownership'], 'NOT_VERIFIED')
        self.assertFalse(row['data']['external_writes'])
        self.assertNotIn('RAW_BODY_SENTINEL', json.dumps(row))
        self.assertEqual(len(reader.calls), 3)
        self.assertTrue(row['data']['source_sha256'])
        self.assertTrue(all(not url.startswith('https://apps.apple.com') for url, _ in reader.calls))
        self.assertEqual(iso_time(row['expires']) - iso_time(row['created']), timedelta(seconds=3600))

    def test_restart_and_expiry_do_not_silently_renew_evidence(self):
        row = self.start()
        restored = SetupDiscovery(Store(self.store.path, seed=False))
        self.assertEqual(restored.list('sample-one')['proposals'][0]['id'], row['id'])
        future = (iso_time(row['expires']) + timedelta(seconds=1)).isoformat()
        with patch('mission_control.setup_discovery.now', return_value=future):
            self.assertEqual(restored.list('sample-one')['proposals'][0]['currentness'], 'EXPIRED')
        self.assertEqual(restored.list('sample-one')['proposals'][0]['expires'], row['expires'])

    def test_foreign_app_body_and_delete_are_rejected(self):
        reader = Reader()
        with self.assertRaises(Invalid):
            self.service.start('sample-two', self.body(), reader)
        self.assertFalse(reader.calls)
        row = self.start()
        with self.assertRaises(Invalid):
            self.service.delete('sample-two', dict(id=row['id'], hash=row['hash'], confirm_delete=True))
        self.assertEqual(self.service.list('sample-two')['proposals'], [])

    def test_exact_inputs_and_current_manifest_are_checked_before_network(self):
        original = self.body()
        app = self.store.app('sample-one')
        self.store.save_app('sample-one', dict(app['data'], name='Changed'), app['version'])
        for body in (original, {**self.body(), 'confirm_read':False}, {**self.body(), 'url':'https://foreign.example/'},
                     {**self.body(), 'app_version':True}, {**self.body(), 'command':'execute'}):
            reader = Reader()
            with self.subTest(body=body), self.assertRaises(Invalid):
                self.service.start('sample-one', body, reader)
            self.assertFalse(reader.calls)

    def test_manifest_change_during_io_denies_adoption_without_transaction_lock(self):
        reader = Reader()
        original = reader.read
        changed = False
        def during_read(*args, **kwargs):
            nonlocal changed
            if not changed:
                changed = True
                app = self.store.app('sample-one')
                self.store.save_app('sample-one', dict(app['data'], name='Changed during read'), app['version'])
            return original(*args, **kwargs)
        reader.read = during_read
        with self.assertRaises(Invalid):
            self.start(reader)
        self.assertEqual(self.service.list('sample-one')['proposals'], [])

    def test_network_failure_is_retained_as_recovery_not_empty_success(self):
        reader = Reader()
        reader.resources[ROOT+'/page'] = ReadError('NETWORK_FAILED')
        row = self.start(reader)
        self.assertEqual(row['state'], 'NEEDS_RESOLUTION')
        self.assertIsNone(row['data']['projection'])
        self.assertIsNone(row['data']['source_sha256'])
        self.assertTrue(any(item['action'] == 'retry_discovery' for item in row['data']['recovery']))

    def test_robots_denial_never_fetches_page(self):
        reader = Reader(robots='User-agent: *\nDisallow: /\n')
        row = self.start(reader)
        self.assertEqual(row['data']['state'], 'BLOCKED_ROBOTS')
        self.assertEqual(reader.calls, [(ROOT+'/robots.txt', 512000)])
        self.assertEqual(row['state'], 'NEEDS_RESOLUTION')

    def test_missing_website_has_actionable_local_recovery_without_reader_creation(self):
        app = self.store.app('sample-one')
        self.store.save_app('sample-one', dict(app['data'], website=''), app['version'])
        with patch('mission_control.setup_discovery.PublicReader', side_effect=AssertionError('No network for absent website')):
            row = self.service.start('sample-one', self.body())
        self.assertEqual(row['data']['state'], 'WEBSITE_REQUIRED')
        self.assertTrue(any(item['action'] == 'review_app_setup' and item['enabled'] for item in row['data']['recovery']))

    def test_stale_projection_and_tampered_storage_are_not_current(self):
        row = self.start()
        app = self.store.app('sample-one')
        self.store.save_app('sample-one', dict(app['data'], name='New source scope'), app['version'])
        self.assertEqual(self.service.list('sample-one')['proposals'][0]['currentness'], 'STALE_APP')
        with connection(self.store.path) as db:
            db.execute('UPDATE setup_proposals SET data=? WHERE id=?', ('{}', row['id']))
        with self.assertRaises(Invalid):
            self.service.list('sample-one')

    def test_capacity_has_exact_draft_delete_recovery_and_preserves_app_data(self):
        before = self.store.app('sample-one')
        rows = [self.start() for _ in range(64)]
        reader = Reader()
        with self.assertRaisesRegex(Invalid, 'remove one'):
            self.start(reader)
        self.assertFalse(reader.calls)
        row = rows[0]
        self.assertEqual(self.service.delete('sample-one', dict(id=row['id'], hash=row['hash'], confirm_delete=True))['status'], 'DELETED')
        self.assertEqual(self.store.app('sample-one'), before)
        self.assertEqual(self.start()['state'], 'PENDING')

    def test_delete_requires_exact_hash_and_confirmation(self):
        row = self.start()
        for body in (dict(id=row['id'], hash='wrong', confirm_delete=True),
                     dict(id=[], hash=row['hash'], confirm_delete=True),
                     dict(id=row['id'], hash={}, confirm_delete=True),
                     dict(id=row['id'], hash=row['hash'], confirm_delete=False),
                     dict(id=row['id'], hash=row['hash'], confirm_delete=True, delete_app=True)):
            with self.subTest(body=body), self.assertRaises(Invalid):
                self.service.delete('sample-one', body)
        self.assertEqual(len(self.service.list('sample-one')['proposals']), 1)

    def test_checked_bytes_must_match_hash_and_source_document(self):
        reader = Reader()
        reader.resources[ROOT+'/page'] = resource(ROOT+'/page', '<title>Real</title>')
        reader.resources[ROOT+'/page']['sha256'] = '0'*64
        with self.assertRaisesRegex(Invalid, 'source bytes'):
            self.start(reader)
        self.assertEqual(self.service.list('sample-one')['proposals'], [])
