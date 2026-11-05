"""Read-only owner context and history for the Organic Video policy panel."""
from datetime import datetime, timezone
import json
import re

from .agent_grants import app_scope
from .campaign_contract import exact
from .common import Invalid, canonical, digest, iso_time
from .creative_briefs import bound_record, latest_proof
from .db import connection
from .managed_media_store import derivative_snapshot
from .operation_authority import PROTECTED, check
from .organic_video_policy import _authority, _saved
from .review_access import member
from .hypit_jobs import saved as saved_render

PAGE_SIZE = 100
MAX_OFFSET = 2000
REQUEST_HASH = re.compile(r"^[0-9a-f]{64}$")


def _authorize(db, store, app_id, actor, operation, body):
    """Require the matching protected owner operation and current app membership."""
    context = PROTECTED.get()
    if not context:
        raise PermissionError('An exact protected owner policy read is required')
    admitted = _authority(db, store, app_id, operation, body, True)
    if check(db, admitted) != actor:
        raise PermissionError('Caller identity differs from the protected owner')
    role = member(db, app_id, actor, 'OWNER')
    if role['role'] != 'OWNER':
        raise PermissionError('Only the current app owner can read organic policy context')
    return role


def _has_table(db, name):
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def _require_saved(row, label):
    try:
        saved = _saved(row)
        if not REQUEST_HASH.fullmatch(row['request_hash']):
            raise Invalid(label + ' request hash is invalid')
        return saved
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        raise Invalid(label + ' history integrity changed') from None


def _context_page_choices(db, app_id):
    pages = []
    if not _has_table(db, 'social_connections') or not _has_table(db, 'social_configs'):
        return pages
    stamp = datetime.now(timezone.utc).timestamp()
    rows = db.execute("""SELECT * FROM social_connections WHERE app_id=? AND provider='facebook'
        AND status='CONNECTED_READ_TESTED' ORDER BY created,id""", (app_id,)).fetchall()
    for row in rows:
        if row['lease'] or (row['expires'] is not None and row['expires'] <= stamp):
            continue
        config = db.execute("SELECT version,status FROM social_configs WHERE app_id=? AND provider='facebook'",
                            (app_id,)).fetchone()
        if not config or config['version'] != row['config_version'] or config['status'] == 'DISCONNECTED':
            continue
        try:
            data = json.loads(row['data'])
            if canonical(data) != row['data']:
                raise Invalid('Facebook connection metadata integrity changed')
            destination = data.get('destination')
            if not isinstance(destination, dict) or not isinstance(destination.get('id'), str):
                raise Invalid('Facebook Page selection is unavailable')
            item = dict(connection_id=row['id'], page_id=destination['id'],
                        binding=dict(version=row['version'], config_version=row['config_version'], data_hash=digest(data)))
            label = destination.get('name') or destination.get('label')
            if isinstance(label, str) and 0 < len(label) <= 200 and not re.search(r'[\x00-\x1f\x7f-\x9f\u202a-\u202e\u2066-\u2069]', label):
                item['label'] = label.strip()
            pages.append(item)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            raise Invalid('Facebook Page connection integrity changed') from None
    return pages


def _eligible_sources(db, store, app_id, missing):
    sources = []
    if not _has_table(db, 'managed_media'):
        missing.append(dict(code='NO_REVIEWED_SOURCE', next_action='Add managed source footage and complete a current owner rights review.'))
        return sources
    rows = db.execute('SELECT * FROM managed_media WHERE app_id=? ORDER BY created DESC,id LIMIT 500', (app_id,)).fetchall()
    for row in rows:
        try:
            data = json.loads(row['data'])
            view, _ = derivative_snapshot(db, store, app_id, row['id'], data['source_sha256'], verify_bytes=False)
            title = data.get('filename')
            if isinstance(title, str):
                title = title.replace('\\', '/').rsplit('/', 1)[-1]
                if not 0 < len(title) <= 200 or re.search(r'[\x00-\x1f\x7f-\x9f]', title):
                    title = None
            item = dict(id=row['id'], sha256=data['source_sha256'], review_version=view['review_version'])
            if title:
                item['title'] = title
            sources.append(item)
        except Invalid as exc:
            if 'integrity' in str(exc).lower() or 'changed' in str(exc).lower():
                raise
            continue
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            raise Invalid('Managed source history integrity changed') from None
    if not sources:
        missing.append(dict(code='NO_CURRENT_SOURCE', next_action='Review app-owned managed footage against the current app version.'))
    return sources


