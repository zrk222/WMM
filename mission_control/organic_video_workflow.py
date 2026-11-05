"""Prepare, queue and inspect a policy-bound local render under separate admissions."""
import json

from .common import Invalid, digest
from .db import connection
from .campaign_contract import exact, hashes
from .organic_video_intake import _view as intake_view, _current_outputs
from .organic_video_policy import Policies, _authority, _approved_inputs, _saved
from .hypit_jobs import HypitRenders, resolve_inputs
from .social_contract import reference

def prepare(store, app_id, actor, body) -> object:
    """Bind task-to-brief provenance and existing owner policy without effects.

    This does not forge protected envelopes, approve policy, launch a collector,
    render or publish. Each returned operation needs its own current admission.
    """
    exact(body, ('request_id','intake_id','intake_hash','policy_id','policy_hash','template_id','render_input'))
    reference(body['request_id'])
    with connection(store.path) as db:
        context=_authority(db,store,app_id,'organic-video.workflow-prepare',body)
        from .operation_authority import check
        if check(db,context)!=actor:
            raise PermissionError('Workflow actor differs from current admission')
        row=db.execute('SELECT * FROM organic_video_intakes WHERE app_id=? AND id=?',(app_id,body['intake_id'])).fetchone()
        if row is None:
            raise Invalid('Select an adopted discovery intake from this app')
        intake=intake_view(row)
        if intake['hash']!=body['intake_hash']:
            raise Invalid('Adopted discovery intake changed')
        _current_outputs(db,app_id,intake['data'])
        row=db.execute('SELECT * FROM organic_video_policies WHERE app_id=? AND id=?',(app_id,body['policy_id'])).fetchone()
        policy=Policies(store)._current(db,row)
        if policy['hash']!=body['policy_hash']:
            raise Invalid('Workflow owner policy changed')
        if 'grant_id' in context:
            grant=db.execute('SELECT owner FROM agent_grants WHERE id=?',(context['grant_id'],)).fetchone()
            if grant is None or grant['owner']!=policy['data']['owner']:
                raise PermissionError('Workflow policy belongs to another owner')
        elif context['principal']!=policy['data']['owner']:
            raise PermissionError('Workflow policy belongs to another owner')
        inputs,_=resolve_inputs(db,store,app_id,body['render_input'])
        _approved_inputs(policy['data']['policy'],inputs,body['template_id'])
        brief=inputs['request']['brief']
        research=brief['data'].get('discovery')
        if (not research or research['collection_provenance']!=intake['data']['provenance']
                or research['collection_hash']!=intake['data']['collection']['hash']
                or research['reference_id']!=intake['data']['source']['id']
                or research['source_hash']!=intake['data']['source']['hash']
                or research['review_hash']!=intake['data']['review']['hash']
                or brief['data']['analysis']['hash']!=intake['data']['analysis']['hash']):
            raise Invalid('Workflow brief is not bound to this adopted discovery')
        # The exact brief_hash binds the complete frozen collection/provenance.
        # reserve resolves it again and persists digest(inputs), not a new copy
        # of unchecked intake fields in its separately defined schema.
        proposal=dict(policy_id=policy['id'],policy_hash=policy['hash'],request_id=body['request_id'],
                      template_id=body['template_id'],render_input=body['render_input'])
        data=dict(app_id=app_id,intake_id=intake['id'],intake_hash=intake['hash'],
                  policy_id=policy['id'],policy_hash=policy['hash'],inputs_hash=digest(inputs),
                  next_operation=dict(app_id=app_id,operation='organic-video.policy-reserve',input=proposal),
                  state='READY_FOR_SEPARATE_RESERVATION',render='NOT_RUN',publication='NOT_RUN',
                  source_verification='EXTERNAL_AGENT_REPORTED_NOT_INDEPENDENTLY_VERIFIED',
                  authority='RECHECK_EACH_EXACT_OPERATION',paid_calls=0)
        return dict(data=data,hash=digest(data))


def _owner_policy(db, app_id, policy_id, actor):
    policy = _saved(db.execute('SELECT * FROM organic_video_policies WHERE app_id=? AND id=?',
                               (app_id, policy_id)).fetchone())
    if policy['data']['owner'] != actor:
        raise PermissionError('Render reservation belongs to another approving owner')
    return policy


def render_status(store, app_id, actor, body):
    """Read an exact reservation and its bound job, even after approval expiry."""
    exact(body, ('policy_id', 'policy_hash', 'request_id', 'request_hash'))
    reference(body['policy_id'])
    reference(body['request_id'])
    hashes([body['policy_hash']], True)
    hashes([body['request_hash']], True)
    with connection(store.path) as db:
        db.execute('BEGIN')
        _authority(db, store, app_id, 'organic-video.render-status', body, True)
        exists = db.execute("SELECT 1 FROM sqlite_master WHERE name='organic_video_policies'").fetchone()
        if not exists or _owner_policy(db, app_id, body['policy_id'], actor)['hash'] != body['policy_hash']:
            raise Invalid('Select the exact saved production approval')
        row = db.execute('''SELECT * FROM organic_video_generation_reservations
            WHERE app_id=? AND policy_id=? AND request_id=?''',
                         (app_id, body['policy_id'], body['request_id'])).fetchone()
        if row is None:
            return dict(reservation=None, job=None, publication='NOT_RUN')
        if row['request_hash'] != body['request_hash']:
            raise Invalid('Saved render request differs from this exact review')
        reservation = _saved(row)
        binding = db.execute('SELECT job_id FROM organic_video_reserved_jobs WHERE app_id=? AND reservation_id=?',
                             (app_id, reservation['id'])).fetchone()
        job = None
        if binding is not None:
            saved = db.execute('''SELECT id, action, request_key, data, status, updated, result FROM jobs
                WHERE app_id=? AND id=?''', (app_id, binding['job_id'])).fetchone()
            if (saved is None or saved['action'] != 'hypit_render'
                    or saved['request_key'] != reservation['data']['job_request_key']
                    or digest(json.loads(saved['data'])) != reservation['data']['inputs_hash']):
                raise Invalid('Reserved render job binding changed')
            result = json.loads(saved['result']) if saved['result'] else {}
            job = dict(id=saved['id'], status=saved['status'], updated=saved['updated'],
                       render_id=result.get('render_id'))
        return dict(reservation=reservation, job=job, publication='NOT_RUN')


def queue_render(store, app_id, actor, body):
    """Queue only the input retained by a current, exact owner reservation."""
    exact(body, ('reservation_id', 'reservation_hash'))
    reference(body['reservation_id'])
    hashes([body['reservation_hash']], True)
    with connection(store.path) as db:
        _authority(db, store, app_id, 'organic-video.render-queue', body, True)
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='organic_video_generation_reservations'").fetchone():
            raise Invalid('Reserve this exact render before queueing it')
        row = db.execute('SELECT * FROM organic_video_generation_reservations WHERE app_id=? AND id=?',
                         (app_id, body['reservation_id'])).fetchone()
        reservation = _saved(row)
        if reservation['hash'] != body['reservation_hash']:
            raise Invalid('Render reservation changed')
        _owner_policy(db, app_id, row['policy_id'], actor)
    data = reservation['data']
    job = HypitRenders(store).queue(app_id, dict(data=data['render_input'], request_key=data['job_request_key']))
    return dict(id=job['id'], status=job['status'], updated=job['updated'], publication='NOT_RUN')
