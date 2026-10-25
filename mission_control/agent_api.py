"""Pinned public HTTPS text inference; no redirects, tools or raw error disclosure."""
import time
from urllib.parse import urlsplit
from .common import Invalid,canonical
from .aeo_transport import public_url,address,PinnedHTTPS,response_headers,response_body
from .aeo_tls import trust_context
from .payment_signature import strict_json
from .agent_contract import draft


def request(profile,key,prompt,max_tokens=2048,alive=lambda:None):
    """Protect authorization from DNS rebinding and redirect forwarding."""
    if profile['provider']=='local_api':
        from .local_agent_api import request as local_request
        return local_request(profile,key,prompt,max_tokens,alive)
    return public_request(profile,key,prompt,max_tokens,alive)


def public_request(profile,key,prompt,max_tokens,alive):
    """Retain pinned public HTTPS inference for the existing keyed adapters."""
    url=public_url(profile['endpoint']);parts=urlsplit(url)
    anthropic=profile['provider']=='anthropic_api'
    route=parts.path.rstrip('/')+('/messages' if anthropic else '/chat/completions')
    headers={'Accept':'application/json','Accept-Encoding':'identity','Content-Type':'application/json'}
    body=dict(model=profile['model'],messages=[{'role':'user','content':prompt}],stream=False)
    if anthropic:
        headers.update({'x-api-key':key,'anthropic-version':'2023-06-01'});body['max_tokens']=max_tokens
    else:
        headers['Authorization']='Bearer '+key
        body['max_completion_tokens' if profile['provider']=='openai_api' else 'max_tokens']=max_tokens
    deadline=time.monotonic()+30;alive()
    conn=PinnedHTTPS(parts.hostname,address(parts.hostname,deadline),trust_context(),deadline)
    try:
        conn.request('POST',route,body=canonical(body).encode(),headers=headers)
        response=conn.getresponse()
        if response.status in (401,403):raise Invalid('Provider permission denied; reconnect and verify the selected account')
        if response.status==429:raise Invalid('Provider allowance or rate limit reached; wait or approve another connection')
        if response.status!=200:raise Invalid('Provider did not accept this inference; no fallback or replay was attempted')
        raw=response_body(response,response_headers(response),1048576,conn,deadline)
    except Invalid:raise
    except (OSError,ValueError,TimeoutError):raise Invalid('Provider inference could not be confirmed; charges may have occurred. Review before retry') from None
    finally:conn.close()
    alive();value=strict_json(raw)
    text=message(value,anthropic)
    if key in text:raise Invalid('Provider echoed a protected key; output was rejected')
    return draft(strict_json(text.encode())),value.get('usage')


def message(value,anthropic):
    """Require a complete plain final response, never tool calls or truncated content."""
    try:
        if anthropic:
            if value['stop_reason']!='end_turn':raise Invalid('Provider response was incomplete; no draft accepted')
            if any(p['type']!='text' for p in value['content']):raise Invalid('Provider returned a tool or unsupported response')
            return ''.join(p['text'] for p in value['content'])
        choice=value['choices'][0]
        if choice['finish_reason']!='stop' or choice['message'].get('tool_calls'):
            raise Invalid('Provider response was incomplete or requested tools; no draft accepted')
        if not isinstance(choice['message']['content'],str):raise ValueError()
        return choice['message']['content']
    except (KeyError,IndexError,TypeError,ValueError):raise Invalid('Provider returned an unsupported final response') from None
