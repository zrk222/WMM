"""Prepare a bound next operation; callers retain separate exact admissions."""
from .common import Invalid, digest
from .db import connection
from .campaign_contract import exact
from .organic_video_intake import _view as intake_view, _current_outputs
from .organic_video_policy import Policies, _authority, _approved_inputs
from .hypit_jobs import resolve_inputs
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
