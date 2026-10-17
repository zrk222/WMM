"""Current-version catalog guidance, never entitlement or release authority."""
from datetime import datetime, timezone
from .common import Invalid, iso_time

REPAIRS = {
    'MISSING_METADATA': 'Complete the product’s missing information in App Store Connect, then read the catalog again.',
    'READY_TO_SUBMIT': 'Review the product information and submit it through Apple’s review workflow. It has not been approved.',
    'WAITING_FOR_REVIEW': 'Apple review is pending. Monitor the submission; do not claim approval.',
    'IN_REVIEW': 'Apple is reviewing this product. Monitor the submission.',
    'PENDING_BINARY_APPROVAL': 'The associated app build needs Apple approval. Check the app submission.',
    'DEVELOPER_ACTION_NEEDED': 'Open Apple’s review message and resolve the requested changes.',
    'REJECTED': 'Review Apple’s rejection reason, fix the product and submit through the review workflow.',
    'DEVELOPER_REMOVED_FROM_SALE': 'Review whether this product should be offered again. Verify availability separately.',
    'REMOVED_FROM_SALE': 'Review Apple’s availability notice before promoting this product.',
    'APPROVED': 'Catalog approved. Still verify localized prices, purchase, entitlement and restore in the app.',
}


def validate_catalog_scope(app, binding):
    """Match configured app identity before queueing and again before networking."""
    store_id = app['data'].get('store_app_id')
    if not store_id or str(store_id) != binding.get('store_app_id'):
        raise Invalid('The App Store connection must match this workspace’s Store app ID.')


def product_guidance(state) -> object:
    """Unknown future statuses require review rather than assuming approval."""
    return REPAIRS.get(state, 'Review this unfamiliar Apple status in App Store Connect before promoting this product.')


def matches(job, binding, app_id):
    """Select catalog attempts for the exact app and current connection version."""
    data = job.get('data', {})
    return (job.get('app_id'), job.get('action'), data.get('connection_id'), data.get('connection_version'), data.get('options')) == (
        app_id, 'sync', binding['id'], binding['version'], {'operation': 'subscription_catalog'})


def current_catalog(binding, jobs, app_id, store_id) -> object:
    """The latest current-connection attempt wins, including failure or cancellation."""
    candidates = [job for job in jobs if matches(job, binding, app_id)]
    if not candidates:
        return dict(state='READ_NEEDED', reason='Read the current subscription catalog before verifying monetization.')
    job = max(candidates, key=lambda item: (item['created'], item['id']))
    if job['status'] != 'SUCCEEDED':
        return dict(state='READ_PENDING' if job['status'] in ('QUEUED', 'RUNNING') else 'READ_BLOCKED',
                    reason=(job.get('result') or {}).get('error') or 'The latest catalog read did not complete. Inspect the saved run and retry.', job_id=job['id'])
    report = job.get('result') or {}
    expected = (app_id, store_id, 'app_store', 'subscription_catalog')
    actual = tuple(report.get(k) for k in ('app_id', 'store_app_id', 'provider', 'operation'))
    if actual != expected or not report.get('source_hash') or not isinstance(report.get('rows'), list):
        return dict(state='READ_BLOCKED', reason='The saved catalog does not match this app. Read it again.', job_id=job['id'])
    return checked_report(report, job['id'])


def checked_report(report, job_id):
    """Check bounded coverage and freshness before allowing a catalog prerequisite."""
    try:
        age = (datetime.now(timezone.utc) - iso_time(report.get('observed_at'))).total_seconds()
    except (Invalid, TypeError, ValueError):
        age = -1
    rows = report['rows']
    if len(rows) > 1000 or any(not isinstance(row, dict) for row in rows):
        return dict(state='READ_BLOCKED', reason='The saved catalog is malformed. Read it again.', job_id=job_id)
    state, reason = catalog_state(report, age)
    return dict(state=state, reason=reason, job_id=job_id, report=report,
                products=[dict(row, next_step=product_guidance(row.get('state'))) for row in rows])


def catalog_state(report, age):
    """Keep stale, partial, empty and unapproved observations distinct."""
    if not 0 <= age <= 86400:
        return 'STALE', 'This catalog observation has expired. Read current Apple data again.'
    if report.get('coverage') != 'COMPLETE':
        return 'PARTIAL', 'Catalog coverage is incomplete. Inspect the read limits before relying on it.'
    if not report['rows']:
        return 'NO_SUBSCRIPTIONS', 'Apple returned no subscriptions. Confirm the app’s billing model before promotion.'
    if any(row.get('state') != 'APPROVED' for row in report['rows']):
        return 'ACTION_NEEDED', 'One or more products need review, missing information or Apple approval.'
    return 'CATALOG_APPROVED', 'Catalog products are approved. In-app billing verification is still required.'


def connection_problem(binding, statuses, store_id):
    """Mismatched, disconnected or unrecoverable keys cannot reuse old proof."""
    if binding['data'].get('store_app_id') != str(store_id):
        return 'The connection targets a different Store app ID. Correct it before reading.'
    status = statuses.get(binding['id'], {}).get('status')
    if status in ('DISCONNECTED', 'RECONNECT_REQUIRED', 'PROTECTED_STORAGE_UNAVAILABLE') or binding['data'].get('auth_mode') == 'disconnected':
        return 'Reconnect App Store Connect, then read the catalog again.'
    return None


def readiness(app, records, jobs, statuses) -> object:
    """Derive app-isolated billing guidance without trusting old connection results."""
    store_id = app['data'].get('store_app_id')
    base = dict(app_id=app['id'], store_app_id=store_id, purchase_verified=False,
                restore_verified=False, prices_verified=False, products=[], external_writes=False)
    if not store_id:
        return dict(base, state='NOT_APPLICABLE', catalog_verified=False, reason='No App Store app is configured for this workspace.')
    bindings = [r for r in records if r['kind'] == 'connection' and r['data'].get('provider') == 'app_store' and r['app_id'] == app['id']]
    if not bindings:
        return dict(base, state='SETUP_NEEDED', catalog_verified=False, reason='Connect App Store Connect to read this app’s subscriptions.')
    binding = max(bindings, key=lambda row: (row['updated'], row['id']))
    base.update(connection_id=binding['id'], connection_version=binding['version'])
    blocked = connection_problem(binding, statuses, store_id)
    if blocked:
        return dict(base, state='CONNECTION_BLOCKED', catalog_verified=False, reason=blocked)
    result = current_catalog(binding, jobs, app['id'], str(store_id))
    return dict(base, **result, catalog_verified=result['state'] == 'CATALOG_APPROVED')
