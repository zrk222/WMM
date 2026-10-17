"""Human-confirmed app/provider destinations, protected retention and read tests."""
import json,time
from dataclasses import asdict
from .common import Invalid,canonical,now,uid
from .db import connection
from .social_contract import exact,reference,account_id
from .social_flows import Flows
from .social_secrets import Secrets,queue
from .social_setup import Setup
from .social_tokens import Grant
from .social_profiles import verify,selected_page


def decoded(row):
    """Decode an internal scoped row, leaving protected references internal."""
    if row is None:raise Invalid('Social account does not belong to this app')
    value=dict(row);value['data']=json.loads(value['data']);return value


def public(row):
    """Operational secret addresses and renewal leases are never browser data."""
    return {key:row[key] for key in ('app_id','id','provider','config_version','version','subject_id','data','status','expires','refresh_expires','renewed_at','created','updated')}


class Connections:
    def __init__(self,store,port=8765):self.store=store;self.secrets=Secrets(store);self.setup=Setup(store,port);self.flows=Flows(store,port)

    def get(self,app_id,identity):
        self.store.app(app_id);reference(identity)
        with connection(self.store.path) as db:
            return decoded(db.execute('SELECT * FROM social_connections WHERE app_id=? AND id=?',(app_id,identity)).fetchone())

    def view(self,app_id):
        """Loading saved status never refreshes tokens or contacts a social provider."""
        self.store.app(app_id)
        with connection(self.store.path) as db:
            rows=[decoded(row) for row in db.execute('SELECT * FROM social_connections WHERE app_id=? ORDER BY created',(app_id,))]
        result=[]
        for row in rows:
            value=public(row);value['reconnect_required']=row['expires'] is not None and row['expires']<=time.time()
            result.append(value)
        return dict(accounts=result,publishing_implemented=False,automatic_ad_spend=False)

    def confirm(self,app_id,body):
        """An explicit destination and exact prior version are required to adopt access."""
        exact(body,('flow_id','destination_id','connection_id','version'))
        destination=account_id(body['destination_id']);flow=self.flows.get(app_id,body['flow_id'])
        if flow['status']!='AWAITING_DESTINATION' or flow['expires']<=time.time():raise Invalid('Destination selection expired or was already used; reconnect')
        choices=flow['data']['identity']['destinations'];matches=[item for item in choices if item['id']==destination]
        if len(matches)!=1:raise Invalid('Choose one of the verified provider destinations')
        if body['connection_id']:reference(body['connection_id'])
        if type(body['version']) is not int or body['version']<0:raise Invalid('Use the current saved-account version')
        credentials=self.secrets.load(app_id,flow['provider'],flow['secret_ref']);selected=matches[0]
        if flow['provider']=='facebook':
            cfg=self.setup.get(app_id,flow['provider']);settings=self.secrets.load(app_id,flow['provider'],cfg['secret_ref'])
            selected,page=selected_page(settings['client_secret'],credentials['access_token'],destination,
                                       lambda:self.selection_alive(app_id,flow))
            credentials={**credentials,'page_token':page}
        ref=self.secrets.stage(app_id,flow['provider'],credentials)
        try:identity,old=self.commit(app_id,flow,selected,ref,body)
        except Exception:self.secrets.retire(app_id,flow['provider'],ref);raise
        for prior in old:self.secrets.retire(app_id,flow['provider'],prior)
        return public(self.get(app_id,identity))

    def selection_alive(self,app_id,flow):
        current=self.flows.get(app_id,flow['id'])
        if current['status']!='AWAITING_DESTINATION' or current['expires']<=time.time():raise Invalid('Destination selection stopped or expired')
        with connection(self.store.path) as db:self.flows.check_config(db,app_id,flow['provider'],flow['config_version'])

    def commit(self,app_id,flow,selected,ref,body):
        """Serialize flow use, duplicate account checks and protected-grant attachment."""
        provider=flow['provider'];stamp=now();identity=body['connection_id'] or uid();old=[]
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE');self.flows.check_config(db,app_id,provider,flow['config_version'])
            current=db.execute('SELECT status,expires FROM social_flows WHERE app_id=? AND id=?',(app_id,flow['id'])).fetchone()
            if current['status']!='AWAITING_DESTINATION' or current['expires']<=time.time():raise Invalid('Destination selection already used or expired')
            prior=db.execute('SELECT * FROM social_connections WHERE app_id=? AND id=?',(app_id,identity)).fetchone()
            self.validate_adoption(db,app_id,flow,selected,identity,prior,body['version'])
            self.secrets.activate(db,app_id,provider,ref,['access_token'])
            facts=flow['data']['facts'];data=dict(identity=flow['data']['identity'],destination=selected,facts=facts,
                last_read_at=stamp,publishing_implemented=False,automatic_ad_spend=False)
            db.execute('INSERT OR REPLACE INTO social_connections VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (app_id,identity,provider,flow['config_version'],body['version']+1,data['identity']['subject_id'],canonical(data),ref,
                 'CONNECTED_READ_TESTED',facts['expires_at'],facts['refresh_expires_at'],facts['issued_at'],None,0,
                 prior['created'] if prior else stamp,stamp))
            db.execute("UPDATE social_flows SET status='CONNECTED',secret_ref=NULL,result=?,updated=? WHERE app_id=? AND id=?",(canonical({'connection_id':identity}),stamp,app_id,flow['id']))
            old.append(flow['secret_ref'])
            if prior:old.append(prior['secret_ref'])
            for value in old:queue(db,app_id,provider,value)
        return identity,old

    def validate_adoption(self,db,app_id,flow,selected,identity,prior,version):
        """A replacement needs the same subject and cannot duplicate another destination."""
        provider=flow['provider'];subject=flow['data']['identity']['subject_id']
        if (prior['version'] if prior else 0)!=version:raise Invalid('Saved account changed; reload before confirmation')
        if prior and (prior['provider']!=provider or prior['subject_id']!=subject):raise Invalid('Reconnection must preserve the same provider account; add a separate account instead')
        rows=db.execute("SELECT id,data FROM social_connections WHERE app_id=? AND provider=? AND subject_id=? AND id!=? AND status!='DISCONNECTED'",(app_id,provider,subject,identity)).fetchall()
        if any(json.loads(candidate['data'])['destination']['id']==selected['id'] for candidate in rows):
            raise Invalid('This account destination is already saved; explicitly select it for reconnection')

    def alive(self,row):
        current=self.get(row['app_id'],row['id'])
        if current['version']!=row['version'] or current['status']!='CONNECTED_READ_TESTED' or current['lease']:raise Invalid('Saved account changed, needs reconnection or is renewing; reload its status')
        if current['expires'] is not None and current['expires']<=time.time():raise Invalid('Saved account expired; reconnect through official login')
        with connection(self.store.path) as db:self.flows.check_config(db,row['app_id'],row['provider'],row['config_version'])

    def read_test(self,app_id,identity,version):
        """Read only the saved subject; never allow a test to adopt another account."""
        row=self.get(app_id,identity)
        if type(version) is not int or row['version']!=version:raise Invalid('Saved account changed; reload before testing')
        self.alive(row);cfg=self.setup.get(app_id,row['provider']);secret=self.secrets.load(app_id,row['provider'],cfg['secret_ref']) if cfg['secret_ref'] else {}
        credentials=self.secrets.load(app_id,row['provider'],row['secret_ref'])
        found=verify(cfg['data'],secret.get('client_secret',''),Grant(credentials,row['data']['facts']),lambda:self.alive(row))
        if found.subject_id!=row['subject_id'] or not any(item['id']==row['data']['destination']['id'] for item in found.destinations):raise Invalid('Saved account destination is no longer verified; reconnect')
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE');self.flows.check_config(db,app_id,row['provider'],row['config_version'])
            data={**row['data'],'identity':asdict(found),'last_read_at':now()}
            changed=db.execute("UPDATE social_connections SET data=?,version=version+1,status='CONNECTED_READ_TESTED',updated=? WHERE app_id=? AND id=? AND version=? AND status!='DISCONNECTED' AND lease IS NULL",(canonical(data),now(),app_id,identity,version)).rowcount
            if not changed:raise Invalid('Saved account changed during testing; reload')
        return public(self.get(app_id,identity))

    def disconnect(self,app_id,identity,version):
        """Remove only this local retained grant; provider-wide revocation is separate."""
        row=self.get(app_id,identity)
        if type(version) is not int:raise Invalid('Use the current saved-account version')
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE')
            changed=db.execute("UPDATE social_connections SET status='DISCONNECTED',secret_ref=NULL,version=version+1,lease=NULL,lease_until=0,updated=? WHERE app_id=? AND id=? AND version=?",(now(),app_id,identity,version)).rowcount
            if not changed:raise Invalid('Saved account changed; reload before disconnecting')
            queue(db,app_id,row['provider'],row['secret_ref'])
        cleanup=self.secrets.retire(app_id,row['provider'],row['secret_ref'])
        return dict(status='DISCONNECTED',cleanup=cleanup,provider_revocation='NOT_PERFORMED',next_action='Official provider settings can revoke access for all sessions if desired.')
