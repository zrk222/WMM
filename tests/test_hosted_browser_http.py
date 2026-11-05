"""Actual loopback HTTP acceptance with synthetic isolated databases only."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from email.message import Message
from http.client import HTTPConnection
from http.cookies import SimpleCookie
import json
from pathlib import Path
import socket
import sqlite3
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlencode, urlsplit

from mission_control.common import Invalid
from mission_control.db import connection
from mission_control.hosted_browser_http import BrowserHandler, BrowserServer, cookies, validate_cookies
from mission_control.hosted_oidc import Identity
from mission_control.hosted_read_control import Control, Unauthenticated, Unassigned
from mission_control.hosted_read_registry import Registry, RegistryUnavailable, app_choice, exact_id, physical_file
from mission_control.service import Service
from mission_control.store import Store


class FakeLogin:
    """HTTP boundary fixture; real RSA/PKCE integration has a separate test."""
    def __init__(self):
        self.provider = SimpleNamespace(config=SimpleNamespace(display_label='Example sign in'))
        self.browser, self.csrf = 'b' * 43, 'c' * 43
        self.identity = Identity('issuer', 'alice', 1100, 999)
        self.calls, self.invalidated = [], []

    def context(self):
        return self.browser, self.csrf

    def context_for(self, browser):
        if browser != self.browser:
            raise ValueError('unknown context')
        return self.csrf

    def start(self, browser, csrf, origin, redirect):
        if (browser, csrf) != (self.browser, self.csrf):
            raise Invalid('Invalid context')
        self.calls.append(('start', origin, redirect))
        return 'https://issuer.example/authorize?state=fixture'

    def callback(self, browser, origin, redirect, params):
        self.calls.append(('callback', browser, origin, redirect, params))
        return self.identity, 'generation'

    def commit_if_current(self, browser, generation, commit):
        return commit()

    def invalidate(self, browser, cleanup=None):
        self.invalidated.append(browser)
        if cleanup:
            return cleanup()


class BrowserHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.now = 1000.0
        self.control = Control(self.root / 'control.sqlite', clock=lambda: self.now)
        self.services = {}
        for client, name, count in [('client-a', 'Alpha client', 1), ('client-b', 'Beta private sentinel', 3)]:
            self.add_client(client, name, count)
        self.registry = Registry(self.root, self.services, self.control.path)
        self.control.set_member('issuer', 'alice', 'tenant', 'client-a', 'VIEWER')
        self.control.set_member('issuer', 'bob', 'tenant', 'client-b', 'OWNER')
        self.alice = self.control.issue_session('issuer', 'alice')
        self.bob = self.control.issue_session('issuer', 'bob')
        self.server = BrowserServer(('127.0.0.1', 0), self.control, self.registry)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def add_client(self, client, name, count=0):
        store = Store(self.root / (client + '.sqlite'), seed=False)
        store.save_app('same-app', dict(name=name, audience='PRIVATE_PROFILE_SENTINEL'))
        with connection(store.path) as db:
            for index in range(count):
                db.execute('INSERT INTO jobs(id,app_id,action,data,status,created,updated,request_key) VALUES(?,?,?,?,?,?,?,?)',
                           (str(index), 'same-app', 'pipeline', '{"private":"SECRET_JOB"}', 'UNKNOWN', 'now', 'now', str(index)))
        self.services[('tenant', client)] = Service(store)
        self.control.register_client('tenant', client)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.temp.cleanup()

    @property
    def origin(self):
        return 'http://127.0.0.1:' + str(self.server.server_port)

    def request(self, path='/api/session', token=None, method='GET', headers=None, body=None):
        headers = dict(headers or {})
        if token is not None:
            headers['Cookie'] = 'wmm_read=' + token
        http = HTTPConnection('127.0.0.1', self.server.server_port, timeout=10)
        try:
            http.request(method, path, body=body, headers=headers)
            response = http.getresponse()
            return response.status, response.getheaders(), response.read()
        finally:
            http.close()

    def post(self, path, csrf, token=None, headers=None):
        return self.request(path, token, 'POST', {
            'Origin': self.origin, 'Content-Type': 'application/x-www-form-urlencoded', **(headers or {})},
            urlencode({'csrf': csrf}))

    def wire(self, request):
        with socket.create_connection(self.server.server_address, timeout=5) as stream:
            stream.sendall(request.encode('ascii'))
            result = bytearray()
            while chunk := stream.recv(65536):
                result.extend(chunk)
            return bytes(result)

    @staticmethod
    def header(headers, name):
        return [value for key, value in headers if key.lower() == name.lower()]

    def session_count(self):
        with closing(sqlite3.connect(self.control.path)) as db:
            return db.execute('SELECT count(*) FROM sessions').fetchone()[0]

    def assert_callback_failed(self, result):
        code, headers, raw = result
        self.assertEqual(code, 303, raw)
        self.assertEqual(self.header(headers, 'Location'), ['/?signin=failed'])
        self.assertEqual(self.header(headers, 'Set-Cookie'), [])
        self.assertEqual(raw, b'')

    def test_get_route_request_context_error_response_disabled_bootstrap(self):
        code, headers, raw = self.request('/auth/context')
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(raw), dict(configured=False, csrf='', label='Sign in'))
        self.assertEqual(self.header(headers, 'Set-Cookie'), [])
        self.assertEqual(self.request()[0], 401)
        for path in ('/api/bootstrap', '/api/apps/same-app/export', '/auth/callback', '/?return=https://evil.example'):
            code, headers, raw = self.request(path, self.alice)
            self.assertEqual(code, 400, path)
            self.assertEqual(self.header(headers, 'Cache-Control'), ['no-store'])
            self.assertEqual(self.header(headers, 'Referrer-Policy'), ['no-referrer'])
            self.assertIn('frame-ancestors', self.header(headers, 'Content-Security-Policy')[0])
            self.assertEqual(set(json.loads(raw)), {'error'})
        self.assertEqual(self.post('/auth/start', 'anything')[0], 401)
        with self.assertRaises(Invalid):
            BrowserServer(('0.0.0.0', 0), self.control, self.registry)
        self.assertFalse(hasattr(self.server, 'runner'))

    def test_commit_login_complete_login_rotates_cookie_after_context_start_callback(self):
        login = self.server.login = FakeLogin()
        code, headers, raw = self.request('/auth/context')
        self.assertEqual(code, 200, raw)
        self.assertEqual(json.loads(raw)['label'], 'Example sign in')
        challenge = self.header(headers, 'Set-Cookie')[0]
        for attribute in ('HttpOnly', 'SameSite=Lax', 'Path=/', 'Max-Age=600'):
            self.assertIn(attribute, challenge)
        self.assertNotIn('Domain=', challenge)
        code, headers, raw = self.post('/auth/start', login.csrf, headers={'Cookie': 'wmm_browser=' + login.browser})
        self.assertEqual(code, 303, raw)
        self.assertEqual(self.header(headers, 'Location'), ['https://issuer.example/authorize?state=fixture'])
        jar = 'wmm_browser=' + login.browser + '; wmm_read=' + self.alice
        code, headers, raw = self.request('/auth/callback?code=SECRET_CODE&state=fixture', headers={'Cookie': jar})
        self.assertEqual(code, 303, raw)
        self.assertEqual(self.header(headers, 'Location'), ['/'])
        cookie = SimpleCookie(); cookie.load(self.header(headers, 'Set-Cookie')[0])
        token = cookie['wmm_read'].value
        self.assertNotEqual(token, self.alice)
        self.assertEqual(raw, b'')
        self.assertEqual(self.request(token=token)[0], 200)
        self.assertEqual(self.request(token=self.alice)[0], 401)
        self.assertEqual(login.calls[-1][1:4], (login.browser, self.origin, self.origin + '/auth/callback'))
        for secret in ('SECRET_CODE', token):
            self.assertNotIn(secret, json.dumps(self.control.receipts()))

    def test_assigned_choices_summary_and_owner_remains_readonly(self):
        for client, token, name, count in [('client-a', self.alice, 'Alpha client', 1),
                                           ('client-b', self.bob, 'Beta private sentinel', 3)]:
            code, _, raw = self.request(token=token)
            self.assertEqual(code, 200, raw)
            data = json.loads(raw)
            self.assertEqual([value['client_id'] for value in data['clients']], [client])
            self.assertEqual(data['clients'][0]['apps'], [dict(id='same-app', name=name, version=1)])
            self.assertFalse(data['more_available'])
            self.assertEqual(data['csrf'], self.server.csrf(token))
            for secret in (token, 'SECRET_JOB', 'PRIVATE_PROFILE_SENTINEL', str(self.root)):
                self.assertNotIn(secret, raw.decode())
            route = '/v1/tenants/tenant/clients/' + client + '/apps/same-app/dashboard'
            code, headers, raw = self.request(route, token)
            self.assertEqual(code, 200, raw)
            self.assertEqual(json.loads(raw)['jobs']['unknown'], count)
            self.assertFalse(json.loads(raw)['effects_enabled'])
            self.assertEqual(len(self.header(headers, 'X-WMM-Receipt')), 1)
            self.assertEqual(self.post(route, data['csrf'], token)[0], 400)
        denied = self.request('/v1/tenants/tenant/clients/client-b/apps/same-app/dashboard', self.alice)
        self.assertEqual(denied[0], 404)
        self.assertNotIn(b'Beta private sentinel', denied[2])

    def test_logout_origin_and_current_csrf_required_then_revoke(self):
        csrf = json.loads(self.request(token=self.alice)[2])['csrf']
        for origin in (None, 'null', 'https://evil.example', self.origin + '/'):
            headers = {'Content-Type': 'application/x-www-form-urlencoded'}
            if origin is not None:
                headers['Origin'] = origin
            code, _, _ = self.request('/auth/logout', self.alice, 'POST', headers, urlencode({'csrf': csrf}))
            self.assertEqual(code, 400, origin)
            self.assertEqual(self.request(token=self.alice)[0], 200)
        self.assertEqual(self.post('/auth/logout', 'wrong', self.alice)[0], 401)
        self.assertEqual(self.post('/auth/logout', self.server.csrf(self.bob), self.alice)[0], 401)
        code, headers, raw = self.post('/auth/logout', csrf, self.alice)
        self.assertEqual(code, 200, raw)
        self.assertEqual(json.loads(raw), {'signed_out': True})
        self.assertEqual(len(self.header(headers, 'Set-Cookie')), 2)
        self.assertTrue(all('Max-Age=0' in value and 'HttpOnly' in value for value in self.header(headers, 'Set-Cookie')))
        self.assertEqual(self.request(token=self.alice)[0], 401)
        self.assertEqual(self.request(token=self.bob)[0], 200)

    def test_cookies_validate_cookies_boundary_headers_identity_headers_reject_ambiguities(self):
        for jar in ('wmm_read=' + self.alice + '; wmm_read=' + self.bob,
                    'wmm_browser=short', 'wmm_read=short', 'wmm_read=' + self.alice + '; broken'):
            self.assertEqual(self.request(headers={'Cookie': jar})[0], 400)
        for extra in ('Cookie: wmm_read=' + self.alice + '\r\nCookie: wmm_read=' + self.bob,
                      'Origin: ' + self.origin + '\r\nOrigin: ' + self.origin,
                      'Host: ' + self.origin[7:], 'Content-Length: 0\r\nContent-Length: 0'):
            raw = self.wire('GET /api/session HTTP/1.1\r\nHost: ' + self.origin[7:] + '\r\n' + extra + '\r\n\r\n')
            self.assertIn(b' 400 ', raw.split(b'\r\n')[0])
        for headers in ({'Authorization': 'Bearer ' + self.alice}, {'X-User': 'alice'},
                        {'X-Forwarded-Host': 'trusted.example'}, {'Host': 'evil.example'},
                        {'Origin': 'null'}, {'Transfer-Encoding': 'chunked'},
                        {f'X-Large-{i}': 'v' for i in range(33)}):
            self.assertEqual(self.request(token=self.alice, headers=headers)[0], 400)

    def test_form_and_callback_grammar_reject_before_login_dispatch(self):
        login = self.server.login = FakeLogin()
        headers = {'Origin': self.origin, 'Content-Type': 'application/x-www-form-urlencoded',
                   'Cookie': 'wmm_browser=' + login.browser}
        for body in ('', 'csrf=x&csrf=y', 'csrf=x&extra=y', 'csrf=%zz', 'csrf=%ff', 'csrf=', 'csrf=' + 'x' * 4096):
            self.assertEqual(self.request('/auth/start', method='POST', headers=headers, body=body)[0], 400, body[:50])
        self.assertEqual(self.request('/auth/start', method='POST', headers={**headers, 'Content-Type': 'application/json'}, body='{}')[0], 400)
        for suffix in ('code=x&code=y&state=s', 'code=x&state=s&extra=z', 'code=x&error=no&state=s',
                       'code=x&state=', 'code=%zz&state=s', 'code=x&state=s#fragment'):
            with self.subTest(suffix=suffix):
                self.assert_callback_failed(self.request('/auth/callback?' + suffix, headers={'Cookie': headers['Cookie']}))
        self.assertEqual(login.calls, [])
        for length in ('+6', '-1', '6,6', ' 6', 'six'):
            wire = ('POST /auth/start HTTP/1.1\r\nHost: ' + self.origin[7:] + '\r\nOrigin: ' + self.origin
                    + '\r\nContent-Type: application/x-www-form-urlencoded\r\nContent-Length: ' + length + '\r\n\r\ncsrf=x')
            self.assertIn(b' 400 ', self.wire(wire).split(b'\r\n')[0], length)
        for method in ('PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS', 'TRACE', 'CONNECT'):
            self.assertEqual(self.request('/api/bootstrap', self.alice, method)[0], 405, method)

    def test_finish_choices_revocation_and_epoch_change_suppress_collected_names(self):
        original = self.registry.apps
        entered, release = threading.Event(), threading.Event()
        def paused(entry):
            value = original(entry)
            entered.set()
            self.assertTrue(release.wait(5))
            return value
        for change in ('member', 'session'):
            with self.subTest(change=change), patch.object(self.registry, 'apps', paused), ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(self.request, token=self.alice)
                self.assertTrue(entered.wait(5))
                if change == 'member':
                    self.control.set_member('issuer', 'alice', 'tenant', 'client-a', 'OPERATOR')
                else:
                    self.control.revoke_session(self.alice)
                release.set()
                code, _, raw = future.result(timeout=10)
            self.assertEqual(code, 404 if change == 'member' else 401)
            self.assertNotIn(b'Alpha client', raw)
            self.alice = self.control.issue_session('issuer', 'alice')
            entered.clear(); release.clear()

    def test_physical_file_missing_store_not_recreated_and_registry_change_fails(self):
        path = self.services[('tenant', 'client-a')].store.path
        saved = path.with_suffix('.saved')
        path.rename(saved)
        try:
            self.assertEqual(self.request(token=self.alice)[0], 503)
            self.assertFalse(path.exists())
        finally:
            saved.rename(path)
        original = self.registry.apps
        def replace(entry):
            value = original(entry)
            path.rename(saved)
            path.write_bytes(b'not a database')
            return value
        try:
            with patch.object(self.registry, 'apps', replace):
                code, _, raw = self.request(token=self.alice)
            self.assertEqual(code, 503)
            self.assertNotIn(b'Alpha client', raw)
        finally:
            path.unlink(); saved.rename(path)

    def test_app_choice_finite_twenty_client_and_app_choices_with_more_marker(self):
        for index in range(20):
            client = 'extra-' + str(index).zfill(2)
            self.add_client(client, 'Assigned ' + str(index))
            self.control.set_member('issuer', 'alice', 'tenant', client, 'VIEWER')
        store = self.services[('tenant', 'client-a')].store
        for index in range(20):
            store.save_app('app-' + str(index).zfill(2), {'name': 'App ' + str(index)})
        self.server.registry = Registry(self.root, self.services, self.control.path)
        token = self.control.issue_session('issuer', 'alice')
        code, _, raw = self.request(token=token)
        self.assertEqual(code, 200, raw)
        data = json.loads(raw)
        self.assertEqual(len(data['clients']), 20)
        self.assertTrue(data['more_available'])
        alpha = data['clients'][0]
        self.assertEqual(alpha['client_id'], 'client-a')
        self.assertEqual(len(alpha['apps']), 20)
        self.assertTrue(alpha['more_available'])
        self.assertNotIn(b'Beta private sentinel', raw)

    def test_issue_verified_session_identity_expires_while_real_sqlite_lock_waits(self):
        self.server.login = FakeLogin()
        before = self.session_count()
        blocker = sqlite3.connect(self.control.path)
        blocker.execute('BEGIN IMMEDIATE')
        entered = threading.Event()
        real_connect = sqlite3.connect
        def traced(*args, **kwargs):
            db = real_connect(*args, **kwargs)
            db.set_trace_callback(lambda statement: entered.set() if statement == 'BEGIN IMMEDIATE' else None)
            return db
        try:
            with patch('mission_control.hosted_read_control.sqlite3.connect', traced), ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(self.request, '/auth/callback?code=fixture&state=fixture',
                                     headers={'Cookie': 'wmm_browser=' + 'b' * 43})
                self.assertTrue(entered.wait(5), 'callback did not reach real SQLite transaction')
                self.now = 1100.0
                blocker.commit()
                code, headers, raw = future.result(timeout=10)
            self.assert_callback_failed((code, headers, raw))
            self.assertEqual(self.session_count(), before)
        finally:
            blocker.rollback(); blocker.close()

    def test_unassigned_callback_cannot_create_member_or_owner(self):
        login = self.server.login = FakeLogin()
        login.identity = Identity('issuer', 'unassigned', 1100, 999)
        before = self.session_count()
        code, headers, raw = self.request('/auth/callback?code=fixture&state=fixture', headers={'Cookie': 'wmm_browser=' + login.browser})
        self.assert_callback_failed((code, headers, raw))
        self.assertEqual(self.session_count(), before)
        with closing(sqlite3.connect(self.control.path)) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM members WHERE subject='unassigned'").fetchone()[0], 0)

    def test_app_choice_exact_id_and_physical_file_reject_invalid_metadata(self):
        self.assertEqual(exact_id('same-app'), 'same-app')
        self.assertEqual(app_choice(('same-app', 1, 'Alpha')), dict(id='same-app', version=1, name='Alpha'))
        for value in ('../escape', 'UPPERCASE', 'same%2dapp'):
            with self.subTest(value=value), self.assertRaises(Invalid):
                exact_id(value)
            with self.subTest(value=value), self.assertRaises(Invalid):
                app_choice((value, 1, 'Alpha'))
        for row in (('same-app', True, 'Alpha'), ('same-app', 0, 'Alpha'),
                    ('same-app', 1, ''), ('same-app', 1, 'a' * 161), ('same-app', 1, None)):
            with self.subTest(row=row), self.assertRaises(RegistryUnavailable):
                app_choice(row)
        entry = self.registry.resolve('tenant', 'client-a')
        path, identity = physical_file(entry.path, self.root.resolve())
        self.assertEqual((path, identity), (entry.path, entry.identity))
        with self.assertRaises(RegistryUnavailable):
            physical_file(entry.path, self.root / 'unrelated')

    def test_cookie_parsers_and_direct_request_boundaries(self):
        headers = Message()
        headers['Host'] = self.origin[7:]
        headers['Cookie'] = 'wmm_read=' + self.alice
        self.assertEqual(cookies(headers), {'wmm_read': self.alice})
        validate_cookies({'wmm_read': self.alice, 'wmm_browser': 'b' * 43})
        with self.assertRaises(Invalid):
            validate_cookies({'wmm_browser': 'b' * 42})
        handler = object.__new__(BrowserHandler)
        handler.server, handler.headers = self.server, headers
        handler.request_version, handler.path = 'HTTP/1.1', '/api/session'
        self.assertEqual(handler.request_context(), {'wmm_read': self.alice})
        with self.assertRaises(Invalid):
            handler.boundary_headers(post=True)
        headers['Origin'] = self.origin
        handler.boundary_headers(post=True)
        headers['Authorization'] = 'Bearer ' + self.alice
        with self.assertRaises(Invalid):
            handler.identity_headers()
        del headers['Authorization']
        handler.path = '/api/session#hidden'
        with self.assertRaises(Invalid):
            handler.request_context()

    def test_verified_session_temporal_values_and_final_choice_expiry(self):
        before = self.session_count()
        for identity in (Identity('issuer', 'alice', 1000, 999), Identity('issuer', 'alice', 1100, 1006),
                         Identity('issuer', 'alice', 1100, 999, 1001), Identity('issuer', 'alice', True, 999)):
            with self.subTest(identity=identity), self.assertRaises(Unauthenticated):
                self.control.issue_verified_session(identity)
        self.assertEqual(self.session_count(), before)
        token = self.control.issue_verified_session(Identity('issuer', 'alice', 1100, 999))
        admissions, more = self.control.choices(token)
        self.now = 1900.0
        with self.assertRaises(Unauthenticated):
            self.control.finish_choices(token, admissions, more)
        self.now = 1000.0
        admissions, more = self.control.choices(self.alice)
        self.control.set_member('issuer', 'alice', 'tenant', 'client-a', 'OPERATOR')
        with self.assertRaises(Unassigned):
            self.control.finish_choices(self.alice, admissions, more)

    def test_login_commit_failure_revokes_new_session_and_route_dispatch_is_finite(self):
        handler = object.__new__(BrowserHandler)
        handler.server, handler.path = self.server, '/api/bootstrap'
        with self.assertRaises(Invalid):
            handler.get_route({})
        identity = Identity('issuer', 'alice', 1100, 999)
        issued = []
        original_issue = self.control.issue_verified_session
        original_revoke = self.control.revoke_session
        def issue(value):
            token = original_issue(value)
            issued.append(token)
            return token
        def revoke(token):
            if token == self.alice:
                raise sqlite3.OperationalError('PRIVATE_REVOKE_SENTINEL')
            return original_revoke(token)
        with patch.object(self.control, 'issue_verified_session', issue), patch.object(self.control, 'revoke_session', revoke):
            with self.assertRaises(sqlite3.OperationalError):
                handler.complete_login(identity, {'wmm_read': self.alice})
        with self.assertRaises(Unauthenticated):
            self.control.choices(issued[-1])
        handler.output = Mock(side_effect=OSError('PRIVATE_WRITE_SENTINEL'))
        with patch.object(self.control, 'issue_verified_session', issue):
            with self.assertRaises(OSError):
                handler.commit_login(identity, {}, 'browser')
        with self.assertRaises(Unauthenticated):
            self.control.choices(issued[-1])

    def test_html_referrer_policy_preserves_exact_post_origin_contract(self):
        code, headers, raw = self.request('/')
        self.assertEqual(code, 200, raw)
        self.assertEqual(self.header(headers, 'Referrer-Policy'), ['same-origin'])
        for path in ('/static/client-dashboard.js', '/static/client-dashboard.css', '/api/session', '/unknown'):
            _, headers, _ = self.request(path)
            self.assertEqual(self.header(headers, 'Referrer-Policy'), ['no-referrer'], path)

    def test_real_rsa_login_flow_through_actual_http(self):
        from mission_control.hosted_login_flow import LoginFlow
        from mission_control.hosted_oidc import OIDCClient
        from tests.test_hosted_oidc import Fixture, config
        fixture = Fixture()
        self.control.set_member(config().issuer, 'subject', 'tenant', 'client-a', 'VIEWER')
        self.server.login = LoginFlow(OIDCClient(config(), fixture, clock=lambda: self.now))
        code, headers, raw = self.request('/auth/context')
        self.assertEqual(code, 200, raw)
        context = json.loads(raw)
        jar = SimpleCookie(); jar.load(self.header(headers, 'Set-Cookie')[0])
        cookie = 'wmm_browser=' + jar['wmm_browser'].value
        code, headers, raw = self.post('/auth/start', context['csrf'], headers={'Cookie': cookie})
        self.assertEqual(code, 303, raw)
        authorize = parse_qs(urlsplit(self.header(headers, 'Location')[0]).query)
        self.assertEqual(authorize['code_challenge_method'], ['S256'])
        self.assertEqual(authorize['redirect_uri'], [self.origin + '/auth/callback'])
        fixture.claims['nonce'] = authorize['nonce'][0]
        callback = '/auth/callback?' + urlencode({'code': 'SYNTHETIC_AUTH_CODE', 'state': authorize['state'][0]})
        code, headers, raw = self.request(callback, headers={'Cookie': cookie})
        self.assertEqual(code, 303, raw)
        result = SimpleCookie(); result.load(self.header(headers, 'Set-Cookie')[0])
        token = result['wmm_read'].value
        self.assertEqual(self.request(token=token)[0], 200)
        self.assert_callback_failed(self.request(callback, headers={'Cookie': cookie}))
        self.assertNotIn('SYNTHETIC_AUTH_CODE', json.dumps(self.control.receipts()))


if __name__ == '__main__':
    unittest.main()
