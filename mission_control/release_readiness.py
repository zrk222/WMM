"""Current selected-release facts; never a publication or authenticity certificate."""
from datetime import datetime, timezone
import re
from .common import Invalid, digest, iso_time
from .subscription_readiness import connection_problem


def attempt_matches(job, binding, app_id, version_id):
    """Scope attempts to one app, connection version and explicit Apple version."""
    data = job.get('data', {})
    return (job.get('app_id'), job.get('action'), data.get('connection_id'), data.get('connection_version'), data.get('options')) == (
        app_id, 'sync', binding['id'], binding['version'], {'operation':'release_inventory','version_id':version_id})


def latest_attempt(jobs, binding, app_id, version_id):
    """A failed or pending maximum attempt never falls back to an old success."""
    rows = [job for job in jobs if attempt_matches(job, binding, app_id, version_id)]
    return max(rows, key=lambda row:(row['created'],row['id'])) if rows else None


def report_problem(job, app_id, store_id, version_id):
    """Revalidate identity, source envelope, freshness and bounded report structure."""
    if job.get('status') != 'SUCCEEDED':
        return 'READ_PENDING' if job.get('status') in ('QUEUED','RUNNING') else 'READ_BLOCKED'
    report = job.get('result')
    if not isinstance(report, dict):
        return 'READ_BLOCKED'
    expected = (app_id,store_id,version_id,'app_store','release_inventory',False)
    actual = tuple(report.get(key) for key in ('app_id','store_app_id','version_id','provider','operation','external_writes'))
    if actual != expected or report.get('external_writes') is not False or not valid_hashes(report):
        return 'READ_BLOCKED'
    if not fresh_report(report):
        return 'STALE'
    if not isinstance(report.get('locales'),list) or len(report['locales'])>2400:
        return 'READ_BLOCKED'
    return None


def fresh_report(report):
    """Accept a provider observation only inside the explicit24-hour window."""
    try:
        age=(datetime.now(timezone.utc)-iso_time(report.get('observed_at'))).total_seconds()
        return 0 <= age <= 86400
    except (Invalid,TypeError,ValueError):
        return False


def valid_hashes(report):
    """Bind the exact ordered source pages without treating hashes as approvals."""
    pages = report.get('page_source_hashes')
    count = report.get('requests')
    if type(count) is not int or not 1 <= count <= 24 or not isinstance(pages,list) or len(pages)!=count:
        return False
    if any(not isinstance(value,str) or not re.fullmatch(r'[a-f0-9]{64}',value) for value in pages):
        return False
    return report.get('source_hash') == digest(pages)


def bound_selection(app, binding, selection):
    """Release labels are explicitly bound, never parsed to guess Apple IDs."""
    expected = (app['data'].get('release'),app['data'].get('locale'),str(app['data'].get('store_app_id')),binding['id'],binding['version'])
    actual = tuple(selection.get(key) for key in ('local_release','locale','store_app_id','connection_id','connection_version'))
    return actual == expected


def metadata_problem(locale):
    """Require typed explicit locale facts, not a precomputed pass assertion."""
    metadata = locale.get('metadata')
    if not isinstance(metadata,dict):
        return 'READ_BLOCKED','The saved locale is malformed. Read Apple data again.'
    missing = [key for key in ('description','keywords','supportUrl') if not isinstance(metadata.get(key),str) or not metadata[key].strip()]
    if missing:
        return 'METADATA_NEEDED','Complete locale metadata: '+', '.join(missing)+'.'
    return None


def sets_problem(sets):
    """Validate the fetched display collections before flattening file facts."""
    if not isinstance(sets,list):
        return 'READ_BLOCKED','The saved locale is malformed. Read Apple data again.'
    if not sets:
        return 'SCREENSHOTS_NEEDED','No screenshot sets were observed for the selected locale. Verify locale fallback or upload reviewed locale assets.'
    if any(not isinstance(row,dict) or row.get('coverage')!='COMPLETE' or not isinstance(row.get('screenshots'),list) for row in sets):
        return 'PARTIAL','Screenshot-set coverage is incomplete or malformed. Read current Apple data again.'
    return None


