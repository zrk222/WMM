"""Explicit local promotion target selection; all source checks share one transaction."""
import json
from .common import Invalid,canonical,now,digest
from .db import connection
from .store import decode,app_data,audit
from .release_readiness import latest_attempt,report_problem


def selection_body(body):
    """Reject ambiguous or unbound local selection requests."""
    keys = {'manifest_version','connection_id','connection_version','job_id','report_hash'}
    if not isinstance(body,dict) or set(body)!=keys:
        raise Invalid('Choose the exact release from the current workspace')
    if any(type(body[key]) is not int or body[key]<1 for key in ('manifest_version','connection_version')):
        raise Invalid('Refresh the app and connection versions before selecting a release')
    if any(not isinstance(body[key],str) or not body[key] for key in ('connection_id','job_id','report_hash')):
        raise Invalid('The selected release source is incomplete')


def source_rows(db, app_id, body):
    """Resolve exact app,connection and saved job inside the atomic selection lock."""
    app = db.execute('SELECT * FROM apps WHERE id=?',(app_id,)).fetchone()
    binding = db.execute("SELECT * FROM records WHERE app_id=? AND id=? AND kind='connection'",(app_id,body['connection_id'])).fetchone()
    job = db.execute('SELECT * FROM jobs WHERE app_id=? AND id=?',(app_id,body['job_id'])).fetchone()
    if app is None or binding is None or job is None:
        raise Invalid('The selected release does not belong to this workspace')
    app,binding,job = decode(app),decode(binding),decode(job)
    if app['version']!=body['manifest_version'] or binding['version']!=body['connection_version']:
        raise Invalid('App or connection changed. Refresh before selecting a release')
    if binding['data'].get('provider')!='app_store' or binding['data'].get('auth_mode')=='disconnected':
        raise Invalid('Reconnect this app to App Store Connect first')
    if str(app['data'].get('store_app_id'))!=binding['data'].get('store_app_id'):
        raise Invalid('The App Store connection targets a different app')
    return app,binding,job


def validate_job(db, app, binding, job, body):
    """A source hash and current maximum attempt are required, not just a saved ID."""
    options = job.get('data',{}).get('options',{})
    version_id = options.get('version_id')
    jobs = [decode(row) for row in db.execute('SELECT * FROM jobs WHERE app_id=?',(app['id'],))]
    latest = latest_attempt(jobs,binding,app['id'],version_id)
    if latest is None or latest['id']!=job['id']:
        raise Invalid('A newer attempt controls the selected version. Inspect the latest read')
    if report_problem(job,app['id'],str(app['data']['store_app_id']),version_id):
        raise Invalid('The selected release read is incomplete,stale or invalid. Read current Apple data')
    report = job['result']
    if report['source_hash']!=body['report_hash']:
        raise Invalid('Release source hash changed. Reopen the exact saved result')
    return report


def selected(app,binding,job,report):
    """Bind user intent to exact identities without parsing the human release label."""
    build = report.get('build')
    if not app['data'].get('release') or not app['data'].get('locale'):
        raise Invalid('Set an exact local release label and tested locale before selecting')
    return dict(version_id=report['version_id'],version=report.get('version'),platform=report.get('platform'),
                build_id=build.get('id') if isinstance(build,dict) else None,
                build_number=build.get('number') if isinstance(build,dict) else None,
                local_release=app['data']['release'],locale=app['data']['locale'],store_app_id=report['store_app_id'],
                connection_id=binding['id'],connection_version=binding['version'],
                selected_job_id=job['id'],selected_source_hash=report['source_hash'])


def choose(store, app_id, body):
    """Commit local selection plus audit or roll back both; never call a provider."""
    selection_body(body)
    with connection(store.path) as db:
        db.execute('BEGIN IMMEDIATE')
        app,binding,job = source_rows(db,app_id,body)
        report = validate_job(db,app,binding,job,body)
        target = selected(app,binding,job,report)
        data = app_data({**app['data'],'promotion_release':target})
        db.execute('UPDATE apps SET data=?,version=version+1,updated=? WHERE id=?',(canonical(data),now(),app_id))
        audit(db,app_id,'release.selected',{'version_id':target['version_id'],'job_id':job['id'],'source_hash':report['source_hash']})
    return dict(app_id=app_id,manifest_version=app['version']+1,selection=target,external_writes=False)
