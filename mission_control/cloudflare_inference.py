"""Bounded Workers AI connection policy; provider billing is not observable here."""
import re
from datetime import date,timedelta
from .common import Invalid, required
from .agent_registry import TASKS

FREE_MODELS=frozenset(('@cf/meta/llama-3.1-8b-instruct-fp8-fast','@cf/meta/llama-3.2-3b-instruct'))


def validate(account_id,model,mode,charges,daily,tokens):
    if not isinstance(account_id,str) or not re.fullmatch(r'[a-f0-9]{32}',account_id):
        raise Invalid('Enter the 32-character lowercase Cloudflare account ID')
    if not isinstance(model,str) or not re.fullmatch(r'@[A-Za-z0-9][A-Za-z0-9._:/-]{0,118}',model):
        raise Invalid('Enter a bounded Cloudflare model identifier')
    if mode not in ('free','paid') or type(charges) is not bool or charges != (mode=='paid'):
        raise Invalid('Choose free-only or explicitly allow paid inference')
    if mode=='free' and model not in FREE_MODELS:raise Invalid('This model is not on the free-only model allowlist')
    if type(daily) is not int or not 1<=daily<=1000:raise Invalid('Daily approvals per connection must be between 1 and 1000')
    if type(tokens) is not int or not 64<=tokens<=2048:raise Invalid('Maximum output tokens must be between 64 and 2048')
    return f'https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1'


def validated_profile(body):
    from .agent_contract import profile_identity,profile_secret
    profile_identity(body);profile_secret('cloudflare_api',body['api_key'])
    if body['endpoint']!='':raise Invalid('Cloudflare endpoint is derived from the account ID')
    endpoint=validate(body['account_id'],body['model'],body['billing_mode'],body['allow_api_charges'],body['daily_request_limit'],body['max_output_tokens'])
    return dict(provider='cloudflare_api',label=required(body['label'],'Connection name',100),model=body['model'],endpoint=endpoint,
        allow_api_charges=body['allow_api_charges'],capabilities=list(TASKS),quota='UNKNOWN',
        billing_policy=dict(account_id=body['account_id'],mode=body['billing_mode'],daily_request_limit=body['daily_request_limit'],max_output_tokens=body['max_output_tokens']))


def verify(data):
    """Revalidate saved policy and destination immediately before use."""
    policy=data.get('billing_policy')
    if not isinstance(policy,dict) or set(policy)!={'account_id','mode','daily_request_limit','max_output_tokens'}:
        raise Invalid('Cloudflare billing policy is missing or malformed')
    endpoint=validate(policy['account_id'],data.get('model'),policy['mode'],data.get('allow_api_charges'),policy['daily_request_limit'],policy['max_output_tokens'])
    if data.get('endpoint')!=endpoint:raise Invalid('Cloudflare destination changed')
    return policy


def reserve(db,app_id,frozen,created):
    """Count both native turns and draft approvals on the UTC creation day, no refunds."""
    day=date.fromisoformat(created[:10]);next_day=day+timedelta(days=1)
    count=db.execute("""SELECT COUNT(*) FROM jobs WHERE app_id=? AND created>=? AND created<? AND
        ((action='agent_run' AND json_extract(data,'$.envelope.connection_id')=? AND json_extract(data,'$.envelope.provider')='cloudflare_api') OR
         (action='ios_agent_turn' AND json_extract(data,'$.frozen.connection_id')=? AND json_extract(data,'$.frozen.provider')='cloudflare_api'))""",
        (app_id,day.isoformat()+'T00:00:00+00:00',next_day.isoformat()+'T00:00:00+00:00',frozen['connection_id'],frozen['connection_id'])).fetchone()[0]
    if count>=frozen['billing_policy']['daily_request_limit']:
        raise Invalid('This connection reached its WMM daily approval limit (UTC)')
