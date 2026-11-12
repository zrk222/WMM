"""Native adapter seam tests; actual Keychain round-trip belongs to Mac CI."""
import types
import unittest
from unittest.mock import Mock, patch

from mission_control import macos_vault as native
from mission_control.common import Invalid


class Backend:
    def __init__(self):
        self.items = {}
        self.keychain = 'ENVIRONMENT_PATH_MUST_NOT_BE_USED'

    def set_password(self, service, account, raw):
        self.items[service, account] = raw

    def get_password(self, service, account):
        return self.items.get((service, account))

    def delete_password(self, service, account):
        del self.items[service, account]


class MacOSVaultTests(unittest.TestCase):
    def setUp(self):
        self.backend = Backend()
        self.importer = patch.object(native.importlib, 'import_module',
                                     return_value=types.SimpleNamespace(Keyring=lambda: self.backend))
        self.importer.start()
        self.addCleanup(self.importer.stop)
        self.vault = native.MacOSVault()

    def test_exact_native_backend_and_scoped_item_lifecycle(self):
        native.importlib.import_module.assert_called_once_with('keyring.backends.macOS')
        self.assertIsNone(self.backend.keychain)
        one, two = 'SocialGrowth/workspace-one/app/ref/access_token', 'SocialGrowth/workspace-two/app/ref/access_token'
        self.vault.put(one, {'token': 'SYNTHETIC_ONE'})
        self.vault.put(two, {'token': 'SYNTHETIC_TWO'})
        self.assertEqual(self.vault.get(one), {'token': 'SYNTHETIC_ONE'})
        self.vault.put(one, {'token': 'REPLACED'})
        self.assertEqual(self.vault.get(one), {'token': 'REPLACED'})
        self.assertEqual(self.vault.get(two), {'token': 'SYNTHETIC_TWO'})
        self.assertEqual(set(self.backend.items), {(native.SERVICE, native.address(one)),
                                                (native.SERVICE, native.address(two))})
        self.vault.delete(one)
        self.vault.delete(one)
        self.assertIsNone(self.vault.get(one))
        self.assertEqual(self.vault.get(two), {'token': 'SYNTHETIC_TWO'})

    def test_bounds_and_corruption_preserve_existing_value(self):
        self.vault.put('scoped', {'token': 'BEFORE'})
        self.assertEqual(len(native.encode('x' * 2558).encode()), 2560)
        with self.assertRaises(Invalid):
            self.vault.put('scoped', 'x' * 2559)
        self.assertEqual(self.vault.get('scoped'), {'token': 'BEFORE'})
        for raw in ('x' * 2561, '{"a":1,"a":2}', 'not-json', '\ud800', 1):
            with self.subTest(raw_type=type(raw).__name__), self.assertRaises(Invalid):
                native.decode(raw)
        for address in ('', None, 'bad\naddress', 'x' * 2049):
            with self.assertRaises(Invalid):
                self.vault.get(address)

    def test_denied_reads_writes_and_deletes_redact_native_error(self):
        self.vault.put('scoped', {'token': 'BEFORE'})
        for method, operation in (
            ('get_password', lambda: self.vault.get('scoped')),
            ('set_password', lambda: self.vault.put('scoped', {'token': 'AFTER'})),
            ('delete_password', lambda: self.vault.delete('scoped')),
        ):
            with self.subTest(method=method), patch.object(
                    self.backend, method, side_effect=RuntimeError('PRIVATE_NATIVE_ERROR')):
                with self.assertRaises(Invalid) as error:
                    operation()
                self.assertNotIn('PRIVATE_NATIVE_ERROR', str(error.exception))
        self.assertEqual(self.vault.get('scoped'), {'token': 'BEFORE'})

    def test_unavailable_dependency_never_chooses_another_backend(self):
        with patch.object(native.importlib, 'import_module', side_effect=ImportError('PRIVATE_PATH')):
            with self.assertRaises(Invalid) as error:
                native.MacOSVault()
            self.assertNotIn('PRIVATE_PATH', str(error.exception))

    def test_concurrent_exact_delete_is_idempotent(self):
        self.vault.put('scoped', {'token': 'BEFORE'})

        def deleted_elsewhere(service, account):
            self.backend.items.pop((service, account))
            raise RuntimeError('already removed')

        with patch.object(self.backend, 'delete_password', side_effect=deleted_elsewhere):
            self.vault.delete('scoped')
        self.assertIsNone(self.vault.get('scoped'))

    def test_facade_selects_only_mac_backend_on_darwin(self):
        from mission_control import credential_vault
        with patch.object(credential_vault.os, 'name', 'posix'), \
                patch.object(credential_vault.sys, 'platform', 'darwin'), \
                patch.object(native, 'MacOSVault', return_value=self.vault) as constructor:
            self.assertIs(credential_vault.Vault().backend, self.vault)
            constructor.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
