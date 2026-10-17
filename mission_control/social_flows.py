"""Single-use official consent handoffs, bounded state and safe cancellation."""
import json,time,hashlib
from .common import Invalid,canonical,now,uid
from .db import connection
from .social_contract import provider_id,reference,opaque
from .social_auth import fresh_state,authorization
from .social_setup import Setup
from .social_secrets import Secrets,queue


def decoded(row):
    """Internal rows are never returned directly through the public HTTP surface."""
    if row is None:raise Invalid('Social login is unavailable for this app; start a new official login')
    value=dict(row);value['data']=json.loads(value['data']);value['result']=json.loads(value['result']) if value['result'] else None
    return value


def public(row):
    """Expose progress and sanitized choices without state hashes or secret addresses."""
    return {key:row[key] for key in ('id','app_id','provider','config_version','data','status','result','expires','created','updated')}


class Flows:
    def __init__(self,store,port=8765):self.store=store;self.setup=Setup(store,port);self.secrets=Secrets(store)

    def get(self,app_id,identity):
        self.store.app(app_id);reference(identity)
        with connection(self.store.path) as db:
            return decoded(db.execute('SELECT * FROM social_flows WHERE app_id=? AND id=?',(app_id,identity)).fetchone())

    def start(self,app_id,provider,version):
        """A fresh PKCE verifier is protected; only its state hash enters SQLite."""
        config=self.setup.get(app_id,provider)
        if type(version) is not int or version!=config['version']:raise Invalid('Provider setup changed; reload before official login')
        state,hashed,verifier=fresh_state();ref=self.secrets.stage(app_id,provider,{'verifier':verifier})
        identity=uid();stamp=now();expires=time.time()+600
        try:
            with connection(self.store.path) as db:
                db.execute('BEGIN IMMEDIATE');self.check_config(db,app_id,provider,version)
                count=db.execute("SELECT COUNT(*) FROM social_flows WHERE app_id=? AND status IN ('PENDING','EXCHANGING','AWAITING_DESTINATION')",(app_id,)).fetchone()[0]
                if count>=8:raise Invalid('Finish or cancel an existing social login before starting another')
                self.secrets.activate(db,app_id,provider,ref,['verifier'])
                db.execute('INSERT INTO social_flows VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                           (identity,app_id,provider,version,hashed,ref,'{}','PENDING',None,expires,stamp,stamp))
        except Exception:self.secrets.retire(app_id,provider,ref);raise
        return dict(flow_id=identity,provider=provider,status='PENDING',expires=expires,
                    authorization_url=authorization(config['data'],state,verifier),browser='DEFAULT_SYSTEM_BROWSER',
                    note='Review the official provider screen, then confirm the detected account in Mission Control.')

    def check_config(self,db,app_id,provider,version):
        row=db.execute('SELECT version,status FROM social_configs WHERE app_id=? AND provider=?',(app_id,provider)).fetchone()
        if row is None or row['version']!=version or row['status']=='DISCONNECTED':raise Invalid('Provider setup changed; start a fresh official login')

    def claim(self,provider,state):
        """Consume state exactly once before any credential-bearing token operation."""
        provider_id(provider);opaque(state,'OAuth state',128,43);hashed=hashlib.sha256(state.encode()).hexdigest()
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE')
            row=decoded(db.execute('SELECT * FROM social_flows WHERE provider=? AND state_hash=?',(provider,hashed)).fetchone())
            if row['status']!='PENDING':raise Invalid('This social login callback was already used; return to its saved progress')
            if row['expires']<=time.time():raise Invalid('Social login expired; start a fresh official login')
            self.check_config(db,row['app_id'],provider,row['config_version'])
            db.execute("UPDATE social_flows SET status='EXCHANGING',updated=? WHERE id=? AND status='PENDING'",(now(),row['id']))
        row['status']='EXCHANGING';return row

    def alive(self,row):
        """Recheck source and cancellation before and after each external operation."""
        current=self.get(row['app_id'],row['id'])
        if current['status']!='EXCHANGING' or current['expires']<=time.time():raise Invalid('Social login stopped or expired; start a new official login')
        with connection(self.store.path) as db:self.check_config(db,row['app_id'],row['provider'],row['config_version'])

    def finish(self,row,status,result,ref=None,data=None):
        """Only the currently owned exchange can attach staged credentials."""
        app_id=row['app_id'];provider=row['provider'];old=None
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE')
            current=decoded(db.execute('SELECT * FROM social_flows WHERE app_id=? AND id=?',(app_id,row['id'])).fetchone())
            if current['status']!='EXCHANGING':raise Invalid('Social login was stopped; the existing connection is preserved')
            self.check_config(db,app_id,provider,row['config_version'])
            if current['expires']<=time.time():raise Invalid('Social login expired before verification; reconnect')
            if ref:self.secrets.activate(db,app_id,provider,ref,['access_token'])
            old=current['secret_ref'];queue(db,app_id,provider,old)
            db.execute('UPDATE social_flows SET status=?,secret_ref=?,data=?,result=?,updated=? WHERE app_id=? AND id=?',
                       (status,ref,canonical(data or {}),canonical(result),now(),app_id,row['id']))
        self.secrets.retire(app_id,provider,old)
        return public(self.get(app_id,row['id']))

    def stop(self,app_id,identity,status='CANCELLED'):
        """Cancellation never changes a retained account or revokes a provider login."""
        row=self.get(app_id,identity)
        if status not in ('CANCELLED','UNCONFIRMED','EXPIRED'):raise Invalid('Unsupported social recovery state')
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE')
            changed=db.execute("UPDATE social_flows SET status=?,result=?,updated=? WHERE app_id=? AND id=? AND status IN ('PENDING','EXCHANGING','AWAITING_DESTINATION')",
                  (status,canonical(dict(next_action='RECONNECT',existing_connection='PRESERVED')),now(),app_id,identity)).rowcount
            if changed:queue(db,app_id,row['provider'],row['secret_ref'],300 if row['status']=='EXCHANGING' else 0)
        if changed and row['status']!='EXCHANGING':self.secrets.retire(app_id,row['provider'],row['secret_ref'])
        return public(self.get(app_id,identity))

    def expire(self,app_id):
        """A read-time recovery sweep handles expired or process-interrupted flows."""
        self.store.app(app_id)
        with connection(self.store.path) as db:
            rows=[dict(row) for row in db.execute("SELECT id,status FROM social_flows WHERE app_id=? AND expires<=? AND status IN ('PENDING','EXCHANGING','AWAITING_DESTINATION') LIMIT 20",(app_id,time.time()))]
        for row in rows:self.stop(app_id,row['id'],'UNCONFIRMED' if row['status']=='EXCHANGING' else 'EXPIRED')
        return len(rows)