def _eligible_claims(db, app_id, manifest, missing):
    claims = []
    if not _has_table(db, 'records'):
        missing.append(dict(code='NO_APPROVED_CLAIM', next_action='Add a current, proof-backed app claim before approving a video policy.'))
        return claims
    rows = db.execute("SELECT id,data,hash FROM records WHERE app_id=? AND kind='claim' ORDER BY updated DESC,id",
                      (app_id,)).fetchall()
    for row in rows:
        try:
            record = bound_record(db, app_id, row['id'], 'claim', manifest)
            actual_hash = digest(dict(kind=record['kind'], data=record['data'], source=record['source']))
            if row['hash'] != actual_hash or record['hash'] != actual_hash:
                raise Invalid('Approved claim evidence integrity changed')
            latest_proof(db, app_id, record, manifest)
            claim = record['data'].get('claim')
            if not isinstance(claim, str) or not 0 < len(claim) <= 2000 or re.search(r'[\x00-\x08\x0b-\x1f\x7f-\x9f]', claim):
                raise Invalid('Approved claim text is unavailable or invalid')
            title = record['data'].get('title')
            item = dict(id=row['id'], sha256=actual_hash)
            if isinstance(title, str) and 0 < len(title) <= 200:
                item['title'] = title
            item['claim'] = claim
            claims.append(item)
        except Invalid as exc:
            if 'integrity' in str(exc).lower() or 'changed' in str(exc).lower():
                raise
            continue
    if not claims:
        missing.append(dict(code='NO_CURRENT_CLAIM', next_action='Add or refresh a claim with a current passing product proof.'))
    return claims


def _recorded_outputs(db, app_id):
    outputs = {}
    if not _has_table(db, 'hypit_renders'):
        return []
    rows = db.execute("""SELECT r.* FROM hypit_renders r JOIN jobs j
        ON j.app_id=r.app_id AND j.id=r.job_id
        WHERE r.app_id=? AND j.action='hypit_render' AND j.status='SUCCEEDED'
        ORDER BY r.created DESC,r.id LIMIT 100""", (app_id,))
    for row in rows:
        data = saved_render(row)['data']
        value = data.get('artifact', {}).get('sha256')
        if data.get('renderer') != 'HYPIT_LOCAL' or not isinstance(value, str) or not REQUEST_HASH.fullmatch(value):
            raise Invalid('Saved local output metadata is invalid')
        outputs.setdefault(value, dict(sha256=value, label='Saved Hypit render ' + row['id']))
    return list(outputs.values())


def context(store, app_id, actor, body):
    """Return current selectable evidence without making or changing any approval."""
    exact(body, ())
    with connection(store.path) as db:
        db.execute('BEGIN')
        role = _authorize(db, store, app_id, actor, 'organic-video.policy-context', body)
        version, app_hash = app_scope(db, app_id)
        app_row = db.execute('SELECT data FROM apps WHERE id=?', (app_id,)).fetchone()
        if not app_row:
            raise Invalid('App workspace is unavailable')
        try:
            manifest = json.loads(app_row['data'])
        except (TypeError, ValueError, json.JSONDecodeError):
            raise Invalid('App workspace integrity changed') from None
        missing = []
        pages = _context_page_choices(db, app_id)
        if not pages:
            missing.append(dict(code='NO_TESTED_PAGE', next_action='Connect and test the Facebook Page used for organic video.'))
        sources = _eligible_sources(db, store, app_id, missing)
        claims = _eligible_claims(db, app_id, manifest, missing)
        from .organic_video_taste_review import choices
        from .creative_taste import guidance
        return dict(app=dict(id=app_id, version=version, hash=app_hash),
                    review=dict(owner_version=role['version'], session_binding=digest(PROTECTED.get()['generation'])), pages=pages,
                    eligible=dict(sources=sources, claims=claims), approved_outputs=_recorded_outputs(db, app_id),
                    missing=missing, taste_reviewers=choices(db, app_id, actor),
                    taste_guidance_sha256=guidance()['policy_sha256'])


def _policy_status(db, row, saved, actor, app_id, app_version, app_hash):
    data = saved['data']
    proposal = data.get('policy')
    if not isinstance(proposal, dict):
        raise Invalid('Organic policy snapshot integrity changed')
    revoked = bool(db.execute('SELECT 1 FROM organic_video_policy_revocations WHERE policy_id=?', (row['id'],)).fetchone()) if _has_table(db, 'organic_video_policy_revocations') else False
    expired = iso_time(proposal['expires_at']) <= datetime.now(timezone.utc)
    app_current = (data.get('app_id') == app_id and (data.get('app_version'), data.get('app_hash')) == (app_version, app_hash))
    owner_current = data.get('owner') == actor
    if owner_current:
        role = db.execute('SELECT role,status,version FROM operator_roles WHERE app_id=? AND principal=?',
                          (app_id, actor)).fetchone()
        owner_current = bool(role and role['role'] == 'OWNER' and role['status'] == 'ACTIVE'
                             and role['version'] == data.get('owner_version'))
    return dict(currentness='CURRENTNESS_NOT_REVALIDATED', revoked=revoked, expired=expired,
                app_current=app_current, owner_current=owner_current)


