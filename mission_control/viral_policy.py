"""Exact viral-only qualification over supplied observations; no discovery authority."""
from fractions import Fraction
from .common import Invalid, digest, iso_time, required
from .creative_library import source_url

MIN_VIEWS = 100000
MULTIPLIER = 10
MIN_BASELINE = 10
MAX_BASELINE = 20
MAX_OBSERVATIONS = 1000
MAX_VIEWS = 1000000000000
FIELDS = {'platform', 'post_id', 'creator_id', 'format', 'url', 'views', 'published_at', 'observed_at'}
PLATFORMS = ('tiktok', 'facebook', 'instagram')


def observation(value, as_of):
    """Require source identity, observed counts and chronology, never estimated views."""
    if not isinstance(value, dict) or set(value) != FIELDS:
        raise Invalid('Complete exactly the viral observation fields')
    if value['platform'] not in PLATFORMS:
        raise Invalid('Choose TikTok, Facebook or Instagram')
    result = {key: required(value[key], key, 120) for key in ('platform', 'post_id', 'creator_id', 'format')}
    views = value['views']
    if type(views) is not int or not 0 <= views <= MAX_VIEWS:
        raise Invalid('Views must be an observed nonnegative integer within the supported range')
    published = iso_time(value['published_at'])
    observed = iso_time(value['observed_at'])
    if not published <= observed <= as_of:
        raise Invalid('Publication and observation times must precede the as-of time')
    return dict(result, views=views, url=source_url(value['url']), published_at=published.isoformat(), observed_at=observed.isoformat())


def prior_posts(candidate, history, as_of):
    """Exclude the candidate, reject ambiguous identities and select recent prior posts."""
    if not isinstance(history, list) or len(history) > MAX_OBSERVATIONS:
        raise Invalid('Supply at most 1000 baseline observations')
    rows = [observation(item, as_of) for item in history]
    seen = set()
    eligible = []
    for row in rows:
        if row['post_id'] in seen:
            raise Invalid('Duplicate baseline post identity')
        seen.add(row['post_id'])
        comparable(candidate, row)
        if row['post_id'] == candidate['post_id']:
            if row != candidate:
                raise Invalid('Candidate identity has conflicting observations')
            continue
        if iso_time(row['published_at']) < iso_time(candidate['published_at']):
            eligible.append(row)
    eligible.sort(key=lambda row: (iso_time(row['published_at']), row['post_id']), reverse=True)
    return eligible[:MAX_BASELINE]


def comparable(candidate, row):
    """Never form a creator median from another platform, owner or format."""
    if any(row[key] != candidate[key] for key in ('creator_id', 'platform', 'format')):
        raise Invalid('Baseline posts must match candidate creator, platform and format')


def median_views(rows):
    """Retain exact even-sample half views rather than round a cutoff downward."""
    ordered = sorted(row['views'] for row in rows)
    if not ordered:
        return None
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return Fraction(ordered[middle])
    return Fraction(ordered[middle - 1] + ordered[middle], 2)


def decision(candidate, rows):
    """Both user-selected thresholds must pass; unknown/zero baselines do not qualify."""
    median = median_views(rows)
    if len(rows) < MIN_BASELINE or median is None or median <= 0:
        return dict(qualification='INSUFFICIENT_BASELINE', reasons=['POSITIVE_MEDIAN_AND_TEN_COMPARABLE_POSTS_REQUIRED'], required_views=None, median=None)
    relative = median * MULTIPLIER
    threshold = max(MIN_VIEWS, -(-relative.numerator // relative.denominator))
    reasons = []
    if candidate['views'] < MIN_VIEWS:
        reasons.append('BELOW_100000_VIEWS')
    if candidate['views'] < relative:
        reasons.append('BELOW_TENFOLD_MEDIAN')
    return dict(qualification='NOT_QUALIFIED' if reasons else 'QUALIFIED_BY_REPORTED_COUNTS', reasons=reasons,
                required_views=threshold, median=dict(numerator=median.numerator, denominator=median.denominator))


def qualify(candidate, history, as_of):
    """Emit a reproducible policy receipt, leaving collection verification and rights separate."""
    stamp = iso_time(as_of)
    candidate = observation(candidate, stamp)
    rows = prior_posts(candidate, history, stamp)
    result = dict(schema='growth.viral-qualification.v1', candidate_id=candidate['post_id'], candidate_hash=digest(candidate),
                  baseline=[dict(post_id=row['post_id'], observation_hash=digest(row)) for row in rows],
                  baseline_count=len(rows), as_of=stamp.isoformat(), minimum_views=MIN_VIEWS, multiplier=MULTIPLIER,
                  collection_verification='REQUIRED', human_review='REQUIRED', reuse_permission='NOT_ESTABLISHED', publication='NOT_RUN',
                  **decision(candidate, rows))
    return dict(result, receipt_hash=digest(result))
