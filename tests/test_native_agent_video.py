"""Native transport, actual decoded video and standing scope with synthetic inputs."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from mission_control import native_runtime_identity as runtime
from mission_control.automation_execution import ACTIVE, execute_admitted
from mission_control.common import Invalid
from mission_control.creative_rendering import Renders, artifact_file
from mission_control.media_native import validate_video
from mission_control.operator_client import OperatorClient, ClientError
from mission_control.service import Service
from mission_control.worker import jobs, run_once
from mission_control.workflow_telemetry import monitor
from tests import test_agent_grants as grants
from tests import test_agent_mcp as sdk
from tests import test_agent_review_clients as clients
from tests import test_complete_automation as authority
from tests.test_creative_rendering import prepared_render

APP = 'sample-one'


class RuntimeTests(unittest.TestCase):
    def test_native_readiness_hashes_actual_bytes_and_does_not_expose_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('ffmpeg', 'ffprobe', 'font'):
                (root / name).write_bytes(name.encode())
            capability = dict(status='READY', tools={name: str(root / name) for name in ('ffmpeg', 'ffprobe')},
                              font=str(root / 'font'), script_support='Latin')
            with patch.object(runtime, 'capability', return_value=capability):
                before = runtime.identity()
                self.assertEqual(before['sha256']['font'], hashlib.sha256(b'font').hexdigest())
                self.assertNotIn(directory, json.dumps(before))
                (root / 'ffmpeg').write_bytes(b'changed')
                self.assertNotEqual(before['sha256'], runtime.identity()['sha256'])
                (root / 'font').unlink()
                self.assertEqual(runtime.identity()['status'], 'UNAVAILABLE')
        with patch.object(runtime, 'capability', return_value=dict(status='UNAVAILABLE', repair='Install fixed tools')):
            self.assertEqual(runtime.identity(), dict(status='UNAVAILABLE', repair='Install fixed tools'))


class NativeClientsTests(unittest.IsolatedAsyncioTestCase):
    body = grants.GrantTests.body
    envelope = grants.GrantTests.envelope
    session = clients.ReviewClientTests.session

    def setUp(self):
        grants.GrantTests.setUp(self)
        app = self.store.app(APP)
        self.store.save_app(APP, dict(app['data'], job='Synthetic job', audience='Synthetic audience',
                                      activation='Saved fictional step'), app['version'])
        self.brief, self.request = prepared_render(self.store, APP)

    def tearDown(self):
        grants.GrantTests.tearDown(self)

    def grant(self, operations):
        body = dict(self.body(operations, 100), manifest_version=self.store.app(APP)['version'])
        issued = self.owner.request('POST', '/api/apps/' + APP + '/agent-grants/issue', body)
        self.token = issued['token']
        return OperatorClient(self.origin, grant_token=self.token)

    def payload(self):
        return dict(data=self.request, request_key='native-client')

    def test_native_parity_rejects_ungranted_foreign_and_unknown_inputs(self):
        agent = self.grant(['native.read'])
        self.assertEqual(agent.call(self.envelope('native.read'))['items'], [])
        self.assertEqual(self.owner.request('GET', '/api/apps/' + APP + '/native-renders')['items'], [])
        for envelope in (self.envelope('native.queue', self.payload()),
                         self.envelope('native.read', app_id='sample-two'),
                         self.envelope('native.read', dict(extra=True))):
            with self.assertRaises((ClientError, Invalid)):
                agent.call(envelope)
        agent = self.grant(['native.queue'])
        with self.assertRaises((ClientError, Invalid)):
            agent.call(self.envelope('native.queue', dict(self.payload(), shell='arbitrary')))
        self.assertEqual(jobs(self.store, APP), [])

    @unittest.skipUnless(sdk.HAS_MCP, 'Official MCP SDK required for client acceptance')
    async def test_native_clients_cli_and_mcp_idempotency_then_actual_decoded_mp4(self):
        self.grant(['native.queue', 'native.read', 'jobs.read'])
        envelope = self.envelope('native.queue', self.payload())
        result = subprocess.run([sys.executable, '-m', 'mission_control.agent_cli', 'call',
                                 '--origin', self.origin, '--use-grant'], input=json.dumps(envelope).encode(),
                                capture_output=True, env=dict(os.environ, WMM_AGENT_GRANT=self.token), timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertNotIn(self.token, result.stdout.decode())
        queued = json.loads(result.stdout)
        async with self.session() as client:
            names = {row.name for row in (await client.list_tools()).tools}
            self.assertTrue({'wmm_native_read', 'wmm_native_queue'} <= names)
            repeated = await client.call_tool('wmm_native_queue', dict(app_id=APP, input=self.payload()))
            self.assertFalse(repeated.isError, repeated.content)
            self.assertEqual(repeated.structuredContent['data']['id'], queued['id'])
            self.assertTrue(run_once(self.store))
            self.assertEqual(jobs(self.store, APP)[0]['status'], 'SUCCEEDED', jobs(self.store, APP)[0]['result'])
            response = await client.call_tool('wmm_native_read', dict(app_id=APP, input={}))
            self.assertFalse(response.isError, response.content)
            row = response.structuredContent['data']['items'][0]
            self.assertEqual(row['job_id'], queued['id'])
            output, data = artifact_file(self.store, APP, row['id'])
            self.assertEqual(validate_video(output, data['request']), data['artifact'])
            self.assertEqual(data['publication'], 'NOT_RUN')
            foreign = await client.call_tool('wmm_native_queue', dict(app_id='sample-two', input=self.payload()))
            self.assertTrue(foreign.isError)


class NativeStandingTests(authority.AuthorityFixture, unittest.TestCase):
    def setUp(self):
        self.setup_authority()
        self.service = Service(self.store)
        app = self.store.app(APP)
        self.store.save_app(APP, dict(app['data'], job='Synthetic job', audience='Synthetic audience',
                                      activation='Saved fictional step'), app['version'])
        self.brief, self.request = prepared_render(self.store, APP)
        self.runtime_patch = patch.object(runtime, 'identity', return_value=dict(status='READY', sha256={'font': 'a' * 64}))
        self.identity = self.runtime_patch.start()

    def tearDown(self):
        self.runtime_patch.stop()
        self.cleanup_authority()

    def proposal(self, workflows=None, **limits):
        value = super().proposal(workflows, **limits)
        value['selection']['manifest_version'] = self.store.app(APP)['version']
        return value

    def queue(self, issued):
        envelope = self.envelope('native.queue', dict(data=self.request, request_key='native-standing'))
        return execute_admitted(self.service, envelope, self.grants.admit(issued['token'], envelope))

    def test_native_readiness_changed_runtime_rejects_preview_activation_and_admission(self):
        self.identity.return_value = dict(status='UNAVAILABLE', repair='Repair fixture runtime')
        blocked = self.automation.preview(APP, authority.OWNER, self.proposal(['native_screen_render']))
        self.assertNotEqual(blocked['summary']['inventory']['scope_status'], 'READY_FOR_SCOPE_REVIEW')
        self.identity.return_value = dict(status='READY', sha256={'font': 'a' * 64})
        preview = self.automation.preview(APP, authority.OWNER, self.proposal(['native_screen_render']))
        self.identity.return_value = dict(status='READY', sha256={'font': 'b' * 64})
        with self.assertRaises((PermissionError, Invalid)):
            self.automation.activate(APP, authority.OWNER, dict(proposal=preview['proposal'], summary_hash=preview['summary_hash']))
        issued = self.activate(['native_screen_render'])
        self.identity.return_value = dict(status='READY', sha256={'font': 'c' * 64})
        with self.assertRaises((PermissionError, Invalid)):
            self.grants.admit(issued['token'], self.envelope('native.read'))

    def test_native_scope_revoked_queued_job_never_creates_an_artifact(self):
        issued = self.activate(['native_screen_render'])
        queued = self.queue(issued)
        self.off(issued)
        with patch('mission_control.creative_rendering.render_native') as render:
            self.assertFalse(run_once(self.store))
            render.assert_not_called()
        self.assertEqual(jobs(self.store, APP)[0]['id'], queued['id'])
        self.assertEqual(jobs(self.store, APP)[0]['status'], 'CANCELLED')
        self.assertEqual(Renders(self.store).list(APP)['items'], [])

    def test_native_scope_runtime_changed_after_queue_blocks_worker(self):
        issued = self.activate(['native_screen_render'])
        self.queue(issued)
        self.identity.return_value = dict(status='READY', sha256={'font': 'b' * 64})
        with patch('mission_control.creative_rendering.render_native') as render:
            self.assertTrue(run_once(self.store))
            render.assert_not_called()
        self.assertNotEqual(jobs(self.store, APP)[0]['status'], 'SUCCEEDED')
        self.assertEqual(Renders(self.store).list(APP)['items'], [])

    def test_native_scope_real_render_commits_under_current_standing_authority(self):
        from mission_control.creative_rendering import render_native
        issued = self.activate(['native_screen_render'])
        queued = self.queue(issued)
        def inspect_active_then_render(*args, **kwargs):
            active = monitor(self.store, APP)['runs'][0]
            self.assertEqual(active['status'], 'RUNNING')
            self.assertEqual(active['latest']['code'], 'NATIVE_ENCODING')
            return render_native(*args, **kwargs)
        with patch('mission_control.creative_rendering.render_native', side_effect=inspect_active_then_render):
            self.assertTrue(run_once(self.store))
        self.assertEqual(jobs(self.store, APP)[0]['status'], 'SUCCEEDED', jobs(self.store, APP)[0]['result'])
        row = Renders(self.store).list(APP)['items'][0]
        self.assertEqual(row['job_id'], queued['id'])
        output, data = artifact_file(self.store, APP, row['id'])
        self.assertEqual(validate_video(output, data['request']), data['artifact'])

        events = monitor(self.store, APP)['runs'][0]['events']
        self.assertEqual([row['code'] for row in events],
                         ['STARTED', 'NATIVE_PROOF', 'NATIVE_SCREENS', 'NATIVE_ENCODING', 'NATIVE_COMMIT', 'SUCCEEDED'])

    def test_native_scope_off_after_real_render_before_commit_rejects_artifact(self):
        from mission_control.creative_rendering import render_native
        issued = self.activate(['native_screen_render'])
        self.queue(issued)
        def render_then_off(*args, **kwargs):
            result = render_native(*args, **kwargs)
            # The independently authenticated owner does not inherit worker scope.
            context = ACTIVE.set(None)
            try:
                self.off(issued)
            finally:
                ACTIVE.reset(context)
            return result
        with patch('mission_control.creative_rendering.render_native', side_effect=render_then_off):
            self.assertTrue(run_once(self.store))
        self.assertEqual(jobs(self.store, APP)[0]['status'], 'CANCELLED')
        self.assertEqual(Renders(self.store).list(APP)['items'], [])
        self.assertEqual(list((self.store.path.parent / 'renders' / APP).rglob('*.mp4')), [])
