"""Real owner connection forms; synthetic credentials and no provider traffic."""
import os
from pathlib import Path
import re
import unittest
from unittest.mock import patch

from mission_control.agent_access import AgentAccess
from mission_control.worker import jobs
from tests import test_agent_grants as grants
from tests.test_measurement_connectors import FakeVault

BROWSER_PROFILE = os.environ.get('WMM_BROWSER_TEST_PROFILE') == '1'
if BROWSER_PROFILE:
    from playwright.sync_api import expect, sync_playwright


@unittest.skipUnless(BROWSER_PROFILE, 'Run the explicitly provisioned browser profile')
class CloudflareBrowserTests(unittest.TestCase):
    def test_owner_selects_free_or_paid_and_reviews_the_exact_policy(self):
        with sync_playwright() as runner:
            browser = runner.chromium.launch(headless=True)
            try:
                for width in (375, 768, 1440):
                    with self.subTest(width=width), patch('mission_control.agent_access.Vault', FakeVault):
                        fixture = grants.GrantTests()
                        fixture.setUp()
                        context = browser.new_context(viewport={'width': width, 'height': 900})
                        unexpected, errors = [], []
                        FakeVault.values = {}
                        FakeVault.fail_delete = 0
                        context.add_cookies([dict(name=c.name, value=c.value, url=fixture.origin, sameSite='Lax')
                                            for c in fixture.owner.cookies])

                        def local_only(route):
                            if route.request.url.startswith(fixture.origin + '/'):
                                route.continue_()
                            else:
                                unexpected.append(route.request.url)
                                route.abort()

                        context.route('**/*', local_only)
                        try:
                            page = context.new_page()
                            page.on('pageerror', lambda error: errors.append(str(error)))
                            page.goto(fixture.origin)
                            page.locator('#navigation summary').click()
                            page.locator('#navigation [data-view="agents"]').click()
                            page.locator('[data-action="agent-setup"][data-id="cloudflare_api"]:not([data-profile])').click()
                            form = page.locator('#agent-setup-form')
                            expect(form).to_be_visible()
                            expect(form.get_by_label('Inference billing mode', exact=True)).to_have_value('free')
                            expect(form.locator('[name="charges"]')).not_to_be_checked()
                            expect(form).to_contain_text('not account-wide or a dollar cap')
                            if capture := os.environ.get('WMM_CLOUDFLARE_CAPTURE'):
                                out = Path(capture)
                                out.mkdir(parents=True, exist_ok=True)
                                page.screenshot(path=str(out / f'cloudflare-free-{width}.png'))
                                if width == 1440:
                                    html = re.sub(r'<script\b[^>]*>.*?</script>', '', page.content(), flags=re.S)
                                    static = Path(__file__).resolve().parents[1] / 'mission_control' / 'static'
                                    for name in ('style.css', 'page-reporting.css', 'video-editor.css', 'packaging.css'):
                                        html = html.replace(f'<link rel="stylesheet" href="/{name}">',
                                                            '<style>' + (static / name).read_text(encoding='utf-8') + '</style>')
                                    (out / 'cloudflare-setup.html').write_text(html, encoding='utf-8')
                            form.get_by_label('Connection name', exact=True).fill('Synthetic free connection')
                            form.get_by_label('Cloudflare account ID', exact=True).fill('a' * 32)
                            form.locator('[name="api_key"]').fill('synthetic-cloudflare-key')
                            form.get_by_label('Daily approval limit for this WMM connection (UTC)', exact=True).fill('2')
                            form.get_by_label('Maximum output tokens per request', exact=True).fill('64')
                            form.get_by_role('button', name='Save protected connection', exact=True).click()
                            expect(page.locator('#main')).to_contain_text('Synthetic free connection')
                            rows = AgentAccess(fixture.store).view('sample-one')['profiles']
                            self.assertEqual(len(rows), 1)
                            self.assertEqual(rows[0]['data']['billing_policy']['mode'], 'free')
                            free_id = rows[0]['id']
                            page.locator('[data-action="agent-test"][data-id="' + free_id + '"]').click()
                            expect(page.locator('#agent-approve-form')).to_contain_text('64 output tokens')
                            expect(page.locator('#agent-approve-form')).to_contain_text('already-paid account')
                            page.locator('#close-modal').click()
                            page.locator('[data-action="agent-setup"][data-id="cloudflare_api"]:not([data-profile])').click()
                            form = page.locator('#agent-setup-form')
                            form.get_by_label('Connection name', exact=True).fill('Synthetic paid connection')
                            form.get_by_label('Cloudflare account ID', exact=True).fill('a' * 32)
                            form.locator('[name="api_key"]').fill('synthetic-cloudflare-key')
                            form.get_by_label('Inference billing mode', exact=True).select_option('paid')
                            form.get_by_label('Maximum output tokens per request', exact=True).fill('128')
                            form.get_by_label('Daily approval limit for this WMM connection (UTC)', exact=True).fill('3')
                            with page.expect_response(lambda r: r.url.endswith('/agent-access/save') and r.request.method == 'POST') as denied:
                                form.get_by_role('button', name='Save protected connection', exact=True).click()
                            self.assertEqual(denied.value.status, 400)
                            expect(form.locator('#agent-error')).to_contain_text('explicitly allow paid inference')
                            self.assertEqual(len(AgentAccess(fixture.store).view('sample-one')['profiles']), 1)
                            form.locator('[name="charges"]').check()
                            form.get_by_role('button', name='Save protected connection', exact=True).click()
                            expect(page.locator('#main')).to_contain_text('Synthetic paid connection')
                            rows = AgentAccess(fixture.store).view('sample-one')['profiles']
                            paid = next(r for r in rows if r['data']['label'] == 'Synthetic paid connection')
                            self.assertEqual(paid['data']['billing_policy']['daily_request_limit'], 3)
                            self.assertEqual(paid['data']['billing_policy']['max_output_tokens'], 128)
                            self.assertTrue(paid['data']['allow_api_charges'])
                            page.locator('[data-action="agent-test"][data-id="' + paid['id'] + '"]').click()
                            review = page.locator('#agent-approve-form')
                            expect(review).to_contain_text('Paid inference allowed')
                            expect(review).to_contain_text('128 output tokens')
                            review.get_by_role('button', name='Approve and run once', exact=True).focus()
                            page.keyboard.press('Tab')
                            self.assertTrue(page.evaluate("document.activeElement.matches('button,input,select,a')"))
                            self.assertFalse(page.evaluate('document.documentElement.scrollWidth > innerWidth'))
                            self.assertEqual(jobs(fixture.store, 'sample-one'), [])
                            self.assertEqual(errors, [])
                            self.assertEqual(unexpected, [])
                        finally:
                            context.close()
                            fixture.tearDown()
                            fixture.doCleanups()
            finally:
                browser.close()


if __name__ == '__main__':
    unittest.main()
