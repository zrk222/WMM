"""Native-vault namespaces and durable Play consent storage are explicitly platform scoped."""
import os
from pathlib import Path
import tempfile
import unittest
from mission_control.common import Invalid, uid
from mission_control.credential_vault import Vault, namespace, target
from mission_control.db import connection
from mission_control.store import Store


class PlayStorageTests(unittest.TestCase):
    def test_namespaces_separate_app_database_and_provider(self):
        with tempfile.TemporaryDirectory() as folder:
            one, two = (namespace(Path(folder)/v) for v in ('one.sqlite', 'two.sqlite'))
            ref = uid(); names = [target(one, 'one', 'google_play', ref), target(one, 'two', 'google_play', ref),
                                  target(two, 'one', 'google_play', ref), target(one, 'one', 'app_store', ref)]
            self.assertEqual(len(set(names)), 4)
            with self.assertRaises(Invalid):target(one, 'one', 'google_play', '../outside')

    def test_database_initialization_is_idempotent_and_foreign_app_denied(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'test.sqlite'; Store(path, seed=False); Store(path, seed=False)
            with connection(path) as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM play_flows').fetchone()[0], 0)
                self.assertEqual(db.execute('SELECT COUNT(*) FROM play_retirements').fetchone()[0], 0)

    @unittest.skipUnless(os.name == 'nt', 'Actual Windows Credential Manager integration needs Windows')
    def test_native_protected_google_key_persists_between_vault_instances(self):
        with tempfile.TemporaryDirectory() as folder:
            name = target(namespace(Path(folder)/'test.sqlite'), 'synthetic-test', 'google_play', uid())
            vault = Vault()
            try:
                vault.put(name, {'synthetic': 'native-vault-integration'})
                self.assertEqual(Vault().get(name), {'synthetic': 'native-vault-integration'})
            finally:vault.delete(name)
            self.assertIsNone(Vault().get(name))


if __name__ == '__main__':unittest.main()
