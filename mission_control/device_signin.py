"""GitHub device sign-in for a CSRF-bound local operator session."""
import json
import math
import os
import re
import secrets
import time
from urllib.parse import urlencode
from urllib.request import Request
from urllib.error import URLError

from .common import Invalid
from .operator_identity import _github_opener, github_read


VERIFY_URL = 'https://github.com/login/device'
MAX_ATTEMPTS = 32
MAX_AGE = 900
TOKEN = re.compile(r'[A-Za-z0-9_]{20,256}')


def request(path, fields):
    """POST only to GitHub's fixed device endpoints with native TLS and no redirects."""
    urls = {'begin': VERIFY_URL + '/code', 'poll': 'https://github.com/login/oauth/access_token'}
    call = Request(urls[path], urlencode(fields).encode('ascii'), method='POST',
                   headers={'Accept': 'application/json', 'Content-Type': 'application/x-www-form-urlencoded',
                            'User-Agent': 'Wize-Marketing-Machine'})
    try:
        with _github_opener().open(call, timeout=10) as response:
            raw = response.read(8193)
        result = json.loads(raw) if len(raw) <= 8192 else None
    except (OSError, URLError, ValueError) as exc:
        raise Invalid('GitHub sign-in was interrupted. Start a fresh sign-in.') from exc
    if not isinstance(result, dict):
        raise Invalid('GitHub returned an invalid sign-in response. Start again.')
    return result


class DeviceSignIns:
    def __init__(self, identities, client_id=None, clock=time.monotonic):
        raw = os.environ.get('WMM_GITHUB_DEVICE_CLIENT_ID', '') if client_id is None else client_id
        self.client_id = raw if re.fullmatch(r'[A-Za-z0-9_]{10,64}', raw) else ''
        self.identities = identities
        self.lock = identities.lock
        self.clock = clock
        self.flows = {}

    @property
    def available(self):
        return bool(self.client_id)

    def cancel(self, session):
        with self.lock:
            self.flows.pop(session, None)

    def _prune(self):
        for session, flow in list(self.flows.items()):
            if flow['expires'] <= self.clock():
                self.flows.pop(session)

    def _current(self, session, app, flow_id):
        self._prune()
        flow = self.flows.get(session)
        if not flow or flow['app'] != app or flow['id'] != flow_id:
            raise PermissionError('This GitHub sign-in expired or belongs to another app. Start again.')
        return flow

    def _summary(self, flow):
        state = flow['state']
        result = dict(status=state, flow_id=flow['id'])
        if state == 'WAITING':
            result.update(user_code=flow['user_code'], verification_url=VERIFY_URL,
                          retry_after=max(0, math.ceil(flow['next_poll'] - self.clock())))
        elif state == 'VERIFIED':
            result.update(principal=flow['user']['principal'], login=flow['user']['login'])
        return result

    def _discard_if_current(self, session, flow):
        with self.lock:
            if self.flows.get(session) is flow:
                self.flows.pop(session)

    def begin(self, session, app):
        if not self.available:
            raise Invalid('GitHub browser sign-in is not configured on this WMM installation.')
        with self.lock:
            self._prune()
            if self.identities.public(session)['status'] != 'SIGNED_OUT':
                raise PermissionError('Sign out before connecting a different GitHub account.')
            flow = self.flows.get(session)
            if flow and flow['app'] == app:
                return self._summary(flow)
            if len(self.flows) >= MAX_ATTEMPTS and flow is None:
                raise Invalid('Too many sign-ins are active. Try again shortly.')
            flow = dict(id=secrets.token_urlsafe(24), app=app, expires=self.clock()+MAX_AGE, state='STARTING')
            self.flows[session] = flow
        try:
            data = request('begin', dict(client_id=self.client_id, scope=''))
            code, shown = data.get('device_code'), data.get('user_code')
            expires, interval = data.get('expires_in'), data.get('interval')
            if (not isinstance(code, str) or not re.fullmatch(r'[A-Za-z0-9_-]{20,256}', code)
                    or not isinstance(shown, str) or not re.fullmatch(r'[A-Z0-9]{4}-[A-Z0-9]{4}', shown)
                    or type(expires) is not int or not 0 < expires <= MAX_AGE
                    or type(interval) is not int or not 5 <= interval <= 60
                    or data.get('verification_uri') != VERIFY_URL):
                raise Invalid('GitHub did not issue a valid sign-in code. Start again.')
            with self.lock:
                self._current(session, app, flow['id'])
                flow.update(state='WAITING', device_code=code, user_code=shown, interval=interval,
                            expires=min(flow['expires'], self.clock()+expires),
                            next_poll=self.clock()+interval, polling=False)
                return self._summary(flow)
        except Exception:
            self._discard_if_current(session, flow)
            raise

    def open_browser(self, session, app, flow_id):
        import webbrowser
        with self.lock:
            flow = self._current(session, app, flow_id)
            if flow['state'] != 'WAITING':
                raise Invalid('Start a GitHub sign-in before opening the browser.')
        try:
            opened = webbrowser.open(VERIFY_URL, new=2)
        except (webbrowser.Error, OSError):
            opened = False
        return dict(browser_opened=opened, verification_url=VERIFY_URL)

    def poll(self, session, app, flow_id):
        with self.lock:
            flow = self._current(session, app, flow_id)
            if flow['state'] != 'WAITING' or flow['polling'] or self.clock() < flow['next_poll']:
                return self._summary(flow)
            flow['polling'] = True
        try:
            data = request('poll', dict(client_id=self.client_id, device_code=flow['device_code'],
                                       grant_type='urn:ietf:params:oauth:grant-type:device_code'))
            error = data.get('error')
            if error in ('authorization_pending', 'slow_down'):
                with self.lock:
                    self._current(session, app, flow_id)
                    if error == 'slow_down':
                        supplied = data.get('interval')
                        flow['interval'] = max(flow['interval']+5, supplied if type(supplied) is int else 0)
                    flow.update(polling=False, next_poll=self.clock()+flow['interval'])
                    return self._summary(flow)
            if error:
                raise Invalid('GitHub did not authorize this sign-in. Start again to try another account.')
            token, token_type = data.get('access_token'), data.get('token_type')
            lifetime = data.get('expires_in', 900)
            if (not isinstance(token, str) or not TOKEN.fullmatch(token)
                    or not isinstance(token_type, str) or token_type.lower() != 'bearer'
                    or data.get('scope') != '' or type(lifetime) is not int or lifetime <= 0):
                raise Invalid('GitHub did not issue a sign-in token with the expected access.')
            user = github_read('/user', token)
            with self.lock:
                self._current(session, app, flow_id)
                flow.pop('device_code')
                flow.pop('user_code')
                flow.update(state='VERIFIED', token=token, user=user, token_expiry=time.time()+min(lifetime, 900))
                return self._summary(flow)
        except Exception:
            self._discard_if_current(session, flow)
            raise

    def confirm(self, session, app, flow_id, principal):
        with self.lock:
            flow = self._current(session, app, flow_id)
            if flow['state'] != 'VERIFIED' or flow['user']['principal'] != principal:
                raise PermissionError('Confirm the exact verified GitHub account.')
            if self.identities.public(session)['status'] != 'SIGNED_OUT':
                raise PermissionError('Sign out before connecting a different GitHub account.')
            if flow['token_expiry'] <= time.time():
                self.flows.pop(session)
                raise PermissionError('The verified account session expired. Start again.')
            self.identities.sessions[session] = dict(token=flow['token'], user=flow['user'],
                                                    expires=flow['token_expiry'])
            self.flows.pop(session)
            return self.identities.public(session)
