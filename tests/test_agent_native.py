"""Native argument authority, owned-process bounds and final-response checks."""
import json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from mission_control.common import Invalid,canonical
from mission_control.agent_native import locate,identity,run
from mission_control.agent_commands import arguments,output
from mission_control.agent_process import capture,environment,failure
from tests.test_agent_access import answer


class NativeTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup);self.root=Path(self.folder.name)

    def test_fixed_command_profiles_never_enable_bypass_or_inherited_tools(self):
        for provider in ('codex','claude','kimi','glm_coding'):
            folder=self.root/provider;folder.mkdir()
            args=arguments(provider,'synthetic.exe',folder,'synthetic-model','Public synthetic input')
            self.assertFalse(any('bypass' in a or a in ('--yolo','--auto','--resume','--continue') for a in args))
            self.assertIn('synthetic-model',args)
            if provider=='codex':
                self.assertIn('--ignore-user-config',args);self.assertIn('features.shell_tool=false',args)
                self.assertIn('permissions.marketing.network.enabled=false',args)
                self.assertIn('default_permissions="marketing"',args)
            elif provider=='kimi':self.assertIn('tools: []', (folder/'agent.md').read_text())
            else:self.assertIn('--safe-mode',args);self.assertEqual(args[args.index('--tools')+1],'')
        with self.assertRaises(Invalid):arguments('arbitrary','evil.exe',self.root,'','')

    def test_own_process_handles_stdin_literal_output_and_secret_environment(self):
        with patch.dict(os.environ,{'OPENAI_API_KEY':'SYNTHETIC_PRIVATE_KEY','ANTHROPIC_AUTH_TOKEN':'SYNTHETIC_PRIVATE_TOKEN'}):
            self.assertNotIn('OPENAI_API_KEY',environment())
            value=capture([sys.executable,'-c','import sys,os;print(sys.stdin.read());print(os.getenv("OPENAI_API_KEY","absent"))'],
                          'literal $() & ` input',timeout=5)
        self.assertEqual(value['code'],0);self.assertIn('literal $() & ` input',value['stdout'])
        self.assertIn('absent',value['stdout']);self.assertNotIn('SYNTHETIC_PRIVATE',canonical(value))

    def test_owned_timeout_output_cap_and_cancellation(self):
        with self.assertRaisesRegex(Invalid,'timed out'):
            capture([sys.executable,'-c','import time;time.sleep(10)'],timeout=1)
        with self.assertRaisesRegex(Invalid,'bounded size'):
            capture([sys.executable,'-c','print("x"*1100000)'],timeout=5)
        def cancelled():raise Invalid('Synthetic cancellation')
        with self.assertRaisesRegex(Invalid,'cancellation'):
            capture([sys.executable,'-c','import time;time.sleep(10)'],alive=cancelled,timeout=5)

    def test_codex_final_only_no_internal_reasoning_or_tools(self):
        events=[{'type':'item.completed','item':{'type':'reasoning','text':'SYNTHETIC_REASONING_NOT_FOR_USER'}},
                {'type':'item.completed','item':{'type':'agent_message','text':canonical(answer())}},
                {'type':'turn.completed','usage':{'input_tokens':10,'output_tokens':20}}]
        value=output('codex',dict(code=0,stdout='\n'.join(map(json.dumps,events)),stderr=''))
        self.assertEqual(value[0],answer());self.assertNotIn('REASONING',canonical(value))
        with self.assertRaisesRegex(Invalid,'complete final'):
            output('codex',dict(code=0,stdout='\n'.join(map(json.dumps,events[:-1])),stderr=''))
        for event in ({'type':'turn.failed'},{'type':'item.started','item':{'type':'command_execution'}}):
            with self.assertRaises(Invalid):output('codex',dict(code=0,stdout=json.dumps(event),stderr=''))
        with self.assertRaises(Invalid):output('codex',dict(code=0,stdout='not JSON',stderr=''))

    def test_claude_and_kimi_structured_output_and_redacted_failures(self):
        self.assertEqual(output('claude',dict(code=0,stdout=json.dumps({'subtype':'success','structured_output':answer()}),stderr=''))[0],answer())
        with self.assertRaises(Invalid):output('claude',dict(code=0,stdout=json.dumps({'subtype':'error_max_turns','structured_output':answer()}),stderr=''))
        self.assertEqual(output('kimi',dict(code=0,stdout=json.dumps({'role':'assistant','content':canonical(answer())}),stderr=''))[0],answer())
        with self.assertRaises(Invalid):output('kimi',dict(code=0,stdout=json.dumps({'role':'assistant','tool_calls':[{}]}),stderr=''))
        result=failure(dict(code=1,stdout='',stderr='Authentication failed: SYNTHETIC_SECRET_VALUE'))
        self.assertIn('reconnect',result);self.assertNotIn('SECRET',result)

    def test_detect_hash_bound_binary_and_reject_drift(self):
        package=self.root/'AppData/Local/Volta/tools/image/packages/@openai/codex/node_modules/@openai/codex'
        exe=package/'node_modules/@openai/codex-win32-x64/vendor/synthetic/bin/codex.exe';exe.parent.mkdir(parents=True)
        exe.write_bytes(b'synthetic-not-executed');(package/'package.json').write_text('{"name":"@openai/codex","version":"0.162.1"}')
        frozen=locate('codex',self.root)
        with patch('mission_control.agent_native.capture',side_effect=[dict(code=0,stdout='codex-cli 0.162.1',stderr=''),dict(code=0,stdout='',stderr='Logged in using ChatGPT')]):
            self.assertEqual(identity('codex',self.root)['login_state'],'SIGNED_IN')
        exe.write_bytes(b'changed-synthetic')
        with patch('mission_control.agent_native.locate',return_value=locate('codex',self.root)):
            with self.assertRaisesRegex(Invalid,'changed'):run('codex',frozen,'synthetic input')
        with self.assertRaises(Invalid):locate('kimi',self.root)

    def test_unverified_kimi_hooks_cannot_start_a_native_process(self):
        with patch('mission_control.agent_native.capture') as execute:
            with self.assertRaisesRegex(Invalid,'hook isolation'):run('kimi',{},'Synthetic public input')
            execute.assert_not_called()


if __name__=='__main__':unittest.main()
