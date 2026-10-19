"""Prepared integration artifacts retain exact app source scope and no credentials."""
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import copy,hashlib,json,unittest,zipfile
from mission_control.common import Invalid,digest
from mission_control.instrumentation import bundle,archive
from mission_control.store import Store
from mission_control.tracking_contract import proposal
from tests.test_tracking_contract import fixture


class InstrumentationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(Path(self.tmp.name)/'synthetic.sqlite3')
        app,experiment,source=fixture(self.store)
        self.plan=dict(proposal(app,experiment,source),origin='https://example.com')

    def test_bundle_is_deterministic_source_bound_and_prepared_not_installed(self):
        value=bundle(self.plan);self.assertEqual(value,bundle(self.plan))
        self.assertEqual(value['status'],'PREPARED_NOT_INSTALLED');self.assertFalse(value['provider_writes'])
        self.assertEqual(value['bundle_hash'],digest({k:v for k,v in value.items() if k!='bundle_hash'}))
        for row in value['files']:self.assertEqual(row['sha256'],hashlib.sha256(row['content'].encode()).hexdigest())
        config=json.loads(next(r['content'] for r in value['files'] if r['name']=='config.json'))
        self.assertEqual(config['experiment_hash'],self.plan['experiment_hash'])
        self.assertEqual(config['release'],self.plan['release']);self.assertEqual(config['locale'],self.plan['locale'])
        self.assertNotIn('source_id',config);self.assertNotIn('api_key',config)

    def test_rejects_extra_inputs_tampered_source_and_nonorigin_targets(self):
        for change in ({'api_key':'PRIVATE'},{'release':'another'},{'origin':'https://example.com/path'}):
            with self.subTest(change=change),self.assertRaises(Invalid):bundle({**self.plan,**change})

    def test_archive_contains_only_fixed_files_and_verifiable_content_manifest(self):
        value=bundle(self.plan);raw=archive(value);self.assertEqual(raw,archive(value))
        with zipfile.ZipFile(BytesIO(raw)) as zipped:
            self.assertEqual(set(zipped.namelist()),{'manifest.json','config.json','example.mjs','experiment-client.mjs','README.md'})
            manifest=json.loads(zipped.read('manifest.json'))
            for row in manifest['files']:self.assertEqual(row['sha256'],hashlib.sha256(zipped.read(row['name'])).hexdigest())
            self.assertEqual(manifest['status'],'PREPARED_NOT_INSTALLED')
            self.assertIn(b'QUEUED_NOT_DELIVERED',zipped.read('README.md'))
        changed=copy.deepcopy(value);changed['files'][0]['content']='tampered'
        with self.assertRaises(Invalid):archive(changed)


if __name__=='__main__':unittest.main()
