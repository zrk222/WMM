"""Separate owner policy and durable admission for local organic video output."""
from datetime import datetime, timedelta, timezone
import json
import re

from .agent_grants import app_scope
from .campaign_contract import exact, hashes, numeric, whole
from .common import Invalid, canonical, digest, iso_time, now, required, safe_data, uid
from .db import connection
from .operation_authority import PROTECTED, check, store_identity
from .review_access import exact_role
from .social_contract import reference

FIELDS = ('connection_id', 'page_id', 'expires_at', 'sources', 'claims', 'templates',
          'transformations', 'generation_providers', 'currency', 'max_model_minor',
          'max_generations', 'max_posts', 'max_calls', 'approved_output_hashes')
OUTPUT_FIELDS = ('request_id', 'artifact_id', 'artifact_sha256', 'template_id', 'caption', 'transformation',
                 'reserve_calls', 'reservation_id', 'reservation_hash')


def validate_policy(body) -> object:
    """Validate a bounded proposal. Durable authority is established by Policies."""
    if not isinstance(body, dict):
        raise Invalid('Use an organic video policy object')
    value = dict(body)
    value.setdefault('mode', 'EXACT')
    exact(value, FIELDS + ('mode',))
    safe_data(value)
    reference(value['connection_id'])
    numeric(value['page_id'])
    if value['mode'] not in ('EXACT', 'STANDING_GENERATED'):
        raise Invalid('Select EXACT or explicitly select STANDING_GENERATED')
    if value['generation_providers'] != ['HYPIT_LOCAL'] or value['transformations'] != ['DECLARATIVE_COMPOSITION']:
        raise Invalid('Only approved local declarative composition is available')
    if not isinstance(value['currency'], str) or not re.fullmatch(r'[A-Z]{3}', value['currency']):
        raise Invalid('Use an explicit three-letter model service currency')
    whole(value['max_model_minor'], 0, 0)
    whole(value['max_generations'], 1, 500)
    whole(value['max_posts'], 1, 20)
    whole(value['max_calls'], 1, 500)
    expiry = iso_time(value['expires_at'])
    current = datetime.now(timezone.utc)
    if not current < expiry <= current + timedelta(hours=24):
        raise Invalid('Policy expiry must be within 24 hours')
    value['expires_at'] = expiry.isoformat()
    for name, fields in (('sources', ('id', 'sha256', 'review_version')), ('claims', ('id', 'sha256'))):
        rows = value[name]
        if not isinstance(rows, list) or not 1 <= len(rows) <= 20:
            raise Invalid('Select one through twenty distinct sources and claims')
        identities = []
        for row in rows:
            exact(row, fields)
            reference(row['id'])
            hashes([row['sha256']], True)
            if name == 'sources':
                whole(row['review_version'], 1, 100)
            identities.append(row['id'])
        if len(set(identities)) != len(identities):
            raise Invalid('Policy source and claim identities must be distinct')
    templates = value['templates']
    if not isinstance(templates, list) or not 1 <= len(templates) <= 20:
        raise Invalid('Select one through twenty literal caption templates')
    seen = set()
    claim_ids = {row['id'] for row in value['claims']}
    for template in templates:
        exact(template, ('id', 'caption', 'claim_ids'))
        reference(template['id'])
        if template['id'] in seen:
            raise Invalid('Template identities must be distinct')
        seen.add(template['id'])
        required(template['caption'], 'Exact caption template', 5000)
        if re.search(r'[\x00-\x09\x0b-\x1f\x7f\ud800-\udfff{}]', template['caption']):
            raise Invalid('Use a literal printable caption without placeholders')
        selected = template['claim_ids']
        if (not isinstance(selected, list) or not selected or any(type(item) is not str for item in selected)
                or len(set(selected)) != len(selected) or not set(selected) <= claim_ids):
            raise Invalid('Each template must select distinct approved claim evidence')
    value['approved_output_hashes'] = hashes(value['approved_output_hashes'], value['mode'] == 'EXACT')
    if value['mode'] == 'STANDING_GENERATED' and value['approved_output_hashes']:
        raise Invalid('Standing generation selects constrained outputs instead of exact output hashes')
    return json.loads(canonical(value))


