"""Protected operational access profiles, separated from marketing evidence exports."""
import json,time
from .common import Invalid,canonical,digest,now,uid,identifier
from .db import connection
from .credential_vault import Vault,namespace
from .agent_registry import catalog,REGISTRY,TASKS,KEYED,NATIVE
from .agent_contract import profile,exact
from .agent_native import locate


def target(store,app_id,reference):
    """A profile can address only its own local credential namespace."""
    identifier(app_id);identifier(reference)
    return 'AgentGrowth/'+namespace(store.path)+'/'+app_id+'/'+reference


def decoded(row):
    """Operational rows contain public configuration and opaque references only."""
    if row is None:raise Invalid('Agent connection does not belong to this app')
    value=dict(row);value['data']=json.loads(value['data'])
    return value


def queue_retirement(db,app_id,reference,delay=0):
    """Persist an opaque cleanup reference, never the protected key itself."""
    if reference:db.execute('INSERT OR REPLACE INTO agent_retirements VALUES(?,?,?)',(app_id,reference,time.time()+delay))


class AgentAccess:
    def __init__(self,store):self.store=store

    def get(self,app_id,identity):
        """Never find a connection by ID without its selected app scope."""
        self.store.app(app_id)
        with connection(self.store.path) as db:
            return decoded(db.execute('SELECT * FROM agent_connections WHERE app_id=? AND id=?',(app_id,identity)).fetchone())

    def view(self,app_id):
        """Refresh without invoking native tools, networking or reading secret values."""
        self.store.app(app_id)
        with connection(self.store.path) as db:
            profiles=[decoded(r) for r in db.execute('SELECT * FROM agent_connections WHERE app_id=? ORDER BY created',(app_id,))]
            route=db.execute('SELECT * FROM agent_routes WHERE app_id=?',(app_id,)).fetchone()
            cleanup=db.execute('SELECT COUNT(*) FROM agent_retirements WHERE app_id=?',(app_id,)).fetchone()[0]
        for row in profiles:
            tool=row['data'].pop('tool',None)
            if tool:row['data']['tool_identity']=dict(fingerprint=tool['fingerprint'],version=tool.get('package_version'))
            row['data']['protected_key']=bool(row['data'].pop('credential_ref',None))
        return dict(providers=catalog(),tasks=TASKS,profiles=profiles,
            routing=decoded(route) if route else dict(version=0,data={'mode':'subscription','routes':{}}),
            app_billing=False,automatic_fallback=False,cleanup_pending=cleanup)

    def save(self,app_id,body):
        """Stage a protected key before optimistic commit; failed saves retire only the stage."""
        self.store.app(app_id);data=profile(body)
        previous=self.previous(app_id,body)
        identity=previous['id'] if previous else uid()
        if data['provider'] in NATIVE:data['tool']=locate(data['provider'])
        reference=self.stage(app_id,body['api_key']) if data['provider'] in KEYED else None
        if reference:data['credential_ref']=reference
        try:self.commit(app_id,identity,data,previous)
        except Exception:
            if reference:self.retire(app_id,{'data':{'credential_ref':reference}})
            raise
        cleanup=self.retire(app_id,previous)
        return dict(connection=self.get(app_id,identity)['id'],status='CONFIGURED_UNTESTED',cleanup=cleanup)

    def stage(self,app_id,key):
        """Register crash recovery before touching protected storage."""
        reference=uid()
        with connection(self.store.path) as db:queue_retirement(db,app_id,reference,300)
        try:Vault().put(target(self.store,app_id,reference),{'api_key':key})
        except Exception:
            self.retire(app_id,{'data':{'credential_ref':reference}});raise
        return reference

    def previous(self,app_id,body):
        """Resolve only the selected app version before staging a replacement key."""
        previous=self.get(app_id,body['id']) if body['id'] else None
        if previous and previous['version']!=body['version']:raise Invalid('Connection changed; reload before editing')
        if not previous and body['version'] is not None:raise Invalid('New connection must not supply a version')
        return previous

    def commit(self,app_id,identity,data,previous):
        """Compare the same app-owned version inside the SQLite writer transaction."""
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE')
            current=db.execute('SELECT version FROM agent_connections WHERE app_id=? AND id=?',(app_id,identity)).fetchone()
            if previous and (current is None or current['version']!=previous['version']):raise Invalid('Connection changed during save')
            if not previous and current:raise Invalid('Connection identity already exists')
            self.activate_stage(db,app_id,data)
            if previous:queue_retirement(db,app_id,previous['data'].get('credential_ref'))
            version=previous['version']+1 if previous else 1
            db.execute('INSERT OR REPLACE INTO agent_connections VALUES(?,?,?,?,?,?,?,?)',
                (app_id,identity,version,canonical(data),'CONFIGURED_UNTESTED',None,previous['created'] if previous else now(),now()))

    def activate_stage(self,db,app_id,data):
        """Serialize active-key attachment against cleanup of an expired stage."""
        reference=data.get('credential_ref')
        if not reference:return
        staged=db.execute('SELECT 1 FROM agent_retirements WHERE app_id=? AND reference=?',(app_id,reference)).fetchone()
        if not staged or not Vault().get(target(self.store,app_id,reference)):raise Invalid('Protected key stage expired; save this connection again')
        db.execute('DELETE FROM agent_retirements WHERE app_id=? AND reference=?',(app_id,reference))

    def retire(self,app_id,previous):
        """Local removal does not imply revocation of a provider account or other tool."""
        reference=previous['data'].get('credential_ref') if previous else None
        if not reference:return 'NO_PRIOR_KEY'
        with connection(self.store.path) as db:queue_retirement(db,app_id,reference)
        try:self.clean_one(app_id,reference);return 'PRIOR_LOCAL_KEY_REMOVED'
        except Invalid:return 'LOCAL_KEY_CLEANUP_REQUIRED'

    def clean_one(self,app_id,reference):
        """Delete only queued retired keys; never remove an active app connection."""
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE')
            pending=db.execute('SELECT eligible FROM agent_retirements WHERE app_id=? AND reference=?',(app_id,reference)).fetchone()
            if pending is None or pending['eligible']>time.time():return
            active=db.execute("SELECT 1 FROM agent_connections WHERE app_id=? AND status!='DISCONNECTED' AND json_extract(data,'$.credential_ref')=?",(app_id,reference)).fetchone()
            if active:raise Invalid('Cleanup cannot remove an active provider key')
            Vault().delete(target(self.store,app_id,reference))
            db.execute('DELETE FROM agent_retirements WHERE app_id=? AND reference=?',(app_id,reference))

    def cleanup(self,app_id):
        """Retry app-owned stale-key cleanup after storage recovery or process restart."""
        self.store.app(app_id)
        with connection(self.store.path) as db:
            pending=[r['reference'] for r in db.execute('SELECT reference FROM agent_retirements WHERE app_id=? AND eligible<=? LIMIT 20',(app_id,time.time()))]
        for reference in pending:self.clean_one(app_id,reference)
        return dict(remaining=self.view(app_id)['cleanup_pending'],provider_revocation='NOT_PERFORMED')

    def disconnect(self,app_id,identity,body):
        """Disable execution first, keeping unrelated provider sessions signed in."""
        exact(body,('version',));row=self.get(app_id,identity)
        if row['version']!=body['version']:raise Invalid('Connection changed; reload before disconnecting')
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE')
            changed=db.execute("UPDATE agent_connections SET status='DISCONNECTED',version=version+1,updated=? WHERE app_id=? AND id=? AND version=?",(now(),app_id,identity,body['version'])).rowcount
            if not changed:raise Invalid('Connection changed during disconnect')
            queue_retirement(db,app_id,row['data'].get('credential_ref'))
        return dict(status='DISCONNECTED',cleanup=self.retire(app_id,row),provider_revocation='NOT_PERFORMED')

    def routes(self,app_id,body):
        """Pin app-owned routes; no implicit API fallback, purchase or provider swap."""
        exact(body,('version','mode','routes'))
        if body['mode'] not in ('subscription','byok','mixed') or not isinstance(body['routes'],dict) or set(body['routes'])-set(TASKS):
            raise Invalid('Choose subscription, BYOK or mixed task routing')
        self.validate_routes(app_id,body)
        self.store.app(app_id)
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE')
            current=db.execute('SELECT version FROM agent_routes WHERE app_id=?',(app_id,)).fetchone()
            version=current['version'] if current else 0
            if type(body['version']) is not int or body['version']!=version:raise Invalid('Routes changed; reload before saving')
            db.execute('INSERT OR REPLACE INTO agent_routes VALUES(?,?,?,?)',(app_id,version+1,canonical({'mode':body['mode'],'routes':body['routes']}),now()))
        return self.view(app_id)['routing']

    def validate_routes(self,app_id,body):
        """Validate each chosen app-owned provider without introducing a fallback."""
        for identity in body['routes'].values():
            if not identity:continue
            row=self.get(app_id,identity)
            if row['status']=='DISCONNECTED':raise Invalid('Reconnect this route before selecting it')
            if body['mode']!='mixed' and REGISTRY[row['data']['provider']]['mode']!=body['mode']:
                raise Invalid('Selected connection is outside the chosen access mode')

    def secret(self,app_id,row):
        """Resolve only the selected connection's protected key just before use."""
        reference=row['data'].get('credential_ref')
        if not reference:return None
        value=Vault().get(target(self.store,app_id,reference))
        if not value or set(value)!={'api_key'}:raise Invalid('Protected provider key is unavailable; reconnect this app profile')
        return value['api_key']


def detect(provider):
    """Explicit official status inspection returns no credential or executable paths."""
    from .agent_native import identity
    if not isinstance(provider,str) or provider not in NATIVE:raise Invalid('Choose a supported native adapter')
    found=identity(provider)
    return {key:found[key] for key in ('version','fingerprint','login_state','quota','account_identity')}
