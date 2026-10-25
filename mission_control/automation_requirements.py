"""Owner-only workflow and credential inventory; saved facts confer no authority."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json

from .common import Invalid, digest, iso_time
from .db import connection
from .operation_catalog import OPERATIONS, exact_keys, path_segment
from .agent_registry import REGISTRY, TASKS
from .agent_contract import model_id
from .review_access import member
from .social_contract import reference, account_id, provider_id, reported_scopes

MAX_WORKFLOWS = 11
MAX_ACCOUNTS = 20
FRESH_HOURS = 24

WORKFLOWS = {
    'local_evidence': dict(name='Local evidence and measurement', operations=[
        'workspace.read', 'evidence.save', 'operations.read', 'growth.read',
        'growth.history', 'growth.save', 'customer.history', 'customer.save',
        'measurement.read', 'snapshot.export', 'cohort.define', 'events.import',
        'billing.save'], blockers=[]),
    'experiment_preparation': dict(name='Local experiment preparation', operations=[
        'experiment.register', 'experiment.evaluate', 'experiment.action'], blockers=[]),
    'pipeline_preparation': dict(name='Local pipeline preparation', operations=[
        'pipeline.prepare', 'jobs.read', 'job.cancel'], blockers=[]),
    'hypit_caption_render': dict(name='Local Hypit caption composition', operations=[
        'hypit.read', 'hypit.queue', 'jobs.read', 'job.cancel'],
        blockers=['LOCAL_MEDIA_RUNTIME_VERIFICATION_REQUIRED']),
    'native_screen_render': dict(name='Local app-screen video', operations=[
        'native.read', 'native.queue', 'jobs.read', 'job.cancel'], blockers=[]),
    'viral_discovery': dict(name='Viral-only source discovery', operations=[],
        blockers=['LIVE_VIRAL_COLLECTOR_REQUIRED']),
    'video_authoring_editing': dict(name='Video authoring and editing', operations=[
        'media.sources', 'editor.list', 'editor.read', 'editor.save', 'editor.edit', 'editor.history', 'editor.diff', 'editor.renders', 'editor.queue',
        'studio.plan', 'studio.start', 'studio.sessions', 'studio.read', 'studio.edit', 'studio.inspect', 'studio.close'],
        blockers=['COMPLETE_AGENT_AND_HUMAN_EDITOR_REQUIRED']),
    'complete_analytics': dict(name='Complete KPI analytics and reports', operations=[],
        blockers=['COMPLETE_KPI_OPERATION_COVERAGE_REQUIRED']),
    'social_publish': dict(name='Publish to selected social accounts', operations=[],
        blockers=['PUBLICATION_ADAPTER_REQUIRED']),
    'release_delivery': dict(name='Build and deployment delivery', operations=[],
        blockers=['RELEASE_EFFECT_OPERATION_COVERAGE_REQUIRED']),
    'paid_effects': dict(name='Paid provider effects', operations=[],
        blockers=['PRICING_AND_ATOMIC_BUDGET_ENFORCEMENT_REQUIRED']),
}


def workflow_catalog():
    """Reject operation drift instead of silently widening an automation policy."""
    mapped = {name for row in WORKFLOWS.values() for name in row['operations']}
    if mapped != set(OPERATIONS):
        raise Invalid('Automation workflow map changed; review every fixed operation')
    value = dict(workflows=deepcopy(WORKFLOWS), operations=deepcopy(OPERATIONS))
    return dict(value, sha256=digest(value))


def selection(body):
    """Close the owner-selected scope without accepting grants, tokens or endpoints."""
    exact_keys(body, ('agent_id', 'manifest_version', 'workflows',
                      'agent_connection_id', 'social_connection_ids'))
    path_segment(body['agent_id'])
    selected = distinct(body['workflows'], 1, MAX_WORKFLOWS)
    if any(name not in WORKFLOWS for name in selected):
        raise Invalid('Choose only explicit automation workflows')
    if type(body['manifest_version']) is not int or body['manifest_version'] < 1:
        raise Invalid('Use the current app manifest version')
    if body['agent_connection_id'] is not None:
        reference(body['agent_connection_id'])
    for identity in distinct(body['social_connection_ids'], 0, MAX_ACCOUNTS):
        reference(identity)
    return deepcopy(body)


def distinct(values, minimum, maximum):
    """Bound list cardinality and reject malformed or duplicate selected identities."""
    if not isinstance(values, list) or not minimum <= len(values) <= maximum:
        raise Invalid('Use the documented selection counts')
    if any(not isinstance(value, str) for value in values) or len(set(values)) != len(values):
        raise Invalid('Selected identities must be unique strings')
    return values


def decoded(row):
    """Reject malformed stored configuration without reflecting its contents."""
    try:
        data = json.loads(row['data'])
    except (ValueError, TypeError):
        raise Invalid('Saved connection configuration needs repair') from None
    if not isinstance(data, dict):
        raise Invalid('Saved connection configuration needs repair')
    return data


def verification(stamp, observed):
    """A future timestamp or missing test can never establish fresh verification."""
    if not stamp:
        return 'NOT_VERIFIED'
    try:
        age = observed - iso_time(stamp)
    except Invalid:
        return 'INVALID_VERIFICATION'
    if age < timedelta(0):
        return 'INVALID_VERIFICATION'
    return 'TESTED_FRESH' if age <= timedelta(hours=FRESH_HOURS) else 'STALE'


def inference_profile(db, app_id, identity, observed):
    """Project only saved public inference facts; never open the protected vault."""
    if identity is None:
        return dict(id=None, status='MISSING', repair='Onboard and test the selected inference connection.')
    row = db.execute('SELECT * FROM agent_connections WHERE app_id=? AND id=?', (app_id, identity)).fetchone()
    if row is None:
        raise Invalid('Inference connection does not belong to the selected app')
    data = decoded(row)
    provider = data.get('provider')
    if not isinstance(provider, str) or provider not in REGISTRY:
        raise Invalid('Saved inference provider needs repair')
    tasks = data.get('capabilities', [])
    if not isinstance(tasks, list) or any(not isinstance(task, str) for task in tasks):
        raise Invalid('Saved inference tasks need repair')
    status = verification(row['last_test'], observed) if row['status'] == 'TESTED' else row['status']
    return dict(id=identity, version=row['version'], provider=provider,
                mode=REGISTRY[provider]['mode'], model=model_id(data.get('model')),
                tasks=[task for task in TASKS if task in tasks],
                status=status, last_successful_test=row['last_test'],
                fresh_until=fresh_until(row['last_test']), binding_sha256=digest(dict(row)),
                account_identity='NOT_INDEPENDENTLY_VERIFIED', quota='UNKNOWN',
                protected_access='REVALIDATE_AT_ACTIVATION_AND_DISPATCH',
                repair='Test this exact profile; verify protected access, tool identity and resource policy before activation.')


def fresh_until(stamp):
    """Return a test's declared freshness deadline without treating it as token expiry."""
    if not stamp:
        return None
    try:
        return (iso_time(stamp) + timedelta(hours=FRESH_HOURS)).isoformat()
    except Invalid:
        return None


