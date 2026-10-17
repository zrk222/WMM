"""Read-only Apple subscription observations through the existing bounded Reader."""
from urllib.parse import urlsplit
from .common import Invalid, required

BASE = 'https://api.appstoreconnect.apple.com'


def entity(row, kind) -> object:
    """Require a typed numeric Apple identity and an attributes object."""
    if not isinstance(row, dict) or row.get('type') != kind or not isinstance(row.get('attributes'), dict):
        raise Invalid('Subscription catalog contains an invalid resource')
    identity = required(row.get('id'), 'Apple resource ID', 30)
    if not identity.isascii() or not identity.isdigit():
        raise Invalid('Apple resource ID must be numeric')
    return identity, row['attributes']


def next_page(payload, path, seen):
    """Keep credentials on the same collection and reject repeated page links."""
    if not isinstance(payload.get('links'), dict):
        raise Invalid('Subscription catalog pagination coverage is missing')
    link = payload['links'].get('next')
    if link is None:
        return None
    if not isinstance(link, str):
        raise Invalid('Subscription catalog pagination is invalid')
    parsed = urlsplit(link)
    if parsed.scheme != 'https' or parsed.netloc != 'api.appstoreconnect.apple.com' or parsed.path != path or parsed.fragment or link in seen:
        raise Invalid('Unsafe or repeating subscription catalog pagination')
    return link


def merge_row(rows, row):
    """Reject malformed IDs and conflicting duplicates instead of overwriting."""
    if not isinstance(row, dict):
        raise Invalid('Subscription catalog row is invalid')
    identity = required(row.get('id'), 'Apple resource ID', 30)
    if identity in rows and rows[identity] != row:
        raise Invalid('Conflicting duplicate subscription catalog resource')
    rows[identity] = row


def collection(reader, path) -> object:
    """Fetch at most three hundred rows and retain incomplete coverage."""
    url = BASE + path + '?limit=100'
    seen, rows = set(), {}
    for _ in range(3):
        seen.add(url)
        payload = reader.read(url)
        page = payload.get('data')
        if not isinstance(page, list) or len(page) > 100:
            raise Invalid('Subscription catalog page exceeds its contract')
        for row in page:
            merge_row(rows, row)
        url = next_page(payload, path, seen)
        if not url:
            break
    return list(rows.values()), url is None


def group_relationship(row, group_id):
    """Optional returned relationship must agree with the scoped collection."""
    relationships = row.get('relationships', {})
    if not isinstance(relationships, dict):
        raise Invalid('Subscription relationships are invalid')
    group = relationships.get('subscriptionGroup', {})
    if not isinstance(group, dict):
        raise Invalid('Subscription group relationship is invalid')
    related = group.get('data')
    if related is not None and (not isinstance(related, dict) or related.get('id') != group_id):
        raise Invalid('Subscription belongs to another group')


def subscription(row, group_id) -> object:
    """Project only Apple facts; never infer price or purchased access."""
    identity, data = entity(row, 'subscriptions')
    group_relationship(row, group_id)
    period = data.get('subscriptionPeriod')
    if period is not None:
        period = required(period, 'Subscription period', 100)
    return dict(id=identity, group_id=group_id, product_id=required(data.get('productId'), 'Product ID', 300),
                name=required(data.get('name'), 'Subscription name', 300), state=required(data.get('state'), 'Subscription state', 100),
                period=period, price=None, currency=None, purchase_verified=False, restore_verified=False)


def group_products(reader, group):
    """Read a group returned by the selected app's own collection."""
    identity, data = entity(group, 'subscriptionGroups')
    rows, complete = collection(reader, '/v1/subscriptionGroups/' + identity + '/subscriptions')
    return dict(id=identity, name=required(data.get('referenceName'), 'Group name', 300)), [subscription(row, identity) for row in rows], complete


def summarize_groups(reader, source, complete):
    """Bound group traversal and mark any excluded resources as partial."""
    complete = complete and len(source) <= 10
    groups, products = [], []
    for group in source[:10]:
        item, rows, covered = group_products(reader, group)
        groups.append(item)
        products.extend(rows[:1000-len(products)])
        complete = complete and covered and len(products) < 1000
        if len(products) >= 1000:
            break
    validate_product_ownership(products)
    return groups, products, complete


def validate_product_ownership(products):
    """Product identity cannot be duplicated across app subscription groups."""
    if len({row['id'] for row in products}) != len(products) or len({row['product_id'] for row in products}) != len(products):
        raise Invalid('Subscription catalog contains duplicate product ownership')


def read_catalog(reader, store_id) -> object:
    """Read scoped identity, groups and products without any product mutation."""
    resource = reader.read(BASE + '/v1/apps/' + store_id).get('data')
    identity, attributes = entity(resource, 'apps')
    if identity != store_id:
        raise Invalid('Provider returned a different app identity')
    source, complete = collection(reader, '/v1/apps/' + store_id + '/subscriptionGroups')
    groups, products, complete = summarize_groups(reader, source, complete)
    return dict(operation='subscription_catalog', groups=groups, rows=products, coverage='COMPLETE' if complete else 'PARTIAL',
                pages=len(reader.hashes), bundle_id=attributes.get('bundleId'),
                interpretation='Apple product status only. Prices, purchase, restore, entitlements and release approval require separate verification.')
