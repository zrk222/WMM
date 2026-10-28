"""Real app-scoped native report reads and pure projection boundaries."""
import json
import unittest
from unittest.mock import patch
from tests import test_ios_host as host_fixture
from mission_control.common import Invalid
from mission_control.ios_reports import projection


class NativeReportTests(unittest.TestCase):
    setUp = host_fixture.NativeRuntimeTests.setUp
    verify = host_fixture.NativeRuntimeTests.verify
    creation = host_fixture.NativeRuntimeTests.creation

    def report(self):return json.loads(self.runtime.report(self.session,'new-app'))

    def test_empty_report_keeps_unknown_and_exports_no_identity_or_connections(self):
        self.runtime.create_workspace(self.session,self.creation())
        value=self.report()
        self.assertEqual(set(value),{'appID','appName','sourceHash','observedAt','rows'})
        self.assertEqual(value['appID'],'new-app')
        self.assertEqual(len(value['sourceHash']),64)
        self.assertIsNone(next(r for r in value['rows'] if r['metric']=='App performance')['observed'])
        encoded=json.dumps(value)
        self.assertNotIn(self.principal,encoded)
        self.assertNotIn(self.session,encoded)

    def test_actual_cohort_arithmetic_and_source_hash_changes(self):
        self.runtime.create_workspace(self.session,self.creation())
        before=self.report()
        body=dict(id='cohort-evidence',kind='cohort',title='Synthetic cohort',source='PRIVATE_SOURCE_LABEL',data=dict(
            cohort_id='PRIVATE_COHORT_LABEL',currency='USD',installs=100,activated=40,paid=10,mature=True,
            acquisition_cost_minor=5000,net_proceeds_minor=9000,delivery_cost_minor=1000,refunds_minor=0,horizon='30 days'))
        self.runtime.service.evidence('new-app',body)
        value=self.report()
        self.assertNotEqual(before['sourceHash'],value['sourceHash'])
        rows={r['metric']:r for r in value['rows']}
        self.assertEqual(rows['Cohort 1: activation_rate']['observed'],'0.4')
        self.assertEqual(rows['Cohort 1: paid_cac_minor']['observed'],'500.0')
        self.assertIn('currency=USD',rows['Cohort 1: paid_cac_minor']['evidence'])
        self.assertNotIn('PRIVATE_SOURCE_LABEL',json.dumps(value))
        self.assertNotIn('PRIVATE_COHORT_LABEL',json.dumps(value))

    def test_foreign_or_lost_native_session_denies_report(self):
        self.runtime.create_workspace(self.session,self.creation())
        with self.assertRaises(PermissionError):self.runtime.report(self.session,'other')
        self.principal='00000000-0000-0000-0000-000000000001'
        with self.assertRaises(PermissionError):self.report()
        self.available=False
        with self.assertRaises(PermissionError):self.report()

    def test_real_event_report_preserves_denominators_costs_and_excludes_subjects(self):
        from tests.test_ledger import cohort, event
        self.runtime.create_workspace(self.session,self.creation())
        self.runtime.service.cohort('new-app',cohort())
        self.runtime.service.events('new-app',dict(cohort_id='pilot-1',events=[
            event('install','INSTALL',subject='PRIVATE_SUBJECT'),
            event('activation','ACTIVATION',subject='PRIVATE_SUBJECT'),
            event('purchase','PURCHASE',amount=2000,subject='PRIVATE_SUBJECT'),
            event('value','VALUE',day='2026-09-20',subject='PRIVATE_SUBJECT'),
            event('cost-a','COST_ACQUISITION',amount=300),event('cost-d','COST_DELIVERY',amount=100)]))
        result=self.report()
        rows={r['metric']:r for r in result['rows']}
        self.assertEqual(rows['Event cohort 1: installs']['observed'],'1')
        self.assertEqual(rows['Event cohort 1: paid_cac_minor']['observed'],'300.0')
        self.assertEqual(rows['Event cohort 1: contribution_after_acquisition_minor']['observed'],'1600')
        self.assertIn('status=SUPPLIED_RECONCILED',rows['Event cohort 1: installs']['evidence'])
        self.assertNotIn('PRIVATE_SUBJECT',json.dumps(result))

    def test_subscription_report_includes_trial_renewal_and_maturity_denominators(self):
        from tests import test_subscription_journey as fixture
        self.runtime.create_workspace(self.session,self.creation())
        self.runtime.service.cohort('new-app',fixture.cohort())
        self.runtime.service.events('new-app',dict(cohort_id='pilot-1',events=fixture.SubscriptionJourneyTests.history(None)))
        result=self.report();rows={r['metric']:r for r in result['rows']}
        self.assertEqual(rows['Event cohort 1, offer 1: trial_to_paid_rate']['observed'],'1.0')
        self.assertEqual(rows['Event cohort 1, offer 1: first_renewal_rate']['observed'],'1.0')
        self.assertEqual(rows['Event cohort 1, offer 1: mature_trial_subjects']['observed'],'1')
        self.assertEqual(rows['Event cohort 1, offer 1: PAYWALL_EXPOSURE']['observed'],'1')
        self.assertIn('coverage=SUPPLIED_NOT_VERIFIED',rows['Event cohort 1, offer 1: first_renewal_rate']['evidence'])
        self.assertNotIn('com.example.monthly',json.dumps(result))

    def test_session_revoked_during_projection_prevents_export(self):
        self.runtime.create_workspace(self.session,self.creation())
        real=projection
        def lost(*args):
            value=real(*args);self.available=False;return value
        with patch('mission_control.ios_reports.projection',lost):
            with self.assertRaises(PermissionError):self.report()

    def test_incomplete_cohort_keeps_rates_unknown_and_overflow_is_not_truncated(self):
        from mission_control.common import now
        self.runtime.create_workspace(self.session,self.creation())
        app=self.runtime.service.store.app('new-app')
        record=dict(kind='cohort',data=dict(installs=1,activated=0,paid=0,mature=False,acquisition_cost_minor=0,
                    net_proceeds_minor=0,delivery_cost_minor=0,refunds_minor=0))
        result=projection(app,[record],[],now())
        self.assertTrue(all(r['observed'] is None for r in result['rows'] if r['metric'].endswith('activation_rate')))
        with self.assertRaises(Invalid):projection(app,[record]*100,[],now())
