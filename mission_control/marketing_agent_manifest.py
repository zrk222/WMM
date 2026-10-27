"""Versioned operating contract; supported execution is explicitly narrower than goal scope."""
from .common import Invalid, digest

APPLE_READ_OPERATIONS = ('identity_inventory', 'reviews', 'subscription_catalog',
                         'release_inventory', 'analytics_reports', 'analytics_metrics')
PLAY_READ_OPERATIONS = ('play_releases','play_subscriptions')
READ_OPERATIONS = APPLE_READ_OPERATIONS + PLAY_READ_OPERATIONS
PROVIDER_READS = {'app_store':APPLE_READ_OPERATIONS,'apple_ads':('identity_inventory',),'google_play':PLAY_READ_OPERATIONS}


def operating_manifest(app):
    """Bind expert operating rules and implemented capabilities to exact app intent."""
    return {
        'schema':'growth.marketing-agent-manifest.v1', 'policy_version':9,
        'app_id':app['id'], 'manifest_version':app['version'],
        'release':app['data'].get('release'), 'locale':app['data'].get('locale'),
        'store_app_id':app['data'].get('store_app_id'),
        'android_package':app['data'].get('android_package'),'android_track':app['data'].get('android_track'),
        'promotion_release':app['data'].get('promotion_release') or {},
        'objective':app['data'].get('job') or None,
        'human_role':'APPROVE_OR_EDIT',
        'supported_execution':{'provider_reads':list(READ_OPERATIONS), 'max_reads_per_collection':12,
                               'provider_writes':[], 'spend_minor':0},
        'supported_resolution_tools':['collect_sources','inspect_site','refresh_analytics','evaluate_experiment','reuse_observation','inspect_tracking','discover_setup'],
        'resolution_approval_seconds':1800,
        'sequence_contract':{'approval':'EXACT_ORDERED_ACTIONS','resume':'SAVED_CHECKPOINT',
                             'completion':'EVIDENCE_REVIEW_REQUIRED','execution_mode':'LOCAL_SERVICE_REQUIRED',
                             'cancellation':'STOP_OWNED_WORK_RETAIN_SHARED_READS'},
        'source_rules':['App-owned configured bindings only', 'Exact release and locale; no cross-app borrowing',
                        'Retain source hashes, versions, timestamps and coverage',
                        'Unknown evidence remains unknown; never invent rights, costs, metrics or success'],
        'workflow':['source','propose','approve_or_edit','execute_supported_actions','read_back','evaluate','learn'],
        'resolution_contract':['Every unverified item has agent-owned resolution options',
                               'Explain action, access, cost, expected artifact, verification and fallback',
                               'Approval binds exact current source; edits invalidate it',
                               'Unsupported actions remain implementation work, never simulated execution'],
        'ab_contract':['Preregister primary metric, arms, unit, allocation, sample and maturity',
                       'Verify sticky assignment and deduplicated exposure before causal claims',
                       'Fixed-window analysis; no repeated significance peeking',
                       'Sample-ratio mismatch, contamination and missing outcomes prevent winner selection',
                       'Respect cost and quality guardrails; verified pause and rollback',
                       'Next experiment or rollout requires exact approval or an existing bounded grant'],
        'recovery':{'job_attempt_limit':3, 'lease_seconds':60, 'ambiguous_effect':'RECONCILE_BEFORE_RETRY',
                    'max_manual_source_retries':3,
                    'failed_or_cancelled_collection':'PRESERVE_NO_SILENT_REPLAY'},
        'persistence':{'safe_transient_read_attempts':3, 'read_backoff_seconds':[5,10],
                       'never_retry_automatically':['Permission denial','Identity or source mismatch','Malformed evidence','External mutations'],
                       'strategy':'Continue independent permitted sources; retain failures and propose alternatives until evidence is obtained or a real authority/resource limit requires approval'},
        'completion_rules':['Queued is not executed', 'Prepared is not published',
                            'Provider observation is not verified business lift',
                            'All required acceptance checks need current source-bound readback'],
        'unimplemented_execution':['Live campaign mutation adapters', 'Live A/B assignment and exposure',
                                   'Complete autonomous resolution of every pipeline stage']
    }


def authorize_read(app, binding, data):
    """Reject changed policies, scope drift or unsupported reads at execution/readback."""
    policy=operating_manifest(app)
    allowed={'connection_id','connection_version','manifest_version','agent_policy_sha256','options'}
    if set(data)-allowed or data.get('agent_policy_sha256') != digest(policy):
        raise Invalid('Agent operating manifest changed or request exceeds its action contract')
    if type(data.get('manifest_version')) is not int or data['manifest_version'] != app['version']:
        raise Invalid('Agent app manifest changed; prepare current source collection')
    authorize_source(policy,binding)
    authorize_operation(policy,binding,data)


def authorize_source(policy,binding):
    """Verify provider, revocation and exact promoted app identity."""
    provider=binding.get('provider')
    if provider=='google_play':
        from .play_contract import require_target
        require_target({'data':policy},binding)
        return
    if (provider not in ('app_store','apple_ads') or binding.get('auth_mode') == 'disconnected' or
        not policy['store_app_id'] or binding.get('store_app_id') != str(policy['store_app_id'])):
        raise Invalid('Agent source is not authorized for this app identity')


def authorize_operation(policy,binding,data):
    """Keep action permission separate from source identity and release intent."""
    provider=binding.get('provider')
    options=data.get('options')
    operation=options.get('operation') if isinstance(options,dict) else 'identity_inventory' if options is None else None
    allowed=PROVIDER_READS.get(provider,())
    if operation not in allowed:
        raise Invalid('Agent operating manifest does not permit this provider operation')
    if provider=='google_play' and (not isinstance(options,dict) or set(options)!={'operation'}):
        raise Invalid('Google Play collection accepts only the fixed read operation')
    if operation=='release_inventory':
        authorize_release(policy,data)


def authorize_release(policy,data):
    """Exact selected target is part of the execution policy fingerprint."""
    target=policy['promotion_release']
    if (target.get('version_id') != data['options'].get('version_id') or
        target.get('connection_id') != data['connection_id'] or
        target.get('connection_version') != data['connection_version'] or
        target.get('local_release') != policy['release'] or target.get('locale') != policy['locale']):
        raise Invalid('Agent release read no longer matches the selected promotion target')
