"""Expiring app-bound setup proposals; public observations never approve themselves."""
from datetime import timedelta
import hashlib
import json
from .common import Invalid, canonical, digest, iso_time, now, uid
from .db import connection
from .store import audit
from .aeo_transport import PublicReader, public_url, text, AGENT
from .aeo_inspection import inspect_page
from .setup_parse import extract


def binding(app, body):
    """No caller-supplied URL, source text, credentials or destination enters discovery."""
    if not isinstance(body, dict) or set(body) != {'app_id', 'app_version', 'app_hash', 'confirm_read'}:
        raise Invalid('Review the current app setup discovery request')
    if body['confirm_read'] is not True or type(body['app_version']) is not int:
        raise Invalid('Approve the read of this app public website')
    if body['app_id'] != app['id'] or body['app_version'] != app['version'] or body['app_hash'] != digest(app['data']):
        raise Invalid('App setup changed; refresh and review discovery again')
    return dict(app_id=app['id'], app_version=app['version'], app_hash=digest(app['data']), website=app['data'].get('website') or '')


class PageTap:
    """Reuse the exact page bytes inspected under the existing robots/network budget."""
    def __init__(self, reader):
        self.reader = reader
        self.resources = []

    def read(self, value, cap, permit=None):
        resource = self.reader.read(value, cap, permit=permit)
        self.resources.append(resource)
        return resource

    def project(self, report):
        """Only a matching observed page produces fields; robots/sitemaps cannot substitute."""
        if report['state'] != 'OBSERVED':
            return None
        page = report['page']
        resource = next((row for row in self.resources if row.get('url') == page['url'] and row.get('sha256') == page['sha256']), None)
        if resource is None or hashlib.sha256(resource['body']).hexdigest() != page['sha256']:
            raise Invalid('Checked source bytes do not match the recorded page')
        return extract(text(resource), resource['url'])


def recover(projection, state):
    """Explicit agent-owned follow-through choices remain available for absent evidence."""
    missing = projection['missing_fields'] if projection else ['name', 'job', 'audience', 'locale', 'store_app_id', 'android_package', 'release', 'activation']
    return [dict(action='retry_discovery', title='Read the current public website again', enabled=state != 'WEBSITE_REQUIRED'),
            dict(action='review_app_setup', title='Review the saved website and selected app facts', enabled=True),
            dict(action='collect_sources', title='Collect configured app-owned provider evidence', enabled=True),
            dict(action='review_evidence', title='Verify unresolved inputs: ' + ', '.join(missing), enabled=True)]


def inspect(bound, reader=None):
    """Persist only public projections and hashes; never page bodies or raw transport errors."""
    if not bound['website']:
        return dict(state='WEBSITE_REQUIRED', projection=None, source_url=None, source_sha256=None,
                    inspection_hash=None, recovery=recover(None, 'WEBSITE_REQUIRED'))
    target = public_url(bound['website'])
    tap = PageTap(reader or PublicReader())
    report = inspect_page(target, tap)
    projection = tap.project(report)
    source = report.get('page') or {}
    return dict(state=report['state'], projection=projection, source_url=source.get('url') or target,
                source_sha256=source.get('sha256'), inspection_hash=digest(report),
                robots=report['policies'][AGENT]['state'], recovery=recover(projection, report['state']))


def decode(row):
    """Proposals are app-owned immutable observations until an explicit apply/delete action."""
    if row is None:
        raise Invalid('Setup proposal does not belong to this app')
    result = dict(row)
    result['data'] = json.loads(result['data'])
    result['result'] = json.loads(result['result']) if result['result'] else None
    if result['hash'] != digest(result['data']):
        raise Invalid('Setup proposal integrity changed; rediscover before approval')
    return result


def proposal(db, app_id, identity):
    return decode(db.execute('SELECT * FROM setup_proposals WHERE app_id=? AND id=?', (app_id, identity)).fetchone())


def capacity(db, app_id):
    """Saved drafts have a finite bound and an explicit local deletion recovery path."""
    count = db.execute('SELECT COUNT(*) FROM setup_proposals WHERE app_id=?', (app_id,)).fetchone()[0]
    if count >= 64:
        raise Invalid('Setup draft storage is full. Review saved drafts and remove one before rediscovery.')


