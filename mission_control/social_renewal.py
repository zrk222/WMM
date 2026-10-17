"""Owned renewal leases: ambiguous rotating-token grants are never replayed."""
import time
from dataclasses import asdict
from .common import Invalid,canonical,now,uid
from .db import connection
from .social_connections import Connections,public
from .social_secrets import queue
from .social_auth import refresh
from .social_profiles import verify,selected_page


class Renewal:
    def __init__(self,store):self.store=store;self.accounts=Connections(store)

    def claim(self,app_id,identity,version):
        """A stale lease requires reconnect, since its refresh may have rotated tokens."""
        row=self.accounts.get(app_id,identity);lease=uid()
        self.eligible(row,version)
        clock=time.time()
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE');self.accounts.flows.check_config(db,app_id,row['provider'],row['config_version'])
            changed=db.execute("UPDATE social_connections SET lease=?,lease_until=?,status='RENEWING',updated=? WHERE app_id=? AND id=? AND version=? AND lease IS NULL AND status='CONNECTED_READ_TESTED'",
                (lease,clock+180,now(),app_id,identity,version)).rowcount
            if not changed:raise Invalid('Account is not ready for renewal; reconnect or reload')
        return row,lease

    def eligible(self,row,version):
        """Check actual grant lifetime and provider renewal rules before leasing."""
        if type(version) is not int or row['version']!=version:raise Invalid('Saved account changed; reload renewal status')
        if row['lease']:raise Invalid('Renewal is running or unconfirmed; inspect status before reconnecting')
        facts=row['data']['facts'];clock=time.time()
        if facts['renewal'] not in ('REFRESH_TOKEN','LONG_LIVED_TOKEN_REFRESH'):raise Invalid('This provider requires official browser reauthorization')
        if facts['expires_at'] is None or facts['expires_at']<=clock:raise Invalid('Saved access expired; reconnect through official login')
        if row['provider']=='instagram' and clock-facts['issued_at']<86400:raise Invalid('Instagram renewal is available after the token is at least 24 hours old')

    def alive(self,row,lease):
        current=self.accounts.get(row['app_id'],row['id'])
        if current['lease']!=lease or current['version']!=row['version'] or current['status']!='RENEWING' or current['lease_until']<=time.time():raise Invalid('Renewal was stopped or source changed; reconnect')
        with connection(self.store.path) as db:self.accounts.flows.check_config(db,row['app_id'],row['provider'],row['config_version'])

    def run(self,app_id,identity,version):
        """Only adopt a renewed token after the original subject and destination read back."""
        row,lease=self.claim(app_id,identity,version);ref=None
        try:
            config=self.accounts.setup.get(app_id,row['provider'])
            settings=self.accounts.secrets.load(app_id,row['provider'],config['secret_ref']) if config['secret_ref'] else {}
            credentials=self.accounts.secrets.load(app_id,row['provider'],row['secret_ref']);secret=settings.get('client_secret','')
            alive=lambda:self.alive(row,lease);alive()
            grant=refresh(config['data'],secret,credentials,row['data']['facts'],alive)
            found=verify(config['data'],secret,grant,alive)
            if found.subject_id!=row['subject_id']:raise Invalid('Renewed provider subject changed; reconnect')
            choices=[item for item in found.destinations if item['id']==row['data']['destination']['id']]
            if len(choices)!=1:raise Invalid('Renewed account no longer contains the selected destination; reconnect')
            alive();ref=self.accounts.secrets.stage(app_id,row['provider'],grant.credentials)
            self.commit(row,lease,ref,grant.facts,found,choices[0])
        except Exception:
            if ref:self.accounts.secrets.retire(app_id,row['provider'],ref)
            self.failed(row,lease)
            return dict(status='RECONNECT_REQUIRED',next_action='Reconnect through official login; an uncertain refresh is never repeated automatically.',existing_access='PRESERVED_UNCONFIRMED')
        self.accounts.secrets.retire(app_id,row['provider'],row['secret_ref'])
        return public(self.accounts.get(app_id,identity))

    def commit(self,row,lease,ref,facts,found,destination):
        """Compare the lease and source again inside the atomic adoption transaction."""
        app_id=row['app_id'];identity=row['id'];provider=row['provider']
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE');self.accounts.flows.check_config(db,app_id,provider,row['config_version'])
            current=self.accounts.get(app_id,identity)
            if current['lease']!=lease or current['version']!=row['version'] or current['status']!='RENEWING' or current['lease_until']<=time.time():raise Invalid('Saved account changed before renewal adoption')
            self.accounts.secrets.activate(db,app_id,provider,ref,['access_token'])
            data={**row['data'],'identity':asdict(found),'destination':destination,'facts':{**facts,'subject_id':found.subject_id},'last_read_at':now()}
            db.execute("UPDATE social_connections SET data=?,secret_ref=?,version=version+1,status='CONNECTED_READ_TESTED',expires=?,refresh_expires=?,renewed_at=?,lease=NULL,lease_until=0,updated=? WHERE app_id=? AND id=?",
                (canonical(data),ref,facts['expires_at'],facts['refresh_expires_at'],facts['issued_at'],now(),app_id,identity))
            queue(db,app_id,provider,row['secret_ref'])

    def failed(self,row,lease):
        """A failed owned attempt retains encrypted old access but disables auto renewal."""
        with connection(self.store.path) as db:
            db.execute("UPDATE social_connections SET status='RECONNECT_REQUIRED',lease=NULL,lease_until=0,version=version+1,updated=? WHERE app_id=? AND id=? AND version=? AND lease=?",
                       (now(),row['app_id'],row['id'],row['version'],lease))

    def recover(self):
        """A process restart never retries a possibly consumed rotating refresh grant."""
        with connection(self.store.path) as db:
            changed=db.execute("UPDATE social_connections SET status='RECONNECT_REQUIRED',lease=NULL,lease_until=0,version=version+1,updated=? WHERE status='RENEWING' AND lease IS NOT NULL AND lease_until<=?",(now(),time.time())).rowcount
        return changed

    def tick(self):
        """One bounded due renewal per worker tick, only already confirmed accounts."""
        self.recover()
        with connection(self.store.path) as db:
            rows=[dict(row) for row in db.execute("SELECT app_id,id,version,data FROM social_connections WHERE status='CONNECTED_READ_TESTED' AND lease IS NULL AND expires>? AND expires<=? ORDER BY expires LIMIT 20",(time.time(),time.time()+86400))]
        for row in rows:
            import json
            facts=json.loads(row['data'])['facts']
            if facts['renewal'] not in ('REFRESH_TOKEN','LONG_LIVED_TOKEN_REFRESH'):continue
            if facts['provider']=='instagram' and time.time()-facts['issued_at']<86400:continue
            try:self.run(row['app_id'],row['id'],row['version'])
            except Invalid:continue
            return True
        return False
