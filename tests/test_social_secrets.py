"""Native-storage namespace, staged ownership, cleanup failure and restart recovery."""
import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from mission_control.common import Invalid,canonical,now
from mission_control.store import Store
from mission_control.db import connection
from mission_control.social_secrets import Secrets,name,queue
from tests.test_measurement_connectors import FakeVault


class SocialSecretTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.store=Store(Path(self.folder.name)/'synthetic.sqlite3');self.secrets=Secrets(self.store)
        FakeVault.values={};FakeVault.fail_delete=0
        vault=patch('mission_control.social_secrets.Vault',FakeVault);vault.start();self.addCleanup(vault.stop)

    def test_separate_long_fields_are_protected_scoped_and_excluded_from_exports(self):
        values={'access_token':'synthetic-access-'+'A'*1500,'refresh_token':'synthetic-refresh-'+'B'*1500}
        ref=self.secrets.stage('sample-one','linkedin',values)
        self.assertEqual(self.secrets.load('sample-one','linkedin',ref),values)
        self.assertEqual(Secrets(Store(self.store.path)).load('sample-one','linkedin',ref),values)
        with self.assertRaises(Invalid):self.secrets.load('sample-two','linkedin',ref)
        with self.assertRaises(Invalid):self.secrets.load('sample-one','tiktok',ref)
        snapshot=canonical(self.store.export('sample-one'))
        self.assertNotIn(ref,snapshot);self.assertNotIn('synthetic-access-',snapshot)
        with connection(self.store.path) as db:
            raw=''.join(str(tuple(r)) for r in db.execute('SELECT * FROM social_retirements'))
        self.assertNotIn('synthetic-access-',raw)

    def test_partial_write_or_failed_retirement_remains_recoverable(self):
        ref=self.secrets.stage('sample-one','tiktok',{'access_token':'synthetic-access','refresh_token':'synthetic-refresh'})
        FakeVault.fail_delete=1
        self.assertEqual(self.secrets.retire('sample-one','tiktok',ref),'LOCAL_CLEANUP_REQUIRED')
        reopened=Secrets(Store(self.store.path));self.assertEqual(reopened.cleanup('sample-two')['remaining'],0)
        self.assertEqual(reopened.cleanup('sample-one')['remaining'],0);self.assertFalse(FakeVault.values)
        original=FakeVault.put
        def fail_second(vault,target,value):
            if target.endswith('/refresh_token'):raise Invalid('Synthetic write failure')
            return original(vault,target,value)
        with patch.object(FakeVault,'put',fail_second):
            with self.assertRaisesRegex(Invalid,'write failure'):self.secrets.stage('sample-one','tiktok',{'access_token':'synthetic-access','refresh_token':'synthetic-refresh'})
        self.assertFalse(FakeVault.values)

    def test_active_config_cannot_be_deleted_and_missing_stage_cannot_activate(self):
        ref=self.secrets.stage('sample-one','facebook',{'client_secret':'synthetic-client-secret'})
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE');self.secrets.activate(db,'sample-one','facebook',ref,['client_secret'])
            db.execute('INSERT INTO social_configs VALUES(?,?,?,?,?,?,?,?)',('sample-one','facebook',1,'{}',ref,'CONFIGURED',now(),now()))
        self.assertEqual(self.secrets.retire('sample-one','facebook',ref),'LOCAL_CLEANUP_REQUIRED')
        with self.assertRaisesRegex(Invalid,'active social'):self.secrets.cleanup('sample-one')
        self.assertEqual(self.secrets.load('sample-one','facebook',ref),{'client_secret':'synthetic-client-secret'})
        with connection(self.store.path) as db:
            with self.assertRaisesRegex(Invalid,'already attached'):self.secrets.activate(db,'sample-one','facebook',ref,['client_secret'])

    def test_interrupted_stages_have_a_grace_period_then_cleanup(self):
        ref=self.secrets.stage('sample-one','instagram',{'verifier':'V'*64})
        self.assertEqual(self.secrets.cleanup('sample-one')['remaining'],1)
        with connection(self.store.path) as db:db.execute('UPDATE social_retirements SET eligible=0')
        self.assertEqual(Secrets(Store(self.store.path)).cleanup('sample-one')['remaining'],0)
        with self.assertRaises(Invalid):self.secrets.load('sample-one','instagram',ref)

    def test_no_free_form_credential_addresses_or_invalid_fields(self):
        for value in ({'password':'no passwords'},{'access_token':'has whitespace'},{'access_token':'x'*2049},{}):
            with self.subTest(value=value),self.assertRaises(Invalid):self.secrets.stage('sample-one','tiktok',value)
        self.assertFalse(FakeVault.values)
        with self.assertRaises(Invalid):name(self.store,'sample-one','tiktok','../outside','access_token')


if __name__=='__main__':unittest.main()
