"""Weekly local evidence never becomes execution authority."""
import unittest
from mission_control.common import Invalid
from mission_control.weekly_controls import decision_controls
from mission_control.packets import weekly


class WeeklyControlsTests(unittest.TestCase):
    def setUp(self):
        self.app = dict(id='sample-one', version=1, data=dict(name='Sample', release='web:1', locale='en-GB'))
        self.stages = [dict(id=i, title=str(i), status='READY') for i in range(1, 13)]

    def test_ready_inputs_never_grant_spend_scale_or_pilot(self):
        result = decision_controls(self.app, [], self.stages)
        self.assertEqual(result['exception_order'], [])
        self.assertTrue(all(g['state'] == 'LOCAL_INPUTS_READY' for g in result['gates']))
        for key in ('spend_allowed', 'scale_allowed', 'learning_pilot_allowed'):
            self.assertIs(result[key], False)

    def test_missing_and_failed_retention_have_recovery(self):
        result = decision_controls(self.app, [], [])
        self.assertEqual(result['exception_order'], ['readiness', 'measurement', 'economics', 'retention'])
        self.assertTrue(all(g['state'] == 'UNKNOWN' and g['next_action'] for g in result['gates']))
        self.stages[9]['status'] = 'BLOCKED'
        result = decision_controls(self.app, [], self.stages)
        self.assertEqual(result['exception_order'], ['retention'])
        self.assertIn('denominator', result['gates'][3]['next_action'])

    def test_duplicate_malformed_or_invented_pass_rejects(self):
        for stages in ([self.stages[0]] * 2, [dict(id=True, status='READY')], [dict(id=2, status='PASS')]):
            with self.assertRaises(Invalid): decision_controls(self.app, [], stages)

    def test_scope_and_version_change_receipt(self):
        first = decision_controls(self.app, [], self.stages)
        self.app['version'] = 2
        self.assertNotEqual(first['source_hash'], decision_controls(self.app, [], self.stages)['source_hash'])
        with self.assertRaises(Invalid):
            decision_controls(self.app, [dict(app_id='other-app')], self.stages)

    def test_weekly_packet_contains_controls_without_claiming_lift(self):
        report = weekly(self.app, [], self.stages)
        self.assertEqual(report['incremental_lift'], 'UNPROVEN')
        self.assertEqual(report['approved_spend_minor'], 0)
        self.assertEqual(report['decision_controls']['authority'], 'NO_EXECUTION_AUTHORITY')
