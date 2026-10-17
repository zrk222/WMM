"""Fixed subscription command profiles and strict final-message extraction."""
import json
from .common import Invalid,canonical
from .agent_contract import OUTPUT_SCHEMA,draft
from .agent_process import failure
from .payment_signature import strict_json


def codex_args(executable,folder,model):
    """Disable inherited tools/config and scope any remaining filesystem access."""
    schema=folder/'output-schema.json';schema.write_text(canonical(OUTPUT_SCHEMA))
    args=[executable,'exec','--ignore-user-config','--strict-config','--skip-git-repo-check','--ephemeral',
        '--json','--color','never','--output-schema',str(schema)]
    for key,value in {'features.shell_tool':'false','features.apps':'false','features.hooks':'false',
        'features.plugins':'false','features.multi_agent':'false','features.memories':'false',
        'features.image_generation':'false','features.browser_use':'false','features.computer_use':'false',
        'web_search':'"disabled"','project_doc_max_bytes':'0','model_reasoning_effort':'"low"',
        'default_permissions':'"marketing"',
        'permissions.marketing.filesystem':'{":minimal"="read",":workspace_roots"="read"}',
        'permissions.marketing.network.enabled':'false'}.items():args+=['-c',key+'='+value]
    if model:args+=['--model',model]
    return args+['-']


def claude_args(executable,folder,model):
    """Safe mode retains official login while disabling all inherited customizations."""
    config=folder/'mcp.json';config.write_text('{"mcpServers":{}}')
    args=[executable,'--safe-mode','-p','--tools','','--setting-sources','',
        '--strict-mcp-config','--mcp-config',str(config),'--no-session-persistence',
        '--disable-slash-commands','--output-format','json','--json-schema',canonical(OUTPUT_SCHEMA)]
    if model:args+=['--model',model]
    return args


def kimi_args(executable,folder,model,prompt):
    """An explicit agent profile removes tools and subagents, unlike plan mode."""
    agent=folder/'agent.md';agent.write_text('---\nname: marketing-draft\ndescription: Bounded text drafts\ntools: []\nsubagents: []\n---\nReturn only the requested JSON draft. No external actions.\n')
    skills=folder/'skills';skills.mkdir()
    args=[executable,'--agent-file',str(agent),'--skills-dir',str(skills),'--output-format','stream-json']
    if model:args+=['--model',model]
    return args+['--prompt',prompt]


def arguments(provider,executable,folder,model,prompt):
    """Only adapter-owned command builders can reach the native process boundary."""
    if provider=='codex':return codex_args(executable,folder,model)
    if provider in ('claude','glm_coding'):return claude_args(executable,folder,model)
    if provider=='kimi':return kimi_args(executable,folder,model,prompt)
    raise Invalid('Unsupported native agent adapter')


def codex_output(text):
    """Retain final message only; reasoning and tool output never become draft content."""
    final=None;usage=None;completed=False
    for line in text.splitlines():
        value=strict_json(line.encode());item=codex_event(value)
        if value.get('type')=='item.completed' and item.get('type')=='agent_message':
            if completed:raise Invalid('Agent final message arrived after turn completion')
            final=item.get('text')
        if value.get('type')=='turn.completed':
            if completed:raise Invalid('Agent returned more than one completed turn')
            completed=True;usage=value.get('usage')
    if not completed or not isinstance(final,str):raise Invalid('Agent returned no complete final message')
    return draft(strict_json(final.encode())),usage


def codex_event(value):
    """Only assistant/reasoning events are permitted; unknown tool families fail closed."""
    if not isinstance(value,dict):raise Invalid('Agent returned an unsupported event')
    if value.get('type') in ('error','turn.failed'):raise Invalid('Agent did not complete the draft; review connection and quota')
    item=value.get('item',{})
    if not isinstance(item,dict):raise Invalid('Agent returned an unsupported item')
    if item and item.get('type') not in ('agent_message','reasoning'):
        raise Invalid('Agent attempted a tool outside the text-draft contract')
    return item


def kimi_output(text):
    """Read assistant text only and reject tool calls rather than accepting progress."""
    parts=[]
    for line in text.splitlines():
        value=strict_json(line.encode())
        if value.get('tool_calls') or value.get('role')=='tool':raise Invalid('Kimi attempted a tool outside the draft contract')
        if value.get('role')=='assistant':parts.append(value.get('content',''))
    if not all(isinstance(p,str) for p in parts):raise Invalid('Kimi returned unsupported message content')
    return draft(strict_json(''.join(parts).encode())),None


def output(provider,value):
    """An exit code alone is not a successful, source-bound draft."""
    if value['code']:raise Invalid(failure(value))
    if provider=='codex':return codex_output(value['stdout'])
    if provider=='kimi':return kimi_output(value['stdout'])
    reply=strict_json(value['stdout'].encode())
    if reply.get('is_error') or reply.get('subtype')!='success':raise Invalid(failure(value))
    result=reply.get('structured_output')
    if result is None:result=strict_json(str(reply.get('result','')).encode())
    return draft(result),reply.get('usage')
