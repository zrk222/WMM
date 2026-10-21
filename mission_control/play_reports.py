"""Typed bounded Google Play observations; approval and rollout coverage stay distinct."""
import re
from urllib.parse import quote, urlencode
from .common import Invalid, digest, now
from .play_contract import BASE, operation, page_token, target

LIFECYCLES = ('UNSPECIFIED', 'DRAFT', 'NOT_SENT_FOR_REVIEW', 'IN_REVIEW',
              'APPROVED_NOT_PUBLISHED', 'NOT_APPROVED', 'PUBLISHED')


def bounded_text(value, label, maximum=200):
    """Keep public provider labels finite and exclude control/bidi injection."""
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise Invalid('Google Play returned invalid ' + label)
    if re.search(r'[\x00-\x1f\x7f-\x9f\u202a-\u202e\u2066-\u2069]', value):
        raise Invalid('Google Play returned unsafe ' + label)
    return value


def rows(payload, key, maximum):
    """An omitted protobuf repeated field is empty; errors and wrong types never are."""
    if not isinstance(payload, dict) or 'error' in payload or 'errors' in payload:
        raise Invalid('Google Play read failed; check current permission and reconnect')
    result = payload.get(key, [])
    if not isinstance(result, list) or len(result) > maximum or any(not isinstance(v, dict) for v in result):
        raise Invalid('Google Play returned an invalid ' + key + ' collection')
    return result


def release(row, selected):
    """Published includes partial and resumable halted rollouts; never infer global availability."""
    if row.get('track') != selected['track']:
        raise Invalid('Google Play returned a different track; no observation adopted')
    lifecycle = row.get('releaseLifecycleState', 'RELEASE_LIFECYCLE_STATE_UNSPECIFIED')
    if not isinstance(lifecycle, str) or not re.fullmatch(r'RELEASE_LIFECYCLE_STATE_[A-Z_]{1,80}', lifecycle):
        raise Invalid('Google Play returned an invalid release lifecycle state')
    artifacts = rows(row, 'activeArtifacts', 100)
    codes = [v.get('versionCode') for v in artifacts]
    if any(type(v) is not int or not 1 <= v <= 2100000000 for v in codes) or len(set(codes)) != len(codes):
        raise Invalid('Google Play returned invalid or duplicate version codes')
    name = row.get('releaseName')
    return dict(release_name=bounded_text(name, 'release name') if name is not None else None,
                track=selected['track'], lifecycle=lifecycle,
                recognized_state=lifecycle.removeprefix('RELEASE_LIFECYCLE_STATE_') in LIFECYCLES,
                version_codes=codes, rollout_fraction=None, country_availability=None,
                global_availability='NOT_VERIFIED')


def subscription(row, selected):
    """Project public SKU/plan states only; no subscriber data, purchase token or inferred price."""
    if row.get('packageName') != selected['package_name']:
        raise Invalid('Google Play returned another package; no catalog adopted')
    product = bounded_text(row.get('productId'), 'subscription product ID')
    plans = []
    for plan in rows(row, 'basePlans', 100):
        plans.append(dict(base_plan_id=bounded_text(plan.get('basePlanId'), 'base plan ID'),
                          state=bounded_text(plan.get('state', 'STATE_UNSPECIFIED'), 'base plan state')))
    if len({p['base_plan_id'] for p in plans}) != len(plans):
        raise Invalid('Google Play returned duplicate base plan identities')
    locales = [bounded_text(v.get('languageCode'), 'listing language') for v in rows(row, 'listings', 100)]
    return dict(product_id=product, base_plans=plans, locales=sorted(set(locales)),
                localized_price='NOT_ASSESSED', purchase_and_restore='NOT_TESTED')


def release_inventory(selected, reader, hashes):
    """The official read excludes obsolete releases and returns at most twenty entries."""
    url = BASE + selected['package_name'] + '/tracks/' + quote(selected['track'], safe='') + '/releases'
    payload = reader.read(url); hashes.append(digest(payload))
    releases = rows(payload, 'releases', 20)
    return dict(releases=[release(r, selected) for r in releases],
                coverage='LIMITED' if len(releases) == 20 else 'RETURNED_NON_OBSOLETE_RELEASES',
                obsolete_releases='EXCLUDED_BY_PROVIDER', maximum_releases=20)


def subscription_catalog(selected, reader, hashes):
    """Read at most three fixed-host pages and reject duplicate or looping pagination."""
    url = BASE + selected['package_name'] + '/subscriptions'
    seen, products, catalog = set(), set(), []
    query = {'pageSize': 100}
    for _ in range(3):
        payload = reader.read(url + '?' + urlencode(query)); hashes.append(digest(payload))
        for raw in rows(payload, 'subscriptions', 100):
            item = subscription(raw, selected)
            if item['product_id'] in products:
                raise Invalid('Google Play catalog changed or repeated; retry the read')
            products.add(item['product_id']); catalog.append(item)
        token = payload.get('nextPageToken')
        if token is None or token == '':
            return dict(subscriptions=catalog, coverage='COMPLETE_RETURNED_CATALOG', pages=len(hashes))
        token = page_token(token)
        if token in seen:
            raise Invalid('Google Play pagination repeated; retry the read')
        seen.add(token); query['pageToken'] = token
    return dict(subscriptions=catalog, coverage='LIMITED', pages=len(hashes), remaining_pages='NOT_READ')


def read(binding, operation_name, reader):
    """Use an injected fixed-host reader; credentials and authorization live outside projection."""
    selected = target({key: binding.get(key) for key in ('package_name', 'track')})
    operation(operation_name)
    hashes = []
    result = (release_inventory if operation_name == 'play_releases' else subscription_catalog)(selected, reader, hashes)
    return dict(result, provider='google_play', **selected, operation=operation_name,
                observed_at=now(), source_hash=digest(hashes), page_source_hashes=hashes,
                authority='NO_EXECUTION_AUTHORITY', external_writes=False,
                attribution='NOT_ASSESSED', scope='Scoped provider observation; no edit, publication, purchase or global availability verification')
