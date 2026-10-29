"""Real native SQLite records and host callback boundary; no device claim."""
import json
import unittest
from unittest.mock import patch
from uuid import uuid4

from mission_control.connection_setup import Connections, STATUS_SOURCE
from mission_control.db import connection
from mission_control.ios_connection_status import native_connection_status
from tests import test_ios_host as fixture


class NativeConnectionStatusTests(unittest.TestCase):
    setUp = fixture.NativeRuntimeTests.setUp
    verify = fixture.NativeRuntimeTests.verify
    creation = fixture.NativeRuntimeTests.creation

    def setUp_records(self):
        self.runtime.create_workspace(self.session, self.creation())
        with connection(self.path) as db:
            for identity, provider, mode in [('apple','app_store','managed_key'), ('ads','apple_ads','managed_key'),
                                             ('play','google_play','managed_key'), ('old','app_store','disconnected')]:
                data = dict(provider=provider, auth_mode=mode, credential_ref=str(uuid4()))
                db.execute('INSERT INTO records VALUES(?,?,?,?,?,?,?,?,?,?)',
                    (identity,'new-app','connection','Synthetic',json.dumps(data),'test','test','hash',1,'2026-01-01'))

    def test_unsupported_connections_report_repair_without_vault_or_secret_reads(self):
        self.setUp_records()
        callback = lambda raw: self.fail('No supported native connection key namespace exists')
        with patch('mission_control.connection_setup.Vault', side_effect=AssertionError('Desktop vault used')):
            with native_connection_status(self.runtime.service, self.runtime.identities, self.session, callback):
                result = Connections(self.runtime.service.store).statuses('new-app')
        for identity in ('apple','ads','play'):
            self.assertEqual(result[identity], dict(status='RECONNECT_REQUIRED', repair='NATIVE_PROVIDER_ONBOARDING_REQUIRED'))
        self.assertEqual(result['old'], dict(status='DISCONNECTED', cleanup='UNCONFIRMED'))
        self.assertNotIn('credential_ref', json.dumps(result))
        self.assertIsNone(STATUS_SOURCE.get())

    def test_foreign_owner_lock_and_exception_restore_context(self):
        self.setUp_records()
        with native_connection_status(self.runtime.service, self.runtime.identities, self.session, None):
            with self.assertRaises(PermissionError): Connections(self.runtime.service.store).statuses('other')
            self.available = False
            with self.assertRaises(PermissionError): Connections(self.runtime.service.store).statuses('new-app')
        self.assertIsNone(STATUS_SOURCE.get())
        self.available = True
        with self.assertRaises(RuntimeError):
            with native_connection_status(self.runtime.service, self.runtime.identities, self.session, None):
                raise RuntimeError('synthetic')
        self.assertIsNone(STATUS_SOURCE.get())

    def test_standing_pipeline_records_repair_without_desktop_vault(self):
        from mission_control.ios_agent_access import NativeAgentAccess
        from mission_control.ios_automation import native_access
        from mission_control.ios_jobs import NativeJobs, native_pipeline_context
        from tests.test_ios_automation import NativeStandingTests
        helper = NativeStandingTests('test_standing_pipeline_queue_run_and_off_are_owner_and_scope_bound')
        helper.setUp()
        self.addCleanup(helper.doCleanups)
        helper.setup_standing()
        with connection(helper.path) as db:
            db.execute('INSERT INTO records VALUES(?,?,?,?,?,?,?,?,?,?)',
                ('apple','new-app','connection','Synthetic',json.dumps(dict(provider='app_store',auth_mode='managed_key',credential_ref=str(uuid4()))), 'test','test','hash',1,'2026-01-01'))
        preview = helper.manage('preview', helper.proposal(['pipeline_preparation']))
        issued = helper.manage('activate', dict(proposal=preview['proposal'], summary_hash=preview['summary_hash'], confirm_scope=True))
        request = json.dumps(dict(app_id='new-app', operation='pipeline.prepare',
            input=dict(action='pipeline', data=dict(stage=1), request_key='status-proof'))).encode()
        with native_access(helper.runtime.service, helper.runtime.identities, helper.session, helper.vault):
            with native_pipeline_context(helper.runtime.service, helper.runtime.identities, helper.session):
                queued = json.loads(NativeAgentAccess(helper.runtime.service, helper.runtime.identities).call(helper.session, issued['token'], request))
            with patch('mission_control.connection_setup.Vault', side_effect=AssertionError('Desktop vault used')):
                result = json.loads(NativeJobs(helper.runtime.service, helper.runtime.identities, vault_callback=helper.vault).call(
                    helper.session, 'new-app', 'run', json.dumps(dict(id=queued['id'])).encode()))
        self.assertEqual(result['status'], 'SUCCEEDED')
        self.assertEqual(result['result']['native_connection_status']['apple']['repair'], 'NATIVE_PROVIDER_ONBOARDING_REQUIRED')


if __name__ == '__main__': unittest.main()
