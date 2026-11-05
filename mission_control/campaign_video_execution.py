"""Durable Page Reel stages; no client/scheduler registration yet.

Unknown mutations hold their admission. Provider phase completion does not prove
public visibility, remote byte equality, installs or marketing effectiveness.
"""
import json
from .campaign_contract import reel_data, numeric
from .campaign_locks import paid_lock
from .campaign_transport import Unconfirmed
from .common import Invalid, canonical, digest, now, uid
from .db import connection
from .operation_authority import PROTECTED, check, store_identity
from .organic_video_policy import Policies, _saved, _page, child_deadline
from .review_access import member
from .social_connections import Connections
from .social_profiles import facebook, selected_page
from . import campaign_video_transport as provider


def _schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS campaign_video_intents(
        app_id TEXT NOT NULL REFERENCES apps(id), id TEXT PRIMARY KEY,
        request_id TEXT NOT NULL, admission_id TEXT NOT NULL UNIQUE,
        data TEXT NOT NULL, hash TEXT NOT NULL, stage TEXT NOT NULL,
        remote_id TEXT, calls INTEGER NOT NULL DEFAULT 0, observation TEXT,
        finish_attempted INTEGER NOT NULL DEFAULT 0,
        created TEXT NOT NULL, updated TEXT NOT NULL, UNIQUE(app_id,request_id))''')
    db.execute('''CREATE TABLE IF NOT EXISTS campaign_video_events(
        intent_id TEXT NOT NULL REFERENCES campaign_video_intents(id), sequence INTEGER NOT NULL,
        data TEXT NOT NULL, hash TEXT NOT NULL, PRIMARY KEY(intent_id,sequence))''')


def _authority(db, store, app_id, actor, operation, body):
    context = PROTECTED.get()
    if context is None:
        from .campaign_schedule_authority import video_context
        return video_context(db, store, app_id, actor, operation, body)
    if (not context or context.get('store') != store_identity(store)
            or context['envelope'] != canonical(dict(app_id=app_id, operation=operation, input=body))
            or check(db, context) != actor):
        raise PermissionError('Exact current Reel operation authority is required')
    return context


def _row(db, app_id, identity):
    row = db.execute('SELECT * FROM campaign_video_intents WHERE app_id=? AND id=?', (app_id, identity)).fetchone()
    if row is None or digest(json.loads(row['data'])) != row['hash']:
        raise Invalid('Reel intent is unavailable or changed')
    return row


def _event(db, row, stage, observation=None):
    sequence = db.execute('SELECT count(*) FROM campaign_video_events WHERE intent_id=?', (row['id'],)).fetchone()[0]
    value = dict(stage=stage, observed_at=now(), provider_observation=observation)
    db.execute('INSERT INTO campaign_video_events VALUES(?,?,?,?)', (row['id'], sequence, canonical(value), digest(value)))
    db.execute('UPDATE campaign_video_intents SET stage=?,observation=?,updated=? WHERE id=?',
               (stage, canonical(observation) if observation is not None else None, value['observed_at'], row['id']))


def _view(row):
    unresolved = row['stage'] in ('CREATE_PENDING', 'UPLOAD_PENDING', 'UPLOAD_UNRESOLVED', 'FINISH_PENDING', 'PUBLISH_UNRESOLVED')
    return dict(id=row['id'], app_id=row['app_id'], request=json.loads(row['data'])['request'],
                stage=row['stage'], remote_id=row['remote_id'], calls_used=row['calls'],
                recovery_required=unresolved, effect_state='UNKNOWN' if unresolved else 'RECORDED_STAGE',
                finish_attempted=bool(row['finish_attempted']),
                allowance_note='Conservative boundary-check units; permission reads can consume two units per request. Upload heartbeats do not consume additional units.',
                observation=json.loads(row['observation']) if row['observation'] else None,
                updated=row['updated'], public_visibility='NOT_VERIFIED', remote_bytes='NOT_VERIFIED',
                measured_app_outcome=None)


def _bound(db, store, app_id, row, context, *, recovery=False, historical=False, heartbeat=False):
    request = json.loads(row['data'])['request']
    policy_row = db.execute('SELECT * FROM organic_video_policies WHERE app_id=? AND id=?', (app_id, request['policy_id'])).fetchone()
    policy = _saved(policy_row) if recovery or historical else Policies(store)._current(db, policy_row, verify_bytes=not heartbeat)
    if policy['hash'] != request['policy_hash']:
        raise Invalid('Reel policy changed')
    owner = policy['data']['owner']
    if recovery:
        if 'grant_id' in context or context.get('principal') != owner:
            raise PermissionError('Only the current approving owner can reconcile retained Reel effects')
        member(db, app_id, owner, 'OWNER')
        if _page(db, app_id, policy['data']['policy']) != policy['data']['page']:
            raise PermissionError('Reel recovery connection changed')
    elif 'grant_id' in context:
        grant = db.execute('SELECT owner FROM agent_grants WHERE id=?', (context['grant_id'],)).fetchone()
        if grant is None or grant['owner'] != owner:
            raise PermissionError('Reel policy belongs to another owner')
    elif context.get('principal') != owner:
        raise PermissionError('Reel policy belongs to another owner')
    admission = _saved(db.execute('SELECT * FROM organic_video_admissions WHERE app_id=? AND id=?', (app_id, request['admission_id'])).fetchone())
    if (admission['hash'] != request['admission_hash'] or admission['data']['policy_id'] != policy['id']
            or admission['data']['policy_hash'] != policy['hash']):
        raise Invalid('Reel admission changed')
    check_admission_deadline(admission, policy, recovery=recovery, historical=historical)
    output = admission['data']['output']
    if (output['artifact_id'], output['artifact_sha256'], output['caption']) != (request['artifact_id'], request['artifact_sha256'], request['caption']):
        raise Invalid('Reel output differs from its admitted artifact or caption')
    rights = sorted({item['rights_hash'] for item in admission['data']['proofs']['sources']})
    if rights != request['rights_hashes'] or request['page_id'] != policy['data']['policy']['page_id']:
        raise Invalid('Reel Page or source rights changed')
    if not recovery and not historical:
        from .hypit_jobs import artifact_file, current_inputs, saved
        if heartbeat:
            artifact = saved(db.execute('SELECT * FROM hypit_renders WHERE app_id=? AND id=?', (app_id, output['artifact_id'])).fetchone())['data']
        else:
            _, artifact = artifact_file(store, app_id, output['artifact_id'])
        if digest(artifact) != admission['data']['artifact_record_hash']:
            raise Invalid('Admitted Reel artifact record changed')
        if not heartbeat:
            current_inputs(db, store, app_id, artifact['inputs'])
    return policy, admission


def check_admission_deadline(admission, policy, *, recovery=False, historical=False):
    """Expire further effects while preserving retained history and owner readback."""
    if not recovery and not historical:
        child_deadline(admission['data'], policy['data']['policy']['expires_at'])


def create_intent(store, app_id, actor, body) -> object:
    """Consume one exact admission once without contacting a provider."""
    request = reel_data(body)
    if request['app_id'] != app_id:
        raise Invalid('Reel request belongs to another app')
    with connection(store.path) as db:
        db.execute('BEGIN IMMEDIATE')
        context = _authority(db, store, app_id, actor, 'organic-video.intent-create', body)
        _schema(db)
        data = dict(request=request)
        prior = db.execute('SELECT * FROM campaign_video_intents WHERE app_id=? AND request_id=?', (app_id, request['request_id'])).fetchone()
        if prior and prior['hash'] != digest(data):
            raise Invalid('Reel retry identity was used for different content')
        _bound(db, store, app_id, dict(data=canonical(data)), context, historical=prior is not None)
        if prior:
            return _view(_row(db, app_id, prior['id']))
        if db.execute('SELECT 1 FROM campaign_video_intents WHERE admission_id=?', (request['admission_id'],)).fetchone():
            raise Invalid('This admission already has a retained Reel intent')
        identity = uid()
        stamp = now()
        db.execute('INSERT INTO campaign_video_intents VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                   (app_id, identity, request['request_id'], request['admission_id'], canonical(data), digest(data),
                    'NEW', None, 0, None, 0, stamp, stamp))
        row = _row(db, app_id, identity)
        _event(db, row, 'NEW')
        return _view(_row(db, app_id, identity))


def _guard(store, app_id, actor, identity, operation, *, recovery=False, charge=False, stage=None, heartbeat=False):
    with connection(store.path) as db:
        db.execute('BEGIN IMMEDIATE')
        context = _authority(db, store, app_id, actor, operation, dict(intent_id=identity))
        row = _row(db, app_id, identity)
        policy, admission = _bound(db, store, app_id, row, context, recovery=recovery, heartbeat=heartbeat)
        if charge:
            if row['calls'] >= admission['data']['provider_calls_reserved']:
                raise PermissionError('Reel provider-call reservation exhausted; retain and inspect this intent')
            db.execute('UPDATE campaign_video_intents SET calls=calls+1 WHERE id=?', (identity,))
        if stage is not None:
            _event(db, row, stage)
            if stage == 'FINISH_PENDING':
                if row['finish_attempted']:
                    raise Invalid('Reel finish was already attempted; reconcile its retained identity')
                db.execute('UPDATE campaign_video_intents SET finish_attempted=1 WHERE id=?', (identity,))
        return _view(_row(db, app_id, identity)), policy


def _credentials(store, app_id, policy):
    connections = Connections(store)
    selection = policy['data']['policy']
    row = connections.get(app_id, selection['connection_id'])
    connections.alive(row)
    cfg = connections.setup.get(app_id, 'facebook')
    client = connections.secrets.load(app_id, 'facebook', cfg['secret_ref'])
    grant = connections.secrets.load(app_id, 'facebook', row['secret_ref'])
    return cfg['data'], client['client_secret'], grant


def _permission_check(store, app_id, policy, config, secret, grant, alive, *, read_only=False):
    """Reuse provider inspection, conservatively charging its read boundaries."""
    found = facebook(config, secret, grant['access_token'], alive)
    saved = Connections(store).get(app_id, policy['data']['policy']['connection_id'])
    required = {'pages_show_list', 'pages_read_engagement'}
    if not read_only:
        required.add('pages_manage_posts')
    if found.subject_id != saved['subject_id'] or not required <= set(found.permissions or []):
        raise PermissionError('Current Page publishing permissions are required')
    page, token = selected_page(secret, grant['access_token'], policy['data']['policy']['page_id'], alive)
    if page['id'] != policy['data']['policy']['page_id'] or (not read_only and 'CREATE_CONTENT' not in page['tasks']):
        raise PermissionError('The selected Page does not grant content creation')
    return token


def _save(store, app_id, identity, stage, *, remote_id=None, observation=None):
    with connection(store.path) as db:
        db.execute('BEGIN IMMEDIATE')
        row = _row(db, app_id, identity)
        if remote_id is not None:
            numeric(remote_id)
            if row['remote_id'] is not None and row['remote_id'] != remote_id:
                raise Invalid('Retained Reel identity changed')
            db.execute('UPDATE campaign_video_intents SET remote_id=? WHERE id=?', (remote_id, identity))
        _event(db, row, stage, observation)
        return _view(_row(db, app_id, identity))


def _observed(value, remote_id):
    fields = {'video_id', 'video_status', 'uploading_phase', 'processing_phase', 'publishing_phase'}
    if not isinstance(value, dict) or set(value) != fields or value['video_id'] != remote_id:
        raise Unconfirmed('Exact Reel phase observation is unavailable')
    if value['video_status'] not in ('uploading', 'processing', 'ready', 'error'):
        raise Unconfirmed('Unsupported Reel phase observation')
    if any(value[key] not in (None, 'not_started', 'in_progress', 'complete', 'error') for key in fields - {'video_id', 'video_status'}):
        raise Unconfirmed('Unsupported Reel phase observation')
    return value


def _read(store, app_id, actor, identity, transport, context, operation, recovery=False):
    view, _ = _guard(store, app_id, actor, identity, operation, recovery=recovery, charge=True)
    observed = _observed(transport.read(view['remote_id'], context), view['remote_id'])
    if 'error' in observed.values():
        stage = 'PROVIDER_ERROR'
    elif observed['video_status'] == 'ready' and all(observed[key] == 'complete' for key in ('uploading_phase', 'processing_phase', 'publishing_phase')):
        stage = 'PROVIDER_PHASE_COMPLETE'
    elif view['finish_attempted']:
        stage = 'FINISH_ACKNOWLEDGED' if view['stage'] == 'FINISH_ACKNOWLEDGED' else 'PUBLISH_UNRESOLVED'
    elif observed['uploading_phase'] != 'complete':
        stage = 'UPLOAD_UNRESOLVED'
    elif observed['uploading_phase'] == 'complete' and observed['processing_phase'] == 'complete' and observed['video_status'] == 'ready':
        stage = 'READY_TO_FINISH'
    else:
        stage = 'PROCESSING'
    return _save(store, app_id, identity, stage, observation=observed)


def execute(store, app_id, actor, intent_id, transport) -> object:
    """Advance known stages once; uncertain mutations require read-only recovery."""
    operation = 'organic-video.intent-execute'
    transport = transport or provider
    with paid_lock(store, app_id, intent_id):
        view, policy = _guard(store, app_id, actor, intent_id, operation)
        if view['stage'] in ('CREATE_PENDING', 'UPLOAD_PENDING', 'UPLOAD_UNRESOLVED', 'FINISH_PENDING', 'PROVIDER_ERROR', 'PUBLISH_UNRESOLVED', 'PROVIDER_PHASE_COMPLETE'):
            return view
        config, secret, grant = _credentials(store, app_id, policy)
        charged = lambda: _guard(store, app_id, actor, intent_id, operation, charge=True)
        alive = lambda: _guard(store, app_id, actor, intent_id, operation, heartbeat=True)
        token = _permission_check(store, app_id, policy, config, secret, grant, charged)
        context = provider.Context(policy['data']['policy']['page_id'], token, secret, alive)
        if view['stage'] == 'NEW':
            _guard(store, app_id, actor, intent_id, operation, charge=True, stage='CREATE_PENDING')
            result = transport.create(view['request']['page_id'], {}, context)
            if not isinstance(result, dict) or result.get('state') != 'CREATED':
                raise Unconfirmed('Reel creation was not confirmed')
            view = _save(store, app_id, intent_id, 'CREATED', remote_id=numeric(result.get('video_id')))
        if view['stage'] == 'CREATED':
            from .hypit_jobs import artifact_file
            path, artifact = artifact_file(store, app_id, view['request']['artifact_id'])
            _guard(store, app_id, actor, intent_id, operation, charge=True, stage='UPLOAD_PENDING')
            result = transport.upload(view['remote_id'], dict(path=path, sha256=view['request']['artifact_sha256'],
                bytes=artifact['artifact']['bytes'], duration_seconds=artifact['inputs']['request']['duration_seconds']), context)
            if result != dict(video_id=view['remote_id'], state='UPLOAD_ACKNOWLEDGED'):
                raise Unconfirmed('Reel upload acknowledgement was not confirmed')
            view = _save(store, app_id, intent_id, 'UPLOADED')
        if view['stage'] in ('UPLOADED', 'PROCESSING'):
            view = _read(store, app_id, actor, intent_id, transport, context, operation)
        if view['stage'] == 'READY_TO_FINISH':
            _guard(store, app_id, actor, intent_id, operation, charge=True, stage='FINISH_PENDING')
            result = transport.publish(view['remote_id'], dict(caption=view['request']['caption']), context)
            if result != dict(video_id=view['remote_id'], state='PUBLISH_ACKNOWLEDGED'):
                raise Unconfirmed('Reel finish acknowledgement was not confirmed')
            view = _save(store, app_id, intent_id, 'FINISH_ACKNOWLEDGED')
        if view['stage'] == 'FINISH_ACKNOWLEDGED':
            view = _read(store, app_id, actor, intent_id, transport, context, operation)
        return view


def reconcile(store, app_id, actor, intent_id, transport) -> object:
    """Owner-only finite readback, including after policy revocation or expiry."""
    operation = 'organic-video.intent-reconcile'
    transport = transport or provider
    with paid_lock(store, app_id, intent_id):
        view, policy = _guard(store, app_id, actor, intent_id, operation, recovery=True)
        if view['remote_id'] is None:
            return view
        config, secret, grant = _credentials(store, app_id, policy)
        charged = lambda: _guard(store, app_id, actor, intent_id, operation, recovery=True, charge=True)
        token = _permission_check(store, app_id, policy, config, secret, grant, charged, read_only=True)
        alive = lambda: _guard(store, app_id, actor, intent_id, operation, recovery=True)
        context = provider.Context(view['request']['page_id'], token, secret, alive)
        return _read(store, app_id, actor, intent_id, transport, context, operation, recovery=True)
