"""Actual Chromium journey over synthetic RSA OIDC and isolated client databases."""
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
from urllib.parse import parse_qs, urlencode, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from playwright.sync_api import sync_playwright
from mission_control.hosted_browser_http import BrowserServer
from mission_control.hosted_login_flow import LoginFlow
from mission_control.hosted_oidc import OIDCClient, ProviderConfig
from mission_control.hosted_read_control import Control
from mission_control.hosted_read_registry import Registry
from mission_control.service import Service
from mission_control.store import Store


class Provider:
    """Explicit injected token transport, no production HTTP bypass."""
    def __init__(self):
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.nonce = None
        self.subject = 'reader'
        self.config = ProviderConfig('https://identity.example/', 'https://identity.example/authorize',
                                     'https://identity.example/token', 'https://identity.example/keys', 'wmm')

    def request(self, url, method, body, deadline):
        if method == 'POST':
            claims = dict(iss=self.config.issuer, sub=self.subject, aud='wmm',
                          exp=time.time() + 120, iat=time.time(), nonce=self.nonce)
            return json.dumps(dict(id_token=jwt.encode(claims, self.key, algorithm='RS256',
                                                      headers={'kid': 'fixture'}))).encode()
        key = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key()))
        return json.dumps(dict(keys=[dict(key, kid='fixture', use='sig', alg='RS256')])).encode()