def social_state(row, data, config, observed):
    """Read-tested OAuth is neither permanent account access nor publish authority."""
    if row['status'] != 'CONNECTED_READ_TESTED':
        return row['status']
    if not config or config['version'] != row['config_version'] or config['status'] == 'DISCONNECTED':
        return 'PROVIDER_SETUP_CHANGED'
    if row['lease']:
        return 'RENEWING'
    if row['expires'] is None:
        return 'EXPIRY_UNKNOWN'
    if row['expires'] <= observed.timestamp():
        return 'EXPIRED'
    if data.get('facts', {}).get('reported_scopes') is None:
        return 'SCOPES_UNKNOWN'
    return verification(data.get('last_read_at'), observed)


def social_account(db, app_id, identity, observed):
    """Return selected subject/destination facts without token references or leases."""
    row = db.execute('SELECT * FROM social_connections WHERE app_id=? AND id=?', (app_id, identity)).fetchone()
    if row is None:
        raise Invalid('Social connection does not belong to the selected app')
    data = decoded(row)
    provider_id(row['provider'])
    facts = object_field(data, 'facts')
    destination = object_field(data, 'destination')
    scopes = facts.get('reported_scopes')
    if scopes is not None:
        scopes = reported_scopes(scopes)
    config = db.execute('SELECT version,status FROM social_configs WHERE app_id=? AND provider=?', (app_id, row['provider'])).fetchone()
    return dict(id=identity, version=row['version'], provider=row['provider'],
                config_version=row['config_version'], subject_id=account_id(row['subject_id']),
                destination_id=account_id(destination.get('id')),
                reported_scopes=scopes,
                status=social_state(row, data, config, observed),
                last_successful_read=data.get('last_read_at'),
                expires_at=row['expires'], refresh_expires_at=row['refresh_expires'],
                renewal=renewal_state(facts.get('renewal')),
                binding_sha256=digest(dict(connection=dict(row), config=dict(config) if config else None)),
                publishing_implemented=False,
                protected_access='REVALIDATE_AT_ACTIVATION_AND_DISPATCH',
                repair='Verify the exact account, destination and required read/publish scopes through official onboarding.')


