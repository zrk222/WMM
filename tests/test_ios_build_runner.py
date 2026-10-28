import importlib.util
from pathlib import Path
import unittest

path=Path(__file__).resolve().parents[1]/'ios/Build/run_simulators.py'
spec=importlib.util.spec_from_file_location('ios_simulator_runner',path)
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)


class SimulatorSelectionTests(unittest.TestCase):
    def test_selects_actual_available_ios_phone_and_tablet_only(self):
        inventory={'devices':{'com.apple.CoreSimulator.SimRuntime.iOS-26-0':[
            {'name':'iPhone Test','udid':'actual-phone-id','isAvailable':True},
            {'name':'iPad Test','udid':'actual-tablet-id','isAvailable':True},
            {'name':'iPhone Unavailable','udid':'bad','isAvailable':False}],
            'com.apple.CoreSimulator.SimRuntime.tvOS-26-0':[
            {'name':'iPhone Not iOS','udid':'tv','isAvailable':True}]}}
        self.assertEqual([d['udid'] for d in runner.select_devices(inventory)],['actual-phone-id','actual-tablet-id'])

    def test_missing_ipad_does_not_pass_as_complete_coverage(self):
        inventory={'devices':{'iOS':[{'name':'iPhone Test','udid':'phone','isAvailable':True}]}}
        with self.assertRaisesRegex(ValueError,'iPad'):runner.select_devices(inventory)

    def test_no_device_inventory_is_not_a_pass(self):
        with self.assertRaises(ValueError):runner.select_devices({'devices':{}})
