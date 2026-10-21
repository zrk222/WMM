"""Atomic selected-field approval; no provider credentials, app data or authority borrowing."""
from datetime import timedelta
from unittest.mock import patch
from mission_control.common import Invalid, digest, iso_time
from mission_control.db import connection
from mission_control.setup_approval import apply
from tests.test_setup_discovery import SetupFixture


class SetupApprovalTests(SetupFixture):
    def approval(self, row, changes=None):
        app = self.store.app('sample-one')
        return dict(app_id='sample-one', id=row['id'], proposal_hash=row['hash'], app_version=app['version'],
                    app_hash=digest(app['data']), changes=changes if changes is not None else {'name':'Real app'}, confirm_apply=True)

    def test_apply_selected_observation_and_edited_value_without_readiness_claim(self):
        row = self.start()
        before = self.store.app('sample-one')
        result = apply(self.store, 'sample-one', self.approval(row, {'name':'Real app', 'audience':'Reviewed audience'}))
        app = self.store.app('sample-one')
        self.assertEqual(result['app_version'], before['version'] + 1)
        self.assertEqual(app['data']['name'], 'Real app')
        self.assertEqual(app['data']['store_app_id'], '123')
        sources = app['data']['setup_sources']
        self.assertEqual(sources['name']['label'], 'PUBLIC_METADATA_UNVERIFIED')
        self.assertEqual(sources['audience']['label'], 'HUMAN_EDIT')
        self.assertEqual(sources['name']['value_sha256'], digest('Real app'))
        self.assertEqual(result['readiness'], 'NOT_VERIFIED')
        self.assertFalse(result['external_writes'])
        self.assertEqual(self.service.list('sample-one')['proposals'][0]['currentness'], 'APPLIED')

    def test_replay_and_changed_manifest_are_rejected_without_second_update(self):
        row = self.start()
        body = self.approval(row)
        apply(self.store, 'sample-one', body)
        saved = self.store.app('sample-one')
        with self.assertRaises(Invalid):
            apply(self.store, 'sample-one', body)
        self.assertEqual(self.store.app('sample-one'), saved)

    def test_foreign_and_altered_source_hash_do_not_mutate_either_app(self):
        row = self.start()
        body = self.approval(row)
        first, second = self.store.app('sample-one'), self.store.app('sample-two')
        for target, changed in [('sample-two', body), ('sample-one', {**body, 'proposal_hash':'0'*64}),
                                ('sample-one', {**body, 'app_hash':'0'*64}), ('sample-one', {**body, 'app_id':'sample-two'})]:
            with self.subTest(target=target, changed=changed), self.assertRaises(Invalid):
                apply(self.store, target, changed)
        self.assertEqual(self.store.app('sample-one'), first)
        self.assertEqual(self.store.app('sample-two'), second)

    def test_expired_proposal_is_not_rescued_by_a_new_request_version(self):
        row = self.start()
        future = (iso_time(row['expires']) + timedelta(seconds=1)).isoformat()
        with patch('mission_control.setup_discovery.now', return_value=future), self.assertRaises(Invalid):
            apply(self.store, 'sample-one', self.approval(row))

    def test_invalid_selection_identity_and_normalization_roll_back(self):
        row = self.start()
        app = self.store.app('sample-one')
        selections = [{}, {'authorized_spend_minor':'999'}, {'name':'x'*101}, {'store_app_id':'foreign'},
                      {'locale':'English language'}, {'name':True}, {'job':' '}, {'android_package':'com.example.new'}]
        for changes in selections:
            with self.subTest(changes=changes), self.assertRaises(Invalid):
                apply(self.store, 'sample-one', self.approval(row, changes))
            self.assertEqual(self.store.app('sample-one'), app)
            self.assertEqual(self.service.list('sample-one')['proposals'][0]['state'], 'PENDING')

    def test_failed_discovery_cannot_approve_its_own_facts(self):
        from tests.test_aeo_inspection import Reader
        row = self.start(Reader(robots='User-agent: *\nDisallow: /\n'))
        with self.assertRaises(Invalid):
            apply(self.store, 'sample-one', self.approval(row))

    def test_android_pair_and_provider_records_remain_separate_from_apple_id(self):
        connection_row = self.store.save_record('sample-one', dict(kind='connection', title='Synthetic Apple access',
            source='Synthetic test', data=dict(provider='app_store', store_app_id='123', account_id='0', env_ref='SYNTHETIC_KEY')))
        row = self.start()
        apply(self.store, 'sample-one', self.approval(row, {'android_package':'com.example.new', 'android_track':'internal'}))
        app = self.store.app('sample-one')
        self.assertEqual(app['data']['store_app_id'], '123')
        self.assertEqual(app['data']['android_package'], 'com.example.new')
        self.assertEqual(self.store.records('sample-one'), [connection_row])
        self.assertEqual(app['data']['authorized_spend_minor'], 0)

    def test_delete_applied_draft_preserves_approved_setup_and_provenance(self):
        row = self.start()
        apply(self.store, 'sample-one', self.approval(row))
        saved = self.store.app('sample-one')
        self.service.delete('sample-one', dict(id=row['id'], hash=row['hash'], confirm_delete=True))
        self.assertEqual(self.store.app('sample-one'), saved)
        with connection(self.store.path) as db:
            events = [item[0] for item in db.execute("SELECT action FROM audit WHERE action LIKE 'setup.%' ORDER BY rowid")]
        self.assertEqual(events, ['setup.proposal_created', 'setup.proposal_applied', 'setup.proposal_deleted'])

    def test_malformed_review_identity_and_extra_fields_fail_before_sql(self):
        row = self.start()
        original = self.approval(row)
        bad = [{'id':{}}, {'proposal_hash':[]}, {'app_hash':True}, {'app_version':True},
               {'app_id':None}, {'override':True}, {'confirm_apply':False}]
        for patch_fields in bad:
            with self.subTest(fields=patch_fields), self.assertRaises(Invalid):
                apply(self.store, 'sample-one', {**original, **patch_fields})
        self.assertEqual(self.service.list('sample-one')['proposals'][0]['state'], 'PENDING')
