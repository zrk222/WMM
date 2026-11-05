"""Actual owner policy controls against isolated WMM HTTP and SQLite."""
import json
import os
from pathlib import Path
import unittest

from mission_control.db import connection
from tests.test_organic_video_policy import APP
from tests import test_organic_video_policy_http as policy_fixture

PROFILE = os.environ.get('WMM_BROWSER_TEST_PROFILE') == '1'
if PROFILE:
    from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / '.factory/organic-video-automation/hypit/policy-browser'


@unittest.skipUnless(PROFILE, 'Use the provisioned browser profile')
class OrganicPolicyBrowserTests(unittest.TestCase):
    def setUp(self):
        self.fixture = policy_fixture.PolicyHTTPTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        playwright = sync_playwright().start()
        self.addCleanup(playwright.stop)
        self.browser = playwright.chromium.launch()
        self.addCleanup(self.browser.close)

    def page(self, width):
        context = self.browser.new_context(viewport={'width': width, 'height': 900}, accept_downloads=True)
        self.addCleanup(context.close)
        context.add_cookies([dict(name=c.name,value=c.value,domain='127.0.0.1',path=c.path or '/',httpOnly=True)
                             for c in self.fixture.owner.cookies])
        context.add_init_script("localStorage.setItem('growth-app'," + json.dumps(APP) + ")")
        page = context.new_page()
        page.set_default_timeout(10000)
        self.errors, self.external = [], []
        page.on('pageerror', lambda error: self.errors.append(str(error)))

        def restrict(route):
            if route.request.url.startswith(self.fixture.origin + '/'):
                route.continue_()
            else:
                self.external.append(route.request.url)
                route.abort()

        context.route('**/*', restrict)
        page.goto(self.fixture.origin)
        page.wait_for_function("() => typeof state !== 'undefined' && state.workspace?.app?.id === " + json.dumps(APP))
        nav = page.locator('[data-view="research"]')
        if not nav.is_visible():
            page.locator('details').filter(has=nav).locator('summary').first.click()
        nav.click()
        page.locator('[data-action="opolicy-open"]').click()
        page.locator('[data-action="opolicy-new"]').click()
        expect(page.locator('#opolicy-form')).to_be_visible()
        return page

    def review(self, page):
        form = page.locator('#opolicy-form')
        form.locator('#opolicy-page').select_option(index=1)
        form.locator('#opolicy-mode').select_option('STANDING_GENERATED')
        form.locator('[name="sources"]').first.check()
        form.locator('[name="claims"]').first.check()
        form.locator('[name^="template-"]').first.check()
        form.locator('textarea[name^="caption-"]').fill('See the synthetic app in action')
        form.locator('#opolicy-max_posts').fill('21')
        form.locator('button[type="submit"]').click()
        expect(form.locator('#opolicy-max_posts')).to_have_attribute('aria-invalid', 'true')
        form.locator('#opolicy-max_posts').fill('1')
        form.locator('button[type="submit"]').click()
        expect(page.locator('#modal')).to_contain_text('See the synthetic app in action')
        expect(page.locator('#modal')).to_contain_text('Request SHA256')
        expect(page.locator('[data-action="opolicy-confirm"]')).to_be_visible()

    def history(self):
        return self.fixture.request('policy-history', dict(offset=0, request_id=None))['items']

    def snapshot(self, page, width):
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(ARTIFACTS/f'{width}-review.png'))
        dialog = page.locator('#modal').evaluate('(node)=>node.outerHTML')
        heading = page.locator('#main .page-heading').evaluate('(node)=>node.outerHTML')
        css = (ROOT/'mission_control/static/style.css').read_text(encoding='utf-8')
        (ARTIFACTS/f'{width}-review.html').write_text(
            f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Video production approval</title><style>{css}</style></head><body><main>{heading}{dialog}</main></body></html>',
            encoding='utf-8')

    def journey(self, width):
        page = self.page(width)
        self.review(page)
        self.assertEqual(self.history(), [])
        self.assertTrue(page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
        self.assertTrue(page.locator('.organic-policy-workspace').evaluate('(n)=>n.scrollWidth <= n.clientWidth'))
        self.snapshot(page,width)
        page.locator('[data-action="opolicy-confirm"]').press('Enter')
        page.locator('[data-action="opolicy-read"]').click()
        expect(page.locator('#modal')).to_contain_text('current policy revalidated')
        saved = self.history()[0]
        with page.expect_download() as download:
            page.locator('[data-action="opolicy-json"]').click()
        report = json.loads(Path(download.value.path()).read_text(encoding='utf-8'))
        self.assertEqual(report['policy_snapshot'], saved['snapshot'])
        with page.expect_popup() as captured:
            page.locator('[data-action="opolicy-pdf"]').click()
        popup = captured.value
        popup.wait_for_selector('#print-page-report')
        self.assertIn(saved['hash'], popup.locator('body').inner_text())
        self.assertIn(saved['snapshot']['proofs']['sources'][0]['rights_hash'], popup.locator('body').inner_text())
        self.assertTrue(popup.pdf().startswith(b'%PDF'))
        popup.close()
        page.locator('[data-action="opolicy-revoke"]').click()
        page.locator('[data-action="opolicy-confirm"]').click()
        expect(page.locator('#modal')).to_contain_text('Revoked.')
        self.assertTrue(self.history()[0]['revoked'])
        with connection(self.fixture.store.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM organic_video_generation_reservations').fetchone()[0], 0)
        self.assertEqual(self.errors, [])
        self.assertEqual(self.external, [])

    def test_desktop_approval_revalidation_exports_and_revoke(self):
        self.journey(1440)

    def test_mobile_approval_revalidation_exports_and_revoke(self):
        self.journey(390)

    def test_acknowledged_save_readback_denial_keeps_recoverable_identity(self):
        page = self.page(1440)
        self.review(page)
        page.route('**/organic-video/policy-read', lambda route: route.fulfill(
            status=403, content_type='application/json', body='{"error":"Refresh owner session for readback"}'))
        page.locator('[data-action="opolicy-confirm"]').click()
        expect(page.locator('[data-action="opolicy-inspect"]')).to_be_visible()
        self.assertEqual(page.locator('[data-action="opolicy-retry"]').count(), 0)
        self.assertEqual(len(self.history()), 1)
        page.locator('[data-action="opolicy-inspect"]').click()
        expect(page.locator('[data-action="opolicy-read"]')).to_be_visible()
        self.assertEqual(len(self.history()), 1)
        self.assertEqual(page.locator('[data-action="opolicy-inspect"]').count(), 0)

    def test_unknown_create_requires_inspection_and_retains_identity_after_rejection(self):
        page = self.page(1440)
        self.review(page)
        bodies = []

        def interrupted(route):
            bodies.append(route.request.post_data)
            if len(bodies) == 1:
                route.abort()
            else:
                route.fulfill(status=403, content_type='application/json', body='{"error":"Owner context changed"}')

        page.route('**/organic-video/policy-create', interrupted)
        page.locator('[data-action="opolicy-confirm"]').click()
        expect(page.locator('[data-action="opolicy-inspect"]')).to_be_visible()
        self.assertEqual(page.locator('[data-action="opolicy-retry"]').count(), 0)
        page.locator('[data-action="opolicy-inspect"]').click()
        page.locator('[data-action="opolicy-retry"]').click()
        expect(page.locator('#opolicy-error')).to_contain_text('Owner context changed')
        expect(page.locator('[data-action="opolicy-inspect"]')).to_be_visible()
        self.assertEqual(bodies, [bodies[0], bodies[0]])
        self.assertEqual(self.history(), [])
