"""Owner-facing publication composition; provider effects remain in the executor."""
from .common import Invalid,digest,uid
from .db import connection
from .operation_authority import check
from .review_access import member
from .publication_authority import Publications,_admit,_view,_row
from .publication_contract import SCHEMA,validate_draft
from .publication_artifacts import describe
from .social_contract import exact,reference

DRAFT_FIELDS=('provider','kind','connection_id','connection_version','destination_id','title','caption','link','artifact_id','settings')

def _owner(store,app_id,operation,body,*,agent_ok=False):
    context,_,owner=_admit(store,app_id,operation,body,not agent_ok)
    with connection(store.path) as db:check(db,context);member(db,app_id,owner,'OWNER')
    return context,owner

def _channel_rows():
    """Project executable organic channel kinds in the browser's closed catalog shape."""
    from .publication_contract import channel_catalog
    return [{'provider':provider,'name':row['name'],'kinds':row['kinds']}
            for provider,row in channel_catalog().items() if row['execution_implemented']]

def _account_rows(store,app_id):
    """Return saved connection metadata separately from channel capabilities."""
    from .social_connections import Connections
    return [{key:row[key] for key in ('id','provider','version','status','data')}
            for row in Connections(store).view(app_id)['accounts']]

def _current_renders(store,app_id):
    """List only current app-owned render artifacts with their public review metadata."""
    from .hypit_jobs import HypitRenders
    from .publication_artifacts import describe
    renders=[]
    for row in HypitRenders(store).list(app_id)['items']:
        if row.get('status')!='CURRENT':continue
        try:renders.append(describe(store,app_id,row['id']))
        except (Invalid,KeyError,OSError):continue
    return renders

def _schedule_projection(db,app_id,authority_id,provider_status):
    """Project persisted worker and provider phases without conflating them."""
    row=db.execute('SELECT s.status AS schedule_status,s.due,s.next_due,s.job_id,j.status AS job_status FROM publication_schedules s LEFT JOIN jobs j ON j.id=s.job_id AND j.app_id=s.app_id WHERE s.app_id=? AND s.authority_id=?',(app_id,authority_id)).fetchone()
    if row is None:return None
    return {'status':row['schedule_status'],'job_id':row['job_id'],'job_status':row['job_status'],
            'due':row['due'],'next_due':row['next_due'],'provider_status':provider_status}

def _authority_rows(store,app_id,owner,intents):
    """Build owner-scoped approvals with separate saved schedule/job/provider state."""
    provider_status={item.get('authority_id'):item.get('status') for item in intents if isinstance(item,dict)}
    with connection(store.path) as db:
        rows=db.execute('SELECT * FROM publication_authorities WHERE app_id=? AND owner=? ORDER BY created DESC LIMIT 200',(app_id,owner)).fetchall()
        result=[]
        for row in rows:
            checked,draft,_=_row(db,app_id,row['id'])
            item={**_view(checked),'draft':draft}
            item['schedule']=_schedule_projection(db,app_id,row['id'],provider_status.get(row['id']))
            result.append(item)
    return result

def list_publications(store,app_id):
    """Return owner-visible channels, saved media, approvals and retained receipts."""
    _,owner=_owner(store,app_id,'publication.list',{},agent_ok=True)
    from .publication_execution import list_intents
    from .publication_schedule import initialize as initialize_schedules
    Publications(store)
    initialize_schedules(store)
    intents=list_intents(store,app_id)
    if not isinstance(intents,list):raise Invalid('Publication intent list is unavailable')
    authorities=_authority_rows(store,app_id,owner,intents)
    allowed={row['id'] for row in authorities}
    return {'channels':_channel_rows(),'accounts':_account_rows(store,app_id),'renders':_current_renders(store,app_id),
            'authorities':authorities,'intents':[item for item in intents if item.get('authority_id') in allowed]}

def draft(store,app_id,body):
    _owner(store,app_id,'publication.draft',body,agent_ok=True);exact(body,DRAFT_FIELDS)
    with connection(store.path) as db:
        row=db.execute('SELECT version FROM apps WHERE id=?',(app_id,)).fetchone()
        if row is None:raise Invalid('Publication workspace unavailable')
        version=row['version']
    artifact_id=body['artifact_id']
    if body['kind']=='linkedin_text':
        if artifact_id is not None:raise Invalid('LinkedIn text cannot include video')
        artifact=None;rights=[digest({'kind':'OWNER_ORIGINAL_COPY','title':body['title'],'caption':body['caption'],'link':body['link']})];sources=[]
    else:
        info=describe(store,app_id,reference(artifact_id));artifact={'id':info['id'],'sha256':info['sha256']};rights=info['rights_hashes'];sources=info['source_hashes']
    value={key:body[key] for key in ('provider','kind','connection_id','connection_version','destination_id','title','caption','link','settings')}
    value.update(schema=SCHEMA,request_id=uid(),app_id=app_id,manifest_version=version,artifact=artifact,rights_hashes=rights,source_hashes=sources)
    return {'draft':validate_draft(value)}

def _prepare(store,app_id,body):
    """Persist a reviewed draft after checking the closed preparation payload."""
    exact(body,('draft','preflight_id'))
    return Publications(store).prepare(app_id,body['draft'],body['preflight_id'])

def _preflight(store,app_id,body):
    """Fetch fresh TikTok creator options for the exact current destination."""
    exact(body,('connection_id','connection_version','destination_id'))
    from .publication_authority import record_preflight
    return record_preflight(store,app_id,**body)

def _instagram_account(store,app_id,body):
    """Read the Instagram link through its selected Facebook Page with one-call bound."""
    exact(body,('connection_id','connection_version'))
    admitted,_=_owner(store,app_id,'publication.instagram-account',body);count=0
    def heartbeat():
        with connection(store.path) as db:check(db,admitted)
    def before():
        nonlocal count
        heartbeat();count+=1
        if count>1:raise PermissionError('Instagram account read limit reached')
    from .publication_credentials import inspect_instagram
    return inspect_instagram(store,app_id,body['connection_id'],body['connection_version'],before,heartbeat)

def _execute(store,app_id,body):
    """Enqueue only the exact approved publication; this does not call the provider."""
    exact(body,('id',));reference(body['id']);_owner(store,app_id,'publication.execute',body,agent_ok=True)
    from .publication_schedule import enqueue_approved
    return enqueue_approved(store,app_id,body['id'])

def _authority_action(store,app_id,action,body,identity):
    """Handle only owner-authorized activation, revocation, and reconciliation."""
    reference(identity)
    if action=='activate':return Publications(store).activate(app_id,identity,body)
    if action=='revoke':
        exact(body,('version',));return Publications(store).revoke(app_id,identity,body['version'])
    if action=='reconcile':
        exact(body,('id',))
        if body['id']!=identity:raise Invalid('Publication identity changed')
        _owner(store,app_id,'publication.reconcile',body)
        from .publication_execution import reconcile
        return reconcile(store,app_id,identity)
    raise Invalid('Unknown publication operation')

def dispatch(store,app_id,action,body,identity=None):
    """Dispatch a fixed organic-publication operation to its semantic handler."""
    actions={'draft':draft,'prepare':_prepare,'preflight':_preflight,
             'instagram-account':_instagram_account,'execute':_execute}
    handler=actions.get(action)
    if handler:return handler(store,app_id,body)
    return _authority_action(store,app_id,action,body,identity)
