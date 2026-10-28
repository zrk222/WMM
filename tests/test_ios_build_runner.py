import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
import tempfile

path=Path(__file__).resolve().parents[1]/'ios/Build/run_simulators.py'
spec=importlib.util.spec_from_file_location('ios_simulator_runner',path)
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
buildspec=importlib.util.spec_from_file_location('ios_runtime_builder',path.with_name('build_runtime.py'))
builder=importlib.util.module_from_spec(buildspec);buildspec.loader.exec_module(builder)


class SimulatorSelectionTests(unittest.TestCase):
    def test_source_commit_and_annotated_tag_have_separate_checks(self):
        lock={'source_commit':'commit-id','source_tag_object':'tag-object-id','source_tag':'v3.14.0'}
        with patch.object(builder,'run',side_effect=['commit-id','tag-object-id','']):
            builder.verify_source(Path('source'),lock)
        with patch.object(builder,'run',return_value='tag-object-id'):
            with self.assertRaisesRegex(SystemExit,'commit differs'):
                builder.verify_source(Path('source'),lock)
        with patch.object(builder,'run',side_effect=['commit-id','changed-tag']):
            with self.assertRaisesRegex(SystemExit,'tag object differs'):
                builder.verify_source(Path('source'),lock)

    def test_source_framework_requires_packaging_helper(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);framework=root/'cross-build/iOS/Python.xcframework'
            framework.mkdir(parents=True);(framework/'Info.plist').write_text('fixture')
            with self.assertRaisesRegex(SystemExit,'helper is absent'):builder.framework_output(root)
            (framework/'build').mkdir();(framework/'build/utils.sh').write_text('fixture')
            self.assertEqual(builder.framework_output(root),framework)

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
