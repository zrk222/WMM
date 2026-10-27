"""Actual protected owner HTTP, immutable SQLite and current creative preferences."""
import copy
import sqlite3
import unittest
from unittest.mock import patch
from mission_control import creative_taste_store as taste
from mission_control.creative_taste import guidance
from mission_control.creative_library import Library
from mission_control.common import Invalid
from mission_control.db import connection, initialize
from mission_control.operator_client import ClientError, OperatorClient
from mission_control.operation_authority import PROTECTED
from tests import test_agent_grants as grants
from tests.test_creative_library import reference
from tests import test_verified_review as identities


class CreativeTasteTests(unittest.TestCase):
    setUp = grants.GrantTests.setUp
    tearDown = grants.GrantTests.tearDown

    def body(self, **changes):
        data = dict(lens='product', voice='Use plain and specific language.',
                    visual='Show authentic app controls clearly.', examples=[],
                    exclusions=['Do not invent testimonials.'])
        return dict(dict(id='taste-one', version=0, manifest_version=self.store.app('sample-one')['version'],
                         policy_sha256=guidance()['policy_sha256'], data=data), **changes)

    def call(self, action, body, app='sample-one', client=None):
        return (client or self.owner).request('POST', '/api/apps/' + app + '/packaging/' + action, body)

    def test_owner_save_read_revisions_restart_and_uncertain_observation(self):
        body = self.body()
        self.assertEqual(self.call('taste-reconcile', body)['status'], 'NO_REVISION_OBSERVED')
        first = self.call('taste-review', body)
        self.assertEqual(first['source_status'], 'CURRENT_OWNER_REVIEW')
        self.assertEqual(first['data']['reviewer']['principal'], identities.OWNER['principal'])
        self.assertFalse(first['execution_authority']);self.assertFalse(first['reuse_authority'])
        self.assertEqual(self.call('taste-read', {'id': first['id']}), first)
        observed = self.call('taste-reconcile', body)
        self.assertEqual(observed['status'], 'MATCHING_REVISION_OBSERVED')
        self.assertFalse(observed['automatic_retry'])
        altered = copy.deepcopy(body);altered['data']['voice'] = 'Different proposed voice'
        self.assertEqual(self.call('taste-reconcile', altered)['status'], 'DIFFERENT_REVISION_OBSERVED')
        with self.assertRaises(ClientError):self.call('taste-review', body)
        second = self.call('taste-review', dict(altered, version=1))
        self.assertEqual(second['version'], 2)
        initialize(self.store.path)
        self.assertEqual(self.call('taste-read', {'id': first['id'], 'version': 1}), first)
        with connection(self.store.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM jobs').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT count(*) FROM creative_taste_reviews').fetchone()[0], 2)

    def test_limits_unknown_fields_missing_owner_foreign_app_and_policy(self):
        body = self.body()
        with self.assertRaises(PermissionError):taste.save(self.store, 'sample-one', body)
        with connection(self.store.path) as db:
            token = PROTECTED.set(dict(grant_id='not-an-owner'))
            try:
                with self.assertRaises(PermissionError):taste.owner(db, self.store, 'sample-one')
            finally:PROTECTED.reset(token)
        for bad in [dict(body, approved=True), dict(body, reviewer=identities.OWNER), dict(body, manifest_version=999),
                    dict(body, policy_sha256='0'*64), dict(body, version=True), dict(body, version=1)]:
            with self.subTest(bad=bad), self.assertRaises(ClientError):self.call('taste-review', bad)
        for changes in [dict(voice='x'*4001), dict(exclusions=['x']*21), dict(examples=[{}]*13), dict(lens='guaranteed-viral')]:
            with self.subTest(changes=changes), self.assertRaises(ClientError):
                self.call('taste-review', dict(body, data=dict(body['data'], **changes)))
        with self.assertRaises(ClientError):self.call('taste-review', body, app='sample-two')
        stranger = OperatorClient(self.origin);stranger.bootstrap()
        with self.assertRaises(ClientError):self.call('taste-review', body, client=stranger)

    def test_source_examples_are_hash_bound_interpretations_not_reuse_rights(self):
        lib = Library(self.store)
        created = lib.save('sample-one', dict(data=reference()))
        source = next(row for row in lib.list('sample-one') if row['id'] == created['id'])
        capture = source['current']
        example = dict(reference=dict(kind='SOURCE', id=source['id'], version=capture['version'], sha256=capture['hash']),
                       interpretation='Observe the contrast, not the product claim.')
        body = self.body();body['data']['examples'] = [example]
        saved = self.call('taste-review', body)
        self.assertEqual(saved['data']['definition']['examples'], [example])
        self.assertNotIn('example.com', str(saved))
        duplicate = copy.deepcopy(body);duplicate['data']['examples'].append(example)
        with self.assertRaises(ClientError):self.call('taste-review', dict(duplicate, id='duplicate'))
        forged = copy.deepcopy(body);forged['data']['examples'][0]['reference']['sha256'] = '0'*64
        with self.assertRaises(ClientError):self.call('taste-review', dict(forged, id='forged'))
        lib.save('sample-one', dict(id=source['id'], version=1, data=reference(title='Changed source')))
        self.assertEqual(self.call('taste-read', {'id': saved['id']})['source_status'], 'STALE_OWNER_REVIEW')
        with self.assertRaises(ClientError):self.call('taste-review', dict(body, id='stale-example'))

    def test_app_policy_and_role_changes_invalidate_saved_owner_review(self):
        saved = self.call('taste-review', self.body())
        app = self.store.app('sample-one')
        self.store.save_app('sample-one', dict(app['data'], release='next-build'), app['version'])
        self.assertEqual(self.call('taste-read', {'id': saved['id']})['source_status'], 'STALE_OWNER_REVIEW')
        updated = self.call('taste-review', self.body(id='current-taste'))
        with patch.object(taste, 'guidance', return_value=dict(guidance(), policy_sha256='f'*64)):
            self.assertEqual(self.call('taste-read', {'id': updated['id']})['source_status'], 'STALE_OWNER_REVIEW')
        with connection(self.store.path) as db:
            db.execute('UPDATE operator_roles SET version=version+1 WHERE app_id=?', ('sample-one',))
        self.assertEqual(taste.read(self.store, 'sample-one', {'id': updated['id']})['source_status'], 'STALE_OWNER_REVIEW')
        with self.assertRaises(Invalid):taste.read(self.store, 'sample-two', {'id': updated['id']})

    def test_commit_rechecks_owner_and_rolls_back_review(self):
        actual = taste.bindings
        def revoke(db, store, app_id, value, app):
            result = actual(db, store, app_id, value, app)
            db.execute('UPDATE operator_roles SET version=version+1 WHERE app_id=?', (app_id,))
            return result
        with patch.object(taste, 'bindings', side_effect=revoke):
            with self.assertRaises(ClientError):self.call('taste-review', self.body())
        with connection(self.store.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM creative_taste_reviews').fetchone()[0], 0)

    def test_sql_history_rejects_update_delete_conflict_and_rowid_replace(self):
        saved = self.call('taste-review', self.body())
        with connection(self.store.path) as db:
            row = dict(db.execute('SELECT rowid,* FROM creative_taste_reviews').fetchone())
        statements = [('UPDATE creative_taste_reviews SET hash=?', ('0'*64,)),
                      ('DELETE FROM creative_taste_reviews', ()),
                      ('INSERT OR REPLACE INTO creative_taste_reviews VALUES(?,?,?,?,?,?)', tuple(row[k] for k in ['app_id','id','version','data','hash','created'])),
                      ('INSERT OR REPLACE INTO creative_taste_reviews(rowid,app_id,id,version,data,hash,created) VALUES(?,?,?,?,?,?,?)', (row['rowid'],row['app_id'],'other',1,row['data'],row['hash'],row['created']))]
        for sql, args in statements:
            with self.subTest(sql=sql), self.assertRaises(sqlite3.IntegrityError):
                with connection(self.store.path) as db:db.execute(sql, args)
        self.assertEqual(self.call('taste-read', {'id': saved['id']}), saved)

    def test_additive_initialization_preserves_existing_apps_roles_and_audit(self):
        with connection(self.store.path) as db:
            # Pre-feature shape: existing operational tables, no taste table.
            db.execute('DROP TABLE creative_taste_reviews')
            apps = [dict(row) for row in db.execute('SELECT * FROM apps ORDER BY id')]
            roles = [dict(row) for row in db.execute('SELECT * FROM operator_roles ORDER BY app_id,principal')]
            audit = [dict(row) for row in db.execute('SELECT * FROM audit ORDER BY id')]
        initialize(self.store.path);initialize(self.store.path)
        with connection(self.store.path) as db:
            self.assertEqual([dict(row) for row in db.execute('SELECT * FROM apps ORDER BY id')], apps)
            self.assertEqual([dict(row) for row in db.execute('SELECT * FROM operator_roles ORDER BY app_id,principal')], roles)
            self.assertEqual([dict(row) for row in db.execute('SELECT * FROM audit ORDER BY id')], audit)
        self.assertEqual(self.call('taste-review', self.body())['source_status'], 'CURRENT_OWNER_REVIEW')


if __name__ == '__main__':unittest.main()
