"""Closed Google Play targets and non-executing discovery of explicit project metadata."""
import json
import re
from xml.etree import ElementTree
from .common import Invalid
from .payment_signature import unique_pairs

PACKAGE = r'[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+'
TRACK = r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,99}'
BASE = 'https://androidpublisher.googleapis.com/androidpublisher/v3/applications/'
SCOPE = 'https://www.googleapis.com/auth/androidpublisher'
CLIENT_ID = r'[A-Za-z0-9_-]{3,160}\.apps\.googleusercontent\.com'


def target(value):
    """Validate package and track before either can enter a provider destination."""
    if not isinstance(value, dict) or set(value) != {'package_name', 'track'}:
        raise Invalid('Select only the Android package and Play track')
    package, track = value['package_name'], value['track']
    if not isinstance(package, str) or len(package) > 255 or not re.fullmatch(PACKAGE, package):
        raise Invalid('Use the explicit Android application ID from your app configuration')
    if not isinstance(track, str) or not re.fullmatch(TRACK, track) or '..' in track:
        raise Invalid('Use one Play track name, such as production or internal')
    return dict(package_name=package, track=track)


def json_package(text):
    """Read Expo or plain Android JSON metadata; duplicate and computed identities fail."""
    data = json.loads(text, object_pairs_hook=unique_pairs)
    if not isinstance(data, dict):
        raise Invalid('Android app metadata must be an object')
    root = data.get('expo', data)
    if not isinstance(root, dict) or not isinstance(root.get('android', {}), dict):
        raise Invalid('Android app metadata has an invalid shape')
    value = root.get('android', {}).get('package')
    return [] if value is None else [value]


def xml_package(text):
    """Read only the manifest package; reject declarations and entity expansion."""
    if re.search(r'<!\s*(?:DOCTYPE|ENTITY)', text, re.I):
        raise Invalid('Use a manifest without document types or entity declarations')
    root = ElementTree.fromstring(text)
    if root.tag != 'manifest':
        raise Invalid('Select the Android manifest root document')
    value = root.attrib.get('package')
    return [] if value is None else [value]


def gradle_packages(text):
    """Read literal application IDs only; do not evaluate Gradle or interpolate variables."""
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.S)
    lines = [line.split('//', 1)[0] for line in text.splitlines()]
    source = '\n'.join(lines)
    return re.findall(r'\bapplicationId\s*(?:=\s*)?[\'"]([A-Za-z0-9_.]+)[\'"]', source)


def package_candidates(kind, text):
    """Return explicit candidate identities and unresolved variant selection honestly."""
    readers = {'app.json': json_package, 'AndroidManifest.xml': xml_package,
               'build.gradle': gradle_packages, 'build.gradle.kts': gradle_packages}
    if kind not in readers or not isinstance(text, str) or len(text.encode('utf-8')) > 131072:
        raise Invalid('Select app.json, AndroidManifest.xml or build.gradle metadata up to 128 KiB')
    try:
        values = readers[kind](text)
        packages = sorted({target(dict(package_name=v, track='production'))['package_name'] for v in values})
    except (ValueError, TypeError, RecursionError, ElementTree.ParseError):
        raise Invalid('Project metadata could not be parsed; select an explicit Android configuration') from None
    variants = kind.startswith('build.gradle') and bool(re.search(r'\bapplicationIdSuffix\b', text))
    return dict(package_candidates=packages, source_kind=kind, basis='EXPLICIT_METADATA_ONLY',
                requires_selection=len(packages) != 1 or variants,
                unresolved_variants=variants, executed_project_code=False,
                next_action='Confirm the exact built variant in Play Console before connecting')


def operation(value):
    """Keep the read operation allowlist separate from publishing and purchase APIs."""
    if value not in ('play_releases', 'play_subscriptions'):
        raise Invalid('Choose Google Play release state or subscription catalog')
    return value


def page_token(value):
    """Encode opaque pagination only into a fixed destination, never follow a URL."""
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9._~+/=-]{1,2048}', value):
        raise Invalid('Google Play returned invalid pagination; retry the read')
    return value


def connection_metadata(data):
    """Validate public metadata independently of the protected grant and provider result."""
    if not isinstance(data, dict) or data.get('provider') != 'google_play':
        raise Invalid('Use the guided Google Play connection')
    selected = target({k: data.get(k) for k in ('package_name', 'track')})
    if data.get('store_app_id') != selected['package_name'] or data.get('scopes') != [SCOPE]:
        raise Invalid('Google Play package or permission metadata differs; reconnect')
    if data.get('auth_mode') not in ('managed_oauth', 'disconnected'):
        raise Invalid('Google Play requires protected official OAuth setup')
    if not re.fullmatch(CLIENT_ID, str(data.get('client_id', ''))):
        raise Invalid('Google Play client identity differs; reconnect')
    if not re.fullmatch(r'[a-f0-9-]{36}', str(data.get('credential_ref', ''))):
        raise Invalid('Google Play protected reference is unavailable; reconnect')
    return selected


def manifest_target(data):
    """Normalize paired optional Android fields without assigning an Apple identity."""
    if not data.get('android_package') and not data.get('android_track'):return {}
    selected=target(dict(package_name=data.get('android_package'),track=data.get('android_track')))
    return dict(android_package=selected['package_name'],android_track=selected['track'])


def require_target(app, data):
    """Separate Android package/track authority from an app's numeric Apple Store ID."""
    selected = connection_metadata(data)
    expected = dict(package_name=app['data'].get('android_package'), track=app['data'].get('android_track'))
    if selected != expected or data.get('auth_mode') != 'managed_oauth':
        raise Invalid('Google Play connection does not match this app target; review setup or reconnect')
    return selected
