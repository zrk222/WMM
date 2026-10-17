"""Fresh-install package behavior and persisted local app isolation."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from mission_control.common import Invalid
from mission_control.server import Server
from mission_control.server import check_timezone_support
from mission_control.service import Service
from mission_control.store import Store


class DistributionTests(unittest.TestCase):
    def test_launcher_workspace_identity_is_stable_and_path_scoped(self):
        with tempfile.TemporaryDirectory() as folder:
            first=Service(Store(Path(folder)/'one.sqlite3')).bootstrap()
            reopened=Service(Store(Path(folder)/'one.sqlite3')).bootstrap()
            other=Service(Store(Path(folder)/'two.sqlite3')).bootstrap()
            self.assertEqual(first['workspace_instance_id'],reopened['workspace_instance_id'])
            self.assertNotEqual(first['workspace_instance_id'],other['workspace_instance_id'])
            self.assertRegex(first['workspace_instance_id'],r'^[a-f0-9]{24}$')
            self.assertNotIn(folder,json.dumps(first))

    def test_timezone_dependency_is_available_after_setup(self):
        from datetime import datetime,timedelta
        from zoneinfo import ZoneInfo
        check_timezone_support()
        zone=ZoneInfo('America/Toronto')
        self.assertEqual(datetime(2026,7,1,12,tzinfo=zone).utcoffset(),timedelta(hours=-4))
        self.assertEqual(datetime(2026,1,1,12,tzinfo=zone).utcoffset(),timedelta(hours=-5))

    def test_missing_timezone_data_has_actionable_setup_error(self):
        from zoneinfo import ZoneInfoNotFoundError
        with patch('zoneinfo.ZoneInfo',side_effect=ZoneInfoNotFoundError('missing')):
            with self.assertRaisesRegex(Invalid,'pip install --require-hashes'):
                check_timezone_support()

    def test_fresh_install_needs_no_credentials_or_external_files(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(Path(folder)/'workspace.sqlite3')
            service=Service(store)
            bootstrap=service.bootstrap()
            self.assertEqual(len(bootstrap['apps']),3)
            self.assertFalse(bootstrap['automatic_external_writes'])
            self.assertEqual(bootstrap['authorized_spend_minor'],0)
            for app in store.apps():
                self.assertTrue(app['id'].startswith('sample-'))
                workspace=service.workspace(app['id'])
                self.assertEqual(workspace['records'],[])
                self.assertEqual(workspace['jobs'],[])

    def test_local_data_survives_reopen_and_stays_app_scoped(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'workspace.sqlite3'
            store=Store(path)
            store.save_app('my-new-app',dict(name='My app',job='A useful job',release='test'))
            store.save_record('my-new-app',dict(kind='claim',title='Local fact',source='Synthetic test',
                data=dict(claim='A fact',release='test',proof='Synthetic test')))
            reopened=Store(path)
            self.assertEqual(reopened.app('my-new-app')['data']['job'],'A useful job')
            self.assertEqual(len(reopened.records('my-new-app')),1)
            self.assertEqual(reopened.records('sample-one'),[])
            with self.assertRaises(Invalid):
                reopened.save_app('my-new-app',dict(name='Stale edit'),version=0)

    def test_remote_bind_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(Invalid):
                Server(('0.0.0.0',0),Store(Path(folder)/'workspace.sqlite3'))

    def test_generic_research_contract_exists(self):
        root=Path(__file__).resolve().parents[1]/'package'
        ledger=json.loads((root/'research-ledger.json').read_text(encoding='utf-8'))
        acquisition=json.loads((root/'acquisition-profiles.json').read_text(encoding='utf-8'))
        self.assertEqual(ledger['primary_notebook'],{})
        self.assertEqual(ledger['other_notebooks'],[])
        self.assertEqual(acquisition['apps'],[])
        self.assertEqual(acquisition['authorized_spend_minor_units'],0)
