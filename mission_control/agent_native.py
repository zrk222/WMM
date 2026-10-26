"""Detect supported installed tools; never acquire software or export login secrets."""
import json,re,tempfile,sys
from pathlib import Path
from .common import Invalid,digest
from .audit_tools import file_hash
from .agent_registry import REGISTRY
from .agent_process import capture
from .agent_commands import arguments,output


def candidates(tool,home):
    """Known official installation locations only; no request-supplied executables."""
    if sys.platform.startswith('linux'):
        from .linux_agent_paths import candidates as linux_candidates
        return linux_candidates(tool,home)
    if tool=='codex':
        package=home/'AppData/Local/Volta/tools/image/packages/@openai/codex/node_modules/@openai/codex'
        files=sorted(package.glob('node_modules/@openai/codex-win32-*/vendor/*/bin/codex.exe'))
        return [(p,package/'package.json','@openai/codex') for p in files]
    if tool=='claude':
        package=home/'AppData/Local/Volta/tools/image/packages/@anthropic-ai/claude-code/node_modules/@anthropic-ai/claude-code'
        return [(package/'bin/claude.exe',package/'package.json','@anthropic-ai/claude-code')]
    if tool=='kimi':return [(home/'.local/bin/kimi.exe',None,None)]
    return []


def native_candidate(executable):
    """Apply the running platform's native-file check before trusting a fixed candidate."""
    if not executable.is_file():return False
    if sys.platform.startswith('linux'):
        from .linux_agent_paths import native_file
        return native_file(executable)
    return True


def locate(provider,home=None):
    """Hash actual binary bytes and package identity without trusting PATH shims."""
    if provider not in REGISTRY or not REGISTRY[provider]['tool']:raise Invalid('Choose a native subscription adapter')
    for executable,metadata,name in candidates(REGISTRY[provider]['tool'],Path(home) if home else Path.home()):
        if not native_candidate(executable):continue
        package=json.loads(metadata.read_text(encoding='utf-8')) if metadata else {}
        if metadata and package.get('name')!=name:continue
        result=dict(executable=str(executable.resolve()),sha256=file_hash(executable),package_version=package.get('version'))
        result['fingerprint']=digest(result)
        return result
    raise Invalid('Official agent tool is not installed in a supported location; use the linked official installer')


def identity(provider,home=None):
    """Inspect version and closed sign-in status without returning account identifiers."""
    tool=locate(provider,home)
    version=capture([tool['executable'],'--version'],timeout=15)
    if version['code'] or not re.search(r'\d+\.\d+\.\d+',version['stdout']):raise Invalid('Agent version could not be verified')
    tool['version']=re.search(r'\d+\.\d+\.\d+',version['stdout']).group()
    if provider=='codex':
        value=capture([tool['executable'],'login','status'],timeout=15)
        signed=value['code']==0 and 'using ChatGPT' in value['stdout']+value['stderr']
        state='SIGNED_IN' if signed else 'SIGN_IN_REQUIRED'
    elif provider=='claude':
        value=capture([tool['executable'],'auth','status'],timeout=15)
        try:details=json.loads(value['stdout'])
        except ValueError:details={}
        state='SIGNED_IN' if details.get('loggedIn') and details.get('authMethod') in ('oauth','claude.ai') else 'SIGN_IN_REQUIRED'
    else:state='TEST_REQUIRED'
    return dict(tool,login_state=state,quota='UNKNOWN',account_identity='NOT_INDEPENDENTLY_VERIFIED')


def run(provider,frozen,prompt,model='',secret=None,alive=lambda:None):
    """Recheck exact installed bytes and invoke only the fixed profile in a fresh folder."""
    if provider=='kimi':raise Invalid('Kimi runner needs installed-version hook isolation verification; choose a tested connection meanwhile')
    current=locate(provider)
    if current['fingerprint']!=frozen['fingerprint']:raise Invalid('Installed agent changed; detect and approve the current tool')
    with tempfile.TemporaryDirectory(prefix='growth-agent-task-') as name:
        folder=Path(name);args=arguments(provider,current['executable'],folder,model,prompt)
        extra={}
        if provider=='glm_coding':
            if not secret:raise Invalid('GLM coding-plan key is missing; reconnect this profile')
            extra={'ANTHROPIC_AUTH_TOKEN':secret,'ANTHROPIC_BASE_URL':REGISTRY[provider]['endpoint']}
        value=capture(args,prompt,alive,folder=folder,extra_env=extra)
    if locate(provider)['fingerprint']!=current['fingerprint']:raise Invalid('Installed agent changed during work; result remains unverified')
    return output(provider,value)
