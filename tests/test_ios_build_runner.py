import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
import tempfile
import json

path=Path(__file__).resolve().parents[1]/'ios/Build/run_simulators.py'
spec=importlib.util.spec_from_file_location('ios_simulator_runner',path)
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
buildspec=importlib.util.spec_from_file_location('ios_runtime_builder',path.with_name('build_runtime.py'))
builder=importlib.util.module_from_spec(buildspec);buildspec.loader.exec_module(builder)


class SimulatorSelectionTests(unittest.TestCase):
    def test_isolated_family_does_not_depend_on_the_other_family(self):
        inventory={'devices':{'iOS':[{'name':'iPad Test','udid':'tablet','isAvailable':True}]}}
        self.assertEqual([d['udid'] for d in runner.select_devices(inventory,'ipad')],['tablet'])
        with self.assertRaisesRegex(ValueError,'iPhone'):runner.select_devices(inventory,'iphone')
        for invalid in ('tablet','all','',True):
            with self.assertRaises(ValueError):runner.select_devices(inventory,invalid)

    def test_one_family_command_records_only_actual_profile_and_bounded_discovery(self):
        from contextlib import redirect_stdout
        from io import StringIO
        from types import SimpleNamespace
        inventory={'devices':{'iOS':[{'name':'iPad Test','udid':'tablet','isAvailable':True}]}}
        with tempfile.TemporaryDirectory() as folder:
            commands=[];output=StringIO()
            def execute(argv,**kwargs):
                commands.append(argv)
                if argv[0]=='xcodebuild':Path(argv[argv.index('-resultBundlePath')+1]).mkdir()
                return SimpleNamespace(returncode=0)
            with patch.object(runner,'IOS',Path(folder)),patch.object(runner.platform,'system',return_value='Darwin'), \
                 patch.object(runner.platform,'machine',return_value='x86_64'), \
                 patch.object(runner.subprocess,'check_output',return_value=json.dumps(inventory)), \
                 patch.object(runner.subprocess,'run',side_effect=execute),redirect_stdout(output):
                runner.main('ipad')
            outcomes=json.loads((Path(folder)/'build-evidence/simulator-outcomes.json').read_text())
            self.assertEqual([item['family'] for item in outcomes],['ipad'])
            self.assertEqual(outcomes[0]['exit_code'],0)
            tests=[command for command in commands if command[0]=='xcodebuild']
            self.assertEqual(len(tests),1)
            self.assertEqual(tests[0][tests[0].index('-destination-timeout')+1],'180')
            self.assertIn('iPad simulator test commands passed',output.getvalue())
            self.assertNotIn('iPhone and iPad simulator test commands passed',output.getvalue())

    def test_timeouts_record_exact_phase_and_cannot_pass(self):
        import subprocess
        from types import SimpleNamespace
        device=dict(name='iPhone Test',udid='phone',state='Shutdown')
        for step,expected in ((0,'boot timeout'),(1,'boot readiness timeout'),(2,'compile and test timeout')):
            with tempfile.TemporaryDirectory() as folder:
                evidence=Path(folder);calls=[]
                def execute(argv,**kwargs):
                    calls.append((argv,kwargs))
                    if len(calls)-1==step:raise subprocess.TimeoutExpired(argv,kwargs['timeout'])
                    return SimpleNamespace(returncode=0)
                with patch.object(runner.subprocess,'run',side_effect=execute):
                    result=runner.run_device(device,'x86_64',evidence)
                self.assertEqual(result['exit_code'],124)
                self.assertEqual(result['phase'],expected)
                self.assertEqual(json.loads((evidence/'iphone-phase.json').read_text())['phase'],expected)
                self.assertTrue(all(c[1]['timeout']>0 for c in calls))

    def test_success_without_xcresult_is_failure(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as folder,patch.object(runner.subprocess,'run',return_value=SimpleNamespace(returncode=0)):
            result=runner.run_device(dict(name='iPad Test',udid='tablet'),'arm64',Path(folder))
            self.assertEqual(result['exit_code'],1)
            self.assertEqual(result['phase'],'missing xcresult')

    def test_phone_failure_still_runs_tablet_and_remains_failure(self):
        inventory={'devices':{'iOS':[
            {'name':'iPhone Test','udid':'phone','isAvailable':True},
            {'name':'iPad Test','udid':'tablet','isAvailable':True}]}}
        with tempfile.TemporaryDirectory() as folder:
            commands=[]
            def execute(argv,**kwargs):
                from types import SimpleNamespace
                commands.append(argv)
                if argv[0]=='xcodebuild':
                    Path(argv[argv.index('-resultBundlePath')+1]).mkdir()
                    return SimpleNamespace(returncode=65 if 'platform=iOS Simulator,id=phone' in argv else 0)
                return SimpleNamespace(returncode=0)
            with patch.object(runner,'IOS',Path(folder)),patch.object(runner.platform,'system',return_value='Darwin'), \
                 patch.object(runner.platform,'machine',return_value='arm64'), \
                 patch.object(runner.subprocess,'check_output',return_value=json.dumps(inventory)), \
                 patch.object(runner.subprocess,'run',side_effect=execute):
                with self.assertRaises(SystemExit) as failure:runner.main()
            self.assertEqual(failure.exception.code,65)
            outcomes=json.loads((Path(folder)/'build-evidence/simulator-outcomes.json').read_text())
            self.assertEqual([item['family'] for item in outcomes],['iphone','ipad'])
            self.assertEqual([item['exit_code'] for item in outcomes],[65,0])
            self.assertTrue(all(item['xcresult_exists'] for item in outcomes))
            phone_stop=commands.index(['xcrun','simctl','shutdown','phone'])
            tablet_boot=commands.index(['xcrun','simctl','boot','tablet'])
            self.assertLess(phone_stop,tablet_boot)
            self.assertEqual([item['shutdown_exit_code'] for item in outcomes],[0,0])

    def test_packaging_uses_one_supported_host_architecture(self):
        for arch in ('arm64','x86_64'):
            self.assertEqual(runner.simulator_architecture(arch),arch)
        for invalid in ('arm64 x86_64','arm64e','','unknown'):
            with self.assertRaises(ValueError):runner.simulator_architecture(invalid)

    def test_runtime_reuse_requires_source_toolchain_and_current_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            framework=Path(folder)/'Python.xcframework';framework.mkdir()
            binary=framework/'synthetic-binary';binary.write_bytes(b'synthetic fixture')
            identity={'source_commit':'source-a','xcode':'toolchain-a'}
            receipt=framework.parent/'runtime-cache.json'
            receipt.write_text(json.dumps({'identity':identity,'tree_sha256':builder.tree_hash(framework)}))
            self.assertTrue(builder.reusable_framework(framework,identity))
            self.assertFalse(builder.reusable_framework(framework,dict(identity,xcode='toolchain-b')))
            self.assertFalse(builder.reusable_framework(framework,dict(identity,source_commit='source-b')))
            binary.write_bytes(b'changed')
            self.assertFalse(builder.reusable_framework(framework,identity))
            receipt.unlink()
            self.assertFalse(builder.reusable_framework(framework,identity))

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
