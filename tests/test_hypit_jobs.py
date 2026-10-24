"""Real SQLite/worker lifecycle with a controlled runtime boundary, no paid calls."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from mission_control.common import Invalid, canonical, digest
from mission_control.db import connection
from mission_control.store import Store
from mission_control.worker import run_once, jobs, claim
from mission_control.hypit_jobs import HypitRenders, artifact_file, brief_scene, current_inputs, private_path, saved
from tests.test_creative_rendering import prepared_render

APP = 'render-test'
KEY = 'bld_20261024_TEST1234'
CONTENT = b'Controlled adapter output; media decoding is tested independently'


class HypitJobTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / 'state.sqlite')
        self.brief, self.request = prepared_render(self.store)
        self.renders = HypitRenders(self.store)
        self.launcher = patch('mission_control.hypit_jobs.identity', return_value=dict(launcher='fixture', launcher_sha256='0' * 64))
        self.launcher.start()

    def tearDown(self):
        self.launcher.stop()
        self.tmp.cleanup()

    def queue(self, key='hypit-lifecycle', **changes):
        return self.renders.queue(APP, dict(data=dict(self.request, **changes), request_key=key))

    def adapter(self, folder, scene, alive, submitted):
        alive()
        submitted(KEY)
        reopened = Store(self.store.path, seed=False)
        attempt = HypitRenders(reopened).list(APP)['attempts'][0]
        self.assertEqual((attempt['status'], attempt['data']['build_id']), ('SUBMITTED', KEY))
        self.assertTrue((reopened.path.parent / attempt['data']['project']).is_dir())
        (folder / 'video.mp4').write_bytes(CONTENT)
        return dict(build_id=KEY, artifact=dict(sha256=hashlib.sha256(CONTENT).hexdigest(), bytes=len(CONTENT)),
                    cleanup=dict(worker='STOPPED'), publication='NOT_RUN', visual_review='REQUIRED')

    def test_worker_persists_exact_build_output_and_replays_without_new_render(self):
        queued = self.queue()
        self.assertEqual(queued['id'], self.queue()['id'])
        with patch('mission_control.hypit_jobs.render', side_effect=self.adapter) as runtime:
            self.assertTrue(run_once(self.store))
            job = jobs(self.store, APP)[0]
            self.assertEqual(job['status'], 'SUCCEEDED', job['result'])
            row = self.renders.list(APP)['items'][0]
            path, data = artifact_file(self.store, APP, row['id'])
            self.assertEqual(path.read_bytes(), CONTENT)
            self.assertEqual((row['status'], data['renderer'], data['visual_review']), ('CURRENT', 'HYPIT_LOCAL', 'REQUIRED'))
            self.assertEqual(self.renders.list(APP)['attempts'][0]['status'], 'COMPLETE')
            with connection(self.store.path) as db:
                db.execute("UPDATE jobs SET status='QUEUED' WHERE id=?", (queued['id'],))
            self.assertTrue(run_once(Store(self.store.path, seed=False)))
            self.assertEqual(runtime.call_count, 1)
            self.assertEqual(jobs(self.store, APP)[0]['result'], job['result'])

    def test_queue_rejects_conflicts_missing_tools_and_invalid_brief_fields(self):
        self.queue()
        with self.assertRaisesRegex(Invalid, 'different job'):
            self.queue(shape='LANDSCAPE')
        for value in (None, {}, dict(data=self.request, request_key='x', command='arbitrary')):
            with self.assertRaises(Invalid):
                self.renders.queue(APP, value)
        with self.assertRaises(Invalid):
            self.queue('stale', brief_hash='changed')
        with patch('mission_control.hypit_jobs.identity', side_effect=Invalid('Missing runtime')), self.assertRaises(Invalid):
            self.queue('missing')
        self.assertEqual(len(jobs(self.store, APP)), 1)

    def test_lost_result_and_recovery_retain_attempt_and_never_submit_again(self):
        queued = self.queue()
        def interrupted(folder, scene, alive, submitted):
            submitted(KEY)
            raise OSError('PRIVATE_HOST_VALUE')
        with patch('mission_control.hypit_jobs.render', side_effect=interrupted) as runtime:
            run_once(self.store)
            job = jobs(self.store, APP)[0]
            self.assertEqual(job['status'], 'BLOCKED')
            self.assertNotIn('PRIVATE_HOST_VALUE', str(job['result']))
            attempt = self.renders.list(APP)['attempts'][0]
            self.assertEqual((attempt['status'], attempt['data']['build_id']), ('NEEDS_INSPECTION', KEY))
            with connection(self.store.path) as db:
                db.execute("UPDATE jobs SET status='QUEUED' WHERE id=?", (queued['id'],))
            run_once(Store(self.store.path, seed=False))
            self.assertEqual(runtime.call_count, 1)
            self.assertIn('without resubmitting', jobs(self.store, APP)[0]['result']['error'])
            self.assertEqual(self.renders.list(APP)['items'], [])

    def test_no_second_submission_after_crash_before_runtime_call(self):
        self.queue()
        job = claim(self.store)
        folder = self.renders.begin(job)
        self.assertTrue(folder.is_dir())
        self.renders.submitted(job, KEY)
        with self.assertRaisesRegex(Invalid, 'already recorded'):
            self.renders.submitted(job, KEY)
        with patch('mission_control.hypit_jobs.render') as runtime, self.assertRaisesRegex(Invalid, 'already exists'):
            self.renders.execute(job)
        runtime.assert_not_called()
        self.assertEqual(self.renders.list(APP)['attempts'][0]['data']['build_id'], KEY)

    def test_cancellation_and_stale_proof_prevent_artifact_commit(self):
        for change in ('cancel', 'stale'):
            queued = self.queue(change)
            def changed(folder, scene, alive, submitted):
                result = self.adapter(folder, scene, alive, submitted)
                with connection(self.store.path) as db:
                    if change == 'cancel':
                        db.execute("UPDATE jobs SET status='CANCELLED' WHERE id=?", (queued['id'],))
                    else:
                        row = db.execute('SELECT data FROM apps WHERE id=?', (APP,)).fetchone()
                        data = json.loads(row['data'])
                        data['name'] = 'Changed app name'
                        db.execute('UPDATE apps SET data=? WHERE id=?', (canonical(data), APP))
                return result
            with patch('mission_control.hypit_jobs.render', side_effect=changed):
                run_once(self.store)
            self.assertEqual(self.renders.list(APP)['items'], [])
            selected = next(row for row in jobs(self.store, APP) if row['id'] == queued['id'])
            self.assertEqual(selected['status'], 'CANCELLED' if change == 'cancel' else 'BLOCKED')

    def test_commit_rejects_wrong_build_and_changed_output(self):
        for change in ('build', 'bytes', 'empty'):
            self.queue(change)
            def changed(folder, scene, alive, submitted):
                result = self.adapter(folder, scene, alive, submitted)
                if change == 'build':
                    result['build_id'] = KEY + 'DIFFERENT'
                elif change == 'bytes':
                    (folder / 'video.mp4').write_bytes(b'Modified after decoder acceptance')
                else:
                    (folder / 'video.mp4').write_bytes(b'')
                return result
            with patch('mission_control.hypit_jobs.render', side_effect=changed):
                run_once(self.store)
            self.assertEqual(self.renders.list(APP)['items'], [])
            self.assertFalse(list((self.store.path.parent / 'hypit').rglob('artifacts/*.mp4')))

    def test_database_failure_removes_only_new_shared_artifact_and_retains_private_project(self):
        self.queue()
        with connection(self.store.path) as db:
            db.execute("CREATE TRIGGER reject_hypit BEFORE INSERT ON hypit_renders BEGIN SELECT RAISE(ABORT,'fixture'); END")
        with patch('mission_control.hypit_jobs.render', side_effect=self.adapter):
            run_once(self.store)
        self.assertEqual(self.renders.list(APP)['items'], [])
        attempt = self.renders.list(APP)['attempts'][0]
        self.assertTrue((self.store.path.parent / attempt['data']['project'] / 'video.mp4').is_file())
        self.assertFalse(list((self.store.path.parent / 'hypit').rglob('artifacts/*.mp4')))

    def test_scope_checksum_missing_bytes_and_tampered_saved_history(self):
        self.queue()
        with patch('mission_control.hypit_jobs.render', side_effect=self.adapter):
            run_once(self.store)
        row = self.renders.list(APP)['items'][0]
        with self.assertRaises(Invalid):
            artifact_file(self.store, 'sample-two', row['id'])
        with self.assertRaises(Invalid):
            artifact_file(self.store, APP, '../escape')
        self.assertEqual(self.renders.list('sample-two')['items'], [])
        path, _ = artifact_file(self.store, APP, row['id'])
        path.write_bytes(b'changed')
        with self.assertRaisesRegex(Invalid, 'changed'):
            artifact_file(self.store, APP, row['id'])
        self.assertEqual(self.renders.list(APP)['items'][0]['status'], 'STALE_OR_UNAVAILABLE')
        path.unlink()
        with self.assertRaisesRegex(Invalid, 'missing'):
            artifact_file(self.store, APP, row['id'])
        with self.assertRaisesRegex(Invalid, 'history changed'):
            saved(dict(data='{}', hash='wrong'))

    def test_scene_timing_exact_copy_and_forged_worker_data_rejected(self):
        queued = self.queue()
        scene = brief_scene(queued['data']['request'])
        self.assertEqual(sum(item['seconds'] for item in scene['scenes']), queued['data']['request']['duration_seconds'])
        uneven = brief_scene(dict(queued['data']['request'], duration_seconds=15))
        self.assertEqual([item['seconds'] for item in uneven['scenes']], [4, 4, 4, 3])
        self.assertEqual([item['text'] for item in scene['scenes']], queued['data']['request']['captions'])
        with connection(self.store.path) as db:
            current_inputs(db, self.store, APP, queued['data'])
            for value in ({}, dict(queued['data'], scene=dict(scene, title='forged'))):
                with self.assertRaises(Invalid):
                    current_inputs(db, self.store, APP, value)
        with self.assertRaises(Invalid):
            private_path(self.store, APP, '..', '..', '..', '..')
        # A schema-valid scene can still be forged relative to the approved brief.
        job = claim(self.store)
        job['data']['scene']['scenes'][0]['text'] = 'An unapproved statement'
        with patch('mission_control.hypit_jobs.render') as runtime, self.assertRaises(Invalid):
            self.renders.execute(job)
        runtime.assert_not_called()
        self.assertEqual(digest(queued['data']['request']), digest(job['data']['request']))
