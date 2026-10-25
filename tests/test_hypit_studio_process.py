"""Internal process lifecycle and actual loopback read boundaries over isolated files."""
import hashlib
import io
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from mission_control.common import Invalid
from mission_control.hypit_authoring import project
from mission_control.hypit_studio_project import source_path,sources_current,local_profile,snapshot_current,cleanup_current,snapshot_sources,compiled_file,runtime_directory,compiled_current,compiled_files
from mission_control.hypit_studio_process import StudioProcess
from mission_control import hypit_studio_process as target
from mission_control.hypit_studio_http import session_bytes,bounded_body,OwnedConnection,connection_for


class Child:
    pid=12345
    code=None
    overflow=False
    failure=None
    listener_owned=True
    def poll(self):return self.code
    def stop(self):self.code=0
    def owns_listener(self,port):return self.listener_owned


class StudioTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='wmm-studio-unit-');self.addCleanup(self.tmp.cleanup)
        self.folder=Path(self.tmp.name)
        value=project(dict(title='Synthetic approved video',shape='PORTRAIT',scenes=[dict(text='A useful step',seconds=2)]))
        for name,text in value['files'].items():(self.folder/name).write_bytes(text.encode())
        (self.folder/'font.ttf').write_bytes(b'synthetic font; never rendered')
        self.sources={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in self.folder.iterdir()}
        self.installation=dict(node='synthetic-node',entrypoint='synthetic-entry',id='frozen-installation')
        self.authorized=True;self.child=Child();self.child.code=None;self.child.listener_owned=True
        self.compiled=dict(root='film.svml',files=['build.svrun','film.svml','style.svs'])
        self.session=StudioProcess(self.folder,self.installation,self.sources,self.compiled,self.alive)
        self.check=patch.object(target,'revalidate',return_value=self.installation);self.check.start();self.addCleanup(self.check.stop)
        self.capture=patch.object(target,'capture_owned_command',side_effect=self.command);self.command_mock=self.capture.start();self.addCleanup(self.capture.stop)

    def alive(self):
        if not self.authorized:raise Invalid('Synthetic owner scope was revoked')

    def command(self,args,**kwargs):
        kwargs['alive']()
        if 'down' in args:return dict(code=0,stdout=json.dumps(dict(worker='stopped')),stderr='')
        value=dict(ok=True,preflight=dict(ok=True),requestCount=1,localRequestCount=1,
                   needs=[dict(endpoint='html.local')])
        for k in ('requestIssueCount','producerFailureCount','providerRequestCount','unresolvedRequestCount','unsupportedRequestCount'):value[k]=0
        return dict(code=0,stdout=json.dumps(value),stderr='')

    def snapshot(self):
        return dict(revision=1,run=dict(path='build.svrun'),source=dict(path='film.svml',
            files=[dict(path=name,text=(self.folder/name).read_text(encoding='utf-8'))
                   for name in ('build.svrun','film.svml','style.svs')]),
            tracks=[dict(items=[dict(inspector=[dict(id='private-native-id',control='record',
                   schema=dict(kind='record'),value=dict(x=1))])])])

    def ready(self):
        self.session.control.mkdir();self.session.admitted=True
        info=target.plain(self.session.control,directory=True)
        self.session.control_identity=(info.st_dev,info.st_ino)
        self.session.runtime_identity=runtime_directory(self.folder,create=True)
        for name in ('stdout.log','stderr.log'):(self.session.control/name).write_bytes(b'')
        self.session.process=self.child;self.session.state='READY'

    def server(self,body=None,status=200,headers=None,slow=None,port=0):
        payload=json.dumps(body if body is not None else self.snapshot()).encode()
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                if slow=='headers':
                    try:
                        self.wfile.write(b'HTTP/1.1 200 OK\r\nX-Slow: ');self.wfile.flush()
                        for _ in range(100):
                            self.wfile.write(b'a');self.wfile.flush();time.sleep(.01)
                        self.wfile.write(b'\r\nContent-Type: application/json\r\n\r\n'+payload)
                    except OSError:pass
                    return
                self.send_response(status);self.send_header('Content-Type','application/json')
                for k,v in (headers or {}).items():self.send_header(k,v)
                self.end_headers()
                try:
                    if slow=='body':
                        for byte in payload:
                            self.wfile.write(bytes([byte]));self.wfile.flush();time.sleep(.01)
                    else:self.wfile.write(payload)
                except OSError:pass
        server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.server_close);self.addCleanup(thread.join,3);self.addCleanup(server.shutdown)
        return 'http://127.0.0.1:'+str(server.server_port)

    def test_exact_snapshot_preserves_all_package_control_schema_data(self):
        self.ready();self.session.origin=self.server()
        value=self.session.read()
        self.assertEqual(value,self.snapshot())
        self.assertEqual(value['tracks'][0]['items'][0]['inspector'][0]['control'],'record')

    def test_source_paths_and_changed_frozen_files_reject(self):
        for name in ('../outside','/absolute','C:/outside','a\\b','a//b','./film.svml'):
            with self.assertRaises(Invalid):source_path(self.folder,name)
        (self.folder/'film.svml').write_text('changed source')
        with self.assertRaisesRegex(Invalid,'changed'):sources_current(self.folder,self.sources)

    def test_nonlocal_profile_rejects_even_with_a_fresh_file_hash(self):
        path=self.folder/'runtime.json';value=json.loads(path.read_text())
        value['dataRoot']='../foreign-runtime';path.write_text(json.dumps(value))
        sources=dict(self.sources,**{'runtime.json':hashlib.sha256(path.read_bytes()).hexdigest()})
        session=StudioProcess(self.folder,self.installation,sources,self.compiled,self.alive)
        with self.assertRaisesRegex(Invalid,'local-only'):session.start()
        self.command_mock.assert_not_called();self.assertFalse(session.control.exists())

    def test_owned_start_fixed_arguments_and_retained_attempt_denial(self):
        with patch.object(target,'spawn_studio_child',return_value=self.child) as launch, patch.object(self.session,'observe_start',return_value=self.snapshot()):
            self.assertEqual(self.session.start(),self.snapshot())
            args,kw=launch.call_args.args[0],launch.call_args.kwargs
            self.assertEqual(args[:3],['synthetic-node','--dns-result-order=ipv4first','synthetic-entry'])
            self.assertIn('studio',args);self.assertEqual(kw['max_log_bytes'],target.MAX_LOG_BYTES)
            self.assertNotIn('WMM_AGENT_GRANT',kw['env'])
            self.assertEqual(self.session.state,'READY')
            with self.assertRaisesRegex(Invalid,'already exists'):self.session.start()
            another=StudioProcess(self.folder,self.installation,self.sources,self.compiled,self.alive)
            with self.assertRaisesRegex(Invalid,'already exists'):another.start()
            self.assertEqual(launch.call_count,1)
        self.assertEqual(self.session.close()['worker'],'stopped')
        count=self.command_mock.call_count;self.session.close()
        self.assertEqual(self.command_mock.call_count,count)

    def test_authority_revocation_rejects_reads_but_allows_owned_cleanup(self):
        self.ready();self.session.origin=self.server();self.authorized=False
        with self.assertRaisesRegex(Invalid,'revoked'):self.session.read()
        self.assertEqual(self.session.close()['worker'],'stopped')
        self.assertEqual(self.child.code,0);self.assertEqual(self.session.state,'CLOSED')

    def test_foreign_or_incomplete_compiled_sources_reject(self):
        for change in ('run','source','missing','duplicate','style','author','root'):
            value=self.snapshot()
            if change=='run':value['run']['path']='foreign.svrun'
            if change=='source':value['source']['files'][1]['text']='foreign bytes'
            if change=='missing':value['source']['files']=value['source']['files'][1:]
            if change=='duplicate':value['source']['files'].append(value['source']['files'][0])
            if change=='style':value['source']['files']=value['source']['files'][:2]
            if change=='author':value['source']['files']=[value['source']['files'][0]]
            if change=='root':value['source']['path']='build.svrun'
            with self.assertRaises(Invalid):snapshot_current(self.folder,self.sources,self.compiled,value)

    def test_redirect_and_response_and_log_bounds_reject(self):
        self.ready();foreign=self.server()
        self.session.origin=self.server(status=302,headers={'Location':foreign+'/foreign'})
        with self.assertRaises(HTTPError) as error:self.session.read()
        self.assertEqual(error.exception.code,302)
        self.session.origin=self.server()
        with patch.object(target,'MAX_RESPONSE_BYTES',10),self.assertRaisesRegex(Invalid,'response exceeded'):
            self.session.read()
        (self.session.control/'stdout.log').write_bytes(b'x'*100)
        with patch.object(target,'MAX_LOG_BYTES',10),self.assertRaisesRegex(Invalid,'diagnostics exceeded'):
            self.session.read()

    def test_dead_owned_child_marks_inspection_without_relaunch(self):
        self.ready();self.session.origin=self.server();self.child.code=1
        with self.assertRaisesRegex(Invalid,'no longer running'):self.session.read()
        self.assertEqual(self.session.state,'NEEDS_INSPECTION')
        self.command_mock.assert_not_called()

    def test_startup_failure_cleans_owned_child_and_retains_diagnostics(self):
        def launch(*args,**kwargs):
            kwargs['stdout_path'].write_bytes(b'Synthetic Studio startup')
            kwargs['stderr_path'].write_bytes(b'Synthetic compilation diagnostic')
            return self.child
        with patch.object(target,'spawn_studio_child',side_effect=launch), patch.object(self.session,'observe_start',side_effect=Invalid('Synthetic compilation failure')):
            with self.assertRaisesRegex(Invalid,'compilation failure'):self.session.start()
        self.assertEqual(self.child.code,0);self.assertEqual(self.session.state,'FAILED_CLEANED')
        self.assertTrue((self.session.control/'stdout.log').exists())
        self.assertTrue((self.session.control/'state.json').exists())

    def test_changed_caption_still_allows_safe_private_shutdown(self):
        self.ready();(self.folder/'film.svml').write_text('edited or failed draft')
        cleanup_current(self.folder,self.sources,self.session.runtime_identity)
        self.assertEqual(self.session.close()['worker'],'stopped')

    def test_compiled_file_and_snapshot_sources_reject_malformed_fields(self):
        value=self.snapshot();seen=set()
        compiled_file(self.folder,self.sources,value['source']['files'][0],seen)
        self.assertEqual(seen,{'build.svrun'})
        self.assertEqual(snapshot_sources(self.folder,self.sources,self.compiled,value['source']),{'build.svrun','film.svml','style.svs'})
        for source in (None,{},dict(files=[]),dict(files=[dict(path='build.svrun',text=None)])):
            with self.assertRaises(Invalid):snapshot_sources(self.folder,self.sources,self.compiled,source)

    def test_logs_current_checks_only_owned_bounded_diagnostics(self):
        self.ready();self.session.logs_current()
        with (self.session.control/'stderr.log').open('wb') as stream:stream.truncate(target.MAX_LOG_BYTES+1)
        with self.assertRaisesRegex(Invalid,'diagnostics exceeded'):self.session.logs_current()

    def test_changed_cleanup_profile_or_executable_prevents_foreign_commands(self):
        self.ready();(self.folder/'runtime.json').write_text('{}')
        with self.assertRaisesRegex(Invalid,'cleanup profile'):self.session.close()
        self.assertEqual(self.child.code,0);self.assertEqual(self.session.state,'NEEDS_INSPECTION')
        self.command_mock.assert_not_called()

    def test_cleanup_requires_an_actual_stopped_receipt(self):
        self.ready()
        with patch.object(self.session,'command',return_value=dict(worker='unknown')):
            with self.assertRaisesRegex(Invalid,'unconfirmed'):self.session.close()
        self.assertEqual(self.session.state,'NEEDS_INSPECTION')

    def test_changed_installation_blocks_start_and_cleanup_execution(self):
        with patch.object(target,'revalidate',side_effect=Invalid('Synthetic changed executable')),patch.object(target,'spawn_studio_child',return_value=self.child) as launch,patch.object(self.session,'observe_start',return_value=self.snapshot()):
            with self.assertRaisesRegex(Invalid,'changed executable'):self.session.start()
            launch.assert_not_called()
        self.assertFalse(self.session.control.exists());self.command_mock.assert_not_called()
        self.ready()
        with patch.object(target,'revalidate',side_effect=Invalid('Synthetic changed executable')):
            with self.assertRaisesRegex(Invalid,'changed executable'):self.session.close()
        self.assertEqual(self.child.code,0);self.command_mock.assert_not_called()

    def test_preflight_revocation_uses_callback_and_cleanup_ignores_revoked_authority(self):
        previous=self.command
        def revoke(args,**kw):
            if 'down' not in args:self.authorized=False
            return previous(args,**kw)
        with patch.object(target,'capture_owned_command',side_effect=revoke),patch.object(target,'spawn_studio_child') as launch:
            with self.assertRaisesRegex(Invalid,'revoked'):self.session.start()
            launch.assert_not_called()
        self.assertEqual(self.session.state,'FAILED_CLEANED')
        self.assertEqual(self.session.cleanup_receipt['worker'],'stopped')

    def test_startup_observation_timeout_never_submits_a_build(self):
        with patch.object(target,'spawn_studio_child',return_value=self.child),patch.object(target,'STARTUP_SECONDS',0):
            with self.assertRaisesRegex(Invalid,'observation expired'):self.session.start()
        self.assertEqual(self.child.code,0)
        self.assertEqual(self.session.state,'FAILED_CLEANED')
        argv=[call.args[0] for call in self.command_mock.call_args_list]
        self.assertEqual(len(argv),2)
        self.assertTrue(all('build' not in args for args in argv))

    def test_linked_runtime_destination_cannot_receive_preflight_or_shutdown(self):
        foreign=self.folder/'foreign';foreign.mkdir();marker=foreign/'marker';marker.write_bytes(b'untouched')
        (self.folder/'.hypit').symlink_to(foreign,target_is_directory=True)
        with patch.object(target,'spawn_studio_child') as launch:
            with self.assertRaisesRegex(Invalid,'linked|reparse'):self.session.start()
            launch.assert_not_called()
        self.command_mock.assert_not_called();self.assertEqual(marker.read_bytes(),b'untouched')

    def test_runtime_links_and_replaced_directory_inodes_cannot_redirect_cleanup(self):
        self.ready();runtime=self.folder/'.hypit/runtimes/local'
        runtime.rename(runtime.with_name('retained-local'));runtime.mkdir()
        with self.assertRaisesRegex(Invalid,'directory changed'):self.session.close()
        self.command_mock.assert_not_called();self.assertEqual(self.child.code,0)

    def test_runtime_parent_junction_or_symlink_is_denied_on_cleanup(self):
        self.ready();parent=self.folder/'.hypit';parent.rename(self.folder/'retained-hypit')
        foreign=self.folder/'foreign';foreign.mkdir();marker=foreign/'marker';marker.write_bytes(b'untouched')
        parent.symlink_to(foreign,target_is_directory=True)
        with self.assertRaisesRegex(Invalid,'linked|reparse'):self.session.close()
        self.command_mock.assert_not_called();self.assertEqual(marker.read_bytes(),b'untouched')

    def test_slow_streamed_body_and_headers_obey_a_total_deadline(self):
        self.ready()
        for mode in ('body','headers'):
            self.session.origin=self.server(slow=mode);started=time.monotonic()
            with patch.object(target,'HTTP_SECONDS',.2),self.assertRaises(TimeoutError):self.session.read()
            self.assertLess(time.monotonic()-started,1.2)

    def test_streamed_body_rechecks_authority_between_chunks(self):
        self.ready();self.session.origin=self.server(slow='body')
        timer=threading.Timer(.1,lambda:setattr(self,'authorized',False));timer.start();self.addCleanup(timer.cancel)
        started=time.monotonic()
        with self.assertRaisesRegex(Invalid,'revoked'):self.session.read()
        self.assertLess(time.monotonic()-started,1.2)

    def test_nonzero_preflight_and_cleanup_command_diagnostics_are_retained(self):
        def failed(args,**kw):return dict(code=3,stdout='partial local plan',stderr='synthetic compiler error')
        with patch.object(target,'capture_owned_command',side_effect=failed):
            with self.assertRaisesRegex(Invalid,'command failed'):self.session.start()
        data=json.loads((self.session.control/'command-plan.json').read_text())
        self.assertEqual(data['code'],3);self.assertEqual(data['stderr'],'synthetic compiler error')
        cleanup=json.loads((self.session.control/'command-cleanup.json').read_text())
        self.assertEqual(cleanup['stderr'],'synthetic compiler error')
        self.assertEqual(self.session.state,'NEEDS_INSPECTION')

    def test_capture_interruption_retains_partial_diagnostics_before_cleanup(self):
        def interrupted(args,**kw):
            if 'down' in args:return self.command(args,**kw)
            kw['diagnostics'](dict(code=-1,stdout='partial output',stderr='partial error',interrupted=True))
            raise Invalid('Synthetic deadline')
        with patch.object(target,'capture_owned_command',side_effect=interrupted):
            with self.assertRaisesRegex(Invalid,'Synthetic deadline'):self.session.start()
        data=json.loads((self.session.control/'command-plan.json').read_text())
        self.assertEqual(data['stdout'],'partial output');self.assertEqual(data['stderr'],'partial error')
        self.assertEqual(data['capture_failure'],'Invalid');self.assertTrue(data['interrupted'])

    def test_write_control_and_retain_command_preserve_bounded_private_records(self):
        self.ready();self.session.retain_command('plan',dict(code=4,stderr='synthetic diagnostic'))
        self.assertEqual(json.loads((self.session.control/'command-plan.json').read_text())['code'],4)
        with self.assertRaises(Invalid):self.session.write_control('../foreign',{})
        with self.assertRaises(Invalid):self.session.retain_command('../foreign',{})
        with patch.object(target,'MAX_DIAGNOSTIC_BYTES',1),self.assertRaisesRegex(Invalid,'diagnostic exceeds'):
            self.session.write_control('state',dict(large='payload'))

    def test_check_read_revalidates_scope_and_current_logs(self):
        self.ready();self.session.check_read();self.authorized=False
        with self.assertRaisesRegex(Invalid,'revoked'):self.session.check_read()

    def test_session_bytes_and_bounded_body_reject_foreign_origins_and_early_eof(self):
        from types import SimpleNamespace
        for origin in ('https://127.0.0.1:80','http://example.invalid:80','http://127.0.0.1:80/foreign'):
            with self.assertRaises(Invalid):session_bytes(origin,lambda:None,time.monotonic()+1,100)
        stream=io.BytesIO(b'current');response=SimpleNamespace(read1=stream.read1,length=0)
        self.assertEqual(bounded_body(response,lambda:None,time.monotonic()+1,100),b'current')
        response=SimpleNamespace(read1=io.BytesIO(b'').read1,length=10)
        with self.assertRaisesRegex(Invalid,'declared size'):bounded_body(response,lambda:None,time.monotonic()+1,100)

    def test_owned_connection_connect_and_expire_close_only_its_socket(self):
        from urllib.parse import urlsplit
        origin=self.server();port=urlsplit(origin).port
        connection=OwnedConnection('127.0.0.1',port,timeout=1)
        other=OwnedConnection('127.0.0.1',port,timeout=1)
        try:
            connection.connect();other.connect()
            connection.expire()
            self.assertEqual(connection.owned_socket.fileno(),-1)
            self.assertNotEqual(other.owned_socket.fileno(),-1)
        finally:connection.close();other.close()

    def test_installation_change_during_preflight_cannot_reach_studio_launch(self):
        changed=False;original=self.command
        def plan(args,**kwargs):
            nonlocal changed
            value=original(args,**kwargs)
            if 'plan' in args:changed=True
            return value
        def verify(value):
            if changed:raise Invalid('Synthetic installation changed during preflight')
            return value
        with patch.object(target,'capture_owned_command',side_effect=plan),patch.object(target,'revalidate',side_effect=verify),patch.object(target,'spawn_studio_child') as launch:
            with self.assertRaisesRegex(Invalid,'changed during preflight'):self.session.start()
            launch.assert_not_called()
        self.assertEqual(self.session.state,'NEEDS_INSPECTION')

    def test_compiled_current_and_compiled_files_require_an_independent_exact_contract(self):
        self.assertEqual(compiled_files(self.compiled),set(self.compiled['files']))
        self.assertEqual(compiled_current(self.folder,self.sources,self.compiled),set(self.compiled['files']))
        for value in (None,{},dict(root='film.svml',files=['film.svml']),dict(root='foreign.svml',files=['build.svrun','film.svml']),
                      dict(root='film.svml',files=['build.svrun','film.svml','film.svml'])):
            with self.assertRaises(Invalid):compiled_current(self.folder,self.sources,value)

    def test_connection_for_requires_canonical_loopback_and_a_future_deadline(self):
        with self.assertRaises(TimeoutError):connection_for('http://127.0.0.1:80',time.monotonic()-1)
        with self.assertRaises(Invalid):connection_for('http://foreign.invalid:80',time.monotonic()+1)
        connection=connection_for(self.server(),time.monotonic()+1)
        self.assertIsNone(connection.sock);connection.close()

    def test_existing_runtime_storage_is_never_adopted_or_shut_down(self):
        runtime_directory(self.folder,create=True)
        runtime=self.folder/'.hypit/runtimes/local'
        marker=runtime/'prior-owner';marker.write_bytes(b'synthetic existing runtime')
        with patch.object(target,'spawn_studio_child') as launch:
            with self.assertRaisesRegex(Invalid,'already exists'):self.session.start()
            launch.assert_not_called()
        self.command_mock.assert_not_called();self.assertFalse(self.session.admitted)
        self.assertIsNone(self.session.runtime_identity)
        self.session.close();self.assertEqual(marker.read_bytes(),b'synthetic existing runtime')
        self.command_mock.assert_not_called()

    def test_even_empty_existing_runtime_storage_requires_inspection(self):
        runtime_directory(self.folder,create=True)
        with self.assertRaisesRegex(Invalid,'already exists'):self.session.start()
        self.assertFalse(self.session.admitted);self.command_mock.assert_not_called()

    def test_existing_safe_parents_allow_exclusive_new_runtime_storage(self):
        (self.folder/'.hypit/runtimes').mkdir(parents=True)
        with patch.object(target,'spawn_studio_child',return_value=self.child),patch.object(self.session,'observe_start',return_value=self.snapshot()):
            self.session.start()
        self.assertTrue(self.session.admitted);self.assertEqual(self.session.close()['worker'],'stopped')

    def test_relative_project_is_anchored_before_the_callers_cwd_changes(self):
        previous=Path.cwd()
        try:
            os.chdir(self.folder.parent)
            self.session=StudioProcess(Path(self.folder.name),self.installation,self.sources,self.compiled,self.alive)
            os.chdir(previous)
            with patch.object(target,'spawn_studio_child',return_value=self.child) as launch,patch.object(self.session,'observe_start',return_value=self.snapshot()):
                self.session.start()
                args=launch.call_args.args[0];kw=launch.call_args.kwargs
                self.assertEqual(kw['folder'],self.folder)
                self.assertEqual(args[args.index('--project')+1],str(self.folder))
                self.assertTrue(Path(args[args.index('--project')+1]).is_absolute())
                self.assertEqual(self.command_mock.call_args.kwargs['folder'],self.folder)
            self.session.close()
            self.assertTrue((self.folder/'.wmm-studio-control/state.json').is_file())
        finally:os.chdir(previous)

    def test_absolute_anchoring_preserves_project_symlink_rejection(self):
        previous=Path.cwd();alias=self.folder.parent/(self.folder.name+'-alias')
        alias.symlink_to(self.folder,target_is_directory=True)
        self.addCleanup(alias.unlink)
        try:
            os.chdir(self.folder.parent)
            session=StudioProcess(Path(alias.name),self.installation,self.sources,self.compiled,self.alive)
            with self.assertRaisesRegex(Invalid,'linked|reparse'):session.start()
            self.command_mock.assert_not_called()
        finally:os.chdir(previous)

    def test_matching_source_from_an_unowned_listener_cannot_establish_readiness(self):
        from urllib.error import URLError
        self.ready();self.session.origin=self.server();self.child.listener_owned=False
        with self.assertRaisesRegex(URLError,'not owned'):self.session.read()
        self.assertNotEqual(self.session.state,'CLOSED')

    def test_listener_owner_is_rechecked_after_reading_the_response(self):
        self.ready();self.session.origin=self.server()
        with patch.object(self.child,'owns_listener',side_effect=[True,False]):
            with self.assertRaisesRegex(Invalid,'ownership changed'):self.session.read()

    @unittest.skipUnless(os.name=='nt','Windows owned-listener native acceptance')
    def test_port_stolen_before_child_binding_cannot_supply_a_matching_snapshot(self):
        import sys
        from mission_control.studio_child import spawn_studio_child
        owned=[]
        def occupied(argv,**kwargs):
            port=int(argv[argv.index('--port')+1])
            self.server(port=port)
            child=spawn_studio_child([sys.executable,'-u','-c','import time;time.sleep(10)'],**kwargs)
            owned.append(child);return child
        with patch.object(target,'spawn_studio_child',side_effect=occupied),patch.object(target,'STARTUP_SECONDS',.2):
            with self.assertRaisesRegex(Invalid,'observation expired'):self.session.start()
        self.assertEqual(len(owned),1);self.assertIsNotNone(owned[0].poll())
        self.assertEqual(self.session.state,'FAILED_CLEANED')

    def test_cleanup_commands_prevents_false_failed_cleaned_after_unconfirmed_plan_teardown(self):
        previous=self.command
        def failed(args,**kwargs):
            if 'down' in args:return previous(args,**kwargs)
            kwargs['diagnostics'](dict(code=None,tree_stopped=False,recovery_id='synthetic-owned-plan',cleanup_failure='Invalid'))
            raise Invalid('Synthetic preflight cleanup unconfirmed')
        with patch.object(target,'capture_owned_command',side_effect=failed),patch.object(target,'retry_cleanup',side_effect=Invalid('Synthetic still running')):
            with self.assertRaisesRegex(Invalid,'unconfirmed'):self.session.start()
        self.assertEqual(self.session.state,'NEEDS_INSPECTION');self.assertFalse(self.session.closed)
        with patch.object(target,'retry_cleanup',return_value=dict(tree_stopped=True)) as recover:
            self.assertEqual(self.session.close()['worker'],'stopped')
            recover.assert_called_once_with('synthetic-owned-plan')
        self.assertTrue(self.session.closed)
        self.assertTrue(self.session.command_diagnostics['plan']['tree_stopped'])

    def test_pending_native_launch_rollback_prevents_false_cleanup(self):
        from types import SimpleNamespace
        def failed():raise Invalid('Synthetic native rollback still pending')
        owner=SimpleNamespace(stop=failed)
        with patch.object(target,'spawn_studio_child',side_effect=target.LaunchCleanupPending(owner)):
            with self.assertRaises(target.LaunchCleanupPending):self.session.start()
        self.assertFalse(self.session.closed);self.assertEqual(self.session.state,'NEEDS_INSPECTION')
        self.assertIs(self.session.launch_recovery,owner)
        owner.stop=lambda:None
        self.assertEqual(self.session.close()['worker'],'stopped')
        self.assertIsNone(self.session.launch_recovery)

    def test_cleanup_commands_requires_confirmed_recovery_and_persists_the_result(self):
        self.ready()
        self.session.retain_command('plan',dict(tree_stopped=False,recovery_id='synthetic-command'))
        with patch.object(target,'retry_cleanup',return_value=dict(tree_stopped=False)):
            with self.assertRaisesRegex(Invalid,'still unconfirmed'):self.session.cleanup_commands()
        self.assertFalse(self.session.command_diagnostics['plan']['tree_stopped'])
        with patch.object(target,'retry_cleanup',return_value=dict(tree_stopped=True)):
            self.session.cleanup_commands()
        self.assertTrue(self.session.command_diagnostics['plan']['recovered'])

    def test_pending_command_metadata_survives_failed_log_reads_in_both_phases(self):
        from types import SimpleNamespace
        from mission_control import studio_command
        self.ready()
        def failed():raise Invalid('Synthetic owned teardown still pending')
        child=SimpleNamespace(poll=lambda:0,stop=failed,overflow=False,failure=None)
        for phase in ('plan','cleanup'):
            if phase=='cleanup':
                self.session.command_diagnostics={};self.session.closed=False
            with patch.object(target,'capture_owned_command',side_effect=studio_command.capture_owned_command),patch.object(studio_command,'spawn_studio_child',return_value=child),patch.object(studio_command,'output_snapshot',side_effect=OSError('Synthetic log failure')):
                with self.assertRaises(Invalid):self.session.command(['runtime','down'] if phase=='cleanup' else ['plan'],cleanup=phase=='cleanup')
            value=self.session.command_diagnostics[phase]
            self.assertFalse(value['tree_stopped']);self.assertTrue(value['recovery_id'])
            self.session.admitted=False
            with self.assertRaises(Invalid):self.session.close()
            self.assertFalse(self.session.closed);self.assertEqual(self.session.state,'NEEDS_INSPECTION')
            child.stop=lambda:None
            self.session.close();self.assertTrue(self.session.closed)
            child.stop=failed


if __name__=='__main__':unittest.main()
