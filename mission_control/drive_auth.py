"""Selected-file Desktop OAuth protocol; no credential persistence or account activation."""
import hashlib
import json
import re
import secrets
from urllib.parse import parse_qsl, urlencode
from urllib.request import Request
from .common import Invalid
from .payment_signature import unique_pairs
from . import play_auth
from .providers import report_bytes

SCOPE = 'https://www.googleapis.com/auth/drive.file'
AUTHORIZE = play_auth.AUTHORIZE
TOKEN_ENDPOINT = play_auth.TOKEN_ENDPOINT
VIDEO_MIMES = 'video/mp4,video/quicktime,video/webm'


def client(config):
    """Reuse installed Google client validation, without reflecting configuration values."""
    if not isinstance(config, dict):
        raise Invalid('Select a Google Desktop client configuration for Drive')
    try:
        return play_auth.client(config)
    except Invalid:
        raise Invalid('Select valid Google Desktop client credentials for Drive') from None


def configuration(raw):
    """Reuse duplicate-free installed-client parsing and fixed endpoint validation."""
    try:
        return play_auth.installed_config(raw)
    except (Invalid, UnicodeError):
        raise Invalid('Select the original Google Desktop client JSON for Drive') from None


def state_value(value):
    """Normalize a Drive-specific state before the connection layer claims its hash."""
    if not isinstance(value, str) or not re.fullmatch(r'drive_[A-Za-z0-9_-]{43}', value):
        raise Invalid('Drive consent state is invalid; start a new selection')
    return value


def fresh_state():
    """Only the returned hash belongs in persistent public flow metadata."""
    state = 'drive_' + secrets.token_urlsafe(32)
    return state, hashlib.sha256(state.encode()).hexdigest(), secrets.token_urlsafe(48)


def selected_files(value):
    """Opaque selected identities confer no download or adaptation authority themselves."""
    if not isinstance(value, str) or not 1 <= len(value) <= 4823:
        raise Invalid('Choose from one to24 Drive videos in the official file picker')
    identities = value.split(',')
    if len(identities) > 24 or len(set(identities)) != len(identities):
        raise Invalid('Choose at most24 distinct Drive videos')
    if any(not re.fullmatch(r'[A-Za-z0-9_-]{1,200}', identity) for identity in identities):
        raise Invalid('Drive selection contains an invalid file identity; select the videos again')
    return identities


def authorization(config, port, state, verifier):
    """Prepare Google-hosted Picker consent without embedding third-party UI or a secret."""
    fields = dict(client_id=client(config)['client_id'], redirect_uri=play_auth.loopback(port),
        response_type='code', scope=SCOPE, state=state_value(state),
        code_challenge=play_auth.challenge(verifier), code_challenge_method='S256',
        access_type='offline', prompt='consent', trigger_onepick='true',
        include_granted_scopes='false', allow_multiple='true', mimetypes=VIDEO_MIMES)
    return AUTHORIZE + '?' + urlencode(fields)


def callback_fields(query):
    """Reject ambiguous encodings and duplicate keys before interpreting any result."""
    if not isinstance(query, str) or not 1 <= len(query) <= 16384:
        raise Invalid('Drive callback exceeded its limit; start a new selection')
    if re.search(r'[^!-~]|%(?![0-9A-Fa-f]{2})', query):
        raise Invalid('Drive callback encoding is invalid; start a new selection')
    try:
        pairs = parse_qsl(query, keep_blank_values=True, strict_parsing=True,
                          errors='strict', max_num_fields=8)
    except (ValueError, UnicodeError):
        raise Invalid('Drive callback could not be parsed; start a new selection') from None
    fields = dict(pairs)
    if len(fields) != len(pairs) or any(len(value) > 8192 for value in fields.values()):
        raise Invalid('Drive callback contains duplicated or excessive fields')
    return fields


