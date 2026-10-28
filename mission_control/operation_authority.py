"""Trusted request-local execution scope, separate from public actor attribution."""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime,timezone
import json
from pathlib import Path
from .common import canonical,digest

REQUEST=ContextVar('wmm_operation_authority',default=None)
PROTECTED=ContextVar('wmm_protected_operation',default=None)


def utc():return datetime.now(timezone.utc)


def store_identity(store):return str(Path(store.path).resolve())


@contextmanager
def bound_agent(store,envelope,admission,review=None,host_check=None):
    """Only authenticated dispatchers bind this context; retain no bearer credential."""
    from .db import connection
    context=dict(store=store_identity(store),envelope=canonical(envelope),grant_id=admission['grant_id'],
        agent_id=admission['agent_id'],attempt=admission['attempt'],review=review,
        execution_id=admission.get('automation_execution_id'),host_check=host_check)
    with connection(store.path) as db:
        row=db.execute('SELECT * FROM agent_grants WHERE id=?',(context['grant_id'],)).fetchone()
        if row is None:raise PermissionError('Admitted grant is unavailable')
        context['grant_version']=row['version']
    token=REQUEST.set(context)
    try:yield
    finally:REQUEST.reset(token)


@contextmanager
def bound_owner(store,envelope,identities,session,user):
    """HTTP admission supplies a freshly provider-verified user, never body identity."""
    from .db import connection
    from .review_access import member
    local=identities.local(session,user['principal'])
    with connection(store.path) as db:
        role=member(db,envelope['app_id'],user['principal'],'OWNER')
    context=dict(store=store_identity(store),envelope=canonical(envelope),principal=user['principal'],
        role_version=role['version'],identities=identities,session=session,generation=local['session_generation'])
    token=REQUEST.set(context)
    try:yield
    finally:REQUEST.reset(token)


def check_agent(db,context,envelope):
    if context.get('host_check') is not None:context['host_check']()
    from .agent_grants import current
    from .agent_review_policy import ordinary_dispatch
    row=db.execute('SELECT * FROM agent_grants WHERE id=?',(context['grant_id'],)).fetchone()
    if row is None or row['version']!=context['grant_version'] or row['agent_id']!=context['agent_id']:
        raise PermissionError('Admitted grant identity changed')
    current(db,row,envelope,utc(),check_quota=False)
    if type(context['attempt']) is not int or not 1<=context['attempt']<=row['used']:
        raise PermissionError('Grant admission attempt is unavailable')
    if context['review'] is None:ordinary_dispatch(db,row['id'],envelope['operation'])
    else:check_review(db,context,envelope)
    check_standing(db,context,envelope,row)
    return 'grant:'+row['id']


def check_standing(db,context,envelope,grant):
    """A live standing execution cannot borrow an ordinary or different admission."""
    from .automation_execution import ACTIVE,execution_row
    active=ACTIVE.get()
    if active is not None and context['execution_id'] is None:
        raise PermissionError('Standing operation cannot borrow another admission')
    if context['execution_id'] is not None:
        if active is None or active['id']!=context['execution_id']:
            raise PermissionError('Standing operation context is unavailable')
        execution=execution_row(db,active['id'])
        actual=(active['store'],execution['grant_id'],execution['operation'],execution['input_hash'],execution['status'])
        expected=(context['store'],grant['id'],envelope['operation'],digest(envelope),'DISPATCHED')
        if actual!=expected:
            raise PermissionError('Standing operation authority changed')


def check_review(db,context,envelope):
    from .agent_review_dispatch import saved_request
    from .agent_checkpoints import read_row,current
    review=context['review'];request=saved_request(db,envelope['app_id'],review['id'])
    row=read_row(db,envelope['app_id'],review['id'],review['revision'])
    if request['grant_id']!=context['grant_id'] or request['input_hash']!=review['input_hash'] or canonical(request['envelope'])!=context['envelope'] or row['state']!='RUNNING' or row['hash']!=review['packet_hash'] or row['packet']['agent_id']!=context['agent_id'] or row['packet']['input_hash']!=request['input_hash']:
        raise PermissionError('Reviewed operation authority changed')
    current(db,row,utc())


def check(db,context):
    envelope=json.loads(context['envelope'])
    if 'grant_id' in context:return check_agent(db,context,envelope)
    from .review_access import exact_role
    context['identities'].local(context['session'],context['principal'],context['generation'])
    exact_role(db,envelope['app_id'],context['principal'],context['role_version'],'OWNER')
    return context['principal']


def guard_connection(path,db):
    """Runs in the business connection at entry and immediately before commit."""
    context=PROTECTED.get()
    if context is None:return
    if str(Path(path).resolve())!=context['store']:
        raise PermissionError('Protected operation cannot cross its local datastore')
    check(db,context)


@contextmanager
def protected(store,envelope):
    """Opt in only around an exact synchronous operation, never a whole native session."""
    from .db import connection
    context=REQUEST.get()
    if context is None or context['store']!=store_identity(store) or context['envelope']!=canonical(envelope):
        raise PermissionError('Current exact operation authority is required')
    token=PROTECTED.set(context)
    try:
        with connection(store.path) as db:actor=check(db,context)
        yield actor
    finally:PROTECTED.reset(token)
