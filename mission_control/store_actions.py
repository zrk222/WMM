"""Fixed Apple promotional-text transport. No arbitrary mutation endpoint or retries."""
import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener
from .common import Invalid, canonical, required
from .providers import NoRedirect, credential

HOST = "https://api.appstoreconnect.apple.com"


def opaque(value):
    """Reject path/query injection before resolving any credential."""
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9-]{1,100}", value):
        raise Invalid("Use an opaque Apple resource ID containing letters, digits and hyphens")
    return value


def copy_text(value):
    """Validate only bounded nonempty promotional copy, without hidden controls."""
    value = required(value, "Promotional text", 170)
    if any(ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF or ord(c) == 127 for c in value):
        raise Invalid("Promotional text cannot contain control characters or invalid Unicode")
    return value


def destination(path, method, body):
    """Restrict method, exact path and mutation shape before sending credentials."""
    loc = re.fullmatch(r"/v1/appStoreVersionLocalizations/([A-Za-z0-9-]{1,100})(\?include=appStoreVersion)?", path)
    version = re.fullmatch(r"/v1/appStoreVersions/[A-Za-z0-9-]{1,100}\?include=app", path)
    discovery = re.fullmatch(r"/v1/apps/[0-9]+/appStoreVersions\?filter%5Bplatform%5D=IOS&limit=200|/v1/appStoreVersions/[A-Za-z0-9-]{1,100}/appStoreVersionLocalizations\?limit=200", path)
    if method == "GET" and body is None and any((loc, version, discovery)):
        return
    if method != "PATCH" or not loc or loc[2] or not isinstance(body, dict):
        raise Invalid("Unapproved Apple action endpoint")
    mutation_body(body, loc[1])


def mutation_body(body, identity):
    """Compare the complete typed mutation to the sole permitted JSON shape."""
    try:
        text = copy_text(body["data"]["attributes"]["promotionalText"])
    except (KeyError, TypeError) as exc:
        raise Invalid("Unapproved Apple action body") from exc
    expected = {"data": {"type": "appStoreVersionLocalizations", "id": identity, "attributes": {"promotionalText": text}}}
    if body != expected:
        raise Invalid("Only the exact approved promotional text may change")


def request(binding, app_id, path, method="GET", body=None):
    """Send one bounded request, block redirects and redact all raw provider errors."""
    destination(path, method, body)
    if binding.get("provider") != "app_store":
        raise Invalid("Choose this app's App Store Connect connection")
    token = credential(binding, app_id)
    payload = canonical(body).encode() if body is not None else None
    req = Request(HOST+path, data=payload, method=method, headers={"Authorization": "Bearer "+token, "Accept": "application/json", "Content-Type": "application/json"})
    try:
        with build_opener(NoRedirect()).open(req, timeout=15) as response:
            raw = response.read(262145)
        if len(raw) > 262144:
            raise Invalid("Apple action response exceeds 256 KiB; its outcome requires readback")
        result = json.loads(raw)
    except HTTPError as exc:
        raise Invalid(f"Apple action HTTP {exc.code}; verify role and current provider state. No automatic resend.") from exc
    except (URLError, TimeoutError, UnicodeError, ValueError) as exc:
        raise Invalid("Apple action response is unavailable; inspect readback before any new action") from exc
    if not isinstance(result, dict) or result.get("errors"):
        raise Invalid("Apple returned an invalid action response; inspect readback")
    return result


def resource(payload, kind, identity):
    """Validate exact JSON:API resource identity before interpreting attributes."""
    data = payload.get("data")
    if not isinstance(data, dict) or data.get("type") != kind or data.get("id") != identity or not isinstance(data.get("attributes"), dict):
        raise Invalid("Apple returned a different or malformed resource")
    return data


def relationship(data, name, kind):
    """Read typed relationship IDs; never follow provider-supplied links."""
    relationships = data.get("relationships")
    if not isinstance(relationships, dict) or not isinstance(relationships.get(name), dict):
        raise Invalid("Apple resource relationship is missing or malformed")
    relation = relationships[name].get("data")
    if not isinstance(relation, dict) or relation.get("type") != kind:
        raise Invalid("Apple resource relationship is missing or malformed")
    return opaque(relation.get("id"))


def baseline(binding, app_id, localization_id, release, locale):
    """Read actual localization, then independently verify its version/app relationship."""
    localization_id = opaque(localization_id)
    loc = resource(request(binding, app_id, f"/v1/appStoreVersionLocalizations/{localization_id}?include=appStoreVersion"), "appStoreVersionLocalizations", localization_id)
    version_id = relationship(loc, "appStoreVersion", "appStoreVersions")
    version = resource(request(binding, app_id, f"/v1/appStoreVersions/{version_id}?include=app"), "appStoreVersions", version_id)
    remote_app = relationship(version, "app", "apps")
    attrs = loc["attributes"]; current = attrs.get("promotionalText")
    if current is not None and not isinstance(current, str):
        raise Invalid("Apple promotional text has an invalid shape")
    if not remote_app.isdigit() or remote_app != binding.get("store_app_id"):
        raise Invalid("Apple localization belongs to a different app")
    if version["attributes"].get("versionString") != release or attrs.get("locale") != locale or version["attributes"].get("platform") != "IOS":
        raise Invalid("Apple localization differs from this workspace's iOS version or locale")
    return {"store_app_id": remote_app, "localization_id": localization_id, "version_id": version_id, "release": release, "locale": locale, "platform": "IOS", "promotional_text": current}


def apply(binding, app_id, target, text):
    """Make exactly one approved promotional-text PATCH; callers must claim first."""
    identity = opaque(target["localization_id"])
    body = {"data": {"type": "appStoreVersionLocalizations", "id": identity, "attributes": {"promotionalText": copy_text(text)}}}
    return resource(request(binding, app_id, f"/v1/appStoreVersionLocalizations/{identity}", "PATCH", body), "appStoreVersionLocalizations", identity)


def select(payload, kind, expected):
    """Reject malformed/ambiguous bounded discovery instead of guessing a destination."""
    rows = payload.get("data")
    if not isinstance(rows, list) or len(rows) > 200:
        raise Invalid("Apple destination discovery is malformed or exceeds its bounded page")
    matches = [r for r in rows if isinstance(r, dict) and r.get("type") == kind and isinstance(r.get("attributes"), dict) and all(r["attributes"].get(k) == v for k, v in expected.items())]
    if len(matches) != 1:
        raise Invalid("No unique destination on the bounded provider page; check this app's current iOS release and locale")
    return opaque(matches[0].get("id"))


def discover(binding, app_id, release, locale):
    """Resolve configured release and locale through two fixed read-only provider lists."""
    store_id = str(binding.get("store_app_id", ""))
    if not re.fullmatch(r"[0-9]+", store_id):
        raise Invalid("Connection needs a numeric Store app ID")
    versions = request(binding, app_id, f"/v1/apps/{store_id}/appStoreVersions?filter%5Bplatform%5D=IOS&limit=200")
    version = select(versions, "appStoreVersions", {"versionString": release, "platform": "IOS"})
    locales = request(binding, app_id, f"/v1/appStoreVersions/{version}/appStoreVersionLocalizations?limit=200")
    identity = select(locales, "appStoreVersionLocalizations", {"locale": locale})
    return {"localization_id": identity, "release": release, "locale": locale}
