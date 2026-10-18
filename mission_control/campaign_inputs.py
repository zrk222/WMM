"""Agent-selected fixed provider reads, bound to current app and source versions."""
from datetime import datetime, timezone, timedelta
import uuid
from .common import Invalid, canonical, digest, now, uid
from .db import connection
from .worker import json_job
from .marketing_agent_manifest import operating_manifest, authorize_read


def enqueue_task(db,app_id,task):
    """Validate one binding and preserve idempotency inside the caller transaction."""
    binding = db.execute("SELECT version FROM records WHERE app_id=? AND id=? AND kind='connection'",
                         (app_id, task['data']['connection_id'])).fetchone()
    if binding is None or binding['version'] != task['data']['connection_version']:
        raise Invalid('Connection changed before collection; refresh')
    stamp = now()
    db.execute('INSERT OR IGNORE INTO jobs(id,app_id,action,data,status,created,updated,request_key) VALUES(?,?,?,?,?,?,?,?)',
               (uid(), app_id, 'sync', canonical(task['data']), 'QUEUED', stamp, stamp, task['request_key']))
    saved = db.execute('SELECT action,data FROM jobs WHERE app_id=? AND request_key=?',
                       (app_id, task['request_key'])).fetchone()
    if saved['action'] != 'sync' or saved['data'] != canonical(task['data']):
        raise Invalid('Collection request identity conflicts with saved work')


def task_options(app, record):
    """Use saved intent only; never guess a release from a human label."""
    options = [None]
    if record['data']['provider'] == 'app_store':
        options += [{'operation':'reviews'}, {'operation':'subscription_catalog'}]
        selected = app['data'].get('promotion_release') or {}
        if (selected.get('connection_id') == record['id'] and
            selected.get('connection_version') == record['version'] and
            selected.get('local_release') == app['data'].get('release') and
            selected.get('locale') == app['data'].get('locale')):
            from .provider_reports import report_options
            option = {'operation':'release_inventory', 'version_id':selected.get('version_id')}
            report_options('app_store', option)
            options.append(option)
    return options


def usable_binding(app, data):
    """A saved identity is not authority to borrow another app's source."""
    return (data.get('provider') in ('app_store', 'apple_ads') and
            data.get('auth_mode') != 'disconnected' and
            bool(app['data'].get('store_app_id')) and
            data.get('store_app_id') == str(app['data']['store_app_id']))


def derive_tasks(app, records, policy_hash):
    """Bound the fixed action space independently of connection count."""
    tasks, excluded = [], []
    bindings = sorted((r for r in records if r['kind'] == 'connection'), key=lambda r:r['id'])
    for record in bindings:
        data = record['data']
        if not usable_binding(app,data):
            excluded.append({'connection_id':record['id'], 'reason':'Unsupported, disconnected or not bound to this app Store ID'})
            continue
        if len(tasks) >= 12:
            excluded.append({'connection_id':record['id'], 'reason':'Collection limit reached; additional sources remain uncollected'})
            continue
        for options in task_options(app, record):
            if len(tasks) >= 12:
                excluded.append({'connection_id':record['id'], 'reason':'Collection limit reached; additional reads remain uncollected'})
                break
            task = dict(connection_id=record['id'], connection_version=record['version'],
                        manifest_version=app['version'],agent_policy_sha256=policy_hash)
            if options is not None:
                task['options'] = options
            authorize_read(app, data, task)
            tasks.append({'operation':options['operation'] if options else 'identity_inventory',
                          'provider':data['provider'], 'data':task})
    return tasks, excluded


def build_plan(app, records, hour):
    """Derive bounded reads without network access, credentials or side effects."""
    if any(r['app_id'] != app['id'] for r in records):
        raise Invalid('Campaign sources belong to a different app')
    policy=operating_manifest(app)
    policy_hash=digest(policy)
    tasks,excluded=derive_tasks(app,records,policy_hash)
    source = dict(app_id=app['id'], manifest_version=app['version'], hour=hour,
                  tasks=tasks, excluded=excluded, operating_manifest=policy, policy_sha256=policy_hash)
    source_hash = digest(source)
    for task in tasks:
        task['request_key'] = 'campaign-inputs-'+digest(dict(source=source_hash, data=task['data']))
    return dict(source, source_hash=source_hash, schema='growth.campaign-inputs.v1',
                status='READY_TO_COLLECT' if tasks else 'SOURCE_ACCESS_REQUIRED',
                summary='Collect current facts from saved app-owned connections',
                external_writes=False, spend_minor=0,
                next_actions=['Collect supported app-owned facts' if tasks else 'Review source access or establish another permitted evidence source',
                              'Verify collected results before using them as campaign proof'],
                artifacts=[],
                agent_remaining=['Verify the advertised app journeys',
                                 'Collect consented measurement and mature outcome/cost evidence',
                                 'Prepare and verify authentic creative and channel execution'],
                limits='Provider reads only; queued work is not evidence of a completed campaign')


class CampaignInputs:
    def __init__(self, store):
        self.store = store

    def preview(self, app_id):
        """Show derived sources and durable job status; do not request a provider."""
        hour = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H')
        plan = build_plan(self.store.app(app_id), self.store.records(app_id), hour)
        from .source_retry import project
        plan['retry_candidates']=[]
        plan['next_collection_at']=(datetime.fromisoformat(hour+':00:00+00:00')+timedelta(hours=1)).isoformat()
        with connection(self.store.path) as db:
            for task in plan['tasks']:
                row = db.execute('SELECT * FROM jobs WHERE app_id=? AND request_key=?',
                                 (app_id, task['request_key'])).fetchone()
                task['job'] = json_job(row) if row else None
                candidate=project(db,app_id,task,plan['operating_manifest']['recovery']['max_manual_source_retries'])
                if candidate is not None:plan['retry_candidates'].append(candidate)
        plan['artifacts']=[dict(job_id=t['job']['id'],status=t['job']['status']) for t in plan['tasks'] if t['job']]
        if plan['artifacts']:
            plan['status']='COLLECTION_IN_PROGRESS' if any(a['status'] in ('QUEUED','RUNNING') for a in plan['artifacts']) else 'COLLECTION_RESULTS_AVAILABLE'
        return plan

    def start(self, app_id, body):
        """Atomically enqueue only exact current fixed reads; replays preserve results."""
        if not isinstance(body, dict) or set(body) != {'manifest_version', 'source_hash'}:
            raise Invalid('Use the current campaign input collection proposal')
        plan = self.preview(app_id)
        if (type(body['manifest_version']) is not int or
            body['manifest_version'] != plan['manifest_version'] or body['source_hash'] != plan['source_hash']):
            raise Invalid('App or campaign sources changed; refresh the collection proposal')
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE')
            app = db.execute('SELECT version FROM apps WHERE id=?', (app_id,)).fetchone()
            if app is None or app['version'] != plan['manifest_version']:
                raise Invalid('App changed before collection; refresh')
            for task in plan['tasks']:
                enqueue_task(db,app_id,task)
        return self.preview(app_id)

    def retry(self, app_id, parameters, request_key):
        """A separate exact approval can replace failed reads, never reset them."""
        from .source_retry import enqueue
        try:valid=str(uuid.UUID(request_key))==request_key
        except (ValueError,TypeError,AttributeError):valid=False
        if not valid:
            raise Invalid('Use the canonical source retry request identity')
        self.store.app(app_id)
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE')
            plan=self.preview(app_id)
            return enqueue(db,app_id,plan,parameters,request_key,enqueue_task)
