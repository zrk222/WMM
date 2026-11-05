"""Owner-confirmed standing local authority; incomplete workflow effects stay blocked."""
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager
from contextvars import ContextVar
import json
import re
import secrets

from .common import Invalid, canonical, digest, iso_time, required, uid
from .db import connection
from .automation_requirements import inventory_in_db, selection
from .agent_grants import current, issue_in_db
from .operation_catalog import exact_keys, OPERATIONS, path_segment
from .review_access import member
from .store import audit

MAX_CALLS = 10000
MAX_INFLIGHT = 8
MAX_HOURS = 24
SPEND_LIMIT_MINOR = 0
ACCESS_VERIFIER = ContextVar('wmm_automation_access_verifier', default=None)
ACCESS_VERIFYING = ContextVar('wmm_automation_access_verifying', default=False)
ACCESS_STORE = ContextVar('wmm_automation_access_store', default=None)


@contextmanager
def bound_access_verifier(verifier, store):
    """Trusted host-only override, scoped to the synchronous call and its commits."""
    if not callable(verifier):
        raise TypeError('A trusted automation access verifier is required')
    token = ACCESS_VERIFIER.set(verifier)
    store_token = ACCESS_STORE.set(store)
    try:
        yield
    finally:
        ACCESS_STORE.reset(store_token)
        ACCESS_VERIFIER.reset(token)


def utc():
    """Use actual time unless the isolated execution test supplies its own clock."""
    return datetime.now(timezone.utc)


def proposal_data(body, observed):
    """Validate finite owner choices; purpose text cannot widen fixed operation scope."""
    exact_keys(body, ('selection', 'limits', 'purpose'), ('extended_expiry_consent',))
    chosen = selection(body['selection'])
    limits = body['limits']
    exact_keys(limits, ('expires', 'max_calls', 'max_inflight', 'currency', 'spend_limit_minor'))
    integer_limit(limits['max_calls'], MAX_CALLS)
    integer_limit(limits['max_inflight'], MAX_INFLIGHT)
    if type(limits['spend_limit_minor']) is not int or limits['spend_limit_minor'] != SPEND_LIMIT_MINOR:
        raise Invalid('Paid effects require implemented pricing and budget enforcement; this scope has zero spend')
    if not isinstance(limits['currency'], str) or not re.fullmatch(r'[A-Z]{3}', limits['currency']):
        raise Invalid('Use an explicit three-letter spend currency')
    if 'extended_expiry_consent' in body and type(body['extended_expiry_consent']) is not bool:
        raise Invalid('Expiry consent must be an explicit boolean')
    from .authority_expiry import deadline
    expiry = deadline(limits['expires'], observed, body.get('extended_expiry_consent'))
    result = dict(selection=chosen, purpose=required(body['purpose'], 'Automation purpose', 500),
                  limits=dict(limits, expires=expiry.isoformat()))
    if 'extended_expiry_consent' in body:
        result['extended_expiry_consent'] = body['extended_expiry_consent']
    return result


def integer_limit(value, maximum):
    """Reject booleans and unbounded resource allowances before any side effect."""
    if type(value) is not int or not 1 <= value <= maximum:
        raise Invalid('Choose a resource allowance within its documented bounds')


def scope_summary(db, app_id, user, proposal, observed):
    """Build the same immutable owner summary for preview, activation and validation."""
    inventory = inventory_in_db(db, app_id, user, proposal['selection'], observed)
    operations = sorted({name for row in inventory['workflows'] for name in row['operations']})
    deadline = proposal['limits']['expires']
    fresh = inventory['inference'].get('fresh_until')
    if fresh and iso_time(fresh) < iso_time(deadline):
        deadline = fresh
    result = dict(schema='wmm.standing-scope.v1', inventory=inventory,
                purpose=proposal['purpose'], limits=proposal['limits'], stops_at=deadline,
                operations=operations, effects=[dict(operation=name, effect=OPERATIONS[name]['effect']) for name in operations],
                external_effects='NONE_IN_CURRENT_EXECUTABLE_SCOPE',
                content='Typed local evidence and preparation only; existing proof validators still apply.',
                stop_rules=['OFF or revoked owner/grant', 'App, policy or credential revision changed',
                            'Expiry, stale verification or resource allowance exhausted',
                            'Unimplemented, outside-scope or uncertain effect'],
                revocation='OFF blocks new admissions and cancels undispatched owned jobs; committed effects remain recorded.')
    if proposal.get('extended_expiry_consent') is True:
        result['verification_binding'] = stable_connection_binding(db,app_id,proposal['selection']['agent_connection_id'])
        result['permission_expires_at'] = proposal['limits']['expires']
        result['verification_due_at'] = fresh
    return result


