"""Closed agent access adapters; a subscription is not unrestricted API access."""
from copy import deepcopy

TASKS={
    'campaign_plan':'Plan the next useful campaign work from the app facts and missing proof. Use action_feedback to reuse fresh observations, prioritize public repair codes and unresolved proof, and avoid repeating the same read unless a fresh recheck is justified.',
    'original_copy':'Draft original problem, demonstration and limitation copy for this app.',
    'experiment_critique':'Review a proposed experiment for missing evidence, measurement and decision rules.'}
FACTS=('name','website','release','locale','job','audience','activation','brand_voice','brand_boundaries')
SOURCE_IDS=('app_manifest',)+tuple('stage_'+str(n) for n in range(1,13))+('release_observation','subscription_observation','ledger_state','action_feedback')
NATIVE=('codex','claude','kimi','glm_coding')
KEYED=('glm_coding','openai_api','anthropic_api','compatible_api')
REGISTRY={
    'codex':dict(name='Codex subscription',mode='subscription',tool='codex',
        link='https://developers.openai.com/codex/auth',endpoint='',
        explanation='Use the official Codex CLI and its existing ChatGPT sign-in. API keys are not used for this route.'),
    'claude':dict(name='Claude Code subscription',mode='subscription',tool='claude',
        link='https://code.claude.com/docs/en/authentication',endpoint='',
        explanation='Use official Claude Code sign-in. A configured API key does not count as subscription access.'),
    'kimi':dict(name='Kimi Code subscription',mode='subscription',tool='kimi',
        link='https://www.kimi.com/code/docs/en/kimi-code-cli/guides/getting-started',endpoint='',
        explanation='Detect the official Kimi Code CLI. Execution remains unavailable until installed-version hook isolation is verified; choose a tested route meanwhile.'),
    'glm_coding':dict(name='GLM Coding Plan',mode='subscription',tool='claude',
        link='https://docs.z.ai/devpack/tool/claude',endpoint='https://api.z.ai/api/anthropic',
        explanation='Use your coding-plan key through the supported Claude Code integration, without rewriting global settings.'),
    'openai_api':dict(name='OpenAI API key',mode='byok',tool=None,
        link='https://platform.openai.com/api-keys',endpoint='https://api.openai.com/v1',
        explanation='Provider API charges are separate from a ChatGPT or Codex subscription.'),
    'anthropic_api':dict(name='Anthropic API key',mode='byok',tool=None,
        link='https://platform.claude.com',endpoint='https://api.anthropic.com/v1',
        explanation='Use an Anthropic API key. API charges are separate from a Claude subscription.'),
    'compatible_api':dict(name='Compatible API endpoint',mode='byok',tool=None,
        link='',endpoint='',explanation='Use an explicitly approved public HTTPS OpenAI-chat-compatible endpoint. Compatibility must be tested.')}


def catalog():
    """Return public adapter capabilities without assuming installation or permission."""
    return {key:dict(deepcopy(value),tasks=list(TASKS),media=False,
                     quota='UNKNOWN',cost='Provider subscription or API allowance; not advertising spend')
            for key,value in REGISTRY.items()}
