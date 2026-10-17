"""Only selected-app discovery, optimistic approval and crash-safe setup storage."""
import os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from mission_control.common import Invalid,canonical,now
from mission_control.store import Store
from mission_control.db import connection
from mission_control.social_setup import Setup
from mission_control.social_contract import relay_base
from tests.test_measurement_connectors import FakeVault


def body(provider='facebook',**changes):
    return dict(provider=provider,client_id='123456',client_secret='synthetic-client-secret',
                redirect_uri='https://relay.example/cb/'+provider,native_enabled=False,version=0,**changes)


class SocialSetupTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        self.store=Store(Path(folder.name)/'synthetic.sqlite3');self.setup=Setup(self.store)
        FakeVault.values={};FakeVault.fail_delete=0
        vault=patch('mission_control.social_secrets.Vault',FakeVault);vault.start();self.addCleanup(vault.stop)

    def test_known_app_facts_and_setup_links_without_invented_provider_app(self):
        for provider in ('facebook','instagram','linkedin','tiktok'):
            packet=self.setup.packet('sample-one',provider)
            self.assertEqual(packet['app_name'],self.store.app('sample-one')['data']['name'])
            self.assertTrue(packet['official_setup'].startswith('https://'))
            self.assertTrue(packet['no_publication_or_spending'])
            self.assertNotIn('client_id',packet)
        self.assertEqual(self.setup.packet('sample-one','tiktok')['redirect_uri'],'http://127.0.0.1:8765/social/callback/tiktok')

    def test_save_hides_secret_survives_reopen_and_is_app_scoped(self):
        self.setup.save('sample-one',body());public=canonical(self.setup.view('sample-one'))
        self.assertNotIn('synthetic-client-secret',public);self.assertNotIn('secret_ref',public)
        self.assertEqual(Setup(Store(self.store.path)).get('sample-one','facebook')['version'],1)
        self.assertEqual(self.setup.view('sample-two')['configurations'],[])
        with connection(self.store.path) as db:raw=str([tuple(r) for r in db.execute('SELECT * FROM social_configs')])
        self.assertNotIn('synthetic-client-secret',raw)
        self.assertNotIn('social_configs',canonical(self.store.export('sample-one')))

    def test_conflicting_save_removes_only_unattached_stage(self):
        self.setup.save('sample-one',body());before=dict(FakeVault.values)
        with self.assertRaisesRegex(Invalid,'setup changed'):self.setup.save('sample-one',body())
        self.assertEqual(FakeVault.values,before);self.assertEqual(self.setup.get('sample-one','facebook')['version'],1)
        update={**body(),'version':1,'client_secret':'synthetic-new-secret'}
        self.setup.save('sample-one',update)
        self.assertEqual(self.setup.get('sample-one','facebook')['version'],2)
        self.assertEqual(len(FakeVault.values),1)

    def test_discovery_reads_only_selected_prefix_and_approval_rechecks_preview(self):
        values={'GROWTH_SAMPLE_ONE_FACEBOOK_CLIENT_ID':'123456','GROWTH_SAMPLE_ONE_FACEBOOK_CLIENT_SECRET':'synthetic-client-secret',
                'GROWTH_SAMPLE_ONE_FACEBOOK_REDIRECT_URI':'https://relay.example/cb/facebook',
                'GROWTH_SAMPLE_TWO_FACEBOOK_CLIENT_SECRET':'DO_NOT_READ_OR_RETURN'}
        with patch.dict(os.environ,values,clear=True):
            preview=self.setup.discover('sample-one','facebook')
            self.assertTrue(preview['secret_present']);self.assertNotIn('synthetic-client-secret',canonical(preview))
            self.assertNotIn('DO_NOT_READ',canonical(preview))
            request=dict(provider='facebook',configuration=preview['configuration'],version=0)
            with patch.dict(os.environ,{'GROWTH_SAMPLE_ONE_FACEBOOK_CLIENT_ID':'999999'}):
                with self.assertRaisesRegex(Invalid,'setup changed'):self.setup.approve_discovered('sample-one',request)
            self.setup.approve_discovered('sample-one',request)
            self.assertEqual(self.setup.get('sample-one','facebook')['version'],1)
        with patch.dict(os.environ,{},clear=True):self.assertEqual(self.setup.discover('sample-two','tiktok')['status'],'SETUP_REQUIRED')

    def test_native_configuration_has_no_secret_and_wrong_permissions_are_rejected(self):
        value={**body('linkedin'),'client_secret':'','native_enabled':True,'redirect_uri':''}
        self.setup.save('sample-one',value)
        self.assertIsNone(self.setup.get('sample-one','linkedin')['secret_ref']);self.assertFalse(FakeVault.values)
        with self.assertRaises(Invalid):self.setup.save('sample-two',{**body(),'scopes':['publish_everything']})

    def test_relay_base_defaults_are_validated_scoped_and_do_not_replace_native_callbacks(self):
        app=self.store.app('sample-one');base='https://synthetic-relay.example'
        self.store.save_app('sample-one',{**app['data'],'social_callback_base_url':base+'/'},app['version'])
        for provider in ('facebook','instagram','linkedin'):
            self.assertEqual(self.setup.packet('sample-one',provider)['redirect_uri'],base+'/cb/'+provider)
        self.assertEqual(self.setup.packet('sample-two','facebook')['redirect_uri'],'')
        self.assertEqual(self.setup.packet('sample-one','tiktok')['redirect_uri'],'http://127.0.0.1:8765/social/callback/tiktok')
        self.assertEqual(self.setup.packet('sample-one','linkedin',True)['redirect_uri'],'http://127.0.0.1:8765/social/callback/linkedin')
        self.assertEqual(relay_base(''),'')
        for bad in ('http://relay.example','https://127.0.0.1','https://user:secret@relay.example','https://relay.example/cb/facebook','https://relay.example?return=private',None):
            with self.subTest(bad=bad),self.assertRaises(Invalid):relay_base(bad)
        current=self.store.app('sample-one')
        with self.assertRaises(Invalid):self.store.save_app('sample-one',{**current['data'],'social_callback_base_url':'http://relay.example'},current['version'])
        self.assertEqual(self.store.app('sample-one')['version'],current['version'])


if __name__=='__main__':unittest.main()