def stable_connection_binding(db,app_id,identity):
    """Bind configuration and credential references, excluding only test timestamps."""
    row = db.execute('SELECT app_id,id,version,data,created FROM agent_connections WHERE app_id=? AND id=?',(app_id,identity)).fetchone()
    return digest(dict(row)) if row else None


def _normalize_readiness(saved, current):
    current['inventory']['inference']['status'] = saved['inventory']['inference']['status']
    current['inventory']['scope_status'] = saved['inventory']['scope_status']
    for prior, present in zip(saved['inventory']['workflows'], current['inventory']['workflows']):
        present['status'] = prior['status']
        present['blockers'] = [item for item in present['blockers'] if item not in
                               ('FRESH_INFERENCE_TEST_REQUIRED','FRESH_DESTINATION_ACCOUNT_REQUIRED')]
    for prior, present in zip(saved['inventory']['accounts'], current['inventory']['accounts']):
        present['status'] = prior['status']


def same_scope_after_verification(saved, actual, ignore_readiness=False, allow_legacy_refresh=False):
    """Permit only a new health timestamp for the same immutable connection facts."""
    if 'verification_binding' not in saved and not ignore_readiness and not allow_legacy_refresh:
        return digest(actual) == digest(saved)
    import copy
    current = copy.deepcopy(actual)
    for key in ('stops_at','verification_due_at'):
        if key in saved:current[key] = saved[key]
    old = saved['inventory']['inference']
    new = current['inventory']['inference']
    keys = ('last_successful_test','fresh_until','binding_sha256') if ('verification_binding' in saved or allow_legacy_refresh) else ()
    for key in keys:
        new[key] = old[key]
    if ignore_readiness:
        _normalize_readiness(saved,current)
    return digest(current) == digest(saved)


def verify_access(store, app_id, identity):
    """Check protected access and official signed-in tool identity without inference."""
    verifier = ACCESS_VERIFIER.get()
    if verifier is not None:
        token = ACCESS_VERIFYING.set(True)
        try:
            return verifier(store, app_id, identity)
        finally:
            ACCESS_VERIFYING.reset(token)
    from .agent_access import AgentAccess
    from .agent_registry import KEYED, NATIVE
    from .agent_native import identity as native_identity
    access = AgentAccess(store)
    row = access.get(app_id, identity)
    provider = row['data']['provider']
    if provider == 'kimi':
        raise Invalid('This native adapter has not passed execution isolation verification')
    if provider in KEYED:
        key = access.secret(app_id, row)
        if provider != 'local_api' and not key:
            raise Invalid('Reconnect the protected key before activation')
    if provider in NATIVE:
        found = native_identity(provider)
        if found['fingerprint'] != row['data'].get('tool', {}).get('fingerprint'):
            raise Invalid('Installed tool identity changed; test and approve this profile again')
        if provider in ('codex', 'claude') and found['login_state'] != 'SIGNED_IN':
            raise Invalid('Complete official tool sign-in before activation')


def _check_scope_readiness(db,row,summary,proposal,observed):
    actual = scope_summary(db,row['app_id'],dict(principal=row['owner']),proposal,observed)
    from .authority_expiry import legacy_verification_bound
    allow_refresh = legacy_verification_bound(db,row,proposal) if 'verification_binding' not in summary else False
    if not same_scope_after_verification(summary,actual,allow_legacy_refresh=allow_refresh) or actual['inventory']['scope_status'] != 'READY_FOR_SCOPE_REVIEW':
        raise PermissionError('Standing approval facts changed; review the current scope')


