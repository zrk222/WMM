"""Read-only, app-scoped Apple analytics readiness; metadata is never a metric."""
from datetime import date
import re
from urllib.parse import urlsplit
from .common import Invalid, required

BASE = 'https://api.appstoreconnect.apple.com'
REPORTS = frozenset(('App Downloads Standard', 'App Sessions Standard',
    'App Store Purchases Standard', 'App Store Discovery and Engagement Standard',
    'App Store Installation and Deletion Standard'))


def identity(value):
    """Allow opaque Apple resource identities without path or query delimiters."""
    value = required(value, 'Analytics resource identity', 200)
    if not re.fullmatch(r'[A-Za-z0-9-]{1,200}', value):
        raise Invalid('Invalid analytics resource identity')
    return value


def resource(row, kind):
    """Require a typed resource with attributes before accepting its identity."""
    if not isinstance(row, dict) or row.get('type') != kind or not isinstance(row.get('attributes'), dict):
        raise Invalid('Apple analytics returned an invalid resource')
    return identity(row.get('id')), row['attributes']


def next_page(payload, path, seen):
    """Keep every authenticated pagination read on the exact scoped collection."""
    links = payload.get('links')
    if not isinstance(links, dict):
        raise Invalid('Apple analytics pagination coverage is missing')
    link = links.get('next')
    if link is None:
        return None
    if not isinstance(link, str):
        raise Invalid('Invalid Apple analytics pagination')
    parsed = urlsplit(link)
    if parsed.scheme != 'https' or parsed.netloc != 'api.appstoreconnect.apple.com' or parsed.path != path or parsed.fragment or link in seen:
        raise Invalid('Unsafe or repeating Apple analytics pagination')
    return link


def collection(reader, path, kind):
    """Read at most three pages of one hundred typed resources; report truncation."""
    url = BASE + path + '?limit=100'
    seen, rows = set(), {}
    for _ in range(3):
        seen.add(url)
        payload = reader.read(url)
        page = payload.get('data')
        if not isinstance(page, list) or len(page) > 100:
            raise Invalid('Apple analytics page exceeds its contract')
        for row in page:
            key, _ = resource(row, kind)
            if key in rows and rows[key] != row:
                raise Invalid('Conflicting duplicate Apple analytics resource')
            rows[key] = row
        url = next_page(payload, path, seen)
        if url is None:
            break
    return list(rows.values()), url is None


def relationship(row, name, kind, key):
    """Reject supplied parent relationships contradicting a scoped collection."""
    relationships = row.get('relationships', {})
    if not isinstance(relationships, dict):
        raise Invalid('Invalid analytics request relationships')
    app = relationships.get(name, {})
    if not isinstance(app, dict):
        raise Invalid('Invalid analytics request app relationship')
    linked = app.get('data')
    if linked is not None and linked != {'type': kind, 'id': key}:
        raise Invalid('Analytics request belongs to another app')


def active_request(rows, store_id):
    """Select exactly one active ongoing request; never silently choose a snapshot."""
    active = []
    for row in rows:
        key, attributes = resource(row, 'analyticsReportRequests')
        relationship(row, 'app', 'apps', store_id)
        if attributes.get('accessType') not in ('ONGOING', 'ONE_TIME_SNAPSHOT') or type(attributes.get('stoppedDueToInactivity')) is not bool:
            raise Invalid('Invalid analytics request state')
        if attributes['accessType'] == 'ONGOING' and not attributes['stoppedDueToInactivity']:
            active.append(key)
    if len(active) > 1:
        raise Invalid('Multiple ongoing analytics requests require explicit source review')
    return active[0] if active else None


def instance(row, report_id):
    """Project dated report metadata without interpreting it as observed app usage."""
    key, attributes = resource(row, 'analyticsReportInstances')
    relationship(row, 'analyticsReport', 'analyticsReports', report_id)
    processing = required(attributes.get('processingDate'), 'Report processing date', 10)
    try:
        if date.fromisoformat(processing).isoformat() != processing:
            raise ValueError()
    except ValueError:
        raise Invalid('Invalid analytics processing date') from None
    if attributes.get('granularity') not in ('DAILY', 'WEEKLY', 'MONTHLY'):
        raise Invalid('Invalid analytics report granularity')
    return dict(id=key, processing_date=processing, granularity=attributes['granularity'])


def inspect_reports(reader, rows, request_id):
    """Inspect the five declared marketing report families with explicit omissions."""
    selected, complete = [], True
    available = set()
    for row in rows:
        key, attributes = resource(row, 'analyticsReports')
        relationship(row, 'analyticsReportRequest', 'analyticsReportRequests', request_id)
        name = required(attributes.get('name'), 'Analytics report name', 300)
        if name in available:
            raise Invalid('Duplicate analytics report names require explicit source review')
        available.add(name)
        if name not in REPORTS:
            continue
        values, covered = collection(reader, '/v1/analyticsReports/' + key + '/instances', 'analyticsReportInstances')
        selected.append(dict(id=key, name=name, instances=[instance(value, key) for value in values],
            coverage='COMPLETE' if covered else 'PARTIAL'))
        complete = complete and covered
    return selected, complete, sorted(REPORTS - available)


def verify_app(reader, store_id):
    """Verify a numeric app target before traversing any analytics collections."""
    if not isinstance(store_id, str) or not re.fullmatch(r'[0-9]{1,30}', store_id):
        raise Invalid('Analytics store app identity must be numeric')
    app = reader.read(BASE + '/v1/apps/' + store_id)
    data = app.get('data')
    if not isinstance(data, dict) or data.get('id') != store_id or data.get('type') != 'apps':
        raise Invalid('Apple analytics returned a different app identity')


def read_analytics(reader, store_id):
    """Discover source-bound report readiness; creating streams is never a read."""
    verify_app(reader, store_id)
    requests, request_coverage = collection(reader, '/v1/apps/' + store_id + '/analyticsReportRequests', 'analyticsReportRequests')
    selected = active_request(requests, store_id)
    result = dict(operation='analytics_reports', request_id=selected, reports=[], rows=[],
        metric_observations=None, coverage='COMPLETE' if request_coverage else 'PARTIAL',
        missing_report_types=sorted(REPORTS), status='REPORT_SETUP_REQUIRED' if request_coverage else 'REQUEST_INVENTORY_PARTIAL',
        interpretation='Report metadata is not downloads, sales, retention or measured lift. Bulk metric ingestion remains separate.')
    if not selected:
        return result
    reports, report_coverage = collection(reader, '/v1/analyticsReportRequests/' + selected + '/reports', 'analyticsReports')
    values, instance_coverage, missing = inspect_reports(reader, reports, selected)
    result.update(reports=values, missing_report_types=missing,
        unselected_report_count=len(reports)-len(values),
        coverage='COMPLETE' if request_coverage and report_coverage and instance_coverage else 'PARTIAL',
        status='METRIC_DOWNLOAD_REQUIRED' if any(value['instances'] for value in values) else 'WAITING_FOR_REPORTS')
    return result
