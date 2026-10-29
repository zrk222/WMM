"""Native App Store key setup and explicitly requested inventory reads."""
import json
import time
from .common import Invalid, canonical, digest, identifier, now
from .ios_bridge import decode_document, encode_response


def project_metrics(partitions):
    """Project already validated rows separately; never sum overlapping dimensions."""
    return [dict(provider='app_store',metric='download_events',date=row['date'],
                 count=row['count'],download_type=row['type'],source_type=row['source_type'],
                 dimensions=row['dimensions'],processing_date=row['processing_date'],
                 report_id=item['partition']['report_id'],event_data_finality=item['event_data_finality'])
            for item in partitions for row in item['instance']['rows']]


class NativeStoreConnection:
    def __init__(self, service, identities, vault_callback, signer_callback):
        self.service=service;self.identities=identities
        self.vault_callback=vault_callback;self.signer_callback=signer_callback

    def call(self,session,app_id,action,payload):
        from .connection_setup import Connections
        from .credential_vault import namespace
        from .ios_provider_access import NativeVault
        from .operation_authority import bound_owner,protected
        from .provider_auth import bound_native
        body=decode_document(payload);identifier(app_id)
        fields={'view':set(), 'history':set(), 'metrics':{'id'}, 'cleanup':set(), 'disconnect':{'id','version','confirm_disconnect'},
                'queue_inventory':{'connection_id','connection_version','request_key'}, 'run_inventory':{'id'},
                'queue_metrics':{'connection_id','connection_version','request_key','report_id'}, 'run_metrics':{'id'}}
        setup={'store_app_id','key_id','issuer_id','private_key','confirm_storage'}
        if not isinstance(body,dict):raise Invalid('Use a fixed native App Store action')
        if action=='setup':
            if not setup.issubset(body) or set(body)-setup-{'id','version'} or body['confirm_storage'] is not True:
                raise Invalid('Confirm protected storage and exact App Store setup')
        elif action not in fields or set(body)!=fields[action]:raise Invalid('Use the exact native App Store fields')
        user=self.identities.fresh(session);store=self.service.store
        envelope=dict(app_id=app_id,operation='native.store-connection.'+action,
                      input={} if action=='setup' else body)
        scope=namespace(store.path);prefix='AppGrowth/'+scope+'/'+app_id+'/app_store/'
        with bound_owner(store,envelope,self.identities,session,user):
            with protected(store,envelope):
                with bound_native(scope,app_id,lambda:NativeVault(self.vault_callback,prefix),self.signer_callback):
                    access=Connections(store)
                    if action=='view':
                        rows=[r for r in store.records(app_id) if r['kind']=='connection' and r['data'].get('provider')=='app_store']
                        statuses=access.statuses(app_id)
                        result={'connections':[{'id':r['id'],'version':r['version'],'store_app_id':r['data'].get('store_app_id'),
                                                'status':statuses.get(r['id'],{})} for r in rows], 'execution':'FOREGROUND_ONLY'}
                    elif action=='setup':
                        app=store.app(app_id)
                        if not isinstance(app['data'].get('store_app_id'),str) or app['data']['store_app_id']!=body['store_app_id']:
                            raise Invalid('Save the matching numeric App Store app ID in this workspace first')
                        result=access.setup(app_id,dict({k:v for k,v in body.items() if k!='confirm_storage'},provider='app_store'))
                    elif action=='cleanup':
                        from .provider_auth import LOCK
                        with LOCK:result=access.native_cleanup(app_id)
                    elif action=='disconnect':
                        if body['confirm_disconnect'] is not True:raise Invalid('Confirm local disconnect')
                        record=access.record(app_id,body['id'])
                        if record['data'].get('provider')!='app_store':raise Invalid('Select this app’s App Store connection')
                        result=access.disconnect(app_id,body['id'],body['version'])
                    elif action=='history':result=self.history(app_id,user)
                    elif action=='metrics':result=self.metrics(app_id,user,body['id'])
                    elif action in ('queue_inventory','queue_metrics'):result=self.queue(app_id,user,body,access,action=='queue_metrics')
                    else:result=self.run(app_id,user,body['id'],action=='run_metrics')
        return encode_response(result)

    def queue(self,app_id,user,body,access,metrics=False):
        from .worker import enqueue
        from .provider_reports import report_options
        app=self.service.store.app(app_id);record=access.record(app_id,body['connection_id'])
        if (record['version']!=body['connection_version'] or type(body['connection_version']) is not int
                or record['data'].get('provider')!='app_store' or record['data'].get('auth_mode')!='managed_key'
                or record['data'].get('store_app_id')!=app['data'].get('store_app_id')
                or digest({'kind':'connection','data':record['data'],'source':record['source']})!=record['hash']):
            raise Invalid('Select this app’s current protected App Store connection')
        options={'operation':'analytics_metrics_latest','report_id':body['report_id']} if metrics else {'operation':'analytics_reports'}
        report_options('app_store',options)
        data=dict(connection_id=record['id'],connection_version=record['version'],connection_hash=record['hash'],
                  manifest_version=app['version'],native_owner=user['principal'],native_runtime='IOS_STORE_INVENTORY_V1', options=options)
        return enqueue(self.service.store,app_id,'sync',data,body['request_key'])

    def history(self,app_id,user):
        from .db import connection
        from .worker import json_job
        with connection(self.service.store.path) as db:
            rows=db.execute("SELECT * FROM jobs WHERE app_id=? AND action='sync' ORDER BY created DESC LIMIT 500",(app_id,)).fetchall()
            items=[]
            for row in rows:
                job=json_job(row);data=job['data'];options=data.get('options')
                if (data.get('native_runtime')=='IOS_STORE_INVENTORY_V1' and data.get('native_owner')==user['principal']
                        and isinstance(options,dict) and options.get('operation') in ('analytics_reports','analytics_metrics_latest')):
                    items.append(job)
                    if len(items)==100:break
        return {'jobs':items,'execution':'FOREGROUND_ONLY'}

    def metrics(self,app_id,user,identity):
        from .apple_metrics_store import read_partition
        from .db import connection
        from .worker import json_job
        with connection(self.service.store.path) as db:
            row=self.owned(db,app_id,user,identity);job=json_job(row)
            if (job['status']!='SUCCEEDED' or job['data']['options']['operation']!='analytics_metrics_latest'
                    or not isinstance(job['result'],dict)):
                raise Invalid('Choose a completed native download metrics read')
            result=job['result'];data=job['data']
            keys=('store_app_id','report_id','report_family','granularity')
            if any(key not in result for key in keys) or not isinstance(result.get('partitions'),list):
                raise Invalid('Saved metrics receipt is incomplete')
            partitions=[]
            for entry in result['partitions']:
                if not isinstance(entry,dict) or 'event_date' not in entry:raise Invalid('Saved metrics receipt is invalid')
                key=dict(app_id=app_id,connection_id=data['connection_id'],connection_version=data['connection_version'],
                         event_date=entry['event_date'],**{name:result[name] for name in keys})
                item=read_partition(self.service.store.path,key)
                if item is None:raise Invalid('Saved metrics partition is unavailable')
                partitions.append(item)
            return {'job_id':identity,'partitions':partitions,'observations':project_metrics(partitions),
                    'interpretation':result['interpretation']}

    def owned(self,db,app_id,user,identity):
        row=db.execute('SELECT * FROM jobs WHERE app_id=? AND id=?',(app_id,identity)).fetchone()
        if not row:raise Invalid('Inventory job was not found in this app')
        data=json.loads(row['data'])
        options=data.get('options')
        if row['action']!='sync' or data.get('native_runtime')!='IOS_STORE_INVENTORY_V1' or data.get('native_owner')!=user['principal'] or not isinstance(options,dict):
            raise PermissionError('Use this owner’s native inventory job')
        from .provider_reports import report_options
        report_options('app_store',options)
        if options['operation'] not in ('analytics_reports','analytics_metrics_latest'):
            raise PermissionError('Use a native App Store read-only analytics job')
        app=db.execute('SELECT version,data FROM apps WHERE id=?',(app_id,)).fetchone()
        record=db.execute("SELECT version,hash,data,source FROM records WHERE app_id=? AND id=? AND kind='connection'",(app_id,data['connection_id'])).fetchone()
        if (not app or app['version']!=data['manifest_version'] or not record or record['version']!=data['connection_version']
                or record['hash']!=data['connection_hash']):raise Invalid('App or connection changed; queue a fresh inventory read')
        binding=json.loads(record['data']);manifest=json.loads(app['data'])
        if (binding.get('provider')!='app_store' or binding.get('auth_mode')!='managed_key'
                or binding.get('store_app_id')!=manifest.get('store_app_id')
                or digest({'kind':'connection','data':binding,'source':record['source']})!=record['hash']):
            raise Invalid('App Store connection is no longer active for this app')
        return row

    def run(self,app_id,user,identity,metrics=False):
        from .db import connection
        from .provider_auth import bound_page_guard
        from .provider_reports import PreparedAppleMetrics
        from .worker import json_job,process,_persist_prepared_apple_metrics
        store=self.service.store
        with connection(store.path) as db:
            db.execute('BEGIN IMMEDIATE');row=self.owned(db,app_id,user,identity)
            operation=json.loads(row['data'])['options']['operation']
            if operation!=('analytics_metrics_latest' if metrics else 'analytics_reports'):
                raise Invalid('Use the matching native report action')
            if row['status'] in ('SUCCEEDED','BLOCKED','CANCELLED'):return json_job(row)
            if row['status']=='RUNNING' and row['lease']>time.time():raise Invalid('Inventory read is already running')
            if row['attempts']>=3:raise Invalid('Inventory recovery limit reached; queue a new read')
            db.execute("UPDATE jobs SET status='RUNNING',attempts=attempts+1,lease=?,updated=? WHERE id=?",(time.time()+60,now(),identity))
            job=json_job(db.execute('SELECT * FROM jobs WHERE id=?',(identity,)).fetchone())
        def check_page():
            with connection(store.path) as db:
                row=self.owned(db,app_id,user,identity)
                if row['status']!='RUNNING' or row['attempts']!=job['attempts'] or row['lease']<=time.time():
                    raise PermissionError('Inventory job lease or state changed before the next page')
        try:
            with bound_page_guard(check_page):result=process(store,job)
            status='SUCCEEDED'
        except PermissionError:raise
        except Exception:result={'error':'App Store read failed; review connection and retry explicitly'};status='BLOCKED'
        with connection(store.path) as db:
            row=self.owned(db,app_id,user,identity)
            if isinstance(result,PreparedAppleMetrics):
                if not metrics:raise Invalid('Inventory cannot save metrics')
                result,status=_persist_prepared_apple_metrics(db,store,job,result)
                if status is None:raise Invalid('Metrics job lease changed; inspect before retrying')
            else:db.execute('BEGIN IMMEDIATE')
            row=self.owned(db,app_id,user,identity)
            if row['status']!='RUNNING' or row['attempts']!=job['attempts'] or row['lease']<=time.time():
                raise Invalid('Inventory job lease or state changed; inspect before retrying')
            db.execute('UPDATE jobs SET status=?,result=?,lease=0,updated=? WHERE id=?',
                       (status,canonical(result),now(),identity))
            return json_job(db.execute('SELECT * FROM jobs WHERE id=?',(identity,)).fetchone())