def currentness(app, row):
    """Expired or changed sources cannot become current through a read or restart."""
    if row['state'] == 'APPLIED':
        return 'APPLIED'
    if iso_time(row['expires']) <= iso_time(now()):
        return 'EXPIRED'
    expected = row['data']['binding']
    if app['version'] != expected['app_version'] or digest(app['data']) != expected['app_hash']:
        return 'STALE_APP'
    return row['state']


def brief(app, row):
    """Workspace refreshes carry small history entries; candidate details load on demand."""
    data = row['data']
    projection = data['projection'] or {}
    return dict(app_id=row['app_id'], id=row['id'], hash=row['hash'], state=row['state'],
                currentness=currentness(app, row), created=row['created'], expires=row['expires'], result=row['result'],
                source_url=data['source_url'], source_state=data['state'],
                suggested_fields=[key for key, values in projection.get('fields', {}).items() if values],
                ambiguous_fields=projection.get('ambiguous_fields', []))


class SetupDiscovery:
    """Source first, review second; no self-approved manifest or external writes."""
    def __init__(self, store):
        self.store = store

    def start(self, app_id, body, reader=None):
        app = self.store.app(app_id)
        bound = binding(app, body)
        with connection(self.store.path) as db:
            capacity(db, app_id)
        observed = inspect(bound, reader)
        stamp = now()
        data = dict(binding=bound, observed_at=stamp, **observed,
                    ownership='NOT_VERIFIED', external_writes=False, authority='NO_EXECUTION_AUTHORITY')
        state = 'PENDING' if observed['projection'] and any(observed['projection']['fields'].values()) else 'NEEDS_RESOLUTION'
        row = dict(app_id=app_id, id=uid(), data=data, hash=digest(data), state=state, result=None,
                   created=stamp, expires=(iso_time(stamp) + timedelta(seconds=3600)).isoformat())
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE')
            current = db.execute('SELECT data,version FROM apps WHERE id=?', (app_id,)).fetchone()
            if current['version'] != bound['app_version'] or digest(json.loads(current['data'])) != bound['app_hash']:
                raise Invalid('App changed during discovery; discard this read and retry the current source')
            capacity(db, app_id)
            db.execute('INSERT INTO setup_proposals VALUES(?,?,?,?,?,?,?,?,?)',
                       (app_id, row['id'], canonical(data), row['hash'], state, None, stamp, row['expires'], stamp))
            audit(db, app_id, 'setup.proposal_created', dict(id=row['id'], hash=row['hash'], state=state))
        return row

    def list(self, app_id):
        app = self.store.app(app_id)
        with connection(self.store.path) as db:
            rows = [decode(row) for row in db.execute('SELECT * FROM setup_proposals WHERE app_id=? ORDER BY created DESC,id', (app_id,))]
        return dict(app_version=app['version'], app_hash=digest(app['data']), website=app['data'].get('website') or '',
                    proposals=[brief(app, row) for row in rows],
                    capacity=64, authority='NO_EXECUTION_AUTHORITY', external_writes=False)

    def get(self, app_id, identity):
        app = self.store.app(app_id)
        if not isinstance(identity, str) or len(identity) != 36:
            raise Invalid('Choose one saved setup proposal')
        with connection(self.store.path) as db:
            row = proposal(db, app_id, identity)
        return dict(row, currentness=currentness(app, row))

    def delete(self, app_id, body):
        self.store.app(app_id)
        if not isinstance(body, dict) or set(body) != {'id', 'hash', 'confirm_delete'} or body['confirm_delete'] is not True:
            raise Invalid('Confirm the exact local draft to remove; saved app setup is retained')
        if not isinstance(body['id'], str) or len(body['id']) != 36 or not isinstance(body['hash'], str) or len(body['hash']) != 64:
            raise Invalid('Choose the exact saved draft and hash before removing it')
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE')
            row = proposal(db, app_id, body['id'])
            if row['hash'] != body['hash']:
                raise Invalid('Setup draft changed; reload before removing it')
            db.execute('DELETE FROM setup_proposals WHERE app_id=? AND id=?', (app_id, row['id']))
            audit(db, app_id, 'setup.proposal_deleted', dict(id=row['id'], hash=row['hash']))
        return dict(status='DELETED', app_setup_preserved=True, provider_credentials_changed=False)
