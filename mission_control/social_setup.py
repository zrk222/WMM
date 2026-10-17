"""Agent-prepared official developer setup and app-isolated protected configuration."""
import json,os
from .common import Invalid,canonical,now
from .db import connection
from .social_contract import provider_id,configuration,exact
from .social_registry import PROVIDERS,catalog
from .social_secrets import Secrets,queue


def decoded(row):
    """Internal config retains an opaque reference, never a secret value."""
    if row is None:raise Invalid('Prepare this provider setup before connecting')
    value=dict(row);value['data']=json.loads(value['data']);return value


class Setup:
    def __init__(self,store,port=8765):self.store=store;self.port=port;self.secrets=Secrets(store)

    def get(self,app_id,provider):
        """Require the app scope even for internal credential reference lookup."""
        self.store.app(app_id);provider_id(provider)
        with connection(self.store.path) as db:
            return decoded(db.execute('SELECT * FROM social_configs WHERE app_id=? AND provider=?',(app_id,provider)).fetchone())

    def view(self,app_id):
        """No vault or environment reads are triggered by simply rendering a page."""
        self.store.app(app_id)
        with connection(self.store.path) as db:
            rows=[decoded(row) for row in db.execute('SELECT * FROM social_configs WHERE app_id=? ORDER BY provider',(app_id,))]
        for row in rows:row['protected_secret']=bool(row.pop('secret_ref'))
        return dict(providers=catalog(),configurations=rows,publication_implemented=False,automatic_ad_spend=False)

    def packet(self,app_id,provider,native=False):
        """Populate known app facts and official steps; never invent a developer app."""
        app=self.store.app(app_id)['data'];provider_id(provider)
        if type(native) is not bool or (native and provider!='linkedin'):raise Invalid('Native enablement applies only to LinkedIn')
        from .social_contract import callback
        entry=PROVIDERS[provider];local=callback(provider,native,self.port)
        from .social_contract import relay_base
        base=relay_base(app.get('social_callback_base_url',''))
        prepared=local or (base+'/cb/'+provider if base else '')
        extra={'facebook':'Use Facebook Login for Business and select only the Pages for this app.',
               'instagram':'Use Instagram API with Instagram Login and a professional Business or Creator account.',
               'tiktok':'Enable Desktop Login Kit, register the exact displayed loopback callback and request user.info.basic.',
               'linkedin':'Enable Sign In with LinkedIn using OpenID Connect. Native PKCE additionally requires LinkedIn approval.'}[provider]
        return dict(provider=provider,app_id=app_id,app_name=app['name'],website=app.get('website',''),
            suggested_developer_name=app['name']+' Marketing',official_setup=entry['setup'],protocol_source=entry['docs'],
            redirect_uri=prepared,redirect_needed='EXACT_LOOPBACK' if local else 'DEPLOYED_HTTPS_CALLBACK_RELAY',
            scopes=list(entry['scopes']),native_enabled=native,secret_required=not native,
            steps=[extra,'Create or select the developer app owned by this product.',
                   'Register the displayed callback. Meta and LinkedIn web flows need the separate HTTPS callback relay.',
                   'Review provider permissions and required app review before authorizing production accounts.',
                   'Approve this app-specific configuration, then use official login and confirm the detected destination.'],
            login_retention='Protected local credentials with provider-supported renewal; reconnect when the provider requires it.',
            no_publication_or_spending=True)

    def discover(self,app_id,provider):
        """Only four exact selected-app variables; return public setup and presence."""
        self.store.app(app_id);provider_id(provider)
        prefix='GROWTH_'+app_id.replace('-','_').upper()+'_'+provider.upper()+'_'
        client=os.environ.get(prefix+'CLIENT_ID','');redirect=os.environ.get(prefix+'REDIRECT_URI','')
        native=os.environ.get(prefix+'NATIVE_ENABLED','false')
        if native not in ('true','false'):raise Invalid('Selected app native-enabled setting must be true or false')
        secret=os.environ.get(prefix+'CLIENT_SECRET','')
        body=dict(provider=provider,client_id=client,client_secret=secret,redirect_uri=redirect,native_enabled=native=='true',version=0)
        if not client:return dict(status='SETUP_REQUIRED',packet=self.packet(app_id,provider),secret_present=False)
        data=configuration(body,self.port)
        return dict(status='DISCOVERED_NOT_ACTIVE',configuration=data,secret_present=bool(secret),
                    environment_prefix=prefix,requires_approval=True)

    def save(self,app_id,body):
        """Exact version compare prevents replacing another tab's approved setup."""
        self.store.app(app_id);data=configuration(body,self.port);provider=data['provider']
        ref=self.secrets.stage(app_id,provider,{'client_secret':body['client_secret']}) if body['client_secret'] else None
        try:old=self.commit(app_id,data,ref,body['version'])
        except Exception:
            if ref:self.secrets.retire(app_id,provider,ref)
            raise
        if old:self.secrets.retire(app_id,provider,old)
        return dict(provider=provider,status='CONFIGURED_UNTESTED',version=body['version']+1,
                    next_action='OFFICIAL_LOGIN',existing_connections='PRESERVED_RECONNECT_REQUIRED_IF_CONFIG_CHANGED')

    def commit(self,app_id,data,ref,expected):
        """Attach staged configuration atomically and invalidate unfinished old flows."""
        provider=data['provider'];stamp=now()
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE')
            previous=db.execute('SELECT * FROM social_configs WHERE app_id=? AND provider=?',(app_id,provider)).fetchone()
            if (previous['version'] if previous else 0)!=expected:raise Invalid('Provider setup changed; reload and approve the current version')
            if ref:self.secrets.activate(db,app_id,provider,ref,['client_secret'])
            pending=db.execute("SELECT secret_ref,status FROM social_flows WHERE app_id=? AND provider=? AND status IN ('PENDING','EXCHANGING','AWAITING_DESTINATION')",(app_id,provider)).fetchall()
            for row in pending:queue(db,app_id,provider,row['secret_ref'],300 if row['status']=='EXCHANGING' else 0)
            db.execute("UPDATE social_flows SET status='CONFIG_CHANGED',updated=? WHERE app_id=? AND provider=? AND status IN ('PENDING','EXCHANGING','AWAITING_DESTINATION')",(stamp,app_id,provider))
            db.execute('INSERT OR REPLACE INTO social_configs VALUES(?,?,?,?,?,?,?,?)',
                       (app_id,provider,expected+1,canonical(data),ref,'CONFIGURED_UNTESTED',previous['created'] if previous else stamp,stamp))
            db.execute("UPDATE social_connections SET status='RECONNECT_REQUIRED',version=version+1,lease=NULL,lease_until=0,updated=? WHERE app_id=? AND provider=? AND status!='DISCONNECTED'",(stamp,app_id,provider))
            if previous:queue(db,app_id,provider,previous['secret_ref'])
            return previous['secret_ref'] if previous else None

    def approve_discovered(self,app_id,body):
        """Re-read only the selected environment values and compare the public preview."""
        exact(body,('provider','configuration','version'))
        current=self.discover(app_id,body['provider'])
        if current.get('configuration')!=body['configuration']:raise Invalid('Discovered setup changed; inspect the current preview')
        data=current['configuration'];prefix=current['environment_prefix']
        fields={key:data[key] for key in ('provider','client_id','redirect_uri','native_enabled')}
        return self.save(app_id,{**fields,'client_secret':os.environ.get(prefix+'CLIENT_SECRET',''),'version':body['version']})
