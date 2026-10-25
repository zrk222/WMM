"""Fixed owned runtime lifecycle, endpoint admission and uncertain-build boundaries."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from mission_control.common import Invalid
from mission_control.hypit_runtime import identity, stage, local_graph, build_identity, invoke, render, observe, cleanup, source_current, submit, recover_build
from tests.test_hypit_authoring import scene

KEY = 'bld_20261024_TEST1234'


def plan():
    return dict(ok=True, preflight=dict(ok=True), requestIssueCount=0, producerFailureCount=0,
                providerRequestCount=0, unresolvedRequestCount=0, unsupportedRequestCount=0,
                requestCount=3, localRequestCount=3, needs=[dict(endpoint='html.local'), dict(endpoint='media.local')])


def status():
    return dict(build=dict(id=KEY, work=dict(state='done', outcome='complete'), result=dict(state='complete')))


class RuntimeTests(unittest.TestCase):
    def test_stage_only_fixed_files_and_reject_existing_or_unknown_inputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            result = stage(folder, scene())
            self.assertEqual(result['duration_seconds'], 5)
            self.assertEqual({p.name for p in folder.iterdir()}, {'package.json', 'film.svml', 'style.svs', 'build.svrun', 'runtime.json', 'font.ttf'})
            with self.assertRaisesRegex(Invalid, 'empty'):
                stage(folder, scene())
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(Invalid):
                stage(Path(temporary), dict(scene(), command='arbitrary'))
            self.assertEqual(list(Path(temporary).iterdir()), [])

    def test_local_graph_rejects_provider_missing_and_unknown_endpoints(self):
        local_graph(plan())
        for key, value in (('providerRequestCount', 1), ('requestIssueCount', 1), ('requestCount', 0), ('localRequestCount', 2), ('ok', False), ('preflight', {}), ('preflight', None), ('needs', []), ('needs', [dict(endpoint='paid.remote')])):
            with self.subTest(key=key), self.assertRaises(Invalid):
                local_graph(dict(plan(), **{key: value}))
        for value in ({}, dict(build=dict(id='--command')), dict(build=[])):
            with self.assertRaises(Invalid):
                build_identity(value)

    def test_invocation_hash_boundary_and_closed_errors(self):
        runtime = dict(launcher='hypit', launcher_sha256='fixture')
        with patch('mission_control.hypit_runtime.identity', return_value=runtime), patch('mission_control.hypit_runtime.capture') as call:
            call.return_value = dict(code=1, stdout='', stderr='PRIVATE_ACCOUNT_VALUE')
            with self.assertRaises(Invalid) as caught:
                invoke(runtime, Path('.'), ['check', 'build.svrun'])
            self.assertNotIn('PRIVATE_ACCOUNT_VALUE', str(caught.exception))
            self.assertEqual(call.call_args.kwargs['timeout'], 180)
            self.assertEqual(call.call_args.args[0], ['hypit', 'check', 'build.svrun', '--json'])
            call.return_value = dict(code=0, stdout='[]', stderr='')
            with self.assertRaises(Invalid):
                invoke(runtime, Path('.'), ['check', 'build.svrun'])
            call.return_value = dict(code=0, stdout='not JSON', stderr='')
            with self.assertRaises(Invalid):
                invoke(runtime, Path('.'), ['check', 'build.svrun'])
            call.side_effect = OSError('PRIVATE_HOST_PATH')
            with self.assertRaises(Invalid) as caught:
                invoke(runtime, Path('.'), ['check', 'build.svrun'])
            self.assertNotIn('PRIVATE_HOST_PATH', str(caught.exception))
        with patch('mission_control.hypit_runtime.identity', return_value=runtime), self.assertRaises(Invalid):
            invoke(dict(runtime, launcher_sha256='changed'), Path('.'), [])
        with patch('mission_control.hypit_runtime.identity', side_effect=[runtime, dict(runtime, launcher_sha256='changed')]), patch('mission_control.hypit_runtime.capture', return_value=dict(code=0, stdout='{}', stderr='')), self.assertRaisesRegex(Invalid, 'during rendering'):
            invoke(runtime, Path('.'), ['check', 'build.svrun'])
        with patch('mission_control.hypit_runtime.shutil.which', return_value=None), self.assertRaises(Invalid):
            identity()
        with tempfile.TemporaryDirectory() as temporary:
            launcher = Path(temporary) / 'hypit.exe'
            launcher.write_bytes(b'Installed launcher fixture')
            with patch('mission_control.hypit_runtime.shutil.which', return_value=str(launcher)):
                self.assertEqual(identity()['launcher'], str(launcher.resolve()))

    def fake_commands(self, commands, endpoint_plan=None, cancel_after_submit=False):
        def run(runtime, folder, arguments, alive=lambda: None):
            commands.append(arguments)
            if arguments[0] == 'check':
                return dict(ok=True)
            if arguments[0] == 'plan':
                return endpoint_plan if endpoint_plan is not None else plan()
            if arguments[0] == 'build':
                return dict(build=dict(id=KEY))
            if arguments[0] == 'status':
                if cancel_after_submit:
                    raise Invalid('Synthetic cancellation')
                return status()
            if arguments[0] == 'get':
                (folder / 'video.mp4').write_bytes(b'synthetic decoder fixture')
                return dict(path=str(folder / 'video.mp4'))
            if arguments[0] == 'cancel':
                return dict(build=dict(id=KEY))
            if arguments[:2] == ['runtime', 'down']:
                return dict(worker='stopped')
            raise AssertionError(arguments)
        return run

    def test_single_submit_actual_identity_export_validation_and_shutdown_order(self):
        commands = []
        submitted = []
        with tempfile.TemporaryDirectory() as temporary, patch('mission_control.hypit_runtime.identity', return_value=dict(launcher='hypit', launcher_sha256='fixture')), patch('mission_control.hypit_runtime.invoke', side_effect=self.fake_commands(commands)), patch('mission_control.hypit_runtime.validate_video', return_value=dict(sha256='fixture')):
            result = render(Path(temporary), scene(), submitted=submitted.append)
        self.assertEqual(submitted, [KEY])
        self.assertEqual([args[0] for args in commands], ['check', 'plan', 'build', 'status', 'get', 'runtime'])
        self.assertEqual(result['build_id'], KEY)
        self.assertEqual(result['cleanup']['worker'], 'STOPPED')
        self.assertEqual(result['publication'], 'NOT_RUN')

    def test_unknown_endpoint_prevents_build_and_submitted_failure_cancels_then_stops(self):
        for invalid_plan, cancelled in ((dict(plan(), needs=[dict(endpoint='remote')]), False), (None, True)):
            commands = []
            with tempfile.TemporaryDirectory() as temporary, patch('mission_control.hypit_runtime.identity', return_value=dict(launcher='hypit', launcher_sha256='fixture')), patch('mission_control.hypit_runtime.invoke', side_effect=self.fake_commands(commands, invalid_plan, cancelled)), self.assertRaises(Invalid):
                render(Path(temporary), scene())
            names = [args[0] for args in commands]
            if cancelled:
                self.assertEqual(names.count('build'), 1)
                self.assertEqual(names[-2:], ['cancel', 'runtime'])
            else:
                self.assertNotIn('build', names)
                self.assertEqual(names[-1], 'runtime')

    def test_source_mutation_and_missing_font_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            receipt = stage(folder, scene())
            source_current(folder, receipt)
            (folder / 'font.ttf').write_bytes(b'changed font')
            with self.assertRaisesRegex(Invalid, 'source changed'):
                source_current(folder, receipt)
        with tempfile.TemporaryDirectory() as temporary, patch('mission_control.hypit_runtime.capability', return_value=dict(font=None)):
            with self.assertRaises(Invalid):
                stage(Path(temporary), scene())
            self.assertEqual(list(Path(temporary).iterdir()), [])
        commands = []
        fake = self.fake_commands(commands)
        def bad_check(runtime, folder, arguments, alive=lambda: None):
            if arguments[0] == 'check':
                return dict(ok=False)
            return fake(runtime, folder, arguments, alive)
        with tempfile.TemporaryDirectory() as temporary, patch('mission_control.hypit_runtime.identity', return_value=dict(launcher='hypit', launcher_sha256='fixture')), patch('mission_control.hypit_runtime.invoke', side_effect=bad_check), self.assertRaises(Invalid):
            render(Path(temporary), scene())
        self.assertEqual([args[0] for args in commands], ['runtime'])

    def test_observation_timeout_and_identity_mismatch_never_resubmit(self):
        pending = dict(build=dict(id=KEY, work=dict(state='working'), result=dict(state='pending')))
        with patch('mission_control.hypit_runtime.invoke', return_value=pending) as call, patch('mission_control.hypit_runtime.time.monotonic', side_effect=[0, 1, 151]), patch('mission_control.hypit_runtime.time.sleep'):
            with self.assertRaisesRegex(Invalid, 'same retained build'):
                observe({}, Path('.'), KEY, lambda: None)
            call.assert_called_once()
            self.assertEqual(call.call_args.args[2][0], 'status')
        wrong = status()
        wrong['build']['id'] = 'bld_OTHER_12345678'
        with patch('mission_control.hypit_runtime.invoke', return_value=wrong), self.assertRaisesRegex(Invalid, 'different build'):
            observe({}, Path('.'), KEY, lambda: None)

    def test_failed_build_and_cleanup_are_explicit_and_shutdown_is_attempted(self):
        failed = status()
        failed['build']['work']['outcome'] = 'failed'
        with patch('mission_control.hypit_runtime.invoke', return_value=failed), self.assertRaises(Invalid):
            observe({}, Path('.'), KEY, lambda: None)
        calls = []
        def fail_cancel(runtime, folder, args):
            calls.append(args[0])
            if args[0] == 'cancel':
                raise Invalid('Cancellation not confirmed')
            return dict(worker='stopped')
        with patch('mission_control.hypit_runtime.invoke', side_effect=fail_cancel), self.assertRaisesRegex(Invalid, 'cleanup'):
            cleanup({}, Path('.'), KEY, True)
        self.assertEqual(calls, ['cancel', 'runtime'])
        with patch('mission_control.hypit_runtime.invoke', return_value=dict(worker='running')), self.assertRaises(Invalid):
            cleanup({}, Path('.'), None, False)

    def test_lost_submission_receipt_recovers_exact_private_build_without_resubmitting(self):
        replies = [Invalid('Synthetic lost response'), dict(builds=[dict(id=KEY)]), dict(builds=[])]
        with patch('mission_control.hypit_runtime.invoke', side_effect=replies) as call:
            key, mode = submit({}, Path('.'), lambda: None)
        self.assertEqual(key, KEY)
        self.assertEqual(mode, 'RECOVERED_FROM_PRIVATE_PROJECT')
        self.assertEqual([c.args[2][0] for c in call.call_args_list], ['build', 'builds', 'activity'])
        for history, active in ((dict(builds=[]), dict(builds=[])),
                                (dict(builds=[dict(id=KEY)], next='more'), dict(builds=[])),
                                (dict(builds=[dict(id=KEY)]), dict(builds=[dict(id='bld_OTHER_12345678')])),
                                (dict(builds=None), dict(builds=[]))):
            with self.subTest(history=history), patch('mission_control.hypit_runtime.invoke', side_effect=[history, active]), self.assertRaises(Invalid):
                recover_build({}, Path('.'))
