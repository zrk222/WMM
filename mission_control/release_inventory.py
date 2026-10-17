"""Bounded app-owned release facts; inventory never certifies Apple readiness."""
import re
from urllib.parse import urlencode, urlsplit
from .common import Invalid

BASE = 'https://api.appstoreconnect.apple.com'


def release_options(provider, options):
    """Validate the exact report shape before credential resolution."""
    if provider != 'app_store' or set(options) != {'operation', 'version_id'}:
        raise Invalid('Choose an App Store release and only its version ID')
    resource_id(options['version_id'])
    return options


def resource_id(value):
    """Accept opaque Apple IDs without allowing URL syntax or Unicode lookalikes."""
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9-]{1,80}', value):
        raise Invalid('Choose a valid Apple release resource ID')
    return value


def entity(row, kind):
    """Require the exact resource type and typed attributes before projection."""
    if not isinstance(row, dict) or row.get('type') != kind or not isinstance(row.get('attributes'), dict):
        raise Invalid('Release inventory contains an invalid resource')
    return resource_id(row.get('id')), row['attributes']


def parent(row, relation, identity, required=False):
    """Reject conflicting ancestry; collection URLs already carry verified scope."""
    relationships = row.get('relationships', {})
    if not isinstance(relationships, dict):
        raise Invalid('Release relationship is malformed')
    link = relationships.get(relation, {})
    if not isinstance(link, dict):
        raise Invalid('Release relationship is malformed')
    data = link.get('data')
    if data is None and not required:
        return
    if not isinstance(data, dict) or data.get('id') != identity:
        raise Invalid('Release resource belongs to a different parent')


class Inventory:
    def __init__(self, reader):
        self.reader, self.requests, self.uninspected = reader, 0, []

    def fetch(self, path, query=None):
        """Bound total source calls independently of the shared time/byte limits."""
        if self.requests >= 24:
            self.uninspected.append(path)
            return None
        self.requests += 1
        return self.reader.read(BASE + path + ('?' + urlencode(query) if query else ''))

    def collection(self, path, kind, relation, owner):
        """Read same-resource pages with explicit coverage and duplicate integrity."""
        query, seen, rows = {'limit': 100}, set(), {}
        while True:
            seen.add(BASE + path + '?' + urlencode(query))
            payload = self.fetch(path, query)
            if payload is None:
                return list(rows.values()), False
            page = payload.get('data')
            if not isinstance(page, list) or len(page) > 100:
                raise Invalid('Release page exceeds its contract')
            for row in page:
                identity, _ = entity(row, kind)
                parent(row, relation, owner)
                if identity in rows and rows[identity] != row:
                    raise Invalid('Conflicting duplicate release resource')
                rows[identity] = row
            link = next_link(payload, path, seen)
            if link is None:
                return list(rows.values()), True
            seen.add(link)
            query = urlsplit(link).query
            # Preserve Apple's encoded cursor rather than interpret or duplicate it.
            query = dict_query(query)


def dict_query(query):
    """Preserve an exact validated page query without query-key loss."""
    from urllib.parse import parse_qsl
    try:
        pairs = parse_qsl(query, keep_blank_values=True, strict_parsing=True)
    except ValueError as exc:
        raise Invalid('Release page cursor is malformed') from exc
    if len(pairs) > 20 or len(query) > 4000:
        raise Invalid('Release page cursor is too large')
    return pairs


def next_link(payload, path, seen):
    """Require pagination and forbid credential redirects or collection changes."""
    if not isinstance(payload.get('links'), dict):
        raise Invalid('Release pagination coverage is missing')
    link = payload['links'].get('next')
    if link is None:
        return None
    if not isinstance(link, str):
        raise Invalid('Release pagination is malformed')
    parsed = urlsplit(link)
    if parsed.scheme != 'https' or parsed.netloc != 'api.appstoreconnect.apple.com' or parsed.path != path or parsed.fragment or link in seen:
        raise Invalid('Unsafe or repeating release pagination')
    return link


def text(data, key):
    """Keep source text typed; null is unavailable rather than invented content."""
    value = data.get(key)
    if value is not None and not isinstance(value, str):
        raise Invalid('Release text field is malformed')
    return value