def run():
    output = ROOT / '.factory/browser-client-login/browser'
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as directory, sync_playwright() as playwright:
        root = Path(directory)
        control = Control(root / 'control.sqlite')
        services = {}
        provider = Provider()
        for client in ('alpha', 'beta'):
            store = Store(root / (client + '.sqlite'), seed=False)
            store.save_app('sample-app', dict(name=client.title() + ' app', audience='PRIVATE_PROFILE_SENTINEL'))
            services[('team', client)] = Service(store)
            control.register_client('team', client)
            control.set_member(provider.config.issuer, 'reader', 'team', client, 'VIEWER')
        registry = Registry(root, services, control.path)
        login = LoginFlow(OIDCClient(provider.config, provider))
        server = BrowserServer(('127.0.0.1', 0), control, registry, login)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        origin = 'http://127.0.0.1:' + str(server.server_port)
        browser = playwright.chromium.launch(headless=True)
        browser_version = browser.version
        observations = []
        try:
            for width in (1440, 390):
                context = browser.new_context(viewport={'width': width, 'height': 950})
                page = context.new_page()
                page.set_default_timeout(10000)
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                def sign_in():
                    with page.expect_request('https://identity.example/**') as authorization:
                        page.locator('#sign-in-form button').focus()
                        page.locator('#sign-in-form button').press('Enter', no_wait_after=True)
                    query = parse_qs(urlsplit(authorization.value.url).query)
                    assert query['code_challenge_method'] == ['S256']
                    assert 'referer' not in authorization.value.headers
                    provider.nonce = query['nonce'][0]
                    location = query['redirect_uri'][0] + '?' + urlencode(dict(code='fixture-code', state=query['state'][0]))
                    # Provider consent is a fixture: observe the real top-level
                    # authorization navigation, then return its matching callback.
                    page.goto(location)
                page.goto(origin)
                page.locator('#sign-in-form').wait_for(state='visible')
                sign_in()
                page.locator('#count-grid .count').first.wait_for()
                assert page.locator('#app-name').inner_text() == 'Alpha app'
                assert page.locator('#receipt-value').inner_text()
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                assert page.evaluate("getComputedStyle(document.body).backgroundColor !== 'rgb(255, 255, 255)' || getComputedStyle(document.documentElement).backgroundColor !== 'rgba(0, 0, 0, 0)'")
                assert page.evaluate('localStorage.length === 0 && sessionStorage.length === 0')
                assert 'PRIVATE_PROFILE_SENTINEL' not in page.content()
                page.screenshot(path=str(output / f'dashboard-{width}.png'), full_page=True)
                with page.expect_download() as download:
                    page.locator('#export-button').click()
                saved = output / f'summary-{width}.json'
                download.value.save_as(str(saved))
                report = json.loads(saved.read_text(encoding='utf-8'))
                assert report['receipt'] and report['access'] == 'Read only'
                page.pdf(path=str(output / f'summary-{width}.pdf'))
                def delay_dashboard():
                    page.evaluate("""() => {
                      window.__testFetch = window.fetch;
                      let held = false;
                      window.fetch = (...args) => window.__testFetch(...args).then(response => {
                        if (!held && String(args[0]).endsWith('/dashboard')) {
                          held = true;
                          return new Promise(resolve => { window.__releaseTest = () => {
                            window.fetch = window.__testFetch; resolve(response);
                          }; });
                        }
                        return response;
                      });
                    }""")
                delay_dashboard()
                page.locator('#client-select').select_option(label='beta')
                page.wait_for_function('() => typeof window.__releaseTest === "function"')
                page.locator('#client-select').select_option(label='alpha')
                page.wait_for_function("() => document.querySelector('#app-name').textContent === 'Alpha app'")
                page.evaluate('() => { window.__releaseTest(); delete window.__releaseTest; }')
                page.wait_for_function("() => document.querySelector('#summary').getAttribute('aria-busy') === 'false'")
                assert page.locator('#app-name').inner_text() == 'Alpha app'
                delay_dashboard()
                page.locator('#client-select').select_option(label='beta')
                page.wait_for_function('() => typeof window.__releaseTest === "function"')
                page.evaluate("""() => {
                  const original = window.fetch;
                  window.fetch = (...args) => {
                    if (String(args[0]) === '/auth/logout') return new Promise((resolve, reject) => {
                      window.__releaseLogout = () => original(...args).then(resolve, reject);
                    });
                    return original(...args);
                  };
                }""")
                page.locator('#logout-form button').click()
                page.wait_for_function('() => typeof window.__releaseLogout === "function"')
                page.evaluate("async () => { dispatchEvent(new Event('focus')); await new Promise(resolve => setTimeout(resolve, 200)); }")
                assert page.locator('#workspace').is_hidden(), 'Focus must not restore data or interrupt pending sign-out'
                assert page.locator('#status-title').inner_text() == 'Signing you out'
                page.evaluate('() => window.__releaseLogout()')
                page.locator('#sign-in-form').wait_for(state='visible')
                page.evaluate('() => { window.__releaseTest(); delete window.__releaseTest; }')
                assert 'Alpha app' not in page.content() and 'Beta app' not in page.content()
                sign_in()
                page.locator('#count-grid .count').first.wait_for()
                page.locator('#client-select').select_option(label='beta')
                page.wait_for_function("() => document.querySelector('#app-name').textContent === 'Beta app'")
                # Server-side final authorization rejects a changed membership.
                control.set_member(provider.config.issuer, 'reader', 'team', 'beta', 'VIEWER', 'REVOKED')
                page.reload()
                page.wait_for_function("() => document.querySelector('#workspace').hidden")
                page.wait_for_function("() => !document.querySelector('#status-card').hidden")
                assert 'Beta app' not in page.content()
                control.set_member(provider.config.issuer, 'reader', 'team', 'beta', 'VIEWER')
                # Reauthenticate against current epochs, then verify logout clears UI.
                page.goto(origin)
                page.locator('#sign-in-form').wait_for(state='visible')
                sign_in()
                page.locator('#count-grid .count').first.wait_for()
                attempts = []
                def logout_failure(route):
                    attempts.append(1)
                    if len(attempts) == 1:
                        return route.fulfill(status=503, content_type='application/json', body='{"error":"fixture failure"}')
                    route.continue_()
                page.route('**/auth/logout', logout_failure)
                page.locator('#logout-form button').click()
                page.locator('#retry-button').wait_for(state='visible')
                assert page.locator('#workspace').is_hidden()
                page.locator('#retry-button').click()
                page.locator('#sign-in-form').wait_for(state='visible')
                assert len(attempts) == 2
                assert 'Alpha app' not in page.content() and 'Beta app' not in page.content()
                page.evaluate("() => dispatchEvent(new PageTransitionEvent('pageshow', {persisted:true}))")
                page.locator('#sign-in-form').wait_for(state='visible')
                assert 'Alpha app' not in page.content() and 'Beta app' not in page.content()
                assert not errors, errors
                observations.append(dict(width=width, login='PASS', choices='PASS', receipt='PASS',
                                         json_pdf='PASS', revoke='PASS', logout='PASS',
                                         delayed_selection='PASS', delayed_logout='PASS',
                                         pageshow_refresh='PASS', external_referrer_absent='PASS', errors=errors))
                context.close()
        finally:
            browser.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
    receipt = dict(schema='wmm.browser-client-login.acceptance.v1', observations=observations,
                   provider='synthetic RSA fixture; no real provider or public hosting acceptance',
                   python=sys.version, jwt=jwt.__version__, chromium=browser_version)
    (output / 'receipt.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    print(json.dumps(receipt))


if __name__ == '__main__':
    run()
