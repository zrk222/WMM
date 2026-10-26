"""Explicit isolated native acceptance; never run against an operator's keyring."""
import os
import sys
import unittest
import uuid
from contextlib import closing
from mission_control.credential_vault import Vault
from mission_control.common import Invalid


@unittest.skipUnless(sys.platform.startswith('linux') and os.environ.get('WMM_ISOLATED_NATIVE_KEYRING')=='1', 'Requires explicitly isolated Linux Secret Service profile')
class NativeLinuxVaultTests(unittest.TestCase):
    def test_scoped_native_roundtrip_cleanup_then_locked_rejection(self):
        import secretstorage
        name='AppGrowthInsights/isolated-native-'+str(uuid.uuid4());other=name+'-other';vault=Vault()
        try:
            vault.put(name,dict(token='synthetic-not-a-provider-token'));vault.put(other,dict(token='second-synthetic'))
            self.assertEqual(vault.get(name),dict(token='synthetic-not-a-provider-token'))
            # GNOME may add this standard generic-item metadata after persistence.
            from mission_control.linux_vault import address
            with closing(secretstorage.dbus_init()) as bus:
                collection=secretstorage.Collection(bus)
                items=list(collection.search_items(address(name)));self.assertEqual(len(items),1)
                items[0].set_attributes(address(name)|{'xdg:schema':'org.freedesktop.Secret.Generic'})
            self.assertEqual(vault.get(name),dict(token='synthetic-not-a-provider-token'))
            vault.put(name,dict(token='replaced-synthetic'));self.assertEqual(vault.get(name),dict(token='replaced-synthetic'))
            self.assertEqual(vault.get(other),dict(token='second-synthetic'))
        finally:
            vault.delete(name);vault.delete(other)
        self.assertIsNone(vault.get(name));self.assertIsNone(vault.get(other))
        # This opt-in profile must own a disposable keyring: lock only after verified cleanup.
        with closing(secretstorage.dbus_init()) as bus:secretstorage.Collection(bus).lock()
        with self.assertRaises(Invalid):vault.get(name)
        print('LINUX_NATIVE_VAULT_ROUNDTRIP_SCOPE_REPLACE_DELETE_CLEANUP_LOCK_PASS')