def checked_policy(db, policy_id, observed):
    """Revalidate saved scope and grant within the current business transaction."""
    row = db.execute('SELECT * FROM automation_policies WHERE id=?', (policy_id,)).fetchone()
    if row is None or row['status'] != 'ACTIVE':
        raise PermissionError('Standing approval is OFF or unavailable')
    summary = stored_object(row['summary'])
    if digest(summary) != row['summary_hash']:
        raise PermissionError('Standing approval summary integrity changed')
    proposal = stored_object(row['proposal'])
    from .authority_expiry import effective_expiry, initial_base
    base = initial_base(proposal['limits']['expires'], row['created'], proposal.get('extended_expiry_consent'))
    if iso_time(effective_expiry(db, 'AUTOMATION', row, base)['expires']) <= observed:
        raise PermissionError('Standing approval expired; review a fresh scope')
    _check_scope_readiness(db,row,summary,proposal,observed)
    grant = db.execute('SELECT * FROM agent_grants WHERE id=?', (row['grant_id'],)).fetchone()
    if grant is None:
        raise PermissionError('Standing agent grant is unavailable')
    current(db, grant, dict(app_id=row['app_id'], operation=summary['operations'][0]), observed, check_quota=False)
    # The trusted native verifier is also checked at protected business commit.
    # Its scoped reads re-enter this guard and must not recursively verify again.
    if ACCESS_VERIFIER.get() is not None and not ACCESS_VERIFYING.get():
        verify_access_from_policy = summary['inventory']['selection']['agent_connection_id']
        verify_access(ACCESS_STORE.get(), row['app_id'], verify_access_from_policy)
    return dict(row), summary


def stored_object(raw):
    """Corrupt local policy data becomes a repair state, never authority or raw output."""
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        raise Invalid('Standing approval data needs repair') from None
    if not isinstance(value, dict):
        raise Invalid('Standing approval data needs repair')
    return value


def inflight(db, policy_id):
    """Count an execution and its pending job once, preserving inspection/cancel access."""
    rows = db.execute("""SELECT id,operation FROM automation_executions WHERE policy_id=? AND status IN ('ADMITTED','DISPATCHED')
        UNION SELECT e.id,e.operation FROM automation_executions e JOIN automation_job_scopes s ON s.execution_id=e.id
        JOIN jobs j ON j.id=s.job_id WHERE e.policy_id=? AND j.status IN ('QUEUED','RUNNING')
        UNION SELECT e.id,e.operation FROM automation_executions e JOIN ios_agent_media_standing s ON s.execution_id=e.id
        JOIN ios_studio_jobs j ON j.app_id=s.app_id AND j.id=s.job_id WHERE e.policy_id=? AND s.kind='scene' AND j.status='PREPARED'
        UNION SELECT e.id,e.operation FROM automation_executions e JOIN ios_agent_media_standing s ON s.execution_id=e.id
        JOIN ios_agent_timeline_jobs j ON j.app_id=s.app_id AND j.id=s.job_id WHERE e.policy_id=? AND s.kind='timeline' AND j.status='PREPARED'""",
                      (policy_id, policy_id, policy_id, policy_id)).fetchall()
    return sum(not control_effect(OPERATIONS[row['operation']]['effect']) for row in rows)


def control_effect(effect):
    """Inspection and local cancellation do not occupy a work concurrency slot."""
    return effect.startswith('READ_') or effect == 'CANCEL_LOCAL_JOB'


def reserve(db, store, grant, envelope, observed):
    """Reserve linked policy work in the existing atomic grant-admission transaction."""
    row = db.execute('SELECT id FROM automation_policies WHERE grant_id=?', (grant['id'],)).fetchone()
    if row is None:
        return None
    policy, summary = checked_policy(db, row['id'], observed)
    name = envelope['operation']
    if name not in summary['operations']:
        raise PermissionError('Operation is outside this standing approval')
    effect = OPERATIONS[name]['effect']
    blocked = db.execute("SELECT 1 FROM automation_executions WHERE policy_id=? AND input_hash=? AND status IN ('UNKNOWN','CANCEL_REQUESTED')", (policy['id'], digest(envelope))).fetchone()
    if blocked:
        raise PermissionError('Prior execution needs inspection; repeating uncertain work is blocked')
    control = control_effect(effect)
    if effect == 'QUEUE_LOCAL_PREPARATION':
        control = bool(db.execute('SELECT 1 FROM automation_executions e JOIN automation_job_scopes s ON s.execution_id=e.id WHERE e.policy_id=? AND e.input_hash=?', (policy['id'], digest(envelope))).fetchone())
    if not control and inflight(db, policy['id']) >= summary['limits']['max_inflight']:
        raise PermissionError('Standing work allowance is occupied; inspect or cancel owned work')
    verify_access(store, policy['app_id'], summary['inventory']['selection']['agent_connection_id'])
    identity = uid()
    db.execute('INSERT INTO automation_executions(id,policy_id,policy_version,grant_id,operation,input_hash,status,created,updated) VALUES(?,?,?,?,?,?,?,?,?)',
               (identity, policy['id'], policy['version'], grant['id'], name, digest(envelope), 'ADMITTED', observed.isoformat(), observed.isoformat()))
    from .automation_execution import capture_deadline
    capture_deadline(db,identity,policy,grant)
    audit(db, policy['app_id'], 'automation.admitted', dict(policy_id=policy['id'], execution_id=identity, operation=name))
    return identity