def media_problem(locale):
    """Derive file delivery from fetched sets, not screenshot authenticity claims."""
    sets = locale.get('screenshot_sets')
    problem = sets_problem(sets)
    if problem:
        return problem
    files = [file for row in sets for file in row['screenshots']]
    if not files:
        return 'SCREENSHOTS_NEEDED','The selected locale has no observed screenshot files.'
    if any(not isinstance(file,dict) or file.get('delivery_state')!='COMPLETE' for file in files):
        return 'FILES_PROCESSING','One or more screenshot files are not confirmed complete by Apple.'
    return None


def release_target_problem(report, selection):
    """Invalidate partial observations and a changed version or build identity."""
    if report.get('coverage')!='COMPLETE':
        return 'PARTIAL','Release inventory coverage is incomplete. Inspect uninspected resources before relying on the read.'
    build = report.get('build')
    identity = (report.get('version'),report.get('platform'),build.get('id') if isinstance(build,dict) else None)
    if identity != (selection.get('version'),selection.get('platform'),selection.get('build_id')):
        return 'RELEASE_CHANGED','The selected Apple version or attached build changed. Select the intended release again.'
    return None


def locale_problem(report, selection):
    """Require one exact locale without silently inferring language fallback."""
    locales = [row for row in report['locales'] if isinstance(row,dict) and row.get('locale')==selection['locale']]
    if len(locales)!=1:
        return 'LOCALE_NEEDED','The selected app locale is absent or duplicated in Apple data. Verify the exact locale.'
    if locales[0].get('coverage')!='COMPLETE':
        return 'PARTIAL','The selected locale was not completely inspected.'
    return metadata_problem(locales[0]) or media_problem(locales[0])


def review_problem(report, selection):
    """Binary processing and review states remain distinct from public availability."""
    build = report.get('build')
    if not isinstance(build,dict) or build.get('processing_state')!='VALID':
        return 'BUILD_NEEDED','Select a build processed as VALID by Apple, then verify the release again.'
    review = report.get('review_state')
    if review in ('WAITING_FOR_REVIEW','IN_REVIEW'):
        return 'REVIEW_PENDING','Apple review is pending. Prepare local work, but do not claim Apple approval or public availability.'
    if review!='READY_FOR_SALE':
        return 'STATUS_REVIEW_NEEDED','Inspect Apple status '+str(review or 'not supplied')+' before promoting the selected release.'
    return None


def inventory_state(report, selection):
    """Apply ordered named checks; a scoped pass never certifies publication."""
    for check in (release_target_problem,locale_problem,review_problem):
        problem = check(report,selection)
        if problem:
            return problem
    return 'INVENTORY_CHECKED','The selected release inventory meets its scoped checks. Public availability,authentic screenshots,billing and outcomes still need separate evidence.'


def readiness(app, records, jobs, statuses):
    """Project current source facts without networking, mutations or inferred readiness."""
    store_id = app['data'].get('store_app_id')
    base = dict(app_id=app['id'],store_app_id=store_id,inventory_verified=False,external_writes=False)
    if not store_id:
        return dict(base,state='NOT_APPLICABLE',reason='No App Store app is configured for this workspace.')
    rows = [row for row in records if row.get('app_id')==app['id'] and row.get('kind')=='connection' and row['data'].get('provider')=='app_store']
    if not rows:
        return dict(base,state='SETUP_NEEDED',reason='Connect this app to App Store Connect before inspecting its release.')
    binding = max(rows,key=lambda row:(row['updated'],row['id']))
    base.update(connection_id=binding['id'],connection_version=binding['version'])
    problem = connection_problem(binding,statuses,store_id)
    if problem:
        return dict(base,state='CONNECTION_BLOCKED',reason=problem)
    selection = app['data'].get('promotion_release')
    if not isinstance(selection,dict) or not bound_selection(app,binding,selection):
        return dict(base,state='SELECTION_NEEDED',reason='Inspect a current release and explicitly choose the version and build being promoted.')
    job = latest_attempt(jobs,binding,app['id'],selection.get('version_id'))
    if not job:
        return dict(base,state='READ_NEEDED',reason='Read inventory for the selected release using the current connection.')
    problem = report_problem(job,app['id'],str(store_id),selection.get('version_id'))
    base.update(job_id=job['id'],selection=selection)
    if problem:
        return dict(base,state=problem,reason='The latest selected-release read is unavailable,unfinished,stale or invalid. Inspect the run and read again.')
    report = job['result']
    state,reason = inventory_state(report,selection)
    return dict(base,state=state,reason=reason,report=report,inventory_verified=state=='INVENTORY_CHECKED')