def screenshot(row):
    """Retain order-relevant file facts without URLs, tokens or upload operations."""
    identity, data = entity(row, 'appScreenshots')
    asset, delivery = data.get('imageAsset') or {}, data.get('assetDeliveryState') or {}
    if not isinstance(asset, dict) or not isinstance(delivery, dict):
        raise Invalid('Screenshot delivery metadata is malformed')
    dimensions = {key: asset.get(key) for key in ('width', 'height')}
    if any(value is not None and (type(value) is not int or value <= 0) for value in dimensions.values()):
        raise Invalid('Screenshot dimensions are malformed')
    return dict(id=identity, filename=text(data, 'fileName'), checksum=text(data, 'sourceFileChecksum'),
                delivery_state=text(delivery, 'state'), **dimensions)


def screenshot_set(inventory, row, locale_id):
    """Inspect one display set and preserve incomplete screenshot coverage."""
    identity, data = entity(row, 'appScreenshotSets')
    rows, complete = inventory.collection('/v1/appScreenshotSets/' + identity + '/appScreenshots',
                                          'appScreenshots', 'appScreenshotSet', identity)
    return dict(id=identity, display_type=text(data, 'screenshotDisplayType'),
                screenshots=[screenshot(item) for item in rows], coverage='COMPLETE' if complete else 'PARTIAL')


def localization(inventory, row, version_id):
    """Project locale metadata and fetched display sets with honest missing states."""
    identity, data = entity(row, 'appStoreVersionLocalizations')
    rows, complete = inventory.collection('/v1/appStoreVersionLocalizations/' + identity + '/appScreenshotSets',
                                          'appScreenshotSets', 'appStoreVersionLocalization', identity)
    sets = [screenshot_set(inventory, item, identity) for item in rows]
    metadata = {key: text(data, key) for key in ('description', 'keywords', 'supportUrl', 'marketingUrl', 'whatsNew', 'promotionalText')}
    return dict(id=identity, locale=text(data, 'locale'), metadata=metadata,
                missing_fields=[key for key in ('description', 'keywords', 'supportUrl') if not metadata[key]],
                screenshot_sets=sets, coverage='COMPLETE' if complete and all(s['coverage'] == 'COMPLETE' for s in sets) else 'PARTIAL')


def selected_build(payload, version):
    """Read only the build explicitly related to this selected version."""
    relation = version.get('relationships', {}).get('build', {}).get('data')
    if relation is None:
        return None
    identity = resource_id(relation.get('id')) if isinstance(relation, dict) else resource_id(None)
    included = payload.get('included', [])
    if not isinstance(included, list):
        raise Invalid('Release included resources are malformed')
    rows = [row for row in included if isinstance(row, dict) and row.get('type') == 'builds' and row.get('id') == identity]
    if len(rows) != 1:
        raise Invalid('Selected build details are missing or duplicated')
    _, data = entity(rows[0], 'builds')
    return dict(id=identity, number=text(data, 'version'), processing_state=text(data, 'processingState'))


def read_inventory(reader, store_id, version_id):
    """Verify app ownership before inspecting a selected release's child resources."""
    version_id = resource_id(version_id)
    inventory = Inventory(reader)
    payload = inventory.fetch('/v1/appStoreVersions/' + version_id, {'include': 'app,build', 'fields[builds]': 'version,processingState'})
    version = payload.get('data')
    identity, data = entity(version, 'appStoreVersions')
    if identity != version_id:
        raise Invalid('Apple returned a different release')
    parent(version, 'app', store_id, required=True)
    build = selected_build(payload, version)
    rows, complete = inventory.collection('/v1/appStoreVersions/' + identity + '/appStoreVersionLocalizations',
                                          'appStoreVersionLocalizations', 'appStoreVersion', identity)
    locales = [localization(inventory, row, identity) for row in rows]
    complete = complete and all(row['coverage'] == 'COMPLETE' for row in locales)
    return dict(operation='release_inventory', version_id=identity, version=text(data, 'versionString'),
                platform=text(data, 'platform'), review_state=text(data, 'appStoreState'), build=build,
                locales=locales, coverage='COMPLETE' if complete else 'PARTIAL', requests=inventory.requests,
                uninspected=inventory.uninspected, interpretation='Read-only metadata and file inventory. Screenshot content, authenticity, territory availability, purchase behavior and Apple approval require separate verification.')
