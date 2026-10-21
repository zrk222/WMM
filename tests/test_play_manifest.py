"""Android setup stays explicit, versioned and separate from Apple identity."""
import tempfile
import unittest
from pathlib import Path
from mission_control.common import Invalid
from mission_control.store import Store, app_data


class PlayManifestTests(unittest.TestCase):
    def test_optional_android_target_preserves_apple_and_unknowns(self):
        base=dict(name='Synthetic app',store_app_id='123')
        self.assertEqual(app_data(base)['store_app_id'],'123')
        value=app_data(dict(base,android_package='com.example.app',android_track='internal'))
        self.assertEqual(value['store_app_id'],'123')
        self.assertEqual(value['android_track'],'internal')
        self.assertNotIn('android_package',app_data(base))

    def test_partial_or_unsafe_android_identity_is_rejected(self):
        for fields in (dict(android_package='com.example.app'),dict(android_track='internal'),
                       dict(android_package='com.example.app',android_track='../production'),
                       dict(android_package='https://foreign.example',android_track='production'),
                       dict(android_package=['com.example.app'],android_track='production')):
            with self.subTest(fields=fields),self.assertRaises(Invalid):app_data(dict(name='Synthetic',**fields))

    def test_target_edit_is_versioned_and_survives_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'synthetic.sqlite';store=Store(path,seed=False)
            first=store.save_app('synthetic',dict(name='Synthetic',store_app_id='123'))
            data=dict(first['data'],android_package='com.example.app',android_track='internal')
            second=store.save_app('synthetic',data,first['version'])
            with self.assertRaises(Invalid):store.save_app('synthetic',data,first['version'])
            restored=Store(path,seed=False).app('synthetic')
            self.assertEqual(restored,second)
            self.assertEqual(restored['data']['store_app_id'],'123')
            snapshot=store.export('synthetic')
            receiver=Store(Path(directory)/'receiver.sqlite',seed=False)
            receiver.restore(snapshot)
            self.assertEqual(receiver.app('synthetic')['data'],restored['data'])
            self.assertTrue({'learning','payments','storekit','attribution','aeo','followup','pmf_research','inspection_history'}<=set(snapshot['payload']))