def object_field(data, name):
    """Reject nested credential-looking objects in public account projection fields."""
    value = data.get(name)
    if not isinstance(value, dict):
        raise Invalid('Saved account facts need repair')
    return value


def renewal_state(value):
    """Return only closed public renewal states rather than arbitrary stored objects."""
    allowed = ('LONG_TOKEN_EXCHANGE_REQUIRED', 'LONG_LIVED_TOKEN_REFRESH',
               'REFRESH_TOKEN', 'OFFICIAL_REAUTHORIZATION')
    return value if isinstance(value, str) and value in allowed else 'UNKNOWN'


def workflow_states(selected, inference, accounts):
    """Keep incomplete selected workflows visible rather than dropping their effects."""
    result = []
    for identity in selected:
        row = deepcopy(WORKFLOWS[identity])
        if identity == 'native_screen_render':
            from .native_runtime_identity import identity as native_identity
            row['runtime'] = native_identity()
            if row['runtime']['status'] != 'READY':
                row['blockers'].append('NATIVE_RUNTIME_SETUP_REQUIRED')
        if inference['status'] != 'TESTED_FRESH':
            row['blockers'].append('FRESH_INFERENCE_TEST_REQUIRED')
        if identity == 'social_publish' and not any(account['status'] == 'TESTED_FRESH' for account in accounts):
            row['blockers'].append('FRESH_DESTINATION_ACCOUNT_REQUIRED')
        row.update(id=identity, status='BLOCKED' if row['blockers'] else 'READY_FOR_SCOPE_REVIEW')
        result.append(row)
    return result


class Readiness:
    """Inspect one owner-selected scope in a consistent read snapshot, issuing no grant."""

    def __init__(self, store, clock=None):
        self.store = store
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def report(self, app_id, user, body):
        """Bind exact current app, role, workflow and selected credential revisions."""
        path_segment(app_id)
        chosen = selection(body)
        observed = self.clock()
        with connection(self.store.path) as db:
            db.execute('BEGIN')
            inventory = inventory_in_db(db, app_id, user, chosen, observed)
        return dict(inventory=inventory, inventory_sha256=digest(inventory), observed_at=observed.isoformat())


def inventory_in_db(db, app_id, user, chosen, observed):
    """Reuse the exact inventory snapshot inside owner and dispatch transactions."""
    catalog = workflow_catalog()
    owner = member(db, app_id, user['principal'], 'OWNER')
    app = db.execute('SELECT * FROM apps WHERE id=?', (app_id,)).fetchone()
    if app['version'] != chosen['manifest_version']:
        raise Invalid('App manifest changed; review the current scope')
    profile = inference_profile(db, app_id, chosen['agent_connection_id'], observed)
    accounts = [social_account(db, app_id, identity, observed) for identity in chosen['social_connection_ids']]
    workflows = workflow_states(chosen['workflows'], profile, accounts)
    return dict(schema='wmm.automation-readiness.v1', selection=chosen,
                app=dict(id=app_id, version=app['version'], hash=digest(decoded(app))),
                owner=dict(principal=owner['principal'], role_version=owner['version']),
                catalog_sha256=catalog['sha256'], inference=profile, accounts=accounts,
                workflows=workflows, activation='NOT_PERFORMED', grants_issued=False,
                scope_status='BLOCKED' if any(row['blockers'] for row in workflows) else 'READY_FOR_SCOPE_REVIEW',
                required_next=['Owner-confirmed standing policy', 'Activation credential and capability validation',
                               'Atomic admission and revocation', 'Scoped resource reservation and worker interlock'])
