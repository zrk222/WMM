"""Official desktop Google consent and bounded token exchange; no provider-selected URLs."""
import base64
import hashlib
import json
import re
import secrets
import time
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request
from .common import Invalid
from .payment_signature import unique_pairs
from .play_contract import BASE, CLIENT_ID, SCOPE, page_token, target
from .providers import read_json, report_bytes

AUTHORIZE = 'https://accounts.google.com/o/oauth2/v2/auth'
TOKEN_ENDPOINT = 'https://oauth2.googleapis.com/token'


def opaque(value, label, maximum=2048, minimum=1):
    """Reject invalid secret input without reflecting its content in diagnostics."""
    if not isinstance(value, str) or not minimum <= len(value) <= maximum or re.search(r'[^!-~]', value):
        raise Invalid('Invalid Google ' + label + '; reconnect through the official consent flow')
    return value


def client(config):
    """Only a Google installed client identity and bounded secret enter token requests."""
    identity = config.get('client_id')
    if not isinstance(identity, str) or not re.fullmatch(CLIENT_ID, identity):
        raise Invalid('Use the installed Desktop app client from Google Cloud credentials')
    return dict(client_id=identity, client_secret=opaque(config.get('client_secret'), 'client configuration', 512, 8))


def installed_config(text):
    """Import Desktop client JSON without accepting alternate authorization/token hosts."""
    if not isinstance(text, str) or len(text.encode()) > 8192:
        raise Invalid('Select a Google Desktop client JSON file up to 8 KiB')
    try:
        data = json.loads(text, object_pairs_hook=unique_pairs)
    except (ValueError, TypeError, RecursionError):
        raise Invalid('The Google Desktop client JSON could not be read') from None
    if not isinstance(data, dict) or set(data) != {'installed'} or not isinstance(data['installed'], dict):
        raise Invalid('Use Desktop app credentials, not a web or service-account key')
    config = data['installed']
    if config.get('auth_uri', AUTHORIZE) != AUTHORIZE or config.get('token_uri', TOKEN_ENDPOINT) != TOKEN_ENDPOINT:
        raise Invalid('The client configuration contains nonstandard Google endpoints')
    return client(config)


def loopback(port):
    """Use the actual local listener port; no supplied redirect or external return URL."""
    if type(port) is not int or not 1 <= port <= 65535:
        raise Invalid('The local callback port is unavailable')
    return 'http://127.0.0.1:' + str(port)


def fresh_state():
    """Persist only the random state's hash; protect the verifier separately."""
    state = 'play_' + secrets.token_urlsafe(32)
    return state, hashlib.sha256(state.encode()).hexdigest(), secrets.token_urlsafe(48)


def challenge(verifier):
    """Only SHA256 PKCE is used for installed-app authorization."""
    if not isinstance(verifier, str) or not re.fullmatch(r'[A-Za-z0-9._~-]{43,128}', verifier):
        raise Invalid('Google consent proof expired; start a new connection')
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')


def authorization(config, port, state, verifier):
    """Build official consent with one declared scope and an exact loopback return."""
    public = client(config)
    if not isinstance(state, str) or not re.fullmatch(r'play_[A-Za-z0-9_-]{43}', state):
        raise Invalid('Google consent state is invalid; start again')
    return AUTHORIZE + '?' + urlencode(dict(client_id=public['client_id'], redirect_uri=loopback(port),
        response_type='code', scope=SCOPE, state=state, code_challenge=challenge(verifier),
        code_challenge_method='S256', access_type='offline', prompt='consent'))


def token_request(fields):
    """Exchange only at the fixed token host; never retry an authorization code."""
    request = Request(TOKEN_ENDPOINT, data=urlencode(fields).encode(), method='POST',
                      headers={'Content-Type': 'application/x-www-form-urlencoded', 'Accept': 'application/json'})
    raw = report_bytes(request, 15)
    if len(raw) > 8192:
        raise Invalid('Google token response exceeded its size limit; reconnect')
    try:
        value = json.loads(raw, object_pairs_hook=unique_pairs)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise Invalid('Google authorization response could not be verified; reconnect') from None
    if not isinstance(value, dict) or 'error' in value:
        raise Invalid('Google authorization did not complete; reconnect and check Play Console access')
    return value


def grant(payload, previous=None):
    """Check granted scope, bearer type, expiry and retained refresh access explicitly."""
    prior = previous or {}
    scope = payload.get('scope')
    if 'scope' in payload and not isinstance(scope, str):
        raise Invalid('Google returned malformed permission metadata; reconnect')
    scopes = scope.split() if isinstance(scope, str) else prior.get('scopes')
    if scopes != [SCOPE] or payload.get('token_type') != 'Bearer':
        raise Invalid('Google did not confirm the requested Play permission; review consent and reconnect')
    duration = payload.get('expires_in')
    if type(duration) is not int or not 1 <= duration <= 86400:
        raise Invalid('Google token expiry is invalid; reconnect')
    return dict(access_token=opaque(payload.get('access_token'), 'access token'),
                refresh_token=opaque(payload.get('refresh_token', prior.get('refresh_token')), 'refresh grant'),
                scopes=scopes, expires_in=duration)


def exchange(config, code, verifier, port):
    """Consume one code bound to the original proof and actual listener port."""
    challenge(verifier)
    fields = dict(client(config), code=opaque(code, 'authorization code', 4096),
                  code_verifier=verifier, redirect_uri=loopback(port), grant_type='authorization_code')
    return grant(token_request(fields))


def refresh(secret):
    """A refresh may retain the prior scope; it can never expand the approved grant."""
    if secret.get('scopes') != [SCOPE]:
        raise Invalid('Protected Google permission metadata differs; reconnect')
    fields = dict(client(secret), refresh_token=opaque(secret.get('refresh_token'), 'refresh grant'),
                  grant_type='refresh_token')
    return grant(token_request(fields), secret)


class PlayReader:
    """Keep tokens on fixed target-specific read destinations, without redirects."""
    def __init__(self, selected, bearer):
        self.selected = target(selected); self.bearer = opaque(bearer, 'access token')
        self.deadline = time.monotonic() + 30

    def read(self, url):
        """Allow only this package's bounded release and subscription requests."""
        self.destination(url)
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:raise Invalid('Google Play read budget expired; retry this bounded read')
        return read_json(url, {'Authorization': 'Bearer ' + self.bearer}, timeout=min(10, remaining))

    def destination(self, url):
        """No URL, query or track can redirect a credential to another resource."""
        from urllib.parse import quote
        parsed = urlsplit(url); base = BASE + self.selected['package_name']
        if parsed.scheme != 'https' or parsed.netloc != 'androidpublisher.googleapis.com' or parsed.fragment:
            raise Invalid('Unapproved Google Play read destination')
        release = base + '/tracks/' + quote(self.selected['track'], safe='') + '/releases'
        if url == release:return
        if parsed._replace(query='').geturl() != base + '/subscriptions':
            raise Invalid('Google Play read does not match this app and track')
        query = parse_qs(parsed.query, keep_blank_values=True, strict_parsing=True)
        if set(query) not in ({'pageSize'}, {'pageSize', 'pageToken'}) or query['pageSize'] != ['100']:
            raise Invalid('Unapproved Google Play catalog query')
        if 'pageToken' in query:
            if len(query['pageToken']) != 1:raise Invalid('Duplicate Google Play page token')
            page_token(query['pageToken'][0])