def _usage(db, app_id, row, saved):
    policy = saved['data']['policy']
    policy_id = row['id']
    reservations, admissions = [], []
    if _has_table(db, 'organic_video_generation_reservations'):
        rows = db.execute('SELECT * FROM organic_video_generation_reservations WHERE app_id=? AND policy_id=? ORDER BY created,id',
                          (app_id, policy_id)).fetchall()
        reservations = [_require_saved(item, 'Generation reservation') for item in rows]
    if _has_table(db, 'organic_video_admissions'):
        rows = db.execute('SELECT * FROM organic_video_admissions WHERE app_id=? AND policy_id=? ORDER BY created,id',
                          (app_id, policy_id)).fetchall()
        admissions = [_require_saved(item, 'Policy admission') for item in rows]

    calls_used = provider_phase_complete = 0
    if _has_table(db, 'campaign_video_intents') and _has_table(db, 'organic_video_admissions'):
        intents = db.execute('''SELECT i.* FROM campaign_video_intents i JOIN organic_video_admissions a
            ON a.id=i.admission_id AND a.app_id=i.app_id WHERE i.app_id=? AND a.policy_id=? ORDER BY i.created,i.id''',
                             (app_id, policy_id)).fetchall()
        for intent in intents:
            try:
                data = json.loads(intent['data'])
                if canonical(data) != intent['data'] or digest(data) != intent['hash']:
                    raise Invalid('Reel intent history integrity changed')
                if type(intent['calls']) is not int or intent['calls'] < 0:
                    raise Invalid('Reel intent call usage is invalid')
                calls_used += intent['calls']
                if intent['stage'] == 'PROVIDER_PHASE_COMPLETE':
                    provider_phase_complete += 1
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                raise Invalid('Reel intent history integrity changed') from None
    generation_limit = policy['max_generations']
    post_limit = policy['max_posts']
    call_limit = policy['max_calls']
    if any(type(value) is not int or value < 0 for value in (generation_limit, post_limit, call_limit)):
        raise Invalid('Organic policy ceilings are invalid')
    reserved_calls = sum(item['data'].get('provider_calls_reserved', 0) for item in admissions)
    if any(type(item['data'].get('provider_calls_reserved')) is not int for item in admissions):
        raise Invalid('Organic policy call reservation integrity changed')
    if len(reservations) > generation_limit or len(admissions) > post_limit or reserved_calls > call_limit or calls_used > reserved_calls:
        raise Invalid('Organic policy usage exceeds its saved ceilings')
    return dict(generations_held=len(reservations), artifact_slots_admitted=len(admissions),
                provider_calls_reserved=reserved_calls, provider_calls_used=calls_used,
                provider_phase_complete=provider_phase_complete), dict(generations=generation_limit-len(reservations),
                artifact_slots=post_limit-len(admissions), provider_calls=call_limit-reserved_calls)


def history(store, app_id, actor, body):
    """Read an exact, deterministic owner policy page and reconcile retained use."""
    exact(body, ('offset', 'request_id'))
    offset, request_id = body['offset'], body['request_id']
    if type(offset) is not int or not 0 <= offset <= MAX_OFFSET:
        raise Invalid('Use a policy history offset from 0 through 2000')
    if request_id is not None and (not isinstance(request_id, str) or not 1 <= len(request_id) <= 120):
        raise Invalid('Use the exact bounded policy request identity')
    with connection(store.path) as db:
        db.execute('BEGIN')
        _authorize(db, store, app_id, actor, 'organic-video.policy-history', body)
        version, app_hash = app_scope(db, app_id)
        if not _has_table(db, 'organic_video_policies'):
            return dict(items=[], total=0, offset=offset, limit=PAGE_SIZE, next_offset=None)
        query = 'SELECT * FROM organic_video_policies WHERE app_id=?'
        params = (app_id,)
        if request_id is not None:
            query += ' AND request_id=?'
            params += (request_id,)
        rows = db.execute(query + ' ORDER BY created DESC,id DESC', params)
        page, total = [], 0
        for row in rows:
            saved = _require_saved(row, 'Organic policy')
            snapshot = saved['data']
            if snapshot.get('app_id') != app_id:
                raise Invalid('Organic policy app binding changed')
            if snapshot.get('owner') == actor:
                if offset <= total < offset + PAGE_SIZE:
                    page.append((row, saved))
                total += 1
        items = []
        for row, saved in page:
            snapshot = saved['data']
            if snapshot.get('owner') != actor or snapshot.get('app_id') != app_id:
                raise Invalid('Organic policy owner or app binding changed')
            flags = _policy_status(db, row, saved, actor, app_id, version, app_hash)
            usage, remaining = _usage(db, app_id, row, saved)
            items.append(dict(id=row['id'], hash=saved['hash'], request_id=row['request_id'],
                              request_hash=row['request_hash'], created=row['created'], snapshot=snapshot,
                              **flags, usage=usage, remaining=remaining))
        next_offset = offset + PAGE_SIZE if offset + PAGE_SIZE < total and offset + PAGE_SIZE <= MAX_OFFSET else None
        return dict(items=items, total=total, offset=offset, limit=PAGE_SIZE, next_offset=next_offset)