def admit_output(policy, output, evidence) -> object:
    """Check a supplied snapshot without persisting or granting current authority."""
    policy = validate_policy(policy)
    exact(output, OUTPUT_FIELDS)
    safe_data(output)
    for name in ('request_id', 'artifact_id', 'template_id', 'reservation_id'):
        reference(output[name])
    hashes([output['artifact_sha256']], True)
    hashes([output['reservation_hash']], True)
    whole(output['reserve_calls'], 1, policy['max_calls'])
    exact(evidence, ('generation_provider', 'service_cost_minor', 'currency', 'cost_status', 'receipt_hash'))
    hashes([evidence['receipt_hash']], True)
    if (evidence['generation_provider'] != 'HYPIT_LOCAL' or type(evidence['service_cost_minor']) is not int
            or evidence['service_cost_minor'] != 0 or evidence['cost_status'] != 'LOCAL_PLAN_NO_PROVIDER_REQUESTS'
            or evidence['currency'] != policy['currency']):
        raise Invalid('Unknown, external or unsettled model service cost blocks admission')
    templates = [row for row in policy['templates'] if row['id'] == output['template_id']]
    if (len(templates) != 1 or output['caption'] != templates[0]['caption']
            or output['transformation'] not in policy['transformations']):
        raise Invalid('Output differs from the exact approved caption or transformation')
    if policy['mode'] == 'EXACT' and output['artifact_sha256'] not in policy['approved_output_hashes']:
        raise Invalid('Exact policy does not approve these output bytes')
    return dict(output, generation=dict(evidence))


