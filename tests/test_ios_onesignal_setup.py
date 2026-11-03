"""Native owner bridge and host-supplied Keychain callback; synthetic data only."""
import json
from mission_control.common import Invalid
from mission_control.ios_onesignal_setup import OneSignalNativeVault
from tests import test_ios_provider_access as fixture
from tests.test_onesignal_transport import KEY


class NativeOneSignalTests(fixture.NativeProviderTests):
    def native(self,action,body,app='new-app'):
        return json.loads(self.runtime.native_onesignal(self.session,app,action,json.dumps(body).encode()))

    def test_native_setup_is_registered_and_saves_key_only_in_host_vault(self):
        self.setup_access()
        self.assertEqual(self.native('status',{})['state'],'KEY_NOT_CONFIGURED')
        saved=self.native('save-key',{'kind':'app','key':KEY,'version':0})
        self.assertEqual(saved['state'],'KEY_SAVED_UNBOUND');self.assertEqual(saved['version'],1)
        self.assertTrue(self.values);self.assertNotIn(KEY,json.dumps(self.native('status',{})))
        with self.assertRaises(PermissionError):self.native('status',{},app='other')
        self.available=False
        with self.assertRaises(PermissionError):self.native('status',{})

    def test_keychain_adapter_rejects_other_owner_app_and_chunk_paths(self):
        self.setup_access();user=self.runtime.identities.fresh(self.session)
        vault=OneSignalNativeVault(self.vault,self.runtime.service.store,'new-app',user['principal'])
        ref='11111111-1111-4111-8111-111111111111'
        for path in (vault.prefix+ref+'/../manifest',vault.prefix+ref+'/../../escape',
                     vault.prefix+ref+'/bad',vault.prefix+'not-a-uuid/manifest',
                     vault.prefix.replace('new-app','other-app')+ref+'/manifest',
                     vault.prefix.replace(vault.prefix.split('/')[-2],'a'*24)+ref+'/manifest'):
            with self.subTest(path=path),self.assertRaises(Invalid):vault.get(path)
        self.assertEqual(self.calls,[])