class Automation:
    """Fresh-owner controls and public receipts, separate from agent operation tools."""

    def __init__(self, store, clock=None):
        self.store = store
        self.clock = clock or utc

    def preview(self, app_id, user, body):
        """Present a current exact summary without opening protected access or issuing authority."""
        path_segment(app_id)
        proposal = proposal_data(body, self.clock())
        with connection(self.store.path) as db:
            db.execute('BEGIN')
            summary = scope_summary(db, app_id, user, proposal, self.clock())
        return dict(proposal=proposal, summary=summary, summary_hash=digest(summary), authority_issued=False)

    def activate(self, app_id, user, body):
        """Confirm exact owner intent and atomically attach its one-time scoped credential."""
        exact_keys(body, ('proposal', 'summary_hash'))
        observed = self.clock()
        proposal = proposal_data(body['proposal'], observed)
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE')
            observed = self.clock()
            proposal = proposal_data(body['proposal'], observed)
            summary = scope_summary(db, app_id, user, proposal, observed)
            if body['summary_hash'] != digest(summary):
                raise Invalid('Scope summary changed; review and confirm the current summary')
            if summary['inventory']['scope_status'] != 'READY_FOR_SCOPE_REVIEW':
                raise Invalid('Every selected workflow and credential must be ready before activation')
            if db.execute("SELECT 1 FROM automation_policies WHERE app_id=? AND status='ACTIVE'", (app_id,)).fetchone():
                raise Invalid('Switch the existing standing approval OFF before replacing its scope')
            verify_access(self.store, app_id, proposal['selection']['agent_connection_id'])
            grant_body = dict(agent_id=proposal['selection']['agent_id'], manifest_version=proposal['selection']['manifest_version'],
                              operations=summary['operations'], max_calls=proposal['limits']['max_calls'],
                              expires=proposal['limits']['expires'] if proposal.get('extended_expiry_consent') is True else summary['stops_at'])
            if 'extended_expiry_consent' in proposal:
                grant_body['extended_expiry_consent'] = proposal['extended_expiry_consent']
            issued = issue_in_db(db, app_id, user, grant_body, observed, 'wmmg_' + secrets.token_urlsafe(32))
            identity = uid()
            db.execute('INSERT INTO automation_policies VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                       (identity, app_id, issued['grant']['id'], user['principal'], 1, 'ACTIVE', canonical(proposal), canonical(summary), digest(summary), observed.isoformat(), observed.isoformat()))
            from .authority_expiry import initial_base, record_initial
            saved = db.execute('SELECT * FROM automation_policies WHERE id=?', (identity,)).fetchone()
            base = initial_base(proposal['limits']['expires'], saved['created'], proposal.get('extended_expiry_consent'))
            record_initial(db, 'AUTOMATION', saved, base, proposal['limits']['expires'], user['principal'],
                           issued['grant']['owner_version'], proposal, observed)
            audit(db, app_id, 'automation.owner_confirmed', dict(policy_id=identity, summary_hash=digest(summary), owner=user['principal']))
            # Native protected storage can lock after the initial read. Recheck
            # within the writer transaction before the protected commit guard.
            if ACCESS_VERIFIER.get() is not None:
                verify_access(self.store, app_id, proposal['selection']['agent_connection_id'])
        return dict(policy_id=identity, version=1, status='ACTIVE', summary=summary, **issued)

    def off(self, app_id, user, body):
        """Revoke future authority and undispatched work in the same writer transaction."""
        exact_keys(body, ('id', 'version'))
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE')
            member(db, app_id, user['principal'], 'OWNER')
            row = db.execute('SELECT * FROM automation_policies WHERE id=? AND app_id=?', (body['id'], app_id)).fetchone()
            if row is None or type(body['version']) is not int or row['version'] != body['version']:
                raise Invalid('Standing approval revision changed; reload before switching OFF')
            stamp = self.clock().isoformat()
            db.execute("UPDATE automation_policies SET status='OFF',version=version+1,updated=? WHERE id=?", (stamp, row['id']))
            db.execute("UPDATE agent_grants SET status='REVOKED',version=version+1,updated=? WHERE id=?", (stamp, row['grant_id']))
            cancelled = cancel_work(db, row['id'], stamp)
            audit(db, app_id, 'automation.owner_revoked', dict(policy_id=row['id'], owner=user['principal']))
        return dict(id=row['id'], version=row['version'] + 1, status='OFF', **cancelled)

    def status(self, app_id, user):
        """Read exact local policy and execution receipts without returning a bearer token."""
        with connection(self.store.path) as db:
            db.execute('BEGIN')
            member(db, app_id, user['principal'], 'OWNER')
            rows = db.execute('SELECT * FROM automation_policies WHERE app_id=? ORDER BY created,id', (app_id,)).fetchall()
            from .automation_requirements import workflow_catalog
            return dict(policies=[policy_view(db, row, self.clock()) for row in rows], catalog=workflow_catalog())


def cancel_work(db, policy_id, stamp):
    """Cancel only jobs attached to this policy; already-dispatched effects keep receipts."""
    jobs = [row[0] for row in db.execute('SELECT s.job_id FROM automation_job_scopes s JOIN automation_executions e ON e.id=s.execution_id WHERE e.policy_id=?', (policy_id,))]
    count = 0
    for identity in jobs:
        count += db.execute("UPDATE jobs SET status='CANCELLED',updated=? WHERE id=? AND status IN ('QUEUED','RUNNING')", (stamp, identity)).rowcount
    for kind,table in (('scene','ios_studio_jobs'),('timeline','ios_agent_timeline_jobs')):
        owned=db.execute('SELECT s.app_id,s.job_id FROM ios_agent_media_standing s JOIN automation_executions e ON e.id=s.execution_id WHERE e.policy_id=? AND s.kind=?',(policy_id,kind)).fetchall()
        for row in owned:
            count+=db.execute(f"UPDATE {table} SET status='CANCELLED',updated=? WHERE app_id=? AND id=? AND status='PREPARED'",(stamp,row['app_id'],row['job_id'])).rowcount
    db.execute("UPDATE automation_executions SET status=CASE WHEN status='ADMITTED' THEN 'CANCELLED' ELSE 'CANCEL_REQUESTED' END,updated=? WHERE policy_id=? AND status IN ('ADMITTED','DISPATCHED')", (stamp, policy_id))
    return dict(owned_jobs_stopped=count, dispatched_effects='INSPECT_RECEIPTS_NOT_UNDONE')


def policy_view(db, row, observed):
    """Distinguish saved approval from current runnable scope using only public facts."""
    from .authority_expiry import effective_expiry, initial_base
    effective = row['status']
    repair = None
    summary = None
    permission_expires_at = None
    verification_due_at = None
    consent_revision = None
    try:
        candidate = stored_object(row['summary'])
        if digest(candidate) != row['summary_hash']:
            raise Invalid('Standing approval summary integrity changed')
        summary = candidate
        proposal = stored_object(row['proposal'])
        base = initial_base(proposal['limits']['expires'],row['created'],proposal.get('extended_expiry_consent'))
        proof = effective_expiry(db,'AUTOMATION',row,base)
        permission_expires_at,consent_revision = proof['expires'],proof['revision']
        current_summary = scope_summary(db,row['app_id'],dict(principal=row['owner']),proposal,observed)
        verification_due_at = current_summary['inventory']['inference'].get('fresh_until')
        if effective == 'ACTIVE':
            checked_policy(db, row['id'], observed)
    except (Invalid, PermissionError, KeyError):
        effective, repair = 'BLOCKED', 'Review current owner, app, credential and expiry facts before reapproval.'
    executions = [dict(item) for item in db.execute('SELECT id,operation,input_hash,status,write_commits,result_hash,created,updated FROM automation_executions WHERE policy_id=? ORDER BY created,id', (row['id'],))]
    for execution in executions:
        execution['jobs'] = [dict(job) for job in db.execute('SELECT j.id,j.action,j.status,j.created,j.updated FROM jobs j JOIN automation_job_scopes s ON s.job_id=j.id WHERE s.execution_id=?', (execution['id'],))]
    grant = db.execute('SELECT * FROM agent_grants WHERE id=?', (row['grant_id'],)).fetchone()
    usage = None
    if grant:
        usage = {key:grant[key] for key in ('used','max_calls','expires','status')}
        try:usage['expires'] = effective_expiry(db,'AGENT_GRANT',grant,grant['expires'])['expires']
        except PermissionError:usage['expires'] = None
    return dict(id=row['id'], version=row['version'], status=row['status'], effective_status=effective,
                grant_id=row['grant_id'], usage=usage, summary=summary, repair=repair, executions=executions,
                permission_expires_at=permission_expires_at,verification_due_at=verification_due_at,consent_revision=consent_revision)
