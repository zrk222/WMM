"""Actual synthetic native sources, shared timeline math and atomic revision history."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
import json
import tempfile
import unittest

from mission_control.common import Invalid
from mission_control.db import connection
from mission_control.creative_rendering import Renders, artifact_file
from mission_control.store import Store
from mission_control.video_edit_contract import definition, edit, timing, change_clip, split_clip, clip, source, transform, effects, output_frames, crop_bounds
from mission_control.video_edit_projects import Projects, admitted_caller, CALLER, row_view, bind_sources, saved_data, next_state, revision, head
from mission_control.worker import run_once
from tests.test_creative_rendering import prepared_render

APP = 'sample-one'


def project_data(render_id, artifact_hash, locale='en-US'):
    """Synthetic source references identify actual isolated QA-rendered bytes."""
    clip = dict(id='clip-one', source=dict(kind='NATIVE', id=render_id, sha256=artifact_hash), role='HOOK',
                in_frame=0, out_frame=240, speed_percent=100,
                transform=dict(crop=dict(x=0, y=0, width=10000, height=10000), rotation=0,
                               flip_x=False, flip_y=False, fit='CONTAIN', background='#102124'),
                effects=dict(brightness=0, contrast=100, saturation=100))
    return dict(title='Synthetic edit project', purpose='Show the synthetic app screen.', locale=locale,
                output='PORTRAIT', clips=[clip])


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.data = project_data('a' * 36, 'b' * 64)

    def test_project_edits_exact_split_trim_duplicate_move_insert_delete_and_replace(self):
        data = edit(self.data, dict(operation='split', clip_id='clip-one', at_frame=120, new_id='clip-two'))
        self.assertEqual([(x['in_frame'], x['out_frame']) for x in data['clips']], [(0, 120), (120, 240)])
        self.assertEqual(timing(data)['total_frames'], 240)
        data = edit(data, dict(operation='trim', clip_id='clip-two', in_frame=144, out_frame=216))
        data = edit(data, dict(operation='duplicate', clip_id='clip-two', new_id='clip-three'))
        data = edit(data, dict(operation='move', clip_id='clip-three', index=0))
        self.assertEqual([c['id'] for c in data['clips']], ['clip-three', 'clip-one', 'clip-two'])
        replacement = dict(deepcopy(data['clips'][0]), speed_percent=200, role='CTA')
        replacement['transform']['rotation'] = 90
        data = edit(data, dict(operation='replace', clip_id='clip-three', clip=replacement))
        self.assertEqual(timing(data)['clips'][0], dict(id='clip-three', start_frame=0, end_frame=36))
        data = edit(data, dict(operation='delete', clip_id='clip-two'))
        inserted = dict(deepcopy(self.data['clips'][0]), id='clip-four')
        data = edit(data, dict(operation='insert', index=1, clip=inserted))
        self.assertEqual([c['id'] for c in data['clips']], ['clip-three', 'clip-four', 'clip-one'])
        self.assertEqual(self.data['clips'][0]['out_frame'], 240)

    def test_project_state_rejects_hidden_code_bad_timing_crop_profiles_and_duplicate_ids(self):
        mutations = []
        value = deepcopy(self.data);value['shell'] = 'execute';mutations.append(value)
        value = deepcopy(self.data);value['clips'][0]['source']['path'] = '../private';mutations.append(value)
        for key, bad in (('in_frame', True), ('out_frame', 0), ('speed_percent', 133), ('speed_percent', 0), ('out_frame', 239)):
            value = deepcopy(self.data);value['clips'][0][key] = bad
            if key == 'out_frame' and bad == 239:value['clips'][0]['speed_percent'] = 200
            mutations.append(value)
        value = deepcopy(self.data);value['clips'][0]['transform']['crop']['x'] = 1;mutations.append(value)
        value = deepcopy(self.data);value['clips'][0]['transform']['background'] = 'black;movie=url';mutations.append(value)
        value = deepcopy(self.data);value['clips'][0]['transform']['rotation'] = True;mutations.append(value)
        value = deepcopy(self.data);value['output'] = 'http://unsafe';mutations.append(value)
        value = deepcopy(self.data);value['clips'] *= 2;mutations.append(value)
        for value in mutations:
            with self.subTest(value=value), self.assertRaises(Invalid):definition(value)
        for command in (dict(operation='delete', clip_id='clip-one'),
                        dict(operation='split', clip_id='clip-one', at_frame=0, new_id='clip-two'),
                        dict(operation='move', clip_id='foreign', index=0),
                        dict(operation='duplicate', clip_id='clip-one', new_id='clip-one'),
                        dict(operation='delete', clip_id='clip-one', force=True)):
            with self.subTest(command=command), self.assertRaises(Invalid):edit(self.data, command)

    def test_change_clip_split_clip_and_scalar_contracts_reject_hidden_or_lossy_edits(self):
        current=clip(self.data['clips'][0])
        self.assertEqual(source(current['source']),current['source'])
        self.assertEqual(transform(current['transform']),current['transform'])
        self.assertIsNone(crop_bounds(current['transform']['crop']))
        with self.assertRaises(Invalid):crop_bounds(dict(x=9999,y=0,width=2,height=10000))
        self.assertEqual(effects(current['effects']),current['effects'])
        self.assertEqual(output_frames(current),240)
        rows=[deepcopy(current)]
        split_clip(rows,0,dict(at_frame=120,new_id='clip-two'))
        self.assertEqual(sum(output_frames(row) for row in rows),240)
        change_clip(rows,dict(operation='move',clip_id='clip-two',index=0))
        self.assertEqual(rows[0]['id'],'clip-two')
        with self.assertRaises(Invalid):split_clip(rows,0,dict(at_frame=240,new_id='clip-three'))
        with self.assertRaises(Invalid):change_clip(rows,dict(operation='trim',clip_id='clip-two',in_frame=0,out_frame=120,shell='no'))


class ProjectFixture:
    """Produce one genuine native source; no fake artifact metadata or rights shortcut."""
    def setup_project(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / 'source/state.sqlite', seed=False)
        for identity in (APP, 'sample-two'):
            self.store.save_app(identity, dict(name='Synthetic editor app', release='build-1', locale='en-US', currency='USD'))
        app = self.store.app(APP)
        self.store.save_app(APP, dict(app['data'], job='Synthetic job', audience='Synthetic audience',
                                     activation='Saved fictional step'), app['version'])
        self.brief, request = prepared_render(self.store, APP)
        Renders(self.store).queue(APP, dict(data=request, request_key='project-source'))
        assert run_once(self.store)
        self.native = Renders(self.store).list(APP)['items'][0]
        self.data = project_data(self.native['id'], self.native['data']['artifact']['sha256'], self.store.app(APP)['data']['locale'])
        self.projects = Projects(self.store)

    def create_body(self, key='project-create'):
        return dict(id='test-project', revision=0, manifest_version=self.store.app(APP)['version'],
                    data=deepcopy(self.data), request_key=key)

    def change(self, revision, command, key):
        return self.projects.edit(APP, 'test-project', dict(revision=revision,
            manifest_version=self.store.app(APP)['version'], command=command, request_key=key))

    def history(self, operation, revision, key, **extra):
        return self.projects.history(APP, 'test-project', dict(operation=operation, revision=revision,
            manifest_version=self.store.app(APP)['version'], request_key=key, **extra))

    def dump(self):
        with connection(self.store.path) as db:
            return list(db.iterdump())


class ProjectTests(ProjectFixture, unittest.TestCase):
    def setUp(self):self.setup_project()
    def tearDown(self):
        self.assertIsNone(CALLER.get())
        self.tmp.cleanup()

    def test_project_state_binds_actual_source_bytes_and_reports_draft_not_render(self):
        created = self.projects.save(APP, self.create_body())
        self.assertEqual(created['revision'], 1)
        self.assertEqual(created['data']['sources'][0]['sha256'], self.native['data']['artifact']['sha256'])
        self.assertEqual(created['actor'], dict(kind='LOCAL_SESSION'))
        self.assertEqual(created['render_execution'], 'NOT_RUN_EDITS_NOT_RENDERED')
        self.assertEqual(self.projects.read(APP, 'test-project')['source_status'], 'CURRENT')
        self.assertEqual(self.projects.list(APP)['items'][0]['revision'], 1)
        with self.assertRaises(Invalid):self.projects.read('sample-two', 'test-project')

    def test_project_history_undo_redo_restore_diff_restart_and_old_replay_preserve_head(self):
        body = self.create_body();one = self.projects.save(APP, body)
        two = self.change(1, dict(operation='trim', clip_id='clip-one', in_frame=24, out_frame=216), 'trim-one')
        self.assertEqual(self.history('UNDO', 2, 'undo-one')['data'], one['data'])
        self.assertEqual(self.history('REDO', 3, 'redo-one')['data'], two['data'])
        five = self.history('RESTORE', 4, 'restore-one', target_revision=1)
        self.assertEqual(five['data'], one['data'])
        difference = self.projects.diff(APP, 'test-project', dict(from_revision=1, to_revision=2))
        self.assertEqual(difference['changed_fields'], ['clips'])
        self.assertEqual(difference['after']['clips'][0]['in_frame'], 24)
        reopened = Projects(Store(self.store.path))
        self.assertEqual(reopened.read(APP, 'test-project')['revision'], 5)
        self.assertEqual(self.projects.save(APP, body), one)
        self.assertEqual(reopened.read(APP, 'test-project')['revision'], 5)
        self.assertEqual(len(reopened.read(APP, 'test-project')['history']), 5)

    def test_project_conflict_concurrent_writes_only_one_commits_and_failed_key_can_retry(self):
        self.projects.save(APP, self.create_body())
        def attempt(index):
            try:
                self.change(1, dict(operation='trim', clip_id='clip-one', in_frame=24, out_frame=216), 'race-' + str(index))
                return True
            except Invalid:return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            result = list(pool.map(attempt, (1, 2)))
        self.assertEqual(sum(result), 1)
        self.assertEqual(len(self.projects.read(APP, 'test-project')['history']), 2)
        before = self.dump()
        with self.assertRaises(Invalid):self.change(1, dict(operation='delete', clip_id='clip-one'), 'retry-key')
        self.assertEqual(self.dump(), before)
        self.change(2, dict(operation='trim', clip_id='clip-one', in_frame=48, out_frame=192), 'retry-key')

    def test_project_conflict_changed_bytes_stale_app_foreign_source_and_idempotent_collision(self):
        body = self.create_body();self.projects.save(APP, body)
        wrong = dict(body, data=dict(self.data, title='Different request'))
        with self.assertRaises(Invalid):self.projects.save(APP, wrong)
        wrong = deepcopy(body);wrong.update(id='foreign-project', request_key='foreign-create')
        with self.assertRaises(Invalid):self.projects.save('sample-two', wrong)
        wrong = dict(body, id='other-project', request_key='bad-app', manifest_version=1)
        with self.assertRaises(Invalid):self.projects.save(APP, wrong)
        output, data = artifact_file(self.store, APP, self.native['id'])
        output.write_bytes(b'changed source')
        before = self.dump()
        with self.assertRaises(Invalid):self.change(1, dict(operation='trim', clip_id='clip-one', in_frame=24, out_frame=216), 'bad-source')
        self.assertEqual(self.dump(), before)
        self.assertEqual(self.projects.read(APP, 'test-project')['source_status'], 'STALE_OR_UNAVAILABLE')

    def test_project_history_new_edit_after_undo_discards_redo_but_keeps_revision_and_revalidates_source(self):
        self.projects.save(APP, self.create_body())
        self.change(1, dict(operation='trim', clip_id='clip-one', in_frame=24, out_frame=216), 'first-edit')
        self.history('UNDO', 2, 'first-undo')
        self.change(3, dict(operation='duplicate', clip_id='clip-one', new_id='clip-two'), 'branch-edit')
        before = self.dump()
        with self.assertRaises(Invalid):self.history('REDO', 4, 'bad-redo')
        self.assertEqual(self.dump(), before)
        self.assertEqual(len(self.projects.read(APP, 'test-project')['history']), 4)
        output, data = artifact_file(self.store, APP, self.native['id']);output.write_bytes(b'changed')
        with self.assertRaises(Invalid):self.history('RESTORE', 4, 'stale-restore', target_revision=1)
        with self.assertRaises(Invalid):self.history('UNDO', 4, 'stale-undo')

    def test_project_state_gateway_identity_is_public_and_not_request_supplied(self):
        agent = Projects(self.store, 'SCOPED_AGENT')
        with self.assertRaises(PermissionError):agent.save(APP, self.create_body())
        admission = dict(agent_id='test-agent', grant_id='test-grant', attempt=1, token='Never serialize this')
        with admitted_caller(admission):
            created = agent.save(APP, self.create_body())
        self.assertEqual(created['actor'], dict(kind='SCOPED_AGENT', agent_id='test-agent', grant_id='test-grant', attempt=1))
        self.assertNotIn('Never serialize', json.dumps(created))
        with admitted_caller(dict(admission, attempt=2)):
            self.assertEqual(agent.save(APP, self.create_body()), created)

    def test_project_conflict_current_rights_or_locale_invalidates_restore(self):
        self.projects.save(APP,self.create_body())
        self.change(1,dict(operation='trim',clip_id='clip-one',in_frame=24,out_frame=216),'rights-trim')
        with connection(self.store.path) as db:
            identity=self.brief['data']['definition']['asset_ids'][0]
            row=db.execute("SELECT * FROM records WHERE app_id=? AND kind='asset' AND id=?",(APP,identity)).fetchone()
            data=json.loads(row['data']);data['rights_cleared']=False
            db.execute('UPDATE records SET data=?,version=version+1 WHERE app_id=? AND id=?',(json.dumps(data),APP,row['id']))
        before=self.dump()
        with self.assertRaises(Invalid):self.history('RESTORE',2,'rights-restore',target_revision=1)
        self.assertEqual(self.dump(),before)
        self.assertEqual(self.projects.read(APP,'test-project')['source_status'],'STALE_OR_UNAVAILABLE')

    def test_row_view_bind_sources_saved_data_and_next_state_validate_current_proof(self):
        self.projects.save(APP,self.create_body())
        with connection(self.store.path) as db:
            db.execute('BEGIN')
            row=revision(db,APP,'test-project',1)
            view=row_view(row)
            self.assertEqual(view['data']['definition'],self.data)
            self.assertNotIn('request_key',view)
            bindings=bind_sources(db,self.store,APP,self.data)
            self.assertEqual(bindings[0]['id'],self.native['id'])
            data=saved_data(db,self.store,APP,self.store.app(APP)['version'],self.data)
            self.assertEqual(data,view['data'])
            current=head(db,APP,'test-project')
            with self.assertRaises(Invalid):next_state(db,APP,'test-project',current,{},'UNDO')
            changed=deepcopy(self.data);changed['locale']='foreign-locale'
            with self.assertRaises(Invalid):saved_data(db,self.store,APP,self.store.app(APP)['version'],changed)
            changed=deepcopy(self.data);changed['clips'][0]['out_frame']=1440
            with self.assertRaises(Invalid):bind_sources(db,self.store,APP,changed)