def callback(query):
    """Normalize one result; durable one-use state and account guards remain mandatory."""
    fields = callback_fields(query)
    state = state_value(fields.get('state'))
    optional = {'authuser', 'prompt'}
    if 'error' in fields:
        if not {'state', 'error'} <= set(fields) <= {'state', 'error', 'error_description'} | optional:
            raise Invalid('Drive callback mixes consent and error fields; start again')
        if fields['error'] != 'access_denied':
            raise Invalid('Drive consent did not complete; check Google setup and select again')
        return dict(state=state, error='access_denied')
    required = {'state', 'code', 'scope', 'picked_file_ids'}
    if not required <= set(fields) <= required | optional or fields['scope'] != SCOPE:
        raise Invalid('Drive selection permission or callback fields differ; select again')
    return dict(state=state, code=play_auth.opaque(fields['code'], 'authorization code', 4096),
                picked_file_ids=selected_files(fields['picked_file_ids']))


def grant_scope(payload, previous=None):
    """Keep permission validation separate from token lifetime and secret normalization."""
    prior = previous or {}
    if not isinstance(payload, dict) or not isinstance(prior, dict):
        raise Invalid('Drive returned invalid permission metadata; reconnect')
    if previous is not None and prior.get('scopes') != [SCOPE]:
        raise Invalid('Protected Drive permission metadata differs; reconnect')
    scopes = payload['scope'].split() if isinstance(payload.get('scope'), str) else None
    if 'scope' not in payload:
        scopes = prior.get('scopes')
    if scopes != [SCOPE]:
        raise Invalid('Google did not confirm selected-file Drive permission; reconnect')
    return scopes


def grant(payload, previous=None):
    """An initial grant must report its exact scope; refresh can retain verified fields."""
    scopes = grant_scope(payload, previous)
    prior = previous or {}
    if payload.get('token_type') != 'Bearer':
        raise Invalid('Google did not confirm a bearer Drive grant; reconnect')
    duration = payload.get('expires_in')
    if type(duration) is not int or not 1 <= duration <= 86400:
        raise Invalid('Drive token expiry is invalid; reconnect')
    return dict(access_token=play_auth.opaque(payload.get('access_token'), 'access token'),
        refresh_token=play_auth.opaque(payload.get('refresh_token', prior.get('refresh_token')), 'refresh grant'),
        scopes=scopes, expires_in=duration)


def token_request(fields):
    """No redirects or automatic retry; provider diagnostics never reflect token content."""
    request = Request(TOKEN_ENDPOINT, data=urlencode(fields).encode(), method='POST',
        headers={'Content-Type': 'application/x-www-form-urlencoded', 'Accept': 'application/json'})
    try:
        raw = report_bytes(request, 15)
        if len(raw) > 8192:
            raise ValueError('oversize')
        value = json.loads(raw, object_pairs_hook=unique_pairs)
    except (Invalid, ValueError, TypeError, UnicodeError, RecursionError):
        raise Invalid('Drive token response could not be verified; reconnect') from None
    if not isinstance(value, dict) or 'error' in value:
        raise Invalid('Drive consent did not complete; reconnect through Google')
    return value


def exchange(config, code, verifier, port):
    """The connection layer must claim the original flow before calling this once."""
    play_auth.challenge(verifier)
    fields = dict(client(config), code=play_auth.opaque(code, 'authorization code', 4096),
        code_verifier=verifier, redirect_uri=play_auth.loopback(port), grant_type='authorization_code')
    return grant(token_request(fields))


def refresh(secret):
    """Retain only an already-verified selected-file permission without widening access."""
    if not isinstance(secret, dict) or secret.get('scopes') != [SCOPE]:
        raise Invalid('Protected Drive permission metadata differs; reconnect')
    fields = dict(client(secret), refresh_token=play_auth.opaque(secret.get('refresh_token'), 'refresh grant'),
                  grant_type='refresh_token')
    return grant(token_request(fields), secret)
