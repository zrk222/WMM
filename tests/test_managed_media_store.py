"""Immutable original media intake, local owner attestations and scoped resolution."""
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
import unittest
from unittest.mock import patch

from mission_control.common import Invalid, canonical, now
from mission_control.db import connection
from mission_control.managed_media_store import Media
from mission_control.store import Store


RAW = b'bounded synthetic video source'
BODY = {'manifest_version': 3, 'request_key': 'retry-001'}


def synthetic_inspection(raw, _suffix, alive=lambda: None, tools=None):
    alive()
    return {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw),
            'metadata': {'codec': 'h264', 'width': 64, 'height': 64, 'duration_seconds': 1.0,
                         'frame_rate': 24.0, 'audio': False},
            'decoded': {'video_frames': 24, 'audio_frames': 0}}


class ManagedMediaStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.store = Store(self.root / 'state.sqlite', seed=False)
        self.media = Media(self.store)
        with connection(self.store.path) as db:
            for app_id in ('sample-one', 'sample-two'):
                db.execute('INSERT INTO apps(id,data,version,updated) VALUES(?,?,?,?)',
                           (app_id, canonical({'name': app_id}), 3, now()))
            db.execute('INSERT INTO operator_roles(app_id,principal,login,role,status,version,updated,changed_by) VALUES(?,?,?,?,?,?,?,?)',
                       ('sample-one', 'owner-1', 'owner', 'OWNER', 'ACTIVE', 1, now(), 'owner-1'))

    def tearDown(self):
        self.temporary.cleanup()

    def upload(self, raw=RAW, filename='C:\\local\\clip.mp4', body=None, alive=lambda: None):
        with patch('mission_control.managed_media_store.inspect', side_effect=synthetic_inspection):
            return self.media.upload('sample-one', filename, raw, body or dict(BODY), alive)

    def count_rows(self):
        with connection(self.store.path) as db:
            return db.execute('SELECT count(*) FROM managed_media').fetchone()[0]

    def stored_files(self):
        return [path for path in (self.root / 'managed-media').rglob('*') if path.is_file()] if (self.root / 'managed-media').exists() else []

    def review_body(self, item, **overrides):
        body = dict(expected_version=item['review_version'], manifest_version=3,
                    source_sha256=item['source_sha256'], status='ALLOWED', basis='OWNED',
                    evidence='I recorded the source permission for this app.')
        body.update(overrides)
        return body

    def test_upload_replay_public_receipt_redaction_and_distinct_request_identity(self):
        item = self.upload()
        replay = self.upload()
        second = self.upload(body={'manifest_version': 3, 'request_key': 'retry-002'})
        self.assertEqual(item['id'], replay['id'])
        self.assertNotEqual(item['id'], second['id'])
        self.assertNotEqual(item['upload_request_key_sha256'], second['upload_request_key_sha256'])
        self.assertEqual(item['upload_request_key_sha256'], hashlib.sha256(BODY['request_key'].encode()).hexdigest())
        self.assertEqual((self.count_rows(), len(self.stored_files())), (2, 2))
        self.assertEqual(item['filename'], 'clip.mp4')
        self.assertEqual(item['source_sha256'], hashlib.sha256(RAW).hexdigest())
        self.assertEqual(item['bytes'], len(RAW))
        self.assertEqual(item['rights_status'], 'UNKNOWN')
        self.assertFalse(item['reuse_available'])
        self.assertNotIn(BODY['request_key'], json.dumps(item))
        self.assertNotIn('storage_name', item)
        self.assertNotIn('path', item)

    def test_upload_rejects_ambiguous_envelope_bad_bytes_and_nonbasename_before_inspection(self):
        with patch('mission_control.managed_media_store.inspect') as inspect:
            for body in ({'manifest_version': True, 'request_key': 'x'},
                         {'manifest_version': 3, 'request_key': 'x', 'extra': True},
                         {'manifest_version': 3, 'request_key': ' '},
                         {'manifest_version': 3, 'request_key': 'x' * 121}):
                with self.subTest(body=body), self.assertRaises(Invalid):
                    self.media.upload('sample-one', 'clip.mp4', RAW, body)
            for raw, filename in ((bytearray(RAW), 'clip.mp4'), (b'', 'clip.mp4'), (b'x', 'clip.avi'),
                                  (RAW, 'x' * 256 + '.mp4')):
                with self.subTest(raw=type(raw).__name__, filename=filename[:15]), self.assertRaises(Invalid):
                    self.media.upload('sample-one', filename, raw, BODY)
            inspect.assert_not_called()

    def test_same_request_key_with_changed_payload_is_rejected_without_extra_file(self):
        self.upload()
        with patch('mission_control.managed_media_store.inspect', side_effect=synthetic_inspection):
            with self.assertRaisesRegex(Invalid, 'different media upload'):
                self.media.upload('sample-one', 'changed.mp4', b'different source', dict(BODY))
        self.assertEqual((self.count_rows(), len(self.stored_files())), (1, 1))

    def test_upload_rechecks_manifest_inside_insert_after_inspection(self):
        def change_app(raw, suffix, alive=lambda: None, tools=None):
            result = synthetic_inspection(raw, suffix, alive, tools)
            self.store.save_app('sample-one', {'name': 'changed'}, version=3)
            return result
        with patch('mission_control.managed_media_store.inspect', side_effect=change_app):
            with self.assertRaisesRegex(Invalid, 'setup changed'):
                self.media.upload('sample-one', 'clip.mp4', RAW, dict(BODY))
        self.assertEqual(self.count_rows(), 0)
        self.assertEqual([path for path in self.stored_files() if path.is_file()], [])

    def test_concurrent_same_key_uploads_linearize_to_one_file_and_one_receipt(self):
        barrier = threading.Barrier(2)
        def inspect_at_once(raw, suffix, alive=lambda: None, tools=None):
            barrier.wait(timeout=5)
            return synthetic_inspection(raw, suffix, alive, tools)
        with patch('mission_control.managed_media_store.inspect', side_effect=inspect_at_once):
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(lambda _: self.media.upload('sample-one', 'clip.mp4', RAW, dict(BODY)), range(2)))
        self.assertEqual(results[0]['id'], results[1]['id'])
        self.assertEqual((self.count_rows(), len(self.stored_files())), (1, 1))

    def test_database_insert_failure_removes_only_newly_owned_original(self):
        with connection(self.store.path) as db:
            db.execute("CREATE TRIGGER fail_media_insert BEFORE INSERT ON managed_media BEGIN SELECT RAISE(ABORT,'synthetic failure'); END")
        with patch('mission_control.managed_media_store.inspect', side_effect=synthetic_inspection):
            with self.assertRaises(sqlite3.IntegrityError):
                self.media.upload('sample-one', 'clip.mp4', RAW, dict(BODY))
        self.assertEqual((self.count_rows(), len([p for p in self.stored_files() if p.is_file()])), (0, 0))

    def test_app_scope_and_source_hash_are_rechecked_for_read_and_resolve(self):
        item = self.upload()
        with self.assertRaisesRegex(Invalid, 'does not belong'):
            self.media.read('sample-two', item['id'])
        with self.assertRaisesRegex(Invalid, 'does not belong'):
            self.media.resolve('sample-two', item['id'], item['source_sha256'], require_reuse=False)
        with self.assertRaisesRegex(Invalid, 'digest changed'):
            self.media.resolve('sample-one', item['id'], '0' * 64, require_reuse=False)
        path = next(p for p in self.stored_files() if p.is_file())
        path.write_bytes(b'X' * len(RAW))
        with self.assertRaisesRegex(Invalid, 'digest changed'):
            self.media.read('sample-one', item['id'])
        with self.assertRaisesRegex(Invalid, 'digest changed'):
            self.media.resolve('sample-one', item['id'], item['source_sha256'], require_reuse=False)

    def test_original_returns_verified_bytes_only_for_current_owner_without_a_path(self):
        item = self.upload()
        public, raw = self.media.original('sample-one', item['id'], 'owner-1')
        self.assertEqual(raw, RAW)
        self.assertEqual(public['source_integrity'], 'VERIFIED')
        self.assertNotIn('path', public)
        self.assertNotIn('storage_name', public)
        self.assertNotIn('raw', public)
        with self.assertRaises(PermissionError):
            self.media.original('sample-one', item['id'], 'unlisted')
        with connection(self.store.path) as db:
            db.execute("UPDATE operator_roles SET status='REVOKED',version=version+1 WHERE app_id=? AND principal=?",
                       ('sample-one', 'owner-1'))
        with self.assertRaises(PermissionError):
            self.media.original('sample-one', item['id'], 'owner-1')

    def test_allowed_review_becomes_stale_when_attesting_owner_role_is_revoked_or_versioned(self):
        with connection(self.store.path) as db:
            db.execute('INSERT INTO operator_roles(app_id,principal,login,role,status,version,updated,changed_by) VALUES(?,?,?,?,?,?,?,?)',
                       ('sample-one', 'owner-2', 'owner2', 'OWNER', 'ACTIVE', 4, now(), 'owner-1'))
        first = self.upload()
        second = self.upload(body={'manifest_version': 3, 'request_key': 'retry-002'})
        approved_first = self.media.review('sample-one', first['id'], self.review_body(first), {'principal': 'owner-1'})
        approved_second = self.media.review('sample-one', second['id'], self.review_body(second), {'principal': 'owner-2'})
        self.assertTrue(approved_first['reuse_available'] and approved_second['reuse_available'])
        with connection(self.store.path) as db:
            db.execute("UPDATE operator_roles SET status='REVOKED',version=version+1 WHERE app_id=? AND principal=?",
                       ('sample-one', 'owner-1'))
            db.execute("UPDATE operator_roles SET version=version+1 WHERE app_id=? AND principal=?",
                       ('sample-one', 'owner-2'))
        for identity in (first['id'], second['id']):
            with self.subTest(identity=identity):
                stale = self.media.read('sample-one', identity)
                self.assertEqual((stale['rights_status'], stale['rights_reason'], stale['reuse_available']),
                                 ('STALE', 'REVIEWER_ROLE_CHANGED', False))
                self.assertEqual(len(stale['review_history']), 1)
                with self.assertRaisesRegex(Invalid, 'missing, stale or revoked'):
                    self.media.resolve('sample-one', identity, stale['source_sha256'])

    def test_row_integrity_detects_database_tamper_and_db_enforces_immutability(self):
        item = self.upload()
        with connection(self.store.path) as db:
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute('UPDATE managed_media SET request_hash=? WHERE app_id=? AND id=?',
                           ('0' * 64, 'sample-one', item['id']))
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute('DELETE FROM managed_media WHERE app_id=? AND id=?', ('sample-one', item['id']))
            db.execute('DROP TRIGGER managed_media_immutable_update')
            row = db.execute('SELECT data FROM managed_media WHERE app_id=? AND id=?', ('sample-one', item['id'])).fetchone()
            changed = json.loads(row['data']); changed['filename'] = 'tampered.mp4'
            db.execute('UPDATE managed_media SET data=? WHERE app_id=? AND id=?',
                       (canonical(changed), 'sample-one', item['id']))
        with self.assertRaisesRegex(Invalid, 'record integrity'):
            self.media.read('sample-one', item['id'])

    def test_owner_review_is_database_authorized_append_only_and_manifest_bound(self):
        item = self.upload()
        with self.assertRaisesRegex(Invalid, 'missing, stale or revoked'):
            self.media.resolve('sample-one', item['id'], item['source_sha256'])
        forged = {'principal': 'unlisted', 'role': 'OWNER'}
        with self.assertRaises(PermissionError):
            self.media.review('sample-one', item['id'], self.review_body(item), forged)
        allowed = self.media.review('sample-one', item['id'], self.review_body(item), {'principal': 'owner-1', 'role': 'MAKER'})
        self.assertEqual((allowed['rights_status'], allowed['reuse_available'], allowed['review_version']), ('ALLOWED', True, 1))
        self.assertEqual(allowed['latest_review']['authority'], 'OPERATOR_SUPPLIED_NOT_EXTERNALLY_VERIFIED')
        self.assertEqual(self.media.resolve('sample-one', item['id'], item['source_sha256']).read_bytes(), RAW)
        with self.assertRaisesRegex(Invalid, 'changed; reload'):
            self.media.review('sample-one', item['id'], self.review_body(item), {'principal': 'owner-1'})
        self.assertEqual(len(self.media.read('sample-one', item['id'])['review_history']), 1)
        self.store.save_app('sample-one', {'name': 'new manifest'}, version=3)
        stale = self.media.read('sample-one', item['id'])
        self.assertEqual((stale['rights_status'], stale['reuse_available']), ('STALE', False))
        with self.assertRaisesRegex(Invalid, 'missing, stale or revoked'):
            self.media.resolve('sample-one', item['id'], item['source_sha256'])
        self.assertEqual(self.media.resolve('sample-one', item['id'], item['source_sha256'], require_reuse=False).read_bytes(), RAW)

    def test_revocation_and_review_envelopes_fail_closed(self):
        item = self.upload()
        owner = {'principal': 'owner-1'}
        allowed = self.media.review('sample-one', item['id'], self.review_body(item), owner)
        denied = self.media.review('sample-one', item['id'], self.review_body(
            allowed, expected_version=1, status='REVOKED', evidence='Reuse permission was withdrawn.'), owner)
        self.assertEqual((denied['rights_status'], denied['reuse_available'], denied['review_version']), ('REVOKED', False, 2))
        self.assertEqual([x['version'] for x in denied['review_history']], [1, 2])
        with self.assertRaisesRegex(Invalid, 'missing, stale or revoked'):
            self.media.resolve('sample-one', item['id'], item['source_sha256'])
        self.assertEqual(self.media.resolve('sample-one', item['id'], item['source_sha256'], require_reuse=False).read_bytes(), RAW)
        bad = self.review_body(item, evidence='x' * 1001)
        with self.assertRaisesRegex(Invalid, '1 through 1000'):
            self.media.review('sample-one', item['id'], bad, owner)
        bad = self.review_body(item, status=['ALLOWED'])
        with self.assertRaises(Invalid):
            self.media.review('sample-one', item['id'], bad, owner)

    def test_database_reparse_metadata_is_rejected_by_owned_path_checks(self):
        self.upload()
        with patch('mission_control.managed_media_store._linked', side_effect=[False, True]):
            with self.assertRaisesRegex(Invalid, 'linked or unsupported'):
                self.media.list('sample-one')

    def test_collection_limit_is_enforced_without_deleting_retained_items(self):
        with patch('mission_control.managed_media_store.MAX_ITEMS', 1):
            first = self.upload()
            with self.assertRaisesRegex(Invalid, 'already contains'):
                self.upload(body={'manifest_version': 3, 'request_key': 'retry-002'})
            self.assertEqual(self.count_rows(), 1)
            self.assertEqual(self.media.list('sample-one')['items'][0]['id'], first['id'])

    def test_actual_audio_video_bytes_round_trip_through_inspection_and_resolution(self):
        ffmpeg = shutil.which('ffmpeg')
        ffprobe = shutil.which('ffprobe')
        self.assertTrue(ffmpeg and ffprobe, 'local FFmpeg and FFprobe are required for this proof')
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / 'actual-audio.mp4'
            subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-nostdin', '-f', 'lavfi', '-i',
                            'color=c=blue:s=64x64:r=24', '-f', 'lavfi', '-i',
                            'sine=frequency=440:sample_rate=48000', '-t', '1', '-pix_fmt', 'yuv420p',
                            '-c:v', 'libx264', '-preset', 'ultrafast', '-c:a', 'aac', '-shortest',
                            '-y', str(source)], capture_output=True, timeout=40, check=True)
            raw = source.read_bytes()
            item = self.media.upload('sample-one', 'selected.mp4', raw, dict(BODY))
            self.assertTrue(item['metadata']['audio'])
            self.assertGreater(item['decoded']['video_frames'], 0)
            self.assertGreater(item['decoded']['audio_frames'], 0)
            self.assertEqual(self.media.resolve('sample-one', item['id'], item['source_sha256'], False).read_bytes(), raw)
            self.assertEqual(self.media.read('sample-one', item['id'])['source_integrity'], 'VERIFIED')


if __name__ == '__main__':
    unittest.main()
