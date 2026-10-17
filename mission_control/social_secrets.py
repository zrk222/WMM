"""App/provider-scoped native secret fields with crash-safe retirement references."""
import time
from .common import Invalid,identifier,uid
from .db import connection
from .credential_vault import Vault,namespace
from .social_registry import SECRET_FIELDS
from .social_contract import provider_id,reference,opaque


def name(store,app_id,provider,ref,field):
    """A caller cannot construct addresses outside its own fixed credential namespace."""
    identifier(app_id);provider_id(provider);reference(ref)
    if field not in SECRET_FIELDS:raise Invalid('Unsupported social credential field')
    return '/'.join(('SocialGrowth',namespace(store.path),app_id,provider,ref,field))


def queue(db,app_id,provider,ref,delay=0):
    """Only opaque metadata enters SQLite; no token or app secret enters audit data."""
    if ref:
        reference(ref);provider_id(provider)
        db.execute('INSERT OR REPLACE INTO social_retirements VALUES(?,?,?,?)',(app_id,provider,ref,time.time()+delay))


def active(db,app_id,provider,ref):
    """An active config, pending flow or retained connection protects its secret."""
    configs=db.execute("SELECT 1 FROM social_configs WHERE app_id=? AND provider=? AND secret_ref=? AND status!='DISCONNECTED'",(app_id,provider,ref)).fetchone()
    flows=db.execute("SELECT 1 FROM social_flows WHERE app_id=? AND provider=? AND secret_ref=? AND status IN ('PENDING','EXCHANGING','AWAITING_DESTINATION')",(app_id,provider,ref)).fetchone()
    connections=db.execute("SELECT 1 FROM social_connections WHERE app_id=? AND provider=? AND secret_ref=? AND status!='DISCONNECTED'",(app_id,provider,ref)).fetchone()
    return bool(configs or flows or connections)


class Secrets:
    def __init__(self,store):self.store=store

    def stage(self,app_id,provider,values):
        """Register interrupted-write recovery before protecting any individual field."""
        self.store.app(app_id);provider_id(provider)
        if not isinstance(values,dict) or not values or set(values)-set(SECRET_FIELDS):raise Invalid('Use supported social credential fields')
        for value in values.values():opaque(value)
        ref=uid()
        with connection(self.store.path) as db:queue(db,app_id,provider,ref,300)
        try:
            for field,value in values.items():Vault().put(name(self.store,app_id,provider,ref,field),{'value':value})
        except Exception:
            self.retire(app_id,provider,ref);raise
        return ref

    def load(self,app_id,provider,ref):
        """Read only fixed fields in the requested app/provider scope, never a raw path."""
        self.store.app(app_id);provider_id(provider);reference(ref)
        values={}
        for field in SECRET_FIELDS:
            value=Vault().get(name(self.store,app_id,provider,ref,field))
            if value is None:continue
            if not isinstance(value,dict) or set(value)!={'value'}:raise Invalid('Protected social credentials need reconnection')
            values[field]=opaque(value['value'])
        if not values:raise Invalid('Protected social credentials are unavailable; reconnect this account')
        return values

    def activate(self,db,app_id,provider,ref,required):
        """Serialize attachment against cleanup of an expired secret-writing stage."""
        if active(db,app_id,provider,ref):raise Invalid('Protected social stage is already attached')
        pending=db.execute('SELECT 1 FROM social_retirements WHERE app_id=? AND provider=? AND reference=?',(app_id,provider,ref)).fetchone()
        if pending is None:raise Invalid('Protected social setup expired; prepare it again')
        values=self.load(app_id,provider,ref)
        if not set(required)<=set(values):raise Invalid('Required protected social credentials are unavailable')
        db.execute('DELETE FROM social_retirements WHERE app_id=? AND provider=? AND reference=?',(app_id,provider,ref))

    def retire(self,app_id,provider,ref):
        """Keep failed removal recoverable; this never revokes other provider sessions."""
        if not ref:return 'NO_PRIOR_SECRET'
        self.store.app(app_id);provider_id(provider);reference(ref)
        with connection(self.store.path) as db:queue(db,app_id,provider,ref)
        try:self.clean_one(app_id,provider,ref);return 'LOCAL_SECRET_REMOVED'
        except Invalid:return 'LOCAL_CLEANUP_REQUIRED'

    def clean_one(self,app_id,provider,ref):
        """Only a queued inactive bundle is removable, including partially written stages."""
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE')
            pending=db.execute('SELECT eligible FROM social_retirements WHERE app_id=? AND provider=? AND reference=?',(app_id,provider,ref)).fetchone()
            if pending is None or pending['eligible']>time.time():return
            if active(db,app_id,provider,ref):raise Invalid('Cleanup cannot remove active social access')
            for field in SECRET_FIELDS:Vault().delete(name(self.store,app_id,provider,ref,field))
            db.execute('DELETE FROM social_retirements WHERE app_id=? AND provider=? AND reference=?',(app_id,provider,ref))

    def cleanup(self,app_id):
        """Bound recovery to twenty app-owned bundles per explicit recovery action."""
        self.store.app(app_id)
        with connection(self.store.path) as db:
            pending=[dict(r) for r in db.execute('SELECT provider,reference FROM social_retirements WHERE app_id=? AND eligible<=? LIMIT 20',(app_id,time.time()))]
        for row in pending:self.clean_one(app_id,row['provider'],row['reference'])
        with connection(self.store.path) as db:remaining=db.execute('SELECT COUNT(*) FROM social_retirements WHERE app_id=?',(app_id,)).fetchone()[0]
        return dict(remaining=remaining,provider_revocation='NOT_PERFORMED')