def _schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS organic_video_policies(
        app_id TEXT NOT NULL REFERENCES apps(id), id TEXT PRIMARY KEY, request_id TEXT NOT NULL,
        request_hash TEXT NOT NULL, data TEXT NOT NULL, hash TEXT NOT NULL, created TEXT NOT NULL,
        UNIQUE(app_id,request_id))''')
    db.execute('''CREATE TABLE IF NOT EXISTS organic_video_policy_revocations(
        policy_id TEXT PRIMARY KEY REFERENCES organic_video_policies(id), created TEXT NOT NULL)''')
    db.execute('''CREATE TABLE IF NOT EXISTS organic_video_generation_reservations(
        app_id TEXT NOT NULL REFERENCES apps(id), id TEXT PRIMARY KEY,
        policy_id TEXT NOT NULL REFERENCES organic_video_policies(id), request_id TEXT NOT NULL,
        request_hash TEXT NOT NULL, data TEXT NOT NULL, hash TEXT NOT NULL, created TEXT NOT NULL,
        UNIQUE(policy_id,request_id))''')
    db.execute('''CREATE TABLE IF NOT EXISTS organic_video_admissions(
        app_id TEXT NOT NULL REFERENCES apps(id), id TEXT PRIMARY KEY,
        policy_id TEXT NOT NULL REFERENCES organic_video_policies(id), request_id TEXT NOT NULL,
        request_hash TEXT NOT NULL, artifact_id TEXT NOT NULL, artifact_sha256 TEXT NOT NULL,
        reservation_id TEXT NOT NULL UNIQUE REFERENCES organic_video_generation_reservations(id),
        calls INTEGER NOT NULL, data TEXT NOT NULL, hash TEXT NOT NULL, created TEXT NOT NULL,
        UNIQUE(policy_id,request_id), UNIQUE(policy_id,artifact_id), UNIQUE(policy_id,artifact_sha256))''')
    db.execute('''CREATE TABLE IF NOT EXISTS organic_video_reserved_jobs(
        reservation_id TEXT PRIMARY KEY REFERENCES organic_video_generation_reservations(id),
        app_id TEXT NOT NULL REFERENCES apps(id), job_id TEXT NOT NULL UNIQUE REFERENCES jobs(id))''')
    for table in ('organic_video_policies', 'organic_video_policy_revocations',
                  'organic_video_generation_reservations', 'organic_video_admissions', 'organic_video_reserved_jobs'):
        for operation in ('UPDATE', 'DELETE'):
            db.execute(f'''CREATE TRIGGER IF NOT EXISTS {table}_no_{operation.lower()}
                BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT,'Organic video history is immutable'); END''')
    replacements = {
        'organic_video_policies': 'id=NEW.id OR (app_id=NEW.app_id AND request_id=NEW.request_id)',
        'organic_video_policy_revocations': 'policy_id=NEW.policy_id',
        'organic_video_generation_reservations': 'id=NEW.id OR (policy_id=NEW.policy_id AND request_id=NEW.request_id)',
        'organic_video_admissions': 'id=NEW.id OR reservation_id=NEW.reservation_id OR (policy_id=NEW.policy_id AND (request_id=NEW.request_id OR artifact_id=NEW.artifact_id OR artifact_sha256=NEW.artifact_sha256))',
        'organic_video_reserved_jobs': 'reservation_id=NEW.reservation_id OR job_id=NEW.job_id',
    }
    for table, matching in replacements.items():
        db.execute(f'''CREATE TRIGGER IF NOT EXISTS {table}_no_replace BEFORE INSERT ON {table}
            WHEN EXISTS(SELECT 1 FROM {table} WHERE {matching} OR rowid=NEW.rowid)
            BEGIN SELECT RAISE(ABORT,'Organic video history is immutable'); END''')


def _authority(db, store, app_id, operation, body, owner_only=False):
    context = PROTECTED.get()
    if not context or context.get('store') != store_identity(store):
        raise PermissionError('An exact protected organic policy operation is required')
    if json.loads(context['envelope']) != dict(app_id=app_id, operation=operation, input=body):
        raise PermissionError('Organic policy operation differs from its protected admission')
    if owner_only and 'grant_id' in context:
        raise PermissionError('This organic video action requires the app owner')
    check(db, context)
    return context


def _saved(row):
    if row is None:
        raise Invalid('Organic policy or admission is unavailable')
    data = json.loads(row['data'])
    if canonical(data) != row['data'] or digest(data) != row['hash']:
        raise Invalid('Organic policy history integrity changed')
    return dict(id=row['id'], hash=row['hash'], data=data)


def _page(db, app_id, proposal):
    row = db.execute('SELECT * FROM social_connections WHERE app_id=? AND id=?',
                     (app_id, proposal['connection_id'])).fetchone()
    if (not row or row['provider'] != 'facebook' or row['status'] != 'CONNECTED_READ_TESTED'
            or row['lease'] or (row['expires'] is not None and row['expires'] <= datetime.now(timezone.utc).timestamp())
            or json.loads(row['data']).get('destination', {}).get('id') != proposal['page_id']):
        raise PermissionError('Current selected Facebook Page connection is required')
    config = db.execute("SELECT version,status FROM social_configs WHERE app_id=? AND provider='facebook'", (app_id,)).fetchone()
    if not config or config['version'] != row['config_version'] or config['status'] == 'DISCONNECTED':
        raise PermissionError('Facebook configuration changed')
    return dict(version=row['version'], config_version=row['config_version'], data_hash=digest(json.loads(row['data'])))


def _proofs(db, store, app_id, proposal, *, verify_bytes=True):
    from .creative_briefs import bound_record, latest_proof
    from .managed_media_store import derivative_snapshot
    app = db.execute('SELECT * FROM apps WHERE id=?', (app_id,)).fetchone()
    if not app:
        raise Invalid('App workspace is unavailable')
    manifest = json.loads(app['data'])
    sources = []
    for selected in proposal['sources']:
        view, _ = derivative_snapshot(db, store, app_id, selected['id'], selected['sha256'], verify_bytes=verify_bytes)
        if view['review_version'] != selected['review_version']:
            raise Invalid('Source rights review changed')
        sources.append(dict(selected, rights_hash=digest(view['latest_review']), record_hash=view['hash']))
    claims = []
    for selected in proposal['claims']:
        record = bound_record(db, app_id, selected['id'], 'claim', manifest)
        latest_proof(db, app_id, record, manifest)
        actual_hash = digest(dict(kind=record['kind'], data=record['data'], source=record['source']))
        if record['hash'] != selected['sha256'] or record['hash'] != actual_hash:
            raise Invalid('Approved claim evidence changed')
        claims.append(dict(selected, version=record['version'], evidence_hash=digest(record['data'])))
    return dict(sources=sources, claims=claims)


def _approved_inputs(policy, inputs, template_id):
    selected_sources = {(item['id'], item['sha256'], item['review_version']) for item in policy['sources']}
    used_sources = {(item['id'], item['sha256'], item['review_version']) for item in inputs.get('media_bindings', [])}
    if not used_sources or not used_sources <= selected_sources:
        raise Invalid('Output uses unapproved footage or source rights')
    records = inputs['request']['brief']['data']['records']
    allowed_claims = {(item['id'], item['sha256']) for item in policy['claims']}
    used_claims = {(item['id'], item['hash']) for item in records if item['kind'] == 'claim'}
    if not used_claims or not used_claims <= allowed_claims:
        raise Invalid('Output uses unapproved claim evidence')
    templates = [item for item in policy['templates'] if item['id'] == template_id]
    if len(templates) != 1 or {item[0] for item in used_claims} != set(templates[0]['claim_ids']):
        raise Invalid('Output claim evidence differs from the selected template')


def reserved_job_guard(db, store, app_id, request_key, inputs, job_id=None):
    """Recheck an organic reservation and policy in the caller's transaction."""
    prefix='organic-video-reservation:'
    if not isinstance(request_key,str) or not request_key.startswith(prefix):return None
    _schema(db)
    reservation_id=request_key[len(prefix):]
    row=db.execute('SELECT * FROM organic_video_generation_reservations WHERE app_id=? AND id=?',(app_id,reservation_id)).fetchone()
    reservation=_saved(row)
    data=reservation['data']
    if data['job_request_key']!=request_key or data['inputs_hash']!=digest(inputs):raise Invalid('Organic generation reservation does not match this job')
    policy_row=db.execute('SELECT * FROM organic_video_policies WHERE app_id=? AND id=?',(app_id,data['policy_id'])).fetchone()
    policy=Policies(store)._current(db,policy_row)
    if policy['hash']!=data['policy_hash']:raise Invalid('Organic generation policy changed')
    _approved_inputs(policy['data']['policy'],inputs,data['template_id'])
    bound=db.execute('SELECT job_id FROM organic_video_reserved_jobs WHERE app_id=? AND reservation_id=?',(app_id,reservation_id)).fetchone()
    if job_id is not None and (not bound or bound['job_id']!=job_id):raise Invalid('Organic reservation is not bound to this job')
    return reservation, bound['job_id'] if bound else None


class Policies:
    """Local owner approvals and atomic reservations, separate from campaign scopes."""
    def __init__(self, store):
        self.store = store

    def create(self, app_id, body):
        review_fields = ('manifest_version', 'app_hash', 'owner_version', 'page_binding', 'session_binding')
        scoped = isinstance(body, dict) and any(field in body for field in review_fields)
        exact(body, ('request_id', 'policy') + (review_fields if scoped else ()))
        if scoped:
            if type(body['manifest_version']) is not int or body['manifest_version'] < 1:
                raise Invalid('Use the exact reviewed app version')
            hashes([body['app_hash']], True)
            hashes([body['session_binding']], True)
            if type(body['owner_version']) is not int:
                raise Invalid('Use the exact reviewed owner role version')
            exact(body['page_binding'], ('version', 'config_version', 'data_hash'))
            if any(type(body['page_binding'][key]) is not int for key in ('version', 'config_version')):
                raise Invalid('Use the exact reviewed Page version')
            hashes([body['page_binding']['data_hash']], True)
        reference(body['request_id'])
        proposal = validate_policy(body['policy'])
        if iso_time(proposal['expires_at']) <= datetime.now(timezone.utc):
            raise Invalid('Policy expiry must be in the future')
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE')
            context = _authority(db, self.store, app_id, 'organic-video.policy-create', body, True)
            _schema(db)
            version, app_hash = app_scope(db, app_id)
            if scoped and (version != body['manifest_version'] or app_hash != body['app_hash']):
                raise Invalid('Reviewed policy app context changed; reload before approving')
            page = _page(db, app_id, proposal)
            if scoped and (context['role_version'] != body['owner_version'] or page != body['page_binding']):
                raise Invalid('Reviewed owner role or Page connection changed; reload before approving')
            if scoped and digest(context['generation']) != body['session_binding']:
                raise Invalid('Reviewed owner session changed; reload before approving')
            if scoped and proposal['mode'] == 'EXACT':
                from .organic_video_policy_ui import _recorded_outputs
                outputs = {row['sha256'] for row in _recorded_outputs(db, app_id)}
                if not set(proposal['approved_output_hashes']) <= outputs:
                    raise Invalid('Reviewed output is outside the completed local render selection; reload before approving')
            data = dict(policy=proposal, owner=context['principal'], owner_version=context['role_version'],
                        app_id=app_id, app_version=version, app_hash=app_hash,
                        page=page, proofs=_proofs(db, self.store, app_id, proposal))
            prior = db.execute('SELECT * FROM organic_video_policies WHERE app_id=? AND request_id=?',
                               (app_id, body['request_id'])).fetchone()
            if prior:
                if prior['request_hash'] != digest(body) or _saved(prior)['data'] != data:
                    raise Invalid('Policy request identity was used with different approval')
                return self._current(db, prior)
            identity = uid()
            db.execute('INSERT INTO organic_video_policies VALUES(?,?,?,?,?,?,?)',
                       (app_id, identity, body['request_id'], digest(body), canonical(data), digest(data), now()))
            return self._current(db, db.execute('SELECT * FROM organic_video_policies WHERE id=?', (identity,)).fetchone())

    def _current(self, db, row, *, verify_bytes=True):
        saved = _saved(row)
        data = saved['data']
        proposal = data['policy']
        if db.execute('SELECT 1 FROM organic_video_policy_revocations WHERE policy_id=?', (row['id'],)).fetchone():
            raise PermissionError('Organic policy is revoked')
        if iso_time(proposal['expires_at']) <= datetime.now(timezone.utc):
            raise PermissionError('Organic policy expired')
        exact_role(db, data['app_id'], data['owner'], data['owner_version'], 'OWNER')
        if app_scope(db, data['app_id']) != (data['app_version'], data['app_hash']):
            raise PermissionError('Organic policy app changed')
        if _page(db, data['app_id'], proposal) != data['page']:
            raise PermissionError('Organic policy Page connection changed')
        if _proofs(db, self.store, data['app_id'], proposal, verify_bytes=verify_bytes) != data['proofs']:
            raise Invalid('Organic policy source rights or claim evidence changed')
        return saved

    def read(self, app_id, body):
        exact(body, ('policy_id', 'policy_hash'))
        with connection(self.store.path) as db:
            _authority(db, self.store, app_id, 'organic-video.policy-read', body)
            _schema(db)
            row = db.execute('SELECT * FROM organic_video_policies WHERE app_id=? AND id=?', (app_id, body['policy_id'])).fetchone()
            saved = self._current(db, row)
            if saved['hash'] != body['policy_hash']:
                raise Invalid('Policy hash differs from the owner approval')
            return saved

    def revoke(self, app_id, body):
        exact(body, ('policy_id', 'policy_hash'))
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE')
            context = _authority(db, self.store, app_id, 'organic-video.policy-revoke', body, True)
            _schema(db)
            row = db.execute('SELECT * FROM organic_video_policies WHERE app_id=? AND id=?', (app_id, body['policy_id'])).fetchone()
            saved = _saved(row)
            if saved['hash'] != body['policy_hash'] or saved['data']['owner'] != context['principal']:
                raise PermissionError('Only the approving owner can revoke this exact policy')
            if not db.execute('SELECT 1 FROM organic_video_policy_revocations WHERE policy_id=?', (row['id'],)).fetchone():
                db.execute('INSERT INTO organic_video_policy_revocations VALUES(?,?)', (row['id'], now()))
            return dict(policy_id=row['id'], policy_hash=saved['hash'], status='REVOKED')

    def reserve(self, app_id, body):
        """Hold one generation before a trusted workflow queues the exact job.

        The workflow must use the returned job_request_key. A held attempt is
        never automatically released after an uncertain or failed render.
        """
        exact(body, ('policy_id', 'policy_hash', 'request_id', 'template_id', 'render_input'))
        reference(body['request_id'])
        reference(body['template_id'])
        from .hypit_jobs import resolve_inputs
        from .hypit_authoring import project
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE')
            context = _authority(db, self.store, app_id, 'organic-video.policy-reserve', body)
            _schema(db)
            row = db.execute('SELECT * FROM organic_video_policies WHERE app_id=? AND id=?', (app_id, body['policy_id'])).fetchone()
            saved = self._current(db, row)
            if 'grant_id' not in context and saved['data']['owner'] != context['principal']:
                raise PermissionError('Only the approving owner can reserve under this policy')
            if saved['hash'] != body['policy_hash']:
                raise Invalid('Policy hash differs from the owner approval')
            inputs, _ = resolve_inputs(db, self.store, app_id, body['render_input'])
            _approved_inputs(saved['data']['policy'], inputs, body['template_id'])
            project(inputs['scene'])
            prior = db.execute('SELECT * FROM organic_video_generation_reservations WHERE policy_id=? AND request_id=?',
                               (row['id'], body['request_id'])).fetchone()
            if prior:
                if prior['request_hash'] != digest(body):
                    raise Invalid('Generation request identity was used for different input')
                return _saved(prior)
            count = db.execute('SELECT count(*) FROM organic_video_generation_reservations WHERE policy_id=?', (row['id'],)).fetchone()[0]
            if count >= saved['data']['policy']['max_generations']:
                raise PermissionError('Organic policy generation ceiling exhausted')
            identity = uid()
            data = dict(policy_id=row['id'], policy_hash=saved['hash'], inputs_hash=digest(inputs),
                        render_input=body['render_input'], template_id=body['template_id'],
                        job_request_key='organic-video-reservation:' + identity,
                        generation_provider='HYPIT_LOCAL', model_service_minor=0, status='HELD')
            db.execute('INSERT INTO organic_video_generation_reservations VALUES(?,?,?,?,?,?,?,?)',
                       (app_id, identity, row['id'], body['request_id'], digest(body), canonical(data), digest(data), now()))
            self._current(db, row)
            return _saved(db.execute('SELECT * FROM organic_video_generation_reservations WHERE id=?', (identity,)).fetchone())

    def admit(self, app_id, body):
        exact(body, ('policy_id', 'policy_hash', 'output'))
        from .hypit_jobs import artifact_file, current_inputs, saved as hypit_saved
        from .hypit_runtime import local_graph, source_current
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE')
            _authority(db, self.store, app_id, 'organic-video.policy-admit', body)
            _schema(db)
            row = db.execute('SELECT * FROM organic_video_policies WHERE app_id=? AND id=?', (app_id, body['policy_id'])).fetchone()
            saved = self._current(db, row)
            if saved['hash'] != body['policy_hash']:
                raise Invalid('Policy hash differs from the owner approval')
            output = body['output']
            exact(output, OUTPUT_FIELDS)
            reservation_row = db.execute('SELECT * FROM organic_video_generation_reservations WHERE app_id=? AND policy_id=? AND id=?',
                                         (app_id, row['id'], output['reservation_id'])).fetchone()
            reservation = _saved(reservation_row)
            if reservation['hash'] != output['reservation_hash'] or reservation['data']['policy_hash'] != saved['hash']:
                raise Invalid('Generation reservation differs from the approved policy')
            _, artifact = artifact_file(self.store, app_id, output['artifact_id'])
            receipt = artifact.get('receipt', {})
            plan = receipt.get('local_plan')
            if (not isinstance(plan, dict) or artifact.get('renderer') != 'HYPIT_LOCAL'
                    or type(plan.get('localRequestCount')) is not int):
                raise Invalid('Retained generation cost evidence is unknown')
            local_graph(plan)
            attempt = db.execute('SELECT a.* FROM hypit_attempts a JOIN hypit_renders r ON r.app_id=a.app_id AND r.job_id=a.job_id WHERE r.app_id=? AND r.id=?',
                                 (app_id, output['artifact_id'])).fetchone()
            if not attempt or attempt['status'] != 'COMPLETE':
                raise Invalid('Retained local generation attempt is incomplete')
            attempt_data = hypit_saved(attempt)['data']
            folder = self.store.path.parent / attempt_data['project']
            source_current(folder, receipt['source'])
            if attempt_data['build_id'] != receipt['build_id'] or artifact['artifact']['sha256'] != output['artifact_sha256']:
                raise Invalid('Retained output differs from the selected artifact or generation')
            current_inputs(db, self.store, app_id, artifact['inputs'])
            policy = saved['data']['policy']
            _approved_inputs(policy, artifact['inputs'], output['template_id'])
            generation_job = db.execute('SELECT * FROM jobs WHERE app_id=? AND id=?', (app_id, attempt['job_id'])).fetchone()
            if (not generation_job or generation_job['action'] != 'hypit_render'
                    or generation_job['status'] != 'SUCCEEDED'
                    or generation_job['request_key'] != reservation['data']['job_request_key']
                    or generation_job['created'] < reservation_row['created']
                    or generation_job['data'] != canonical(artifact['inputs'])
                    or digest(artifact['inputs']) != reservation['data']['inputs_hash']
                    or output['template_id'] != reservation['data']['template_id']):
                raise Invalid('Generation output does not match its pre-render reservation')
            reserved_job_guard(db,self.store,app_id,generation_job['request_key'],artifact['inputs'],generation_job['id'])
            evidence = dict(generation_provider='HYPIT_LOCAL', service_cost_minor=0, currency=policy['currency'],
                            cost_status='LOCAL_PLAN_NO_PROVIDER_REQUESTS', receipt_hash=digest(receipt))
            validated = admit_output(policy, output, evidence)
            prior = db.execute('SELECT * FROM organic_video_admissions WHERE policy_id=? AND request_id=?',
                               (row['id'], output['request_id'])).fetchone()
            if prior:
                if prior['request_hash'] != digest(body):
                    raise Invalid('Admission request identity was used for different output')
                return _saved(prior)
            if db.execute('SELECT 1 FROM organic_video_admissions WHERE policy_id=? AND (artifact_id=? OR artifact_sha256=? OR reservation_id=?)',
                          (row['id'], output['artifact_id'], output['artifact_sha256'], reservation['id'])).fetchone():
                raise Invalid('Output already has an immutable admission')
            totals = db.execute('SELECT count(*),coalesce(sum(calls),0) FROM organic_video_admissions WHERE policy_id=?', (row['id'],)).fetchone()
            if totals[0] >= policy['max_posts'] or totals[1] + output['reserve_calls'] > policy['max_calls']:
                raise PermissionError('Organic policy generation, post or call ceiling exhausted')
            data = dict(policy_id=row['id'], policy_hash=saved['hash'], output=validated,
                        proofs=saved['data']['proofs'], artifact_record_hash=digest(artifact),
                        build_id=receipt['build_id'], reserved_posts=1, model_service_minor=0,
                        provider_calls_reserved=output['reserve_calls'], status='ADMITTED')
            identity = uid()
            db.execute('INSERT INTO organic_video_admissions VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                       (app_id, identity, row['id'], output['request_id'], digest(body), output['artifact_id'],
                        output['artifact_sha256'], reservation['id'], output['reserve_calls'], canonical(data), digest(data), now()))
            self._current(db, row)
            artifact_file(self.store, app_id, output['artifact_id'])
            self._current(db, row)
            return _saved(db.execute('SELECT * FROM organic_video_admissions WHERE id=?', (identity,)).fetchone())
